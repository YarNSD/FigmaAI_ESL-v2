"""
ESL Figma AI — Pedagogical Debriefing & Feedback Agent
Guides the teacher through a structured, friendly interview after a lesson
to gather specific insights about students, blocks (e.g. 1.1, 5.2), and activities.
Supports text and voice messages via Gemini Multimodal API.
"""
import base64
import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from server import config, agent_logger
from server.agents import student_agent, ai_engine

logger = logging.getLogger("feedback_agent")

# In-memory feedback session states per user
# key: user_id (str) -> state dict
_FEEDBACK_SESSIONS: Dict[str, Dict[str, Any]] = {}


def get_feedback_session(user_id: str) -> Optional[Dict[str, Any]]:
    return _FEEDBACK_SESSIONS.get(str(user_id))


def start_feedback_session(user_id: str, student_id: Optional[str] = None) -> Dict[str, Any]:
    """Initialize a guided feedback interview session."""
    session = {
        "step": "ask_student_and_block",
        "student_id": student_id,
        "block_num": None,
        "engagement_notes": "",
        "language_gaps": "",
        "attention_and_timing": "",
        "next_step_wishes": "",
        "created_at": datetime.now().isoformat()
    }
    _FEEDBACK_SESSIONS[str(user_id)] = session
    return session


def clear_feedback_session(user_id: str) -> None:
    _FEEDBACK_SESSIONS.pop(str(user_id), None)


async def transcribe_and_analyze_voice(voice_bytes: bytes, context_prompt: str = "") -> str:
    """
    Voice transcription via cloud API is disabled for 100% local on-device operation.
    """
    raise ValueError(
        "Голосовые запросы через внешние API отключены: система работает строго локально на вашем ПК без передачи данных в сторонние облака. "
        "Пожалуйста, вводите сообщения текстом."
    )


