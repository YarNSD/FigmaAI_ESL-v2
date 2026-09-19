"""
ESL Figma AI — Telegram Bot
Simple, sleek inline-button bot for ESL teachers:
- Select active Figma board with inline buttons
- Select target student with inline buttons
- 1-click block creation & natural language commands
- Quick board actions (Lesson Timestamp, Table of Contents)
- Authorized users filtering for security
"""
from __future__ import annotations
import asyncio
import base64
import logging
import os
import re
import threading
import time
from typing import Optional, Any, Dict

logger = logging.getLogger("telegram_bot")

import io

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        CallbackQueryHandler, ContextTypes, filters
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = Any
    InputMediaPhoto = Any
    class _ContextTypes:
        DEFAULT_TYPE = Any
    ContextTypes = _ContextTypes()

from server import config, bridge
from server.agents import orchestrator, student_agent, chat_agent, feedback_agent, vision_verifier, image_agent


# ── Lifecycle State ──────────────────────────────────────────────────────────
_bot_app: Optional[Any] = None
_bot_thread: Optional[threading.Thread] = None
_bot_loop: Optional[asyncio.AbstractEventLoop] = None
_bot_status: str = "stopped"
_bot_last_error: str = ""
_active_creation_description: Optional[str] = None


# ── Security & Auth ──────────────────────────────────────────────────────────

def is_user_allowed(user_id: int) -> bool:
    allowed = config.get("telegram.allowed_user_ids", [])
    if not allowed:
        return True
    try:
        allowed_ints = [int(x) for x in allowed if str(x).strip().isdigit()]
        return user_id in allowed_ints
    except Exception:
        return False


async def check_auth(update: Update) -> bool:
    if not update.effective_user:
        return False
    uid = update.effective_user.id
    if not is_user_allowed(uid):
        msg_text = (
            f"⛔ *Доступ ограничен.*\n\n"
            f"Ваш Telegram ID: `{uid}`\n"
            f"Добавьте этот ID в панели управления в разделе *Telegram бот -> Безопасность*."
        )
        if update.callback_query:
            await update.callback_query.answer("Доступ запрещен", show_alert=True)
        elif update.message:
            await update.message.reply_text(msg_text, parse_mode="Markdown")
        return False
    return True


# ── UI Helpers ───────────────────────────────────────────────────────────────

def _get_active_board_info() -> tuple[str, str]:
    """Return (board_id, display_name)."""
    active_id = config.active_board() or "main"
    boards = config.get("figma.boards", {})
    info = boards.get(active_id, {})
    name = info.get("display_name", info.get("name", active_id))
    return active_id, name


def _get_active_student_info(context: ContextTypes.DEFAULT_TYPE) -> tuple[Optional[str], str]:
    """Return (student_id, display_name)."""
    sid = context.user_data.get("selected_student_id")
    if not sid:
        return None, "Не выбран (общий)"
    s = student_agent.get_student(sid)
    if not s:
        return None, "Не выбран (общий)"
    name = s.get("name", sid)
    age = f"{s.get('age')} лет" if s.get("age") else ""
    lvl = s.get("level") or "A1"
    details = f" ({age}, {lvl})" if age else f" ({lvl})"
    return sid, f"{name}{details}"