async def process_feedback_step(user_id: str, text: str) -> Dict[str, Any]:
    """
    Guides the teacher through the debriefing interview step-by-step.
    """
    session = get_feedback_session(user_id)
    if not session:
        session = start_feedback_session(user_id)

    step = session.get("step", "ask_student_and_block")
    msg_lower = text.lower().strip()

    # If teacher explicitly wants to cancel/exit
    if any(k in msg_lower for k in ["отмена", "отменить", "выход", "стоп", "/cancel"]):
        clear_feedback_session(user_id)
        return {
            "reply": "🤝 **Диалог по итогам урока завершен.** Возвращаемся в главное меню!",
            "suggested_replies": ["🎯 Создать задание", "📱 Главное меню"],
            "is_finished": True
        }

    # Helper for student chips
    def _student_chips():
        all_s = student_agent.list_students()
        chips = []
        for s in all_s[:3]:
            c_name = student_agent.get_name_declensions(s.get("name", "")).get("gen", s.get("name"))
            chips.append(f"👤 {s.get('name')}")
        return chips or ["👤 Маша", "👤 Вася"]

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 0: Check if message is an ALL-IN-ONE comprehensive feedback dump
    # ─────────────────────────────────────────────────────────────────────────
    matched_st = student_agent.match_student_in_text(text)
    m_block_any = re.search(r"(?:блок\w*|урок\w*)\s*[:№]?\s*(\d+(?:\.\d+)?)", msg_lower)
    has_gaps_indicators = any(k in msg_lower for k in ["пута", "ошиб", "сложн", "трудн", "не смогл", "забыл"])
    has_positive_indicators = any(k in msg_lower for k in ["понравил", "заш", "отличн", "супер", "азарт", "легко"])

    if matched_st and (has_gaps_indicators or has_positive_indicators) and len(text) > 40:
        # Teacher gave everything in one go! Synthesize immediately.
        session["student_id"] = matched_st["id"]
        if m_block_any:
            session["block_num"] = m_block_any.group(1)
        return await _finalize_and_save_feedback(user_id, text, session)

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1: Identify Student and Block Number (e.g. "Маша, блок 1.1")
    # ─────────────────────────────────────────────────────────────────────────
    if step == "ask_student_and_block":
        # Check student
        st = matched_st or (student_agent.get_student(session.get("student_id")) if session.get("student_id") else None)
        if not st:
            all_s = student_agent.list_students()
            for s in all_s:
                if s["name"].lower() in msg_lower:
                    st = student_agent.get_student(s["id"])
                    break

        # Check block/lesson number (e.g., 1.1, 5.2, блок 3, урок 4)
        m_blk = re.search(r"(?:блок\w*|урок\w*|№|\b)(\d+\.\d+|\d+)\b", msg_lower)
        blk = m_blk.group(1) if m_blk else None

        # Case 1: Neither student nor block was found
        if not st and not blk and not session.get("student_id") and not session.get("block_num"):
            return {
                "reply": (
                    "📝 **Привет! Давай разберём, как всё прошло на практике.** ☕️\n\n"
                    "Назови ученика и номер блока или урока — например: **«Маша, блок 1.1»** или **«Вася, 5.2»**.\n"
                    "*(Можешь просто надиктовать голосовым сообщением или написать текстом)*"
                ),
                "suggested_replies": _student_chips() + ["Блок 1.1", "Урок целиком"],
                "is_finished": False
            }

        # Save whatever was provided
        if st:
            session["student_id"] = st["id"]
        if blk:
            session["block_num"] = blk

        # Case 2: We have block number, but still don't know the student
        if not session.get("student_id"):
            blk_disp = f"блок {session['block_num']}" if session.get("block_num") else "материал"
            return {
                "reply": (
                    f"🎯 **Отлично, {blk_disp} записал!**\n\n"
                    "А с кем из учеников ты его проходил? Назови имя (например, Маша, Вася или Миша):"
                ),
                "suggested_replies": _student_chips(),
                "is_finished": False
            }

        # Case 3: We have the student, but block was not yet mentioned
        if not session.get("block_num"):
            # Check if user said "урок целиком" or similar
            if any(k in msg_lower for k in ["целиком", "весь", "полный", "все блоки"]):
                session["block_num"] = "Урок целиком"
            else:
                s_obj = student_agent.get_student(session.get("student_id"))
                s_name = s_obj.get("name", "ученика") if s_obj else "ученика"
                s_cases = student_agent.get_name_declensions(s_name)
                return {
                    "reply": (
                        f"👤 **Зафиксировал {s_cases.get('acc', s_name)}!**\n\n"
                        f"А какой номер блока или урока вы разбирали? "
                        f"*(Например: **1.1**, **5.2** или **«урок целиком»**)*"
                    ),
                    "suggested_replies": ["1.1", "1.2", "2.1", "Урок целиком"],
                    "is_finished": False
                }

        # Both student and block are now known! Proceed to Question 1
        s_obj = student_agent.get_student(session.get("student_id"))
        s_name = s_obj.get("name", "ученика") if s_obj else "ученика"
        s_cases = student_agent.get_name_declensions(s_name)

        session["step"] = "ask_engagement"
        blk_str = f"блоку {session['block_num']}" if session.get("block_num") else "пройденному материалу"
        
        reply = (
            f"👤 **Супер, разбираем занятие с {s_cases.get('ins', s_name)} ({blk_str})!**\n\n"
            f"1️⃣ **Как прошли задания на доске у {s_cases.get('gen', s_name)}?**\n"
            f"Было ли сразу понятно, что делать с карточками/словами? Что вызвало искренний азарт и улыбку, "
            f"а где возникли заминки или скука?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "🔥 Был азарт и интерес к карточкам",
                "🤔 Зависали на длинных вопросах",
                "⚡ Всё щелкалось легко и быстро"
            ],
            "is_finished": False
        }

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 2: Engagement & Activity Affinity
    # ─────────────────────────────────────────────────────────────────────────
    if step == "ask_engagement":
        session["engagement_notes"] = text
        session["step"] = "ask_language_gaps"
        s_obj = student_agent.get_student(session.get("student_id"))
        s_name = s_obj.get("name", "ученика") if s_obj else "ученика"
        s_cases = student_agent.get_name_declensions(s_name)

        reply = (
            f"💡 **Механику и отклик зафиксировал!**\n\n"
            f"2️⃣ **А теперь давай к языковой конкретике:**\n"
            f"В каких именно словах, грамматических конструкциях или предлогах у {s_cases.get('gen', s_name)} были ошибки или сомнения? "
            f"Что ученик пытался сказать по-английски, но не смог сформулировать?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "🎯 Путаница в предлогах (in/at/on)",
                "📚 Забывались слова темы",
                "🧩 Окончания глаголов (s/ed)"
            ],
            "is_finished": False
        }

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 3: Language Gaps & Emergent Language
    # ─────────────────────────────────────────────────────────────────────────
    if step == "ask_language_gaps":
        session["language_gaps"] = text
        session["step"] = "ask_next_steps"
        s_obj = student_agent.get_student(session.get("student_id"))
        s_name = s_obj.get("name", "ученика") if s_obj else "ученика"
        s_cases = student_agent.get_name_declensions(s_name)

        reply = (
            f"🎯 **Отличные конкретные маркеры, беру в работу!**\n\n"
            f"3️⃣ **И по концентрации и плану на будущее:**\n"
            f"Хватило ли {s_cases.get('dat', s_name)} сил и концентрации до конца урока? "
            f"И что бы ты хотел сделать на следующем уроке — закрепить этот же блок в игровом формате или двигаться дальше?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "🎮 Закрепить в мини-игре на 5 минут",
                "🗣️ Вывести слова в Speaking диалог",
                "⏱️ Усталость к концу, снизить темп",
                "🚀 Идти к следующему блоку"
            ],
            "is_finished": False
        }

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 4: Next Steps & Final Synthesis
    # ─────────────────────────────────────────────────────────────────────────
    if step == "ask_next_steps":
        session["next_step_wishes"] = text
        return await _finalize_and_save_feedback(user_id, "", session)

    return {
        "reply": "Готов зафиксировать фидбек по уроку. Назови ученика или номер блока:",
        "suggested_replies": _student_chips(),
        "is_finished": False
    }


async def _finalize_and_save_feedback(user_id: str, raw_text: str, session: Dict[str, Any]) -> Dict[str, Any]:
    """Synthesizes collected notes into student profile and lessons history."""
    st_id = session.get("student_id") or "masha"
    s_obj = student_agent.get_student(st_id)
    s_name = s_obj.get("name", "ученика") if s_obj else "ученика"
    s_cases = student_agent.get_name_declensions(s_name)
    s_level = s_obj.get("level", "A1") if s_obj else "A1"
    blk = session.get("block_num") or "занятие"

    full_feedback_text = (
        raw_text or 
        f"Блок/урок: {blk}. "
        f"Реакция: {session.get('engagement_notes', '')}. "
        f"Ошибки и пробелы: {session.get('language_gaps', '')}. "
        f"Внимание и след. урок: {session.get('next_step_wishes', '')}."
    )

    # Record in student CRM
    fb_res = student_agent.record_student_feedback(st_id, full_feedback_text)
    strengths_added = fb_res.get("strengths_added", [])
    weaknesses_added = fb_res.get("weaknesses_added", [])

    strengths_str = ", ".join(strengths_added) if strengths_added else (session.get("engagement_notes") or "активное участие и интерес")
    weaknesses_str = ", ".join(weaknesses_added) if weaknesses_added else (session.get("language_gaps") or "отдельные языковые моменты")

    # Clear session
    clear_feedback_session(user_id)

    reply = (
        f"📋 **Итоги урока успешно зафиксированы!** 🎉\n\n"
        f"👤 **Ученик:** {s_name} [{s_level}] | Блок: `{blk}`\n"
        f"• 🌟 **Что зашло на ура (в досье)**: {strengths_str}\n"
        f"• 🎯 **Зоны внимания (на отработку)**: {weaknesses_str}\n"
        f"• 💡 **Фокус на след. урок**: {session.get('next_step_wishes') or 'мягкое повторение трудных тем в игровом формате'}\n\n"
        f"Все инсайты бережно добавлены в профиль {s_cases.get('gen', s_name)} и будут учтены при генерации новых заданий!"
    )

    return {
        "reply": reply,
        "suggested_replies": [
            f"🎯 Задание для {s_cases.get('gen', s_name)}",
            "📊 Профиль ученика",
            "📱 Главное меню"
        ],
        "is_finished": True,
        "student_id": st_id,
        "summary": {
            "student_name": s_name,
            "block": blk,
            "strengths": strengths_str,
            "weaknesses": weaknesses_str
        }
    }