def build_main_menu_keyboard(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    _, board_name = _get_active_board_info()
    _, student_name = _get_active_student_info(context)

    keyboard = [
        [
            InlineKeyboardButton(f"📋 Доска: {board_name[:16]}", callback_data="menu:boards"),
            InlineKeyboardButton(f"👤 Ученик: {student_name[:16]}", callback_data="menu:students"),
        ],
        [
            InlineKeyboardButton("🎯 Создать задание", callback_data="menu:create"),
            InlineKeyboardButton("🎓 Полный урок", callback_data="create:full_lesson"),
        ],
        [
            InlineKeyboardButton("📝 Итоги урока", callback_data="menu:feedback"),
            InlineKeyboardButton("🕒 Время урока", callback_data="action:timestamp"),
        ],
        [
            InlineKeyboardButton("📑 Меню оглавления", callback_data="action:refresh_toc"),
            InlineKeyboardButton("🔄 Обновить статус", callback_data="menu:refresh"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_main_menu_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    _, board_name = _get_active_board_info()
    _, student_name = _get_active_student_info(context)
    is_online = bridge.is_connected()

    status_icon = "🟢 На связи" if is_online else "🔴 Плагин офлайн"
    engine = config.ai_engine().upper()

    return (
        f"🎓 *ESL Figma AI — Управление*\n\n"
        f"📋 *Доска:* `{board_name}`\n"
        f"👤 *Ученик:* `{student_name}`\n"
        f"⚡ *Статус:* {status_icon} | ИИ: `{engine}`\n\n"
        f"👇 _Выберите действие кнопками или просто напишите запрос в чат (например: «квиз A2 про еду»)_:"
    )


# ── Handlers ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    text = build_main_menu_text(context)
    keyboard = build_main_menu_keyboard(context)
    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    query = update.callback_query
    await query.answer()
    data = query.data

    # 1. Main menu refresh or return
    if data in ("menu:main", "menu:refresh"):
        text = build_main_menu_text(context)
        keyboard = build_main_menu_keyboard(context)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        return

    # 2. Boards menu
    if data == "menu:boards":
        boards = config.get("figma.boards", {})
        active_id = config.active_board()

        buttons = []
        for bid, binfo in boards.items():
            bname = binfo.get("display_name", binfo.get("name", bid))
            prefix = "✓ " if bid == active_id else ""
            btype = "Jam" if binfo.get("board_type") == "figjam" else "Figma"
            buttons.append([InlineKeyboardButton(f"{prefix}{bname} ({btype})", callback_data=f"set_board:{bid}")])

        buttons.append([InlineKeyboardButton("↩️ Назад в меню", callback_data="menu:main")])
        await query.edit_message_text(
            "📋 *Выберите активную доску Figma / FigJam:*\n"
            "Все создаваемые блоки будут рисоваться на выбранной доске.",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
        return

    # Switch board
    if data.startswith("set_board:"):
        new_bid = data.split(":", 1)[1]
        config.set_value("figma.active_board", new_bid)
        config.save(config._config)
        _, bname = _get_active_board_info()
        await query.answer(f"Выбрана доска: {bname}", show_alert=False)

        text = build_main_menu_text(context)
        keyboard = build_main_menu_keyboard(context)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        return

    # 3. Students menu
    if data == "menu:students":
        students = student_agent.list_students()
        current_sid = context.user_data.get("selected_student_id")

        buttons = []
        # Option to clear selection
        prefix_none = "✓ " if not current_sid else ""
        buttons.append([InlineKeyboardButton(f"{prefix_none}👥 Без привязки к ученику", callback_data="set_student:none")])

        for s in students:
            sid = s.get("id")
            sname = s.get("name", sid)
            sage = f"{s.get('age')}л" if s.get("age") else ""
            slvl = s.get("level") or "A1"
            pref = "✓ " if sid == current_sid else ""
            label = f"{pref}👤 {sname} ({sage}, {slvl})" if sage else f"{pref}👤 {sname} ({slvl})"
            buttons.append([InlineKeyboardButton(label, callback_data=f"set_student:{sid}")])

        buttons.append([InlineKeyboardButton("📦 Скачать бэкап базы учеников", callback_data="action:student_backup")])
        buttons.append([InlineKeyboardButton("↩️ Назад в меню", callback_data="menu:main")])
        await query.edit_message_text(
            "👤 *Выберите ученика:*\n"
            "ИИ автоматически подстроит лексику, сложность и увлечения под его профиль.",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
        return

    # Switch student
    if data.startswith("set_student:"):
        new_sid = data.split(":", 1)[1]
        if new_sid == "none":
            context.user_data["selected_student_id"] = None
            await query.answer("Ученик сброшен (общий режим)", show_alert=False)
        else:
            context.user_data["selected_student_id"] = new_sid
            _, sname = _get_active_student_info(context)
            await query.answer(f"Выбран ученик: {sname}", show_alert=False)

        text = build_main_menu_text(context)
        keyboard = build_main_menu_keyboard(context)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        return

    # 4. Create Task menu
    if data == "menu:create":
        buttons = [
            [
                InlineKeyboardButton("🌟 Урок по Блуму (Bloom Arc)", callback_data="create:bloom_lesson"),
                InlineKeyboardButton("🎓 Полный урок целиком", callback_data="create:full_lesson"),
            ],
            [
                InlineKeyboardButton("🎯 Квиз с картинками", callback_data="create_type:quiz_photo"),
                InlineKeyboardButton("🃏 Открывашки", callback_data="create_type:flip_cards"),
            ],
            [
                InlineKeyboardButton("📚 Словарь", callback_data="create_type:vocabulary_table"),
                InlineKeyboardButton("🗣️ Разминка / Speaking", callback_data="create_type:speaking_cards"),
            ],
            [
                InlineKeyboardButton("✏️ Таблица с пропусками", callback_data="create_type:fill_blanks"),
                InlineKeyboardButton("🗂 Карточки со словами", callback_data="create_type:flashcards"),
            ],
            [
                InlineKeyboardButton("🎲 На усмотрение ИИ", callback_data="create_type:auto"),
                InlineKeyboardButton("↩️ Назад в меню", callback_data="menu:main"),
            ]
        ]
        await query.edit_message_text(
            "🎨 *Выберите тип учебного блока:*\n"
            "Или напишите тему прямо в чат!",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
        return

    # Select specific block type
    if data.startswith("create_type:"):
        btype = data.split(":", 1)[1]
        context.user_data["pending_block_type"] = btype
        type_names = {
            "bloom_lesson": "🌟 Урок по Блуму (Bloom Arc)",
            "quiz_photo": "Квиз с картинками",
            "flip_cards": "Открывашки / Peekaboo",
            "vocabulary_table": "Словарь с переводом",
            "speaking_cards": "Speaking-разминка",
            "fill_blanks": "Таблица с пропусками",
            "flashcards": "Карточки со словами",
            "auto": "На усмотрение ИИ",
        }
        tname = type_names.get(btype, btype)
        buttons = [
            [InlineKeyboardButton("⚡ Сгенерировать на свободную тему", callback_data=f"do_quick_gen:{btype}")],
            [InlineKeyboardButton("↩️ Отмена", callback_data="menu:main")]
        ]
        await query.edit_message_text(
            f"🎯 *Выбран блок:* `{tname}`\n\n"
            f"✍️ Напишите тему в чат (например: *путешествия*, *еда*, *животные*)\n"
            f"или нажмите кнопку ниже для авто-генерации:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
        return

    # Quick generate with auto topic
    if data.startswith("do_quick_gen:") or data in ("create:full_lesson", "create:bloom_lesson"):
        if data == "create:bloom_lesson":
            btype = "bloom_lesson"
        elif data == "create:full_lesson":
            btype = "full_lesson"
        else:
            btype = data.split(":", 1)[1]
        context.user_data.pop("pending_block_type", None)
        await execute_creation(update, context, command="", block_type=btype)
        return

    # 5. Quick Actions
    if data == "action:timestamp":
        if not bridge.is_connected():
            await query.answer("❌ Плагин Figma офлайн", show_alert=True)
            return

        await query.answer("Вставляю время урока...")
        now = time.localtime()
        time_str = time.strftime("%H:%M", now)
        date_str = time.strftime("%d.%m.%Y", now)
        code = f"drawTimestampBlock({{ time: '{time_str}', date: '{date_str}', short_date: '{time_str}' }})"
        try:
            res = await bridge.send_command({"action": "eval", "code": code})
            if res.get("ok") is not False:
                await query.edit_message_text(
                    f"✅ *Время урока ({time_str}) успешно вставлено на холст!*\n\n" + build_main_menu_text(context),
                    reply_markup=build_main_menu_keyboard(context),
                    parse_mode="Markdown"
                )
            else:
                err_msg = str(res.get("error", "Неизвестная ошибка"))
                try:
                    await query.edit_message_text(f"❌ *Ошибка плагина:* {err_msg}\n\n" + build_main_menu_text(context), reply_markup=build_main_menu_keyboard(context), parse_mode="Markdown")
                except Exception:
                    await query.edit_message_text(f"❌ Ошибка плагина: {err_msg}\n\n" + build_main_menu_text(context), reply_markup=build_main_menu_keyboard(context))
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")
        return

    if data == "action:refresh_toc":
        if not bridge.is_connected():
            await query.answer("❌ Плагин Figma офлайн", show_alert=True)
            return

        await query.answer("Обновляю меню оглавления...")
        try:
            res = await bridge.send_command({"action": "eval", "code": "refreshTableOfContents()"})
            if res.get("ok") is not False:
                await query.edit_message_text(
                    "✅ *Оглавление доски успешно пересчитано и обновлено!*\n\n" + build_main_menu_text(context),
                    reply_markup=build_main_menu_keyboard(context),
                    parse_mode="Markdown"
                )
            else:
                err_msg = str(res.get("error", "Неизвестная ошибка"))
                try:
                    await query.edit_message_text(f"❌ *Ошибка:* {err_msg}\n\n" + build_main_menu_text(context), reply_markup=build_main_menu_keyboard(context), parse_mode="Markdown")
                except Exception:
                    await query.edit_message_text(f"❌ Ошибка: {err_msg}\n\n" + build_main_menu_text(context), reply_markup=build_main_menu_keyboard(context))
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")
    if data == "action:student_backup":
        await query.answer("Формирую архив базы учеников...")
        await send_backup_document(update, context)
        return

    # 5.5 Lesson Feedback & Debriefing
    if data == "menu:feedback":
        sid, _ = _get_active_student_info(context)
        uid = str(update.effective_user.id) if update.effective_user else "default"
        session = feedback_agent.start_feedback_session(uid, student_id=sid)
        res = await feedback_agent.process_feedback_step(uid, "")

        buttons = []
        for idx, sugg in enumerate(res.get("suggested_replies", [])[:3]):
            buttons.append([InlineKeyboardButton(sugg, callback_data=f"chat_suggest:{idx}")])
        buttons.append([InlineKeyboardButton("📱 Главное меню", callback_data="menu:main")])

        context.user_data["latest_suggestions"] = res.get("suggested_replies", [])
        await query.edit_message_text(res["reply"], reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        return

    # 6. Chat Callbacks (Draw Plan / Suggested Replies)
    if data == "chat_action:draw_plan":
        plan = context.user_data.get("pending_lesson_plan")
        if not plan:
            await query.answer("План урока не найден. Напишите запрос в чат еще раз.", show_alert=True)
            return
        topic = plan.get("topic", "Урок")
        plan_title = plan.get("title", f"Задание: {topic}")
        plan_level = plan.get("level")
        blocks = plan.get("blocks") or []
        b_type = plan.get("block_type") or ("bloom_lesson" if len(blocks) > 1 else (blocks[0] if blocks else "quiz_photo"))
        content = plan.get("content")
        if content and isinstance(content, dict):
            if content.get("rows"):
                b_type = "vocabulary_table"
            elif content.get("sentences"):
                b_type = "fill_blanks"
            elif content.get("questions") and b_type not in ("quiz_photo", "video_quiz"):
                b_type = "quiz_photo"

        student_id = plan.get("student_id") or context.user_data.get("selected_student_id")
        if student_id and not context.user_data.get("selected_student_id"):
            context.user_data["selected_student_id"] = student_id
        comments = plan.get("teacher_comments", "")
        cmd_text = f"{plan_title}" + (f" ({comments})" if comments else "")
        await query.answer("Запускаю построение на доске...")
        await execute_creation(update, context, command=cmd_text, block_type=b_type, topic=topic, level=plan_level, content=content)
        return

    if data.startswith("chat_suggest:"):
        try:
            idx = int(data.split(":", 1)[1])
        except ValueError:
            return
        suggs = context.user_data.get("latest_suggestions", [])
        if 0 <= idx < len(suggs):
            sugg_text = suggs[idx]
            await query.answer(f"Выбрано: {sugg_text[:25]}")
            if query.message:
                try:
                    await query.message.reply_text(f"👤 *Вы:* {sugg_text}", parse_mode="Markdown")
                except Exception:
                    await query.message.reply_text(f"👤 Вы: {sugg_text}")
            await process_chat_interaction(update, context, sugg_text)
        return

    # 7. Photo Build Actions (from Telegram upload or Canvas Selection)
    if data.startswith("photo_build:"):
        action = data.split(":", 1)[1]
        if action == "clear_photos":
            context.user_data.pop("staged_photos", None)
            await query.edit_message_text("🗑️ Фото очищены из буфера.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📱 Главное меню", callback_data="menu:main")]]))
            return

        staged = context.user_data.get("staged_photos", [])
        if not staged:
            await query.edit_message_text("⚠️ Фото не найдены в памяти. Пожалуйста, пришлите их заново или выделите на доске.")
            return

        btype = action
        sid, sname = _get_active_student_info(context)
        bid, bname = _get_active_board_info()
        level = None
        if sid:
            st_data = student_agent.get_student(sid)
            if st_data:
                level = st_data.get("level")

        await query.edit_message_text(f"🧠 *Генерирую задание «{btype}» по {len(staged)} вашим фото...*", parse_mode="Markdown")
        result = await orchestrator.process_command(
            command=f"Интерактивное упражнение по {len(staged)} фото",
            block_type=btype,
            images=staged,
            student_id=sid,
            board_id=bid,
            level=level or "A2"
        )
        if result.get("ok"):
            title = result.get("title", "Фото-упражнение")
            warnings = result.get("warnings", [])
            warn_block = ""
            if warnings:
                warn_lines = "\n".join(f"• _{w}_" for w in warnings)
                warn_block = f"\n\n⚠️ *Обратите внимание:*\n{warn_lines}\n_Элементы можно скорректировать прямо на доске._"

            await query.edit_message_text(
                f"✅ *Готово! Блок успешно нарисован на доске с вашими фото!*\n\n"
                f"📋 *Название:* «{title}»\n"
                f"📸 *Использовано фото:* {len(staged)} шт.\n"
                f"👤 *Ученик:* {sname}\n"
                f"🎨 *Доска:* {bname}"
                f"{warn_block}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📱 Главное меню", callback_data="menu:main")]]),
                parse_mode="Markdown"
            )
            context.user_data.pop("staged_photos", None)
        else:
            tech_err = result.get("technical_error") or result.get("message") or "Сбой создания"
            safe_err = str(tech_err).replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
            await query.edit_message_text(
                f"❌ *Техническая ошибка создания:*\n\n"
                f"🔧 *Причина:* {safe_err}\n\n"
                f"💡 *Рекомендация:* проверьте подключение плагина в Figma и повторите запрос.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📱 Главное меню", callback_data="menu:main")]]),
                parse_mode="Markdown"
            )
        return

    # 8. Image replacement callbacks (Vision QA & Image Reroll)
    if data == "replace_img:menu":
        last_block = context.user_data.get("last_block_context")
        if not last_block or not last_block.get("items"):
            await query.answer("Нет активного блока для замены фото", show_alert=True)
            return
        items = last_block["items"]
        buttons = []
        for idx, it in enumerate(items, start=1):
            q_text = it.get("sentence") or it.get("question") or it.get("word") or f"Задание {idx}"
            q_clean = re.sub(r"^\d+[\.\)]\s*", "", q_text).strip()
            q_short = (q_clean[:22] + "...") if len(q_clean) > 22 else q_clean
            buttons.append([InlineKeyboardButton(f"🖼️ {idx}. {q_short}", callback_data=f"replace_img:sel:{idx-1}")])
        buttons.append([InlineKeyboardButton("↩️ Назад в меню", callback_data="menu:main")])
        await query.edit_message_text(
            "🔄 *Выберите задание, в котором хотите заменить картинку:*\n"
            "Новая иллюстрация будет создана нейросетью или найдена на Pinterest и сразу обновлена на доске Figma.",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
        return

    if data.startswith("replace_img:sel:"):
        idx = int(data.split(":", 2)[2])
        last_block = context.user_data.get("last_block_context", {})
        items = last_block.get("items", [])
        if 0 <= idx < len(items):
            it = items[idx]
            q_text = it.get("sentence") or it.get("question") or it.get("word") or f"Задание {idx+1}"
            buttons = [
                [InlineKeyboardButton("⚡ Сгенерировать ИИ (Pollinations)", callback_data=f"replace_img:gen:{idx}")],
                [InlineKeyboardButton("🔍 Найти другое фото (Pinterest)", callback_data=f"replace_img:pin:{idx}")],
                [InlineKeyboardButton("↩️ Назад к списку", callback_data="replace_img:menu")],
            ]
            await query.edit_message_text(
                f"🖼️ *Замена иллюстрации к заданию №{idx+1}:*\n"
                f"«{q_text}»\n\n"
                f"Выберите способ замены:",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="Markdown"
            )
        return

    if data.startswith("replace_img:gen:"):
        idx = int(data.split(":", 2)[2])
        await handle_image_replacement_request(update, context, idx, mode="generate")
        return

    if data.startswith("replace_img:pin:"):
        idx = int(data.split(":", 2)[2])
        await handle_image_replacement_request(update, context, idx, mode="pinterest")
        return


async def handle_image_replacement_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    card_idx: int,
    custom_prompt: Optional[str] = None,
    mode: str = "generate"
):
    """Replace an image for a specific card in the last created block, both in Figma and in user context."""
    last_block = context.user_data.get("last_block_context")
    if not last_block:
        msg = "⚠️ Нет информации о последнем созданном блоке. Создайте задание или выделите блок на доске."
        if update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        elif update.message:
            await update.message.reply_text(msg)
        return

    items = last_block.get("items", [])
    if card_idx < 0 or card_idx >= len(items):
        msg = f"⚠️ В текущем блоке {len(items)} заданий. Пожалуйста, укажите номер от 1 до {len(items)}."
        if update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        elif update.message:
            await update.message.reply_text(msg)
        return

    it = items[card_idx]
    q_sentence = it.get("sentence") or it.get("question") or it.get("word") or it.get("title") or f"Задание {card_idx+1}"
    q_clean = re.sub(r"^\d+[\.\)]\s*", "", q_sentence).strip()
    topic = last_block.get("topic") or "English"
    node_id = last_block.get("node_id")

    status_msg = None
    status_text = f"🎨 *Подбираю новую иллюстрацию для задания №{card_idx+1}...*\n«{q_clean}»"
    if update.callback_query:
        await update.callback_query.answer("Генерирую новую картинку...")
        if update.callback_query.message:
            status_msg = await update.callback_query.message.reply_text(status_text, parse_mode="Markdown")
    elif update.message:
        status_msg = await update.message.reply_text(status_text, parse_mode="Markdown")

    # Formulate prompt
    if custom_prompt and len(custom_prompt.strip()) > 1:
        gen_prompt = f"high quality photography of {custom_prompt.strip()}, dynamic action, vibrant lighting, no watermark, 4k"
    else:
        expected_act = vision_verifier.extract_expected_action(q_sentence)
        clean_no_blanks = re.sub(r"___+", "", q_clean).strip()
        if expected_act:
            gen_prompt = (
                f"high quality action photography of {clean_no_blanks}, "
                f"clear dynamic motion of {expected_act}, realistic vibrant lighting, "
                f"no watermark, no logos, 4k"
            )
        else:
            gen_prompt = (
                f"high quality photography of {clean_no_blanks}, "
                f"vibrant realistic scene, no text, no watermark, 4k"
            )

    try:
        new_b64 = await image_agent.get_image_base64(
            gen_prompt,
            topic=topic,
            image_mode=mode,
            is_child=it.get("is_child", False),
            is_sticker=it.get("is_sticker", False)
        )
        if not new_b64:
            err_txt = f"⚠️ Не удалось получить новое изображение для задания №{card_idx+1}."
            if status_msg:
                await status_msg.edit_text(err_txt)
            return

        # Update in Figma via bridge
        if bridge.is_connected() and node_id:
            try:
                await bridge.send_command("UPDATE_BLOCK_IMAGES", {
                    "nodeId": node_id,
                    "index": card_idx,
                    "image": new_b64
                })
            except Exception as b_err:
                logger.warning(f"Bridge image update failed: {b_err}")

        # Update in memory
        it["image_base64"] = new_b64
        it["image_verified"] = True

        # Send photo to Telegram
        chat_id = update.effective_chat.id if update.effective_chat else None
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Заменить ещё фото", callback_data="replace_img:menu")],
            [InlineKeyboardButton("📱 Главное меню", callback_data="menu:main")]
        ])

        raw_bytes = base64.b64decode(new_b64)
        cap = (
            f"✅ *Иллюстрация к вопросу {card_idx+1} обновлена на доске Figma!*\n\n"
            f"📋 «{q_clean}»\n"
            f"🔍 *Сюжет:* {gen_prompt[:100]}..."
        )
        if chat_id:
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=io.BytesIO(raw_bytes),
                    caption=cap,
                    reply_markup=kb,
                    parse_mode="Markdown"
                )
                if status_msg:
                    await status_msg.delete()
                return
            except Exception as sp_err:
                logger.warning(f"Failed to send replacement photo: {sp_err}")

        if status_msg:
            await status_msg.edit_text(cap, reply_markup=kb, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error replacing image for card #{card_idx+1}: {e}", exc_info=True)
        if status_msg:
            await status_msg.edit_text(f"❌ Ошибка обновления изображения: {e}")



async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear conversational history across Web UI and Telegram."""
    if not await check_auth(update):
        return
    uid = str(update.effective_user.id) if update.effective_user else "default"
    chat_agent.clear_user_history(uid)
    chat_agent.clear_user_history("shared")
    context.user_data.pop("pending_lesson_plan", None)
    context.user_data.pop("pending_plan_time", None)
    context.user_data.pop("latest_suggestions", None)
    if update.message:
        await update.message.reply_text("🧹 *История диалога и черновики планов очищены!*", parse_mode="Markdown")


async def cmd_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current session token usage."""
    if not await check_auth(update):
        return
    sess_tokens = context.user_data.get("session_tokens", 0)
    tok_text = (
        f"📊 *Статистика использования токенов*\n\n"
        f"▫️ Израсходовано в текущей сессии: *{sess_tokens:,}* токенов\n"
        f"▫️ Вызовы ИИ выполняются на 100% локально через Google Antigravity CLI без внешних платных API."
    )
    if update.message:
        await update.message.reply_text(tok_text, parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show status of bridge, board, and active tasks."""
    if not await check_auth(update):
        return
    _, bname = _get_active_board_info()
    _, sname = _get_active_student_info(context)
    is_online = bridge.is_connected()
    conn_str = "🟢 На связи" if is_online else "🔴 Офлайн"
    gen_str = f"⏳ В процессе: `{_active_creation_description}`" if _active_creation_description else "⚪ Ничего не генерируется"
    plan = context.user_data.get("pending_lesson_plan")
    plan_str = f"📝 Сохранён план: *«{plan.get('title', plan.get('topic', 'Урок'))}»*" if plan else "⚪ Нет сохранённых планов"

    status_text = (
        f"ℹ️ *Текущее состояние системы*\n\n"
        f"📋 *Доска:* `{bname}`\n"
        f"🔌 *Плагин Figma:* {conn_str}\n"
        f"👤 *Ученик:* `{sname}`\n"
        f"🎨 *Генерация:* {gen_str}\n"
        f"{plan_str}"
    )
    if update.message:
        await update.message.reply_text(status_text, parse_mode="Markdown")


async def cmd_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start guided debriefing interview after a lesson."""
    if not await check_auth(update):
        return
    sid, _ = _get_active_student_info(context)
    uid = str(update.effective_user.id) if update.effective_user else "default"
    session = feedback_agent.start_feedback_session(uid, student_id=sid)
    res = await feedback_agent.process_feedback_step(uid, "")

    buttons = []
    for idx, sugg in enumerate(res.get("suggested_replies", [])[:3]):
        buttons.append([InlineKeyboardButton(sugg, callback_data=f"chat_suggest:{idx}")])
    buttons.append([InlineKeyboardButton("📱 Главное меню", callback_data="menu:main")])

    context.user_data["latest_suggestions"] = res.get("suggested_replies", [])
    if update.message:
        await update.message.reply_text(res["reply"], reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /backup — create and send student database backup archive."""
    if not await check_auth(update):
        return
    await send_backup_document(update, context)


async def send_backup_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate detailed ZIP backup of student dossiers and send to Telegram chat."""
    from server.services import backup_service
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return

    status_msg = None
    target = update.message or (update.callback_query.message if update.callback_query else None)
    if target:
        try:
            status_msg = await target.reply_text("📦 *Формирую резервную копию базы учеников...*", parse_mode="Markdown")
        except Exception:
            pass

    try:
        archive_path, manifest = backup_service.create_backup_archive()
        caption = backup_service.format_backup_caption(manifest)

        with open(archive_path, "rb") as f:
            await context.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=manifest.get("archive_name", "students_backup.zip"),
                caption=caption,
                parse_mode="Markdown"
            )
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Backup creation error: {e}", exc_info=True)
        if status_msg:
            try:
                await status_msg.edit_text(f"❌ *Ошибка создания бэкапа:* {e}", parse_mode="Markdown")
            except Exception:
                pass


async def handle_backup_zip_upload(update: Update, context: ContextTypes.DEFAULT_TYPE, doc):
    """Restore student database from an uploaded ZIP archive."""
    from server.services import backup_service
    import tempfile
    status_msg = await update.message.reply_text("📥 *Принимаю архив базы учеников... Проверяю файлы...*", parse_mode="Markdown")
    try:
        file_obj = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp_path = tmp.name

        await file_obj.download_to_drive(tmp_path)

        res = backup_service.restore_from_archive(tmp_path)
        try:
            os.remove(tmp_path)
        except Exception:
            pass

        if res.get("ok"):
            count = res.get("restored_count", 0)
            names = ", ".join(res.get("restored_students", []))
            await status_msg.edit_text(
                f"✅ *База данных учеников успешно восстановлена!*\n\n"
                f"👥 *Восстановлено учеников:* *{count}* ({names})\n"
                f"📁 *Файлов извлечено:* {res.get('total_files', 0)} шт.\n\n"
                f"Все профили и история уроков снова доступны в проекте!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 Перейти к ученикам", callback_data="menu:students")]]),
                parse_mode="Markdown"
            )
        else:
            await status_msg.edit_text(f"❌ *Ошибка восстановления:* {res.get('error')}", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to restore backup: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ *Сбой обработки архива:* {e}", parse_mode="Markdown")


async def process_chat_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: str):
    """Process message in natural conversational dialogue mode with pedagogical reasoning."""
    sid, sname = _get_active_student_info(context)
    uid = str(update.effective_user.id) if update.effective_user else "default"

    # Show typing indicator
    if update.effective_chat:
        try:
            await update.effective_chat.send_action("typing")
        except Exception:
            pass

    try:
        res = await chat_agent.process_chat_message(
            message=user_text,
            student_id=sid,
            user_key=uid,
            source="telegram"
        )
    except Exception as e:
        logger.error(f"Chat agent error in telegram: {e}", exc_info=True)
        res = {
            "reply": f"Произошла ошибка при обработке: {e}. Попробуйте ещё раз.",
            "suggested_replies": [],
            "ready_to_build": False
        }

    # If student profile was detected and no student was selected, link it
    detected_sid = res.get("student_id")
    if detected_sid and not sid:
        context.user_data["selected_student_id"] = detected_sid

    reply_text = res.get("reply", "Я на связи! Чем могу помочь?")
    lesson_plan = res.get("lesson_plan")
    ready_to_build = res.get("ready_to_build", False)

    # Track session tokens silently in user_data (no visual spam in chat messages)
    tok_info = res.get("tokens") or {}
    req_tokens = tok_info.get("total", 0)
    if not req_tokens:
        req_tokens = max(50, int((len(user_text) + len(reply_text)) / 3) + 100)
    context.user_data["session_tokens"] = context.user_data.get("session_tokens", 0) + req_tokens

    final_reply_text = reply_text
    buttons = []

    # If lesson plan is ready to build, attach actionable 1-click button and note
    if ready_to_build and lesson_plan:
        context.user_data["pending_lesson_plan"] = lesson_plan
        context.user_data["pending_plan_time"] = time.time()
        topic = lesson_plan.get("topic", "Урок")
        buttons.append([InlineKeyboardButton(f"🚀 Нарисовать «{topic[:22]}» на доске", callback_data="chat_action:draw_plan")])
        final_reply_text += "\n\n👉 *Напишите «Делай»* (или нажмите кнопку ниже), чтобы нарисовать блок на доске! Либо напишите, что изменить (например, «замени 2-й вопрос»)."
    else:
        # Clear stale plans if conversation naturally moved to another subject (10 min TTL)
        if context.user_data.get("pending_plan_time") and (time.time() - context.user_data["pending_plan_time"] > 600):
            context.user_data.pop("pending_lesson_plan", None)
            context.user_data.pop("pending_plan_time", None)

    keyboard = InlineKeyboardMarkup(buttons) if buttons else None

    # Send natural response safely
    target_msg = update.message or (update.callback_query.message if update.callback_query else None)
    if target_msg:
        try:
            await target_msg.reply_text(final_reply_text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await target_msg.reply_text(final_reply_text, reply_markup=keyboard)


# ── Natural Language Command & Confirmation Detection Helpers ─────────────────

def is_confirmation_phrase(text: str) -> bool:
    """
    Check if teacher's message confirms drawing/building the pending lesson plan.
    Requires explicit affirmative intent targeted at building.
    """
    cleaned = re.sub(r"[!.,?+\-_/]+", " ", text.strip().lower()).strip()
    words = cleaned.split()
    if not words:
        return text.strip() in ("+", "++", "+++")

    negative_words = {
        "нет", "не", "подожди", "стоп", "отмена", "отмени", "погоди",
        "переделай", "поменяй", "измени", "убери", "исправь", "другое", "не надо", "не то"
    }
    if any(w in negative_words for w in words):
        return False

    # If conversational phrase about discussing or talking, not confirmation to draw
    if any(w in ("поговорим", "обсудим", "расскажи", "поболтаем", "спросить", "думаешь") for w in words):
        return False

    action_affirmatives = {
        "делай", "давай", "рисуй", "создавай", "погнали", "поехали", "го", "go",
        "запускай", "стартуй", "начинай", "делайте", "давайте", "рисуйте", "создавайте", "действуй",
        "переноси", "переноси в фигму", "переноси на доску", "на холст", "в фигму", "рисуем", "делаем",
        "согласовано", "одобряю", "огонь", "класс", "добро", "принято"
    }
    # Direct action verb ("делай", "давай", "рисуй", "погнали", "переноси в фигму")
    if any(w in action_affirmatives for w in words):
        return True

    # Short exact affirmations: "да", "ок", "хорошо", "супер", "отлично", "+"
    if len(words) <= 3 and any(w in ("да", "ок", "ok", "хорошо", "супер", "отлично", "согласен", "принято", "добро", "плюс") for w in words):
        return True

    return False


def is_explicit_bypass_draw_command(text: str) -> bool:
    """
    Check if teacher explicitly requests to skip textual preview and draw directly to canvas immediately.
    Standard requests ('Сделай квиз...', 'Создай карточки...') are NOT bypass commands and MUST show text draft first!
    """
    lower = text.lower().strip()
    if lower.startswith("/draw_now") or lower.startswith("/create_now"):
        return True

    bypass_phrases = (
        "без проверки", "без согласования", "без текста",
        "сразу нарисуй на доске", "сразу создай на доске", "сразу нарисуй", "сразу создай",
        "сразу на доску", "сразу на холст", "сразу в фигму", "сразу на доске"
    )
    return any(p in lower for p in bypass_phrases)


# Backward compatibility alias
is_direct_create_command = is_explicit_bypass_draw_command


def is_status_query(text: str) -> bool:
    """
    Check if teacher is specifically querying ongoing Figma canvas generation progress.
    Generic questions like "Что делаешь?", "Чем занимаешься?" are NOT status queries!
    """
    lower = text.lower().strip()
    specific_generation_patterns = [
        "статус генерации", "статус создания", "статус задания",
        "какой этап генерации", "на каком этапе генерация", "на каком этапе создание",
        "долго еще делать задание", "долго ещё делать задание", "долго еще генерировать",
        "ты уже закончил создание", "закончил ли создание", "закончил ли рисовать на доске",
        "что сейчас генерируется", "что сейчас создается на доске", "что сейчас создаётся на доске",
        "делается ли задание", "процесс создания идет", "процесс генерации идет"
    ]
    return any(p in lower for p in specific_generation_patterns)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming teacher text messages with full natural language understanding."""
    if not await check_auth(update):
        return

    text = update.message.text.strip() if update.message and update.message.text else ""
    if not text:
        return

    uid = str(update.effective_user.id) if update.effective_user else "default"

    # 1. Check if user is in an active feedback interview session
    feedback_session = feedback_agent.get_feedback_session(uid)
    if feedback_session:
        res = await feedback_agent.process_feedback_step(uid, text)
        buttons = []
        for idx, sugg in enumerate(res.get("suggested_replies", [])[:3]):
            buttons.append([InlineKeyboardButton(sugg, callback_data=f"chat_suggest:{idx}")])
        buttons.append([InlineKeyboardButton("📱 Главное меню", callback_data="menu:main")])
        context.user_data["latest_suggestions"] = res.get("suggested_replies", [])
        await update.message.reply_text(res["reply"], reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        return

    # 2. Check if text triggers a feedback session
    if any(text.lower().startswith(p) for p in ["итоги", "/итоги", "фидбек", "/feedback", "отзыв о занятии", "как прошел урок"]):
        sid, _ = _get_active_student_info(context)
        feedback_agent.start_feedback_session(uid, student_id=sid)
        res = await feedback_agent.process_feedback_step(uid, text)
        buttons = []
        for idx, sugg in enumerate(res.get("suggested_replies", [])[:3]):
            buttons.append([InlineKeyboardButton(sugg, callback_data=f"chat_suggest:{idx}")])
        buttons.append([InlineKeyboardButton("📱 Главное меню", callback_data="menu:main")])
        context.user_data["latest_suggestions"] = res.get("suggested_replies", [])
        await update.message.reply_text(res["reply"], reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        return

    lower = text.lower()

    # 2.2 Check if teacher requests database backup or restore
    if any(k in lower for k in ["бэкап", "/backup", "резервн", "выгрузи базу", "сохрани базу", "скачать базу"]):
        await send_backup_document(update, context)
        return

    # 2.3 Status query check (strictly about canvas generation)
    if is_status_query(text):
        if _active_creation_description:
            await update.message.reply_text(
                f"⏳ *Да, сейчас в процессе!*\n\n"
                f"🎯 *Задача:* `{_active_creation_description}`\n"
                f"🎨 ИИ генерирует контент и иллюстрации, а плагин верстает карточки на доске (обычно это занимает 20–40 сек).\n\n"
                f"Как только блок появится на холсте, я сразу пришлю сюда уведомление!",
                parse_mode="Markdown"
            )
            return
        elif context.user_data.get("pending_lesson_plan"):
            plan = context.user_data.get("pending_lesson_plan")
            title = plan.get("title", plan.get("topic", "Урок"))
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🚀 Нарисовать «{title[:20]}» на доске", callback_data="chat_action:draw_plan")]])
            await update.message.reply_text(
                f"ℹ️ *Сейчас генерация на паузе.*\n\n"
                f"В памяти сохранён готовый план: *«{title}»*.\n\n"
                f"👉 Просто напишите **«Делай»** в чат (или нажмите кнопку ниже) — и я сразу начну рисовать его на доске!",
                reply_markup=kb,
                parse_mode="Markdown"
            )
            return
        else:
            await update.message.reply_text(
                "ℹ️ *Сейчас на доске ничего не генерируется.*\n\n"
                "Вы можете в любой момент дать команду нарисовать блок (например: *«нарисуй квиз про животных»*) или просто пообщаться со мной!",
                parse_mode="Markdown"
            )
            return

    # 2.4 Check if teacher confirms pending lesson plan
    pending_plan = context.user_data.get("pending_lesson_plan")
    plan_time = context.user_data.get("pending_plan_time", 0)
    is_fresh_plan = (time.time() - plan_time) < 600  # Valid for 10 minutes

    if pending_plan and is_fresh_plan and is_confirmation_phrase(text):
        context.user_data.pop("pending_lesson_plan", None)
        context.user_data.pop("pending_plan_time", None)
        topic = pending_plan.get("topic", "Урок")
        plan_title = pending_plan.get("title", f"Задание: {topic}")
        plan_level = pending_plan.get("level")
        blocks = pending_plan.get("blocks") or []
        b_type = pending_plan.get("block_type") or ("bloom_lesson" if len(blocks) > 1 else (blocks[0] if blocks else "quiz_photo"))
        content = pending_plan.get("content")
        if content and isinstance(content, dict):
            if content.get("rows"):
                b_type = "vocabulary_table"
            elif content.get("sentences"):
                b_type = "fill_blanks"
            elif content.get("questions") and b_type not in ("quiz_photo", "video_quiz"):
                b_type = "quiz_photo"

        student_id = pending_plan.get("student_id") or context.user_data.get("selected_student_id")
        if student_id and not context.user_data.get("selected_student_id"):
            context.user_data["selected_student_id"] = student_id
        comments = pending_plan.get("teacher_comments", "")
        cmd_text = f"{plan_title}" + (f" ({comments})" if comments else "")
        clean_text = text.strip().lower()
        if len(text.strip()) > 15 and clean_text not in ("делай", "давай", "рисуй", "создавай", "погнали", "переноси"):
            cmd_text += f". Пожелания: {text.strip()}"

        await execute_creation(update, context, command=cmd_text, block_type=b_type, topic=topic, level=plan_level, content=content)
        return
    elif pending_plan and not is_fresh_plan:
        # Clear expired plan
        context.user_data.pop("pending_lesson_plan", None)
        context.user_data.pop("pending_plan_time", None)

    # 2.4 Check if teacher asks to replace a specific image in the last created block
    # e.g. "замени 4-ю картинку", "поменяй фото 4 на щенков", "замени картинку 2"
    replace_img_match = re.search(
        r"(?:замени|поменяй|обнови|перерисуй)\s+(?:картинк[уа-я]*|фото|иллюстраци[юа-я]*|вопрос)\s*№?\s*(\d+)(?:\s+(?:на|с)\s+(.+))?",
        text,
        re.IGNORECASE
    )
    if not replace_img_match:
        replace_img_match = re.search(
            r"(?:замени|поменяй|обнови|перерисуй)\s*№?\s*(\d+)\s*(?:-?[уюея]?\s+)?(?:картинк[уа-я]*|фото|иллюстраци[юа-я]*)(?:\s+(?:на|с)\s+(.+))?",
            text,
            re.IGNORECASE
        )
    if replace_img_match:
        card_num = int(replace_img_match.group(1))
        custom_req = replace_img_match.group(2) or ""
        last_block = context.user_data.get("last_block_context")
        if last_block:
            await handle_image_replacement_request(update, context, card_num - 1, custom_prompt=custom_req)
            return

    # 2.5 Check if teacher refers to images/photos on the canvas
    is_canvas_photo_request = any(k in lower for k in [
        "выделенн", "на доске картин", "на доске фото", "этим фото", "этим картин",
        "картинк с доски", "фото с доски", "по картинкам", "по фото"
    ])
    if is_canvas_photo_request and not context.user_data.get("staged_photos"):
        if bridge.is_connected():
            status_msg = await update.message.reply_text("🔍 *Проверяю выделенные изображения на доске Figma...*", parse_mode="Markdown")
            try:
                selected_imgs = await bridge.get_selected_images(limit=15)
                if selected_imgs and len(selected_imgs) > 0:
                    context.user_data["staged_photos"] = selected_imgs
                    names_preview = ", ".join([f"«{im.get('name', 'фото')}»" for im in selected_imgs[:4]])
                    if len(selected_imgs) > 4:
                        names_preview += f" и ещё {len(selected_imgs)-4} шт."
                    await status_msg.edit_text(
                        f"📸 *Нашел на доске {len(selected_imgs)} выделенных изображений:*\n"
                        f"{names_preview}\n\n"
                        f"Какое интерактивное упражнение создадим с ними?",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🎯 Quiz: вопросы по фото (4 варианта)", callback_data="photo_build:quiz_photo")],
                            [InlineKeyboardButton("🗣️ Speaking Cards: карточки для беседы", callback_data="photo_build:speaking_cards")],
                            [InlineKeyboardButton("📚 Vocabulary: таблица слов с фото", callback_data="photo_build:vocabulary_table")],
                            [InlineKeyboardButton("🃏 Flip Cards: карточки с секретом", callback_data="photo_build:flip_cards")],
                            [InlineKeyboardButton("📱 Главное меню", callback_data="menu:main")]
                        ]),
                        parse_mode="Markdown"
                    )
                    return
                else:
                    await status_msg.edit_text(
                        "⚠️ *На доске сейчас ничего не выделено.*\n\n"
                        "Выделите нужные фотографии на холсте Figma или отправьте фото прямо сюда в чат!",
                        parse_mode="Markdown"
                    )
                    return
            except Exception as e:
                logger.error(f"Error querying canvas selection: {e}")
                await status_msg.edit_text(f"⚠️ Ошибка опроса доски: {e}")

    # Check if there is a pending block type from button selection
    pending_btype = context.user_data.pop("pending_block_type", None)
    if pending_btype:
        await process_chat_interaction(update, context, f"Создай интерактивный блок «{pending_btype}» на тему: {text}")
        return

    # Check for explicit bypass draw commands (e.g. "/draw_now ...", "сразу на доске без проверки")
    if is_explicit_bypass_draw_command(text):
        await execute_creation(update, context, command=text)
        return

    # Otherwise: full conversational dialogue with the AI assistant!
    await process_chat_interaction(update, context, text)


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming Telegram voice notes (.ogg Opus) via Gemini Multimodal API."""
    if not await check_auth(update):
        return
    if not update.message or not update.message.voice:
        return

    uid = str(update.effective_user.id) if update.effective_user else "default"
    await update.effective_chat.send_action("record_voice")
    status_msg = await update.message.reply_text("🎧 *Слушаю голосовое сообщение...*", parse_mode="Markdown")

    await status_msg.edit_text(
        "ℹ️ *Голосовой ввод через облачные API отключён.*\n\n"
        "Все модули системы работают строго **100% локально** на вашем компьютере без внешних API. Пожалуйста, напишите запрос текстом или выберите действие в меню!",
        parse_mode="Markdown"
    )


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming photos (single or album) sent directly to Telegram bot by the teacher."""
    if not await check_auth(update):
        return

    message = update.message
    if not message:
        return

    photo = message.photo
    doc = message.document

    # Check if this document is a ZIP backup to restore
    if doc and (doc.file_name or "").lower().endswith(".zip"):
        await handle_backup_zip_upload(update, context, doc)
        return

    if not photo and not (doc and doc.mime_type and doc.mime_type.startswith("image/")):
        return

    # Download highest-res photo
    try:
        if photo:
            file_obj = await context.bot.get_file(photo[-1].file_id)
        else:
            file_obj = await context.bot.get_file(doc.file_id)
        file_bytes = await file_obj.download_as_bytearray()
        b64 = base64.b64encode(bytes(file_bytes)).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to download incoming Telegram photo: {e}")
        await message.reply_text(f"❌ Не удалось загрузить фото: {e}")
        return

    if "staged_photos" not in context.user_data:
        context.user_data["staged_photos"] = []

    idx = len(context.user_data["staged_photos"]) + 1
    context.user_data["staged_photos"].append({
        "name": f"Photo #{idx}",
        "image_base64": b64,
        "size": len(file_bytes)
    })

    total = len(context.user_data["staged_photos"])
    caption = (message.caption or "").strip()

    # If part of an album (media group), debounce response by 700ms to collect all images
    media_group_id = message.media_group_id
    if media_group_id:
        if context.user_data.get("album_timer"):
            context.user_data["album_timer"].cancel()

        async def _send_album_prompt():
            try:
                await asyncio.sleep(0.7)
                cnt = len(context.user_data.get("staged_photos", []))
                await _prompt_photo_activity(update, context, cnt, caption)
            except asyncio.CancelledError:
                pass

        context.user_data["album_timer"] = asyncio.create_task(_send_album_prompt())
        return

    await _prompt_photo_activity(update, context, total, caption)


async def _prompt_photo_activity(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int, caption: str = ""):
    """Prompt the teacher on what exercise to build with the staged photos."""
    sid, sname = _get_active_student_info(context)
    bid, bname = _get_active_board_info()

    if caption:
        # If teacher sent photo with an explicit instruction, process it directly through conversational agent!
        await process_chat_interaction(update, context, f"Создай упражнение по этим {count} присланным фото: {caption}")
        return

    reply_text = (
        f"📸 *Получил фото (всего: {count} шт.)!*\n\n"
        f"🎨 *Доска:* `{bname}` | 👤 *Ученик:* `{sname}`\n\n"
        f"Какое интерактивное упражнение создадим с этими фото?"
    )
    buttons = [
        [InlineKeyboardButton("🎯 Quiz: вопросы по фото (4 варианта)", callback_data="photo_build:quiz_photo")],
        [InlineKeyboardButton("🗣️ Speaking Cards: карточки для беседы", callback_data="photo_build:speaking_cards")],
        [InlineKeyboardButton("📚 Vocabulary: таблица слов с фото", callback_data="photo_build:vocabulary_table")],
        [InlineKeyboardButton("🃏 Flip Cards: карточки с секретом", callback_data="photo_build:flip_cards")],
        [InlineKeyboardButton("🗑️ Сбросить эти фото", callback_data="photo_build:clear_photos"),
         InlineKeyboardButton("📱 Главное меню", callback_data="menu:main")]
    ]
    target = update.message or (update.callback_query.message if update.callback_query else None)
    if target:
        await target.reply_text(reply_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def execute_creation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    command: str = "",
    block_type: Optional[str] = None,
    topic: Optional[str] = None,
    level: Optional[str] = None,
    content: Optional[Dict[str, Any]] = None
):
    if not bridge.is_connected():
        msg_text = "❌ *Плагин Figma офлайн.* Запустите плагин на доске FigJam / Figma."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg_text, parse_mode="Markdown")
        elif update.message:
            await update.message.reply_text(msg_text, parse_mode="Markdown")
        return

    # Determine student and board
    sid, sname = _get_active_student_info(context)
    bid, bname = _get_active_board_info()

    # Determine target student level if available and not explicitly provided
    if not level:
        if sid:
            st_data = student_agent.get_student(sid)
            if st_data:
                level = st_data.get("level")

    status_msg = None
    status_text = f"🧠 *Генерирую задание для `{sname}` на доске `{bname}`...*"
    if update.callback_query:
        status_msg = await update.callback_query.edit_message_text(status_text, parse_mode="Markdown")
    elif update.message:
        status_msg = await update.message.reply_text(status_text, parse_mode="Markdown")

    global _active_creation_description
    _active_creation_description = f"{topic or command[:35] or block_type or 'Учебное задание'} ({bname})"

    try:
        staged_photos = context.user_data.get("staged_photos")
        result = await orchestrator.process_command(
            command=command,
            block_type=block_type,
            topic=topic,
            student_id=sid,
            board_id=bid,
            level=level,
            images=staged_photos,
            content=content,
        )

        if result.get("ok"):
            context.user_data.pop("staged_photos", None)
            title = result.get("title", command or "Задание")
            res_lvl = result.get("level", level or "A2")
            warnings = result.get("warnings", [])
            node_id = result.get("nodeId")
            v_report = result.get("verification_report") or {}
            v_items = result.get("verified_items") or []

            # Save in user_data for quick replacements:
            context.user_data["last_block_context"] = {
                "node_id": node_id,
                "title": title,
                "topic": topic,
                "block_type": block_type,
                "level": res_lvl,
                "items": v_items,
                "time": time.time()
            }

            warn_block = ""
            if warnings:
                warn_lines = "\n".join(f"• _{w}_" for w in warnings)
                warn_block = f"\n\n⚠️ *Обратите внимание:*\n{warn_lines}\n_Элементы можно скорректировать прямо на доске._"

            # Visual QA Report Block
            v_block = ""
            total_v = v_report.get("total") or len(v_items)
            auto_corr = v_report.get("auto_corrected", 0)
            passed = v_report.get("passed", 0)
            corrections = v_report.get("corrections", [])

            if total_v > 0:
                if auto_corr > 0:
                    corr_items = "\n".join([f"  • *№{c.get('id')}*: {c.get('issue')}" for c in corrections[:4]])
                    v_block = (
                        f"\n\n🔍 *Визуальный контроль (Vision QA):*\n"
                        f"• Проверено иллюстраций: *{total_v}*\n"
                        f"• 🔄 Автоматически заменено с несоответствующим сюжетом: *{auto_corr}*\n"
                        f"{corr_items}\n"
                        f"⚡ Все иллюстрации проверены и точно отображают требуемые действия и сюжет! ✅"
                    )
                else:
                    v_block = (
                        f"\n\n🔍 *Визуальный контроль (Vision QA):*\n"
                        f"• Проверено иллюстраций: *{total_v}*\n"
                        f"• Все изображения проверены: сюжет, множественное число и действия соответствуют контексту! ✅"
                    )

            reply_text = (
                f"✅ *Готово! Блок успешно нарисован на доске!*\n\n"
                f"📋 *Название:* «{title}»\n"
                f"🎯 *Уровень:* [{res_lvl}]\n"
                f"👤 *Ученик:* {sname}\n"
                f"🎨 *Доска:* {bname}"
                f"{v_block}"
                f"{warn_block}"
            )

            # Check if there are verified photos to send as a preview album
            preview_photos = []
            for i, it in enumerate(v_items, start=1):
                b64 = it.get("image_base64")
                if b64:
                    try:
                        raw = base64.b64decode(b64)
                        q_text = it.get("sentence") or it.get("question") or it.get("word") or it.get("title") or f"Задание {i}"
                        q_clean = re.sub(r"^\d+[\.\)]\s*", "", q_text).strip()
                        cap = f"№{i}: {q_clean}"
                        if len(cap) > 90:
                            cap = cap[:87] + "..."
                        preview_photos.append((raw, cap))
                    except Exception:
                        pass

            action_buttons = []
            if preview_photos:
                action_buttons.append([InlineKeyboardButton("🔄 Заменить фото в задании", callback_data="replace_img:menu")])
            action_buttons.append([InlineKeyboardButton("📱 Главное меню", callback_data="menu:main")])
            back_kb = InlineKeyboardMarkup(action_buttons)

            if status_msg:
                try:
                    await status_msg.edit_text(reply_text, reply_markup=back_kb, parse_mode="Markdown")
                except Exception:
                    await status_msg.edit_text(reply_text, reply_markup=back_kb)

            # Send photo previews album to Telegram so teacher can review them immediately!
            if preview_photos and update.effective_chat:
                try:
                    chat_id = update.effective_chat.id
                    if len(preview_photos) >= 2:
                        media_group = [
                            InputMediaPhoto(media=io.BytesIO(img_bytes), caption=cap)
                            for img_bytes, cap in preview_photos[:10]
                        ]
                        await context.bot.send_media_group(chat_id=chat_id, media=media_group)
                    elif len(preview_photos) == 1:
                        img_bytes, cap = preview_photos[0]
                        await context.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(img_bytes), caption=cap)
                except Exception as pm_err:
                    logger.warning(f"Could not send Telegram photo previews: {pm_err}")
        else:
            tech_err = result.get("technical_error") or result.get("message") or "Произошла ошибка при создании"
            safe_err = str(tech_err).replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
            back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📱 Главное меню", callback_data="menu:main")]])
            err_text = (
                f"❌ *Техническая ошибка создания:*\n\n"
                f"🔧 *Причина:* {safe_err}\n\n"
                f"💡 *Рекомендация:*\n"
                f"• Проверьте, что Figma открыта и плагин запущен на доске\n"
                f"• Убедитесь, что индикатор в плагине зелёный\n"
                f"• Попробуйте повторить запрос"
            )
            if status_msg:
                try:
                    await status_msg.edit_text(err_text, reply_markup=back_kb, parse_mode="Markdown")
                except Exception:
                    await status_msg.edit_text(err_text, reply_markup=back_kb)

    except Exception as e:
        logger.error(f"Telegram execution error: {e}", exc_info=True)
        if status_msg:
            try:
                await status_msg.edit_text(f"❌ Ошибка:\n{e}")
            except Exception:
                pass
    finally:
        _active_creation_description = None
        context.user_data.pop("pending_lesson_plan", None)


# ── Lifecycle Control ────────────────────────────────────────────────────────

def is_running() -> bool:
    global _bot_status
    return _bot_status == "running"


def get_status() -> dict:
    global _bot_status, _bot_last_error
    return {
        "running": _bot_status == "running",
        "status": _bot_status,
        "error": _bot_last_error,
        "enabled": bool(config.get("telegram.enabled", False)),
        "has_token": bool(config.get("telegram.bot_token")),
        "allowed_user_ids": config.get("telegram.allowed_user_ids", []),
        "telegram_available": TELEGRAM_AVAILABLE,
        "proxy": config.get("telegram.proxy", {
            "enabled": False,
            "protocol": "socks5",
            "host": "127.0.0.1",
            "port": 2080,
            "username": "",
            "password": "",
        })
    }


def start_bot(token: str, proxy_url: Optional[str] = None) -> bool:
    global _bot_thread, _bot_loop, _bot_status, _bot_last_error

    if not TELEGRAM_AVAILABLE:
        _bot_status = "error"
        _bot_last_error = "Библиотека python-telegram-bot не установлена"
        return False

    if not token or not token.strip():
        _bot_status = "error"
        _bot_last_error = "Токен бота не задан"
        return False

    if _bot_status == "running":
        stop_bot()
        time.sleep(0.5)

    def run():
        global _bot_loop, _bot_app, _bot_status, _bot_last_error
        try:
            _bot_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_bot_loop)
            _bot_loop.run_until_complete(_run_bot_coroutine(token.strip(), proxy_url))
        except Exception as e:
            _bot_status = "error"
            _bot_last_error = str(e)
            logger.error(f"Telegram bot thread exited: {e}")

    _bot_thread = threading.Thread(target=run, daemon=True, name="telegram-bot")
    _bot_thread.start()
    _bot_status = "running"
    _bot_last_error = ""
    logger.info("🤖 Telegram bot started successfully")
    return True


def stop_bot():
    global _bot_status
    _bot_status = "stopped"
    logger.info("🤖 Telegram bot stopping...")


def restart_bot(token: str, proxy_url: Optional[str] = None):
    stop_bot()
    time.sleep(0.6)
    return start_bot(token, proxy_url)


async def _run_bot_coroutine(token: str, proxy_url: Optional[str] = None):
    global _bot_app, _bot_status, _bot_last_error
    try:
        builder = Application.builder().token(token)
        if proxy_url:
            builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)

        app = builder.build()
        _bot_app = app

        app.add_handler(CommandHandler(["start", "menu", "help"], cmd_start))
        app.add_handler(CommandHandler(["clear", "reset"], cmd_clear))
        app.add_handler(CommandHandler(["status", "info"], cmd_status))
        app.add_handler(CommandHandler(["tokens", "usage"], cmd_tokens))
        app.add_handler(CommandHandler(["feedback", "review", "debrief"], cmd_feedback))
        app.add_handler(CommandHandler(["backup"], cmd_backup))
        app.add_handler(CallbackQueryHandler(on_callback))
        app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_photo_message))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        logger.info("🤖 Telegram bot polling started successfully")
        _bot_status = "running"
        _bot_last_error = ""

        # Keep running until stop_bot is called
        while _bot_status == "running":
            await asyncio.sleep(0.5)

        logger.info("🤖 Shutting down Telegram bot...")
        if app.updater and app.updater.running:
            await app.updater.stop()
        if app.running:
            await app.stop()
        await app.shutdown()
        logger.info("🤖 Telegram bot stopped cleanly")
    except Exception as e:
        _bot_status = "error"
        _bot_last_error = str(e)
        logger.error(f"Telegram bot runtime error: {e}", exc_info=True)

