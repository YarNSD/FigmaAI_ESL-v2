"""
ESL Figma AI — Conversational Pedagogical Knowledge & Expert Partner
Acts as a warm, casual, supportive peer teacher in Telegram / Web UI.
- Maintains long-term student memory, learns from teacher feedback after lessons
- Automatically recognizes students by name ("для Маши", "у Маши") and tailors to their level and strengths
- Inquires about student details and CEFR level if not specified
- Smoothly handles student level changes/progression ("Маша повысила уровень до A2")
- Always asks for nuances/comments before creating or editing materials
- Offers interactive contextual chips as quick answers to questions
- Only initiates board building when the teacher explicitly confirms ("нарисуй", "создай", "давай делать")
"""
from typing import Dict, List, Optional, Any
import re
from server.agents import student_agent


def _extract_conversation_context(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    student: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Scans message and history to detect topic, level, audience, and intent."""
    msg_lower = (message or "").lower().strip()
    history = history or []

    # 1. Level detection (explicit check without hardcoding A2)
    m_lvl = re.search(r"\b([a-cA-C][0-2])\b", msg_lower)
    is_level_explicit = bool(m_lvl)
    if not m_lvl:
        # Check history
        for turn in reversed(history[-6:]):
            if turn.get("role") == "user":
                c_text = (turn.get("content") or "").lower()
                m_h = re.search(r"\b([a-cA-C][0-2])\b", c_text)
                if m_h:
                    m_lvl = m_h
                    is_level_explicit = True
                    break

    level = m_lvl.group(1).upper() if m_lvl else (student.get("level") if student else None)
    has_level = level is not None

    # 2. Age / Audience
    m_age = re.search(r"\b(\d{1,2})\s*(?:лет|года|год|y\.?o\.?|yo)\b", msg_lower)
    age = int(m_age.group(1)) if m_age else (student.get("age") if student else None)

    is_child = (age is not None and age <= 14) or any(
        k in msg_lower for k in ["ребенок", "ребёнок", "дети", "детям", "мальчик", "девочка", "подрост"]
    )

    # 3. Topic detection — check current message first, then history if continuing
    lvl_label = f" ({level})" if level else ""
    topics_map = [
        ("food", [r"\b(еда|еды|еду|едой|пищ\w*|кухн\w*|food|cook\w*|блюд\w*|пицц\w*|ресторан\w*)\b"], "Food & Cooking", "Еда и предпочтения"),
        ("travel", [r"\b(путеш\w*|travel\w*|trip\w*|город\w*|стран\w*|отпуск\w*|аэропорт\w*)\b"], "Travel & Adventures", "Путешествия и страны"),
        ("gadgets", [r"\b(гаджет\w*|телефон\w*|phone\w*|gadget\w*|технолог\w*|смартфон\w*)\b"], "Digital Life & Gadgets", "Гаджеты и технологии"),
        ("games", [r"\b(игр\w*|game\w*|minecraft|roblox|гейминг)\b"], "Gaming & Hobbies", "Игры и увлечения"),
        ("movies", [r"\b(кино|фильм\w*|сериал\w*|movie\w*|cinema|netflix)\b"], "Movies & TV Shows", "Кино и сериалы"),
        ("animals", [r"\b(животн\w*|кот\w*|кошк\w*|собак\w*|питомц\w*|pet\w*|animal\w*|zoo)\b"], "Animals & Pets", "Животные и питомцы"),
        ("work", [r"\b(работ\w*|карьер\w*|професси\w*|job\w*|career\w*|офис\w*)\b"], "Work & Career", "Работа и карьера"),
        ("daily", [r"\b(рутин\w*|распорядок\w*|утро|daily|routine|привычк\w*)\b"], "Daily Life & Routines", "Повседневная жизнь"),
        ("prepositions", [r"\b(предлог\w*|preposition\w*)\b"], f"Prepositions of Place{lvl_label}", f"Предлоги места{lvl_label}"),
        ("people", [r"\b(внешност\w*|appearance|описание людей)\b"], f"Describing People{lvl_label}", f"Описание людей{lvl_label}"),
        ("numbers", [r"\b(числ\w*|счет|цифр\w*|numbers?)\b"], f"Numbers 1-100{lvl_label}", f"Числа от 1 до 100{lvl_label}"),
    ]

    detected_topic_key = None
    detected_topic_en = "Daily Life & Routines"
    detected_topic_ru = "Повседневная жизнь и привычки"
    has_explicit_topic = False

    # Check current message
    for key, patterns, en_title, ru_title in topics_map:
        for pat in patterns:
            if re.search(pat, msg_lower):
                detected_topic_key = key
                detected_topic_en = en_title
                detected_topic_ru = ru_title
                has_explicit_topic = True
                break
        if has_explicit_topic:
            break

    # Fallback to history only if no topic in current message
    if not has_explicit_topic:
        for turn in reversed(history[-4:]):
            if turn.get("role") == "user":
                c_text = (turn.get("content") or "").lower()
                for key, patterns, en_title, ru_title in topics_map:
                    for pat in patterns:
                        if re.search(pat, c_text):
                            detected_topic_key = key
                            detected_topic_en = en_title
                            detected_topic_ru = ru_title
                            break
                    if detected_topic_key:
                        break
                if detected_topic_key:
                    break

    # 4. Full lesson / diagnostic test lesson detection
    full_lesson_keywords = [
        "полноценный урок", "полный урок", "урок целиком", "комплексный урок",
        "урок на 1 час", "урок на час", "урок на 60", "урок на 45", "урок на 30",
        "сделай урок", "создай урок", "подготовь урок", "собери урок",
        "первое занятие", "тестовое занятие", "тестовый урок", "пробный урок", "пробное занятие", "диагностическ"
    ]
    is_full_lesson = any(k in msg_lower for k in full_lesson_keywords)
    is_diagnostic = any(k in msg_lower for k in ["первое занятие", "первый урок", "тестов", "пробн", "диагностик", "знакомств"])
    duration = 60 if any(k in msg_lower for k in ["1 час", "час", "60 мин", "60-мин", "на час", "на 1 час"]) else 45

    if is_diagnostic and not has_explicit_topic:
        detected_topic_key = "about_me"
        detected_topic_en = "All About Me & Diagnostic Starter"
        detected_topic_ru = "Знакомство и диагностика (All About Me)"

    # 4.1 Activity format detection (check current message first, then history)
    activity_type = None
    if is_full_lesson:
        activity_type = "bloom_lesson"
    elif any(k in msg_lower for k in ["квиз", "quiz", "викторин"]):
        activity_type = "quiz_photo"
    elif any(k in msg_lower for k in ["карточ", "speaking", "говорен", "разминк", "дилемм"]):
        activity_type = "speaking_cards"
    elif any(k in msg_lower for k in ["peekaboo", "открываш", "шторк"]):
        activity_type = "flip_cards"
    elif any(k in msg_lower for k in ["пропуск", "fill"]):
        activity_type = "fill_blanks"
    elif any(k in msg_lower for k in ["словар", "словарь", "vocab"]):
        activity_type = "vocabulary_table"

    if not activity_type:
        for turn in reversed(history[-4:]):
            c_text = (turn.get("content") or "").lower()
            if any(k in c_text for k in ["урок", "полный", "комплексный", "блум"]):
                activity_type = "bloom_lesson"
                is_full_lesson = True
                break
            elif any(k in c_text for k in ["квиз", "quiz", "фото", "загадк"]):
                activity_type = "quiz_photo"
                break
            elif any(k in c_text for k in ["карточ", "speaking", "дилемм"]):
                activity_type = "speaking_cards"
                break
            elif any(k in c_text for k in ["peekaboo", "открываш"]):
                activity_type = "flip_cards"
                break
            elif any(k in c_text for k in ["пропуск", "fill"]):
                activity_type = "fill_blanks"
                break

    if not activity_type:
        activity_type = "quiz_photo"

    # 5. Explicit build/draw triggers
    build_triggers = [
        "нарисуй", "создай", "нарисовать", "построй", "сделай блок", "собери урок",
        "собрать урок", "переноси на доску", "рисуй на доске", "давай делать",
        "согласен, делай", "да, рисуй", "погнали", "рисуй", "делай этот вариант",
        "всё отлично, рисуй", "всё супер, рисуй", "рисуй без правок", "всё отлично, создавай",
        "рисуй урок", "создай урок", "нарисуй урок"
    ]
    is_explicit_build = any(t in msg_lower for t in build_triggers)

    # 6. Editing intent triggers
    edit_triggers = [
        "отредактируй", "переделай", "поменяй вопросы", "исправь", "измени",
        "скорректируй", "обнови блок", "откорректируй", "редактир"
    ]
    is_edit_intent = any(t in msg_lower for t in edit_triggers)

    # 7. Nuance / comment input triggers
    nuance_triggers = [
        "добавь", "включи", "пусть", "сделай так чтобы", "акцент на",
        "пожелание", "комментарий", "нюанс", "без сложных", "только простые"
    ]
    is_nuance_input = any(t in msg_lower for t in nuance_triggers) and len(msg_lower) > 6

    return {
        "level": level,
        "has_level": has_level,
        "is_level_explicit": is_level_explicit,
        "age": age,
        "is_child": is_child,
        "topic_en": detected_topic_en,
        "topic_ru": detected_topic_ru,
        "topic_key": detected_topic_key or "daily",
        "has_explicit_topic": has_explicit_topic,
        "activity_type": activity_type,
        "is_full_lesson": is_full_lesson,
        "is_diagnostic": is_diagnostic,
        "duration": duration,
        "is_explicit_build": is_explicit_build,
        "is_edit_intent": is_edit_intent,
        "is_nuance_input": is_nuance_input
    }


def analyze_and_respond(
    message: str,
    student: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Conversational pedagogical peer.
    Provides warm, human, casual help, asks clarifying questions in various situations,
    actively manages student profiles, feedbacks and nuances before building.
    """
    msg_lower = (message or "").lower().strip()
    history = history or []

    # 0. Check if student is mentioned by name in message if not yet bound
    matched_in_text = student_agent.match_student_in_text(message)
    if matched_in_text:
        student = matched_in_text

    ctx = _extract_conversation_context(message, history, student)

    s_name = student.get("name") if student else None
    s_cases = student_agent.get_name_declensions(s_name) if s_name else {}
    has_level = ctx["has_level"]
    target_level = ctx["level"] or (student.get("level") if student else "A2")

    if s_name and ctx["level"]:
        student_desc = f"ученика {s_cases.get('gen', s_name)} ({ctx['level']})"
    elif s_name:
        student_desc = f"ученика {s_cases.get('gen', s_name)}"
    elif ctx["level"]:
        student_desc = f"уровня {ctx['level']}"
    else:
        student_desc = "вашего занятия"

    def _get_student_or_level_chips() -> List[str]:
        chips = []
        all_s = student_agent.list_students()
        for s in all_s[:2]:
            c_name = student_agent.get_name_declensions(s.get("name", "")).get("gen", s.get("name"))
            lvl = s.get("level", "A1")
            chips.append(f"👤 Для {c_name} ({lvl})")
        chips.extend(["🟢 Уровень A1", "🟡 Уровень A2", "🔵 Уровень B1"])
        return chips[:3]

    # ═════════════════════════════════════════════════════════════════════════
    # 0.0 GREETINGS & CASUAL WELCOME (Peer dialogue, no forced lesson templates)
    # ═════════════════════════════════════════════════════════════════════════
    greeting_pattern = r"\b(привет|приветик|приветики|здравствуй|здравствуйте|добрый день|доброе утро|добрый вечер|доброй ночи|хай|хей|салют|ку|йоу|hello|hi|hey)\b"
    has_greeting = bool(re.search(greeting_pattern, msg_lower))

    has_task_instruction = (
        ctx["is_explicit_build"]
        or ctx["is_edit_intent"]
        or ctx["is_full_lesson"]
        or ctx["is_diagnostic"]
        or ctx["is_nuance_input"]
        or ctx["has_explicit_topic"]
        or bool(matched_in_text)
        or bool(re.search(r"(?:для|у|зовут|учениц[аеы]|ученик[аеу]?)\s+[А-ЯЁA-Z][а-яёa-z]+", message))
        or any(k in msg_lower for k in [
            "квиз", "quiz", "викторин", "карточ", "speaking", "открываш", "peekaboo", "шторк",
            "пропуск", "fill", "словар", "словарь", "vocab", "flashcard", "флешкарт",
            "нарисуй", "создай", "построй", "сделай", "собери", "переделай", "исправь", "измени"
        ])
    )

    if has_greeting and not has_task_instruction:
        if student:
            st_level = student.get("level", "A1")
            st_name = student.get("name", "ученика")
            reply = f"Привет! Рад тебя слышать. 😊 Как настроение? Сейчас в фокусе ученик **{st_name}** ({st_level}). Можем поболтать, обсудить идеи или подготовить что-то свежее для занятия!"
        else:
            reply = "Привет! Рад тебя слышать. 😊 Как настроение? Готов поболтать на любые темы или помочь с уроками и идеями!"
        return {
            "reply": reply,
            "suggested_replies": [],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 0.01 SMALL TALK & HOW ARE YOU
    # ═════════════════════════════════════════════════════════════════════════
    small_talk_pattern = r"\b(как дела|как жизнь|как ты|как настроение|как успехи|что делаешь|чем занимаешься|что нового|ты как|как сам|how are you|how's it going|whats up|what's up)\b"
    if re.search(small_talk_pattern, msg_lower) and not has_task_instruction:
        reply = (
            "У меня всё отлично, в строю и на связи! 😊\n\n"
            "Как твой день проходит? Что интересного произошло или просто отдыхаешь?"
        )
        return {
            "reply": reply,
            "suggested_replies": [],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 0.02 STATUS & PRESENCE CHECK
    # ═════════════════════════════════════════════════════════════════════════
    status_pattern = r"\b(ты тут|ты здесь|ты на связи|ты жив|ты онлайн|ты работаешь|на связи\??|are you here|you there)\b"
    if re.search(status_pattern, msg_lower) and not has_task_instruction:
        reply = "Да, я здесь и на связи! Готов поболтать или помочь с любыми задачами. 😊 Что у тебя на уме?"
        return {
            "reply": reply,
            "suggested_replies": [],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 0.03 GRATITUDE & POLITENESS
    # ═════════════════════════════════════════════════════════════════════════
    gratitude_pattern = r"\b(спасибо|спасибочки|благодарю|от души|сяп|сенкс|thanks|thank you|thx)\b"
    if re.search(gratitude_pattern, msg_lower) and not has_task_instruction:
        reply = "Всегда пожалуйста! Рад помочь. 😊 Если захочешь продолжить разговор или что-то создать — я рядом!"
        return {
            "reply": reply,
            "suggested_replies": [],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 0.04 AFFIRMATIONS & SHORT ACKNOWLEDGMENTS
    # ═════════════════════════════════════════════════════════════════════════
    ack_pattern = r"^(?:да\s*,?\s*)?(ок|okay|ok|ладно|хорошо|договорились|супер|отлично|класс|круто|огонь|кайф|понятно|ясно|понял|принял|ясненько|понял тебя|чудно|замечательно|давай|делай|давай делать|согласен|подходит|плюс)[\s\.\!\?]*$"
    if re.search(ack_pattern, msg_lower) or msg_lower in ("да", "да, хорошо", "хорошо", "давай", "делай", "да давай"):
        # Check if previous assistant turn proposed an activity or asked confirmation
        has_pending_proposal = False
        proposed_topic = ctx.get("topic_en", "Daily Life & Routines")
        proposed_title = ctx.get("topic_ru", "Урок")
        proposed_type = ctx.get("activity_type") or "quiz_photo"
        for turn in reversed(history[-3:]):
            if turn.get("role") in ("assistant", "model"):
                c_txt = (turn.get("content") or "").lower()
                if any(w in c_txt for w in ["план", "подготовим", "нарисуем", "создадим", "напиши", "делай", "на доске", "урок", "квиз"]):
                    has_pending_proposal = True
                    break

        if has_pending_proposal:
            type_title = "Фото-квиз" if proposed_type == "quiz_photo" else "Комплексный урок"
            reply = (
                f"🚀 **Отлично, запускаю создание на доске!**\n\n"
                f"Переношу «{type_title}: {proposed_title}» прямо на холст FigJam..."
            )
            lesson_plan = {
                "title": f"{type_title}: {proposed_title}",
                "topic": proposed_topic,
                "level": target_level,
                "format": "game" if ctx["is_child"] else "conversational",
                "use_bloom_arc": False,
                "blocks": [proposed_type]
            }
            return {
                "reply": reply,
                "suggested_replies": [],
                "ready_to_build": True,
                "lesson_plan": lesson_plan,
                "student_id": student["id"] if student else None
            }

        reply = (
            "Договорились! 👌 Буду здесь. Как только понадобится сгенерировать блок, обновить оглавление на холсте или обсудить ученика — я наготове."
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "🎯 Создать задание",
                "👤 Выбрать ученика",
                "📑 Обновить оглавление"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 0.05 TEACHER EMOTIONS & FATIGUE
    # ═════════════════════════════════════════════════════════════════════════
    fatigue_pattern = r"\b(устал|устала|тяжелый день|тяжёлый день|сил нет|вымотался|вымоталась|много уроков)\b"
    if re.search(fatigue_pattern, msg_lower) and not has_task_instruction:
        reply = (
            "Прекрасно тебя понимаю! Преподавание забирает очень много сил и эмоциональной энергии. ☕\n\n"
            "Давай снимем с тебя рутину: я могу полностью взять на себя создание интерактива на доске — "
            "набросаю лёгкий готовый квиз или карточки для говорения, чтобы тебе не пришлось тратить время на подготовку.\n\n"
            "Хочешь, соберу готовый блок на автопилоте?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "💡 Быстрый лёгкий квиз",
                "🗣️ Speaking-разминка",
                "☕ Сделать перерыв"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 0.06 STUDENT DIRECTORY & SELECTION INTENT ("Выбрать ученика", "Список учеников")
    # ═════════════════════════════════════════════════════════════════════════
    student_list_triggers = [
        "выбрать ученика", "список учеников", "досье учеников", "мои ученики",
        "сменить ученика", "кто мои ученики", "посмотреть учеников", "база учеников"
    ]
    if any(k in msg_lower for k in student_list_triggers):
        all_s = student_agent.list_students()
        lines = []
        for s in all_s:
            sname = s.get("name", "Ученик")
            slvl = s.get("level", "A1")
            sage = s.get("age")
            sage_str = f", {sage} лет" if sage else ""
            sints = ", ".join(s.get("interests", [])[:2])
            int_str = f" — интерес: {sints}" if sints else ""
            lines.append(f"• **{sname}** ({slvl}{sage_str}){int_str}")
        list_str = "\n".join(lines) if lines else "Пока нет сохранённых учеников."
        reply = (
            f"👤 **Твои ученики в базе:**\n\n"
            f"{list_str}\n\n"
            f"Напиши имя ученика (например «для Маши») или нажми кнопку ниже, чтобы привязать его к уроку:"
        )
        chips = [f"👤 {s.get('name')}" for s in all_s[:3]]
        if not chips:
            chips = ["➕ Добавить ученика", "🎯 Создать задание"]
        return {
            "reply": reply,
            "suggested_replies": chips,
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 0.07 TASK CREATION OVERVIEW INTENT ("Создать задание", "Варианты заданий")
    # ═════════════════════════════════════════════════════════════════════════
    task_overview_triggers = [
        "создать задание", "новое задание", "что создать", "какие задания бывают",
        "варианты заданий", "хочу задание", "типы блоков", "типы заданий"
    ]
    if any(msg_lower == k or msg_lower.startswith(k) for k in task_overview_triggers):
        reply = (
            "🎨 **Какие интерактивные блоки можно создать на доске:**\n\n"
            "1️⃣ 🎯 **Фото-квиз (Quiz Photo)** — вопросы с 4 вариантами ответа, визуалом и мгновенной подсветкой правильного ответа.\n"
            "2️⃣ 🗣️ **Speaking Cards** — карточки с вопросами и дилеммами для разогрева говорения.\n"
            "3️⃣ 🃏 **Peekaboo-открывашки (Flip Cards)** — карточки со шторками, скрывающими ответ или перевод.\n"
            "4️⃣ 📚 **Иллюстрированный словарь (Vocabulary Table)** — таблица ключевых слов с фото и переводом.\n"
            "5️⃣ ✏️ **Упражнение с пропусками (Fill Blanks)** — предложения с интерактивными кнопками-пропусками.\n"
            "6️⃣ 🎓 **Комплексный урок на 60 мин (Bloom Lesson)** — полноценная 5-этапная дуга по Таксономии Блума.\n\n"
            "Назови тему или выбери формат:"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "🎯 Фото-квиз",
                "🗣️ Speaking Cards",
                "🎓 Полный урок"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 0. EDITING EXISTING BLOCK INTENT (Nuances & comments required)
    # ═════════════════════════════════════════════════════════════════════════
    if ctx.get("is_edit_intent"):
        reply = (
            "✏️ **Перед редактированием задания — какие комментарии и нюансы нужно учесть?**\n\n"
            "Подскажи, что именно изменить в блоке на холсте:\n"
            "• Заменить формулировки вопросов или изменить уровень сложности?\n"
            "• Поменять иллюстрации и картинки на другие сюжетом?\n"
            "• Включить конкретные слова, грамматику или исправить ошибки?\n\n"
            "Напиши свои комментарии текстом или выбери направление:"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "🔄 Заменить вопросы",
                "📸 Поменять картинки",
                "📈 Сделать сложнее"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 0.1 NUANCE / COMMENT INPUT GIVEN BY TEACHER
    # ═════════════════════════════════════════════════════════════════════════
    if ctx.get("is_nuance_input"):
        b_type = ctx.get("activity_type") or "quiz_photo"
        type_title = "Фото-квиз" if b_type == "quiz_photo" else ("Speaking Cards" if b_type == "speaking_cards" else "Интерактивный блок")
        top_name = ctx["topic_ru"]
        top_en = ctx["topic_en"]

        reply = (
            f"✨ **Отличный комментарий! Учёл все нюансы:**\n\n"
            f"• ✍️ **Зафиксировал пожелание**: «{message.strip()}»\n"
            f"• 🎯 **Материал**: {type_title} для {student_desc}\n\n"
            f"Теперь задание будет идеально откалибровано! Нажимай кнопку ниже, чтобы перенести его прямо на доску:"
        )
        lesson_plan = {
            "title": f"{type_title}: {top_name}",
            "topic": top_en,
            "level": target_level,
            "format": "game" if ctx["is_child"] else "conversational",
            "teacher_comments": message.strip(),
            "use_bloom_arc": False,
            "blocks": [b_type]
        }
        return {
            "reply": reply,
            "suggested_replies": [
                "🚀 Всё супер, рисуй!",
                "✍️ Ещё один нюанс",
                "📱 Главное меню"
            ],
            "ready_to_build": True,
            "lesson_plan": lesson_plan,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 0.2 STUDENT FEEDBACK AFTER LESSON (Insight recording)
    # ═════════════════════════════════════════════════════════════════════════
    fb_keywords = ["фидбек", "отзыв", "понравил", "зашел", "зашёл", "путается", "тяжело да", "сложно да", "ошибается в", "хорошо отвечал"]
    if any(k in msg_lower for k in fb_keywords) and student:
        fb_res = student_agent.record_student_feedback(student["id"], message)
        strengths_str = ", ".join(fb_res.get("strengths_added", [])) or "активность и вовлеченность"
        weaknesses_str = ", ".join(fb_res.get("weaknesses_added", [])) or "отдельные грамматические нюансы"

        reply = (
            f"📝 **Спасибо за ценный фидбек по занятию с {s_cases.get('ins', s_name)}!**\n\n"
            f"Я бережно зафиксировал эти инсайты в её досье:\n"
            f"• 🌟 **Что отлично заходит**: {strengths_str}\n"
            f"• 🎯 **Зоны внимания (на что опереться / повторить)**: {weaknesses_str}\n\n"
            f"В следующих материалах я обязательно это учту — будем использовать любимые механики и аккуратно вплетать отработку трудных тем.\n\n"
            f"Над чем планируешь поработать с {s_cases.get('ins', s_name)} на следующем уроке?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                f"🎯 Повторить: {weaknesses_str[:16]}",
                f"🎮 Квиз: {strengths_str[:16]}",
                "🗣️ Speaking-разминка"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"]
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 0.5 STUDENT LEVEL PROGRESSION / CHANGE OVERRIDE
    # ═════════════════════════════════════════════════════════════════════════
    if student and any(k in msg_lower for k in ["обновить профиль", "да, обновить", "обнови профиль"]):
        m_l = re.search(r"\b([a-cA-C][0-2])\b", message)
        new_l = m_l.group(1).upper() if m_l else "A2"
        student_agent.update_student_level(student["id"], new_l)
        reply = (
            f"✅ **Официальный уровень {s_cases.get('gen', s_name)} успешно обновлен на [{new_l}]!** 🎉\n\n"
            f"Теперь все новые задания по умолчанию будут калиброваться под уровень {new_l}.\n\n"
            f"Какую активность готовим для неё прямо сейчас?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                f"🎯 Фото-квиз [{new_l}]",
                f"🗣️ Speaking Cards [{new_l}]",
                "🃏 Открывашки Peekaboo"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"]
        }

    if student and ctx["is_level_explicit"] and ctx["level"].upper() != student.get("level", "A1").upper() and any(k in msg_lower for k in ["повыс", "друг", "нов", "выше", "уровень", "сделай", "хочу"]):
        prof_lvl = student.get("level", "A1")
        new_lvl = ctx["level"].upper()
        reply = (
            f"🎉 **Здорово! Поздравляю {s_cases.get('acc', s_name)} с переходом на уровень {new_lvl}!**\n\n"
            f"Для текущего задания я сразу использую уровень **[{new_lvl}]**.\n\n"
            f"Обновить постоянный уровень в профиле {s_cases.get('gen', s_name)} с {prof_lvl} на **{new_lvl}**, чтобы все будущие материалы создавались под него?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                f"✅ Обновить профиль на {new_lvl}",
                "⏳ Только на этот урок",
                f"🎯 Фото-квиз [{new_lvl}]"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"]
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 0.8 NAMING A SPECIFIC STUDENT (e.g. "Задание для Маши", "Квиз для Маши")
    # ═════════════════════════════════════════════════════════════════════════
    has_student_mention = bool(re.search(r"(?:для|у|зовут|учениц[аеы]|ученик[аеу]?)\s+[А-ЯЁA-Z][а-яёa-z]+", message)) or bool(matched_in_text)
    if has_student_mention and student and not ctx["is_explicit_build"]:
        s_level = student.get("level", "A1")
        s_interests = student.get("interests", [])
        s_strengths = student.get("strengths", [])
        s_weaknesses = student.get("weaknesses", [])

        strengths_str = ", ".join(s_strengths[:2]) if s_strengths else "интерактивные игры и наглядный визуал"
        weaknesses_str = ", ".join(s_weaknesses[:2]) if s_weaknesses else "повторение базовых конструкций"

        # Check if teacher also asked for a specific format in the same message
        has_specific_activity = any(k in msg_lower for k in ["квиз", "quiz", "фото", "карточ", "speaking", "открываш", "peekaboo", "пропуск", "fill"])
        if has_specific_activity:
            btype = ctx.get("activity_type") or "quiz_photo"
            type_title = "Фото-квиз" if btype == "quiz_photo" else ("Speaking Cards" if btype == "speaking_cards" else "Интерактивный блок")
            top_name = ctx["topic_ru"]
            top_en = ctx["topic_en"]

            reply = (
                f"👤 **Отлично, готовим {type_title} для {s_cases.get('gen', s_name)}!**\n\n"
                f"В её досье зафиксирован уровень **[{s_level}]**.\n"
                f"• 🌟 **Что ей отлично заходит**: {strengths_str}\n"
                f"• 🎯 **Зоны внимания (на что опереться / повторить)**: {weaknesses_str}\n\n"
                f"Перед тем как нарисовать блок на доске — **есть ли какие-то важные комментарии или нюансы, которые стоит учесть?**\n"
                f"(Например: конкретные слова для отработки, любимые сюжеты или ограничения?)\n\n"
                f"Если всё устраивает — нажимай кнопку ниже для генерации на холсте!"
            )
            lesson_plan = {
                "title": f"{type_title}: {top_name}",
                "topic": top_en,
                "level": s_level,
                "format": "game" if ctx["is_child"] else "conversational",
                "use_bloom_arc": False,
                "blocks": [btype]
            }
            return {
                "reply": reply,
                "suggested_replies": [
                    f"🚀 Всё супер, рисуй ({s_level})",
                    "✍️ Добавить комментарий / нюанс",
                    f"📈 Повысить уровень"
                ],
                "ready_to_build": True,
                "lesson_plan": lesson_plan,
                "student_id": student["id"]
            }
        else:
            # Teacher just introduced the student: ask about format and focus
            reply = (
                f"👤 **Отлично, готовим задание для {s_cases.get('gen', s_name)}!**\n\n"
                f"В её досье зафиксирован уровень **[{s_level}]**.\n"
                f"• 🌟 **Что ей отлично заходит**: {strengths_str}\n"
                f"• 🎯 **Зоны внимания (на что опереться / повторить)**: {weaknesses_str}\n\n"
                f"Опираемся на этот уровень и сильные стороны, или сегодня хочешь попробовать уровень повыше (например, A2/B1)?\n\n"
                f"И какую активность выберем: фото-квиз с загадками, разговорные карточки или открывашки Peekaboo?"
            )
            return {
                "reply": reply,
                "suggested_replies": [
                    f"🎯 Фото-квиз [{s_level}]",
                    f"🗣️ Speaking-разминка",
                    "📈 Повысить уровень"
                ],
                "ready_to_build": False,
                "lesson_plan": None,
                "student_id": student["id"]
            }

    # ═════════════════════════════════════════════════════════════════════════
    # 1. EXPLICIT BUILD INTENT (Teacher confirmed creation)
    # ═════════════════════════════════════════════════════════════════════════
    if ctx["is_explicit_build"]:
        # If level is completely unknown, we must ask for it before drawing!
        if not has_level and not student:
            reply = (
                "🎯 **Почти всё готово!** Остался один важный момент:\n\n"
                "Под какой уровень языка делаем задания:\n"
                "• 🟢 **A1 (Starter / Elementary)** — простые базовые конструкции и визуальные опоры\n"
                "• 🟡 **A2 (Pre-Intermediate)** — распространенная лексика и базовые времена\n"
                "• 🔵 **B1 (Intermediate)** — свободная речь и более сложный контекст\n\n"
                "Выбери уровень кнопкой ниже, и я сразу перенесу блок на холст:"
            )
            return {
                "reply": reply,
                "suggested_replies": [
                    "🟢 Уровень A1",
                    "🟡 Уровень A2",
                    "🔵 Уровень B1"
                ],
                "ready_to_build": False,
                "lesson_plan": None
            }

        top_name = ctx["topic_ru"]
        top_en = ctx["topic_en"]

        if ctx.get("is_full_lesson") or any(k in msg_lower for k in ["урок", "целиком", "полный", "блум"]):
            btype = "bloom_lesson"
            type_title = "Комплексный урок"
        elif any(k in msg_lower for k in ["квиз", "quiz", "фото", "загадк", "викторин"]):
            btype = "quiz_photo"
            type_title = "Фото-квиз"
        elif any(k in msg_lower for k in ["карточ", "speaking", "говорен", "дилемм", "разминк"]):
            btype = "speaking_cards"
            type_title = "Speaking Cards"
        elif any(k in msg_lower for k in ["peekaboo", "открываш", "шторк", "тайн"]):
            btype = "flip_cards"
            type_title = "Peekaboo-открывашки"
        elif any(k in msg_lower for k in ["пропуск", "fill", "предложен", "вставит"]):
            btype = "fill_blanks"
            type_title = "Упражнение с пропусками"
        elif any(k in msg_lower for k in ["словар", "слов", "vocab", "таблиц"]):
            btype = "vocabulary_table"
            type_title = "Таблица словаря"
        else:
            btype = ctx.get("activity_type") or "quiz_photo"
            type_title = "Фото-квиз" if btype == "quiz_photo" else "Интерактивный блок"

        reply = (
            f"🚀 **Отлично, договорились!**\n\n"
            f"Сформировал {type_title} по теме «{top_name}» для {student_desc}.\n"
            f"Нажимай кнопку ниже, чтобы перенести его прямо на твою доску FigJam!"
        )
        lesson_plan = {
            "title": f"{type_title}: {top_name}",
            "topic": top_en,
            "level": target_level,
            "format": "game" if ctx["is_child"] else "conversational",
            "use_bloom_arc": True if btype == "bloom_lesson" else False,
            "blocks": ["speaking_cards", "vocabulary_table", "fill_blanks", "quiz_photo", "flip_cards"] if btype == "bloom_lesson" else [btype]
        }
        return {
            "reply": reply,
            "suggested_replies": [
                "🔄 Сменить тему",
                "➕ Добавить ещё задание",
                "📱 Главное меню"
            ],
            "ready_to_build": True,
            "lesson_plan": lesson_plan,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 1.5 FULL COMPREHENSIVE / DIAGNOSTIC LESSON REQUEST
    # ═════════════════════════════════════════════════════════════════════════
    if ctx.get("is_full_lesson") and not ctx.get("is_explicit_build"):
        lvl = ctx["level"] or (student.get("level") if student else "A1")
        dur = ctx.get("duration", 60)
        age = ctx.get("age")
        age_str = f"ребёнка {age} лет" if age else ("ребёнка" if ctx["is_child"] else "ученика")
        is_diag = ctx.get("is_diagnostic", False)

        diag_title = "Первое диагностическое пробное занятие" if is_diag else f"Полноценный комплексный урок ({dur} мин)"
        top_name = ctx["topic_ru"]
        top_en = ctx["topic_en"]

        reply = (
            f"🎓 **Отличная задача! {diag_title} для {age_str} ([{lvl}]).** 🌟\n\n"
            f"Для занятия на {dur} минут с 10-летним ребёнком важно **снять страх ошибки**, "
            f"мягко проверить все 4 навыка (Speaking, Vocabulary, Grammar, Reading) и удерживать интерес через частую смену интерактивов.\n\n"
            f"📐 **Сформировал методическую дугу по Таксономии Блума:**\n"
            f"1️⃣ **🗣️ Разминка-знакомство (7-10 мин)** — Speaking-карточки с картинками (*имя, возраст, питомцы, любимый цвет/игры*).\n"
            f"2️⃣ **📚 Иллюстрированный словарь (10-12 мин)** — Базовая визуальная лексика с транскрипцией и переводом (*like, have, play, pets, school*).\n"
            f"3️⃣ **✏️ Интерактив с пропусками (12-15 мин)** — Перетаскивание кнопок со словами мышкой на предложения.\n"
            f"4️⃣ **🎯 Игровой фото-квиз (12-15 мин)** — 10 вопросов с яркими фото и мгновенной проверкой ответов зелёным/красным цветом.\n"
            f"5️⃣ **🃏 Карточки Peekaboo / Открывашки (7-10 мин)** — Весёлая игра в конце со спрятанными ответами под шторкой.\n"
            f"📋 **Шпаргалка преподавателя** с поминутным таймингом будет прикреплена прямо под уроком.\n\n"
            f"💡 **Уточнение по теме перед созданием:**\n"
            f"Взять универсальную тему знакомства — **«All About Me & My World»** или сделать акцент на любимых персонажах ребёнка (например: *Minecraft, Roblox, котики, лего*)?"
        )

        lesson_plan = {
            "title": f"Комплексный урок: {top_name} ({lvl}, {dur} мин)",
            "topic": top_en,
            "level": lvl,
            "format": "game" if ctx["is_child"] else "conversational",
            "use_bloom_arc": True,
            "duration": dur,
            "is_child": ctx["is_child"],
            "blocks": ["speaking_cards", "vocabulary_table", "fill_blanks", "quiz_photo", "flip_cards"]
        }

        return {
            "reply": reply,
            "suggested_replies": [
                f"🚀 Рисуй урок «All About Me»",
                "🎮 Тема: Minecraft & Игры",
                "🐾 Тема: Животные и питомцы",
                "✍️ Свои пожелания"
            ],
            "ready_to_build": True,
            "lesson_plan": lesson_plan,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 2. TEACHER SELECTS OR SPECIFIES CEFR LEVEL (A1, A2, B1, B2, etc.)
    # ═════════════════════════════════════════════════════════════════════════
    m_direct_lvl = re.search(r"\b([a-cA-C][0-2])\b", msg_lower)
    if not ctx.get("is_full_lesson") and m_direct_lvl and any(k in msg_lower for k in ["уровень", "для", "делаем", "a0", "a1", "a2", "b1", "b2", "c1"]):
        chosen_lvl = m_direct_lvl.group(1).upper()
        b_type = ctx.get("activity_type") or "quiz_photo"
        type_title = "Фото-квиз" if b_type == "quiz_photo" else ("Speaking Cards" if b_type == "speaking_cards" else "Интерактивный блок")
        type_title_gen = "фото-квиза" if b_type == "quiz_photo" else ("карточек Speaking Cards" if b_type == "speaking_cards" else "интерактивного блока")
        top_name = ctx["topic_ru"]
        top_en = ctx["topic_en"]

        reply = (
            f"🎉 **Супер, зафиксировал уровень {chosen_lvl}!**\n\n"
            f"Теперь у нас есть всё необходимое для создания {type_title_gen} по теме «{top_name}» ([{chosen_lvl}]).\n\n"
            f"Перед созданием — **есть ли какие-то особые пожелания или нюансы к этому заданию?**\n"
            f"(Например: конкретные слова, которые нужно включить, любимые темы или запреты?)\n\n"
            f"Если всё отлично — нажимай кнопку ниже для генерации на холсте!"
        )
        lesson_plan = {
            "title": f"{type_title}: {top_name}",
            "topic": top_en,
            "level": chosen_lvl,
            "format": "game" if ctx["is_child"] else "conversational",
            "use_bloom_arc": False,
            "blocks": [b_type]
        }
        return {
            "reply": reply,
            "suggested_replies": [
                "🚀 Всё отлично, рисуй!",
                "✍️ Добавить пожелания",
                "📱 Главное меню"
            ],
            "ready_to_build": True,
            "lesson_plan": lesson_plan,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 3. STYLE & DETAIL SELECTION (With Mandatory Nuance/Comment Inquiry)
    # ═════════════════════════════════════════════════════════════════════════
    style_triggers = [
        ("фото-загадк", "quiz_photo", "Фото-квиз с загадками"),
        ("с юмором", "quiz_photo", "Квиз с юмором и мемами"),
        ("серьезная практик", "quiz_photo", "Практический квиз"),
        ("дилемм", "speaking_cards", "Speaking Cards с дилеммами"),
        ("свободная речь", "speaking_cards", "Speaking Cards для свободной речи"),
        ("шаблон", "speaking_cards", "Speaking Cards с опорными фразами"),
        ("загадки и ответ", "flip_cards", "Peekaboo-открывашки с загадками"),
        ("скрытый перевод", "flip_cards", "Peekaboo-открывашки со словами"),
        ("мемы", "flip_cards", "Peekaboo-открывашки с мемами"),
        ("предлоги и грамм", "fill_blanks", "Упражнение с пропусками на грамматику"),
        ("связки слов", "fill_blanks", "Упражнение со связками слов"),
        ("связной истор", "fill_blanks", "Интерактивная история с пропусками"),
        ("блиц на 3", "speaking_cards", "Блиц-разминка на 3 минуты"),
        ("вопрос с дилемм", "speaking_cards", "Разминка с дилеммой"),
        ("визуальная загадк", "quiz_photo", "Визуальная фото-загадка"),
        ("exit ticket", "speaking_cards", "Карточка Exit Ticket"),
        ("челлендж на 30", "speaking_cards", "30-секундный челлендж"),
        ("шкала уверенност", "speaking_cards", "Шкала уверенности"),
    ]

    for trigger, b_type, style_title in style_triggers:
        if trigger in msg_lower:
            top_name = ctx["topic_ru"]
            top_en = ctx["topic_en"]

            # If level is NOT known yet, ask for the level!
            if not has_level:
                reply = (
                    f"✨ **Договорились, сделаем {style_title}!**\n\n"
                    f"Уточни, пожалуйста, уровень твоего ученика:\n"
                    f"• 🟢 **A1 (Starter / Elementary)** — простые слова и наглядные фото-подсказки\n"
                    f"• 🟡 **A2 (Pre-Intermediate)** — базовая лексика и простые времена\n"
                    f"• 🔵 **B1 (Intermediate)** — свободная речь и развернутый контекст\n\n"
                    f"Выбери нужный уровень кнопкой:"
                )
                return {
                    "reply": reply,
                    "suggested_replies": [
                        "🟢 Уровень A1",
                        "🟡 Уровень A2",
                        "🔵 Уровень B1"
                    ],
                    "ready_to_build": False,
                    "lesson_plan": None,
                    "student_id": student["id"] if student else None
                }

            # Level is already known: ask for nuances and comments before final drawing!
            reply = (
                f"✨ **Договорились, отличный выбор!**\n\n"
                f"Зафиксировал: {style_title} по теме «{top_name}» для {student_desc}.\n\n"
                f"Перед тем как нарисуем блок на холсте — **есть ли какие-то особые пожелания или нюансы к этому заданию?**\n"
                f"(Например: конкретные слова, которые нужно включить, любимые персонажи, запретные темы или акцент на правиле?)\n\n"
                f"Если всё устраивает как есть — просто нажми кнопку ниже!"
            )
            lesson_plan = {
                "title": f"{style_title}: {top_name}",
                "topic": top_en,
                "level": target_level,
                "format": "game" if ctx["is_child"] else "conversational",
                "use_bloom_arc": False,
                "blocks": [b_type]
            }
            return {
                "reply": reply,
                "suggested_replies": [
                    "🚀 Всё отлично, рисуй!",
                    "✍️ Добавить пожелания",
                    "📱 Главное меню"
                ],
                "ready_to_build": True,
                "lesson_plan": lesson_plan,
                "student_id": student["id"] if student else None
            }

    # ═════════════════════════════════════════════════════════════════════════
    # 4. GRAMMAR & VOCABULARY INQUIRIES
    # ═════════════════════════════════════════════════════════════════════════
    if any(k in msg_lower for k in [
        "грамматик", "как объяснить", "past simple", "present perfect", "present simple",
        "времен", "правил", "ccq", "индуктив", "пассивный залог", "passive voice",
        "герундий", "модальн", "артикл", "предлог"
    ]):
        reply = (
            "💡 **Классный методический вопрос!**\n"
            "Вместо долгой теории по формулам лучше всего заходит индуктивный подход (Guided Discovery): "
            "сначала дать ученику наглядную ситуацию или картинку, а потом парой вопросов подтолкнуть его к тому, чтобы он сам вывел правило.\n\n"
            "А в каком виде ты хотел бы видеть это на доске в этой ситуации:\n"
            "• 🔍 **Наглядный квиз-детектив** с картинками, где нужно угадать форму?\n"
            "• ✏️ **Интерактивные предложения с пропусками** и банком слов для закрепления?\n"
            "• 🗣️ **Сразу вывод в речь** на карточках с забавными жизненными ситуациями?\n\n"
            "Что из этого сейчас нужнее твоему ученику?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "🔍 Квиз по картинкам",
                "✏️ Предложения с пропусками",
                "🗣️ Вывод в живую речь"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 5. STUDENT BARRIERS, EMOTIONS & PSYCHOLOGY
    # ═════════════════════════════════════════════════════════════════════════
    if any(k in msg_lower for k in [
        "зева", "не хочет говорить", "не говорит", "молчит", "стесняется", "боится",
        "барьер", "страх", "зажат", "скучно", "непоседа", "отвлекается", "не сидит",
        "теряет внимание", "быстро устает", "не слушает", "устал"
    ]):
        reply = (
            "Ох, как же я тебя понимаю! 🤝 С такими ситуациями сталкивается абсолютно каждый преподаватель.\n"
            "Тут главное — сбить градус тревожности и монотонности, убрав ощущение школьного опроса.\n\n"
            "В таких случаях безотказно работают простые приемы:\n"
            "• **Выбор из двух вместо открытого вопроса**: вместо широкого *«Tell me about...»* спросить *«Are you team Pizza or team Sushi?»* — выбрать из готового психологически в 10 раз легче!\n"
            "• **Быстрая смена механики**: переключить с разговора на наглядную угадайку или открывашку на 3 минуты.\n\n"
            "А что твоего ученика обычно оживляет в обычной жизни (игры, мемы, питомцы, YouTube)? "
            "И что из интерактивов ты хотел бы попробовать на доске в первую очередь?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "🎮 Тема игр и соцсетей",
                "🗣️ Вопросы-дилеммы без оценок",
                "🃏 Интерактив Peekaboo"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 6. SPECIFIC MECHANIC / ACTIVITY FORMAT CHOSEN BY TEACHER
    # ═════════════════════════════════════════════════════════════════════════

    # 6.1 Quiz format
    if any(k in msg_lower for k in ["создать квиз", "сделать квиз", "хочу квиз", "фото-квиз", "викторин", "квиз", "мини-квиз"]):
        if not has_level:
            reply = (
                "🎯 **Квиз с картинками — отличный выбор!** Ученики любого возраста обожают визуальный азарт.\n\n"
                "Подскажи пару деталей, чтобы задания получились в самый раз:\n"
                "1. 👤 **Для кого готовим:** назови имя постоянного ученика (например «для Маши») или укажи уровень (A1, A2, B1)?\n"
                "2. 🎨 **Какой стиль ближе:** фото-загадки с интригой, с легким юмором или на проверку правил?\n"
                "3. 🔢 **Сколько вопросов нужно:** быстрый блиц на 4–5 штук или большой блок на 8–10?\n\n"
                "Выбери ученика или уровень кнопками ниже:"
            )
            suggested = _get_student_or_level_chips()
        else:
            reply = (
                f"🎯 **Квиз с картинками для {student_desc} — отличный выбор!**\n\n"
                f"Подскажи, в каком стиле ты хочешь его сделать:\n"
                f"• С забавными фото-загадками и неожиданными вопросами?\n"
                f"• С легким соревновательным юмором и мемами?\n"
                f"• Или более академический на проверку контекста и грамматики?\n\n"
                f"И сколько вопросов тебе комфортнее: быстрый блиц на 4–5 штук или полноценный блок на 8–10?"
            )
            suggested = [
                "📸 Фото-загадки (4-5 шт.)",
                "😄 С юмором и мемами",
                "🎯 Серьезная практика (8-10 шт.)"
            ]

        return {
            "reply": reply,
            "suggested_replies": suggested,
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # 6.2 Speaking Cards
    if any(k in msg_lower for k in ["speaking", "карточки говорения", "разговорн", "разговорить", "говорени"]):
        if not has_level:
            reply = (
                "🗣️ **Разговорные карточки (Speaking Cards) — супер!** Они здорово снимают напряжение и включают живую речь.\n\n"
                "Уточни, пожалуйста, для кого готовим (имя ученика или уровень A1, A2, B1) и что сейчас важнее:\n"
                "• Чтобы ученик просто свободно выговорился на интересную тему (дилеммы «Что бы ты выбрал»)?\n"
                "• Или дать ему опору на готовые фразы-шаблоны (sentence starters)?\n\n"
                "Выбери ученика или уровень кнопками ниже:"
            )
            suggested = _get_student_or_level_chips()
        else:
            reply = (
                f"🗣️ **Разговорные карточки для {student_desc} — супер!**\n\n"
                f"А что тебе сейчас важнее в этой ситуации:\n"
                f"• Чтобы ученик просто свободно выговорился на интересную тему (дилеммы «Что бы ты выбрал», провокационные вопросы)?\n"
                f"• Или дать ему опору на готовые фразы-шаблоны (sentence starters), чтобы отработать конкретные речевые обороты?\n\n"
                f"Какое настроение задать для беседы?"
            )
            suggested = [
                "🗣️ Свободная речь и дилеммы",
                "🧩 С опорой на шаблоны фраз",
                "🎮 Веселая дискуссия про хобби"
            ]

        return {
            "reply": reply,
            "suggested_replies": suggested,
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # 6.3 Peekaboo
    if any(k in msg_lower for k in ["peekaboo", "открываш", "карточки-открывашки", "скрытый слой"]):
        reply = (
            "🃏 **О, открывашки Peekaboo — одна из самых залипательных механик на созвонах!** "
            "Элемент тайны моментально приковывает внимание к экрану.\n\n"
            "А какую интригу ты хочешь спрятать под шторками карточек:\n"
            "• Загадки, правильные ответы на которые открываются по клику?\n"
            "• Новые слова со скрытым контекстным переводом?\n"
            "• Или забавные картинки/мемы для вау-эффекта при проверке?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "🔍 Загадки и ответы",
                "📚 Слова со скрытым переводом",
                "🎭 Забавные картинки и мемы"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # 6.4 Fill in the blanks
    if any(k in msg_lower for k in ["пропуск", "fill blanks", "fill in", "вставить слова", "предложен"]):
        reply = (
            "✏️ **Интерактивные пропуски со словами — отличная контролируемая практика!** "
            "Кнопки со словами парят поверх предложений, и их очень удобно перетаскивать мышкой прямо в пропуски.\n\n"
            "Подскажи, на что делаем главный фокус:\n"
            "• На отработку грамматики (времена, предлоги места, артикли)?\n"
            "• На связки слов и устойчивые фразы (collocations)?\n\n"
            "И в каком виде лучше составить предложения — как отдельные жизненные примеры или как связную историю-детектив?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "🎯 Предлоги и грамматика",
                "📚 Связки слов (collocations)",
                "📖 В виде связной истории"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 7. LESSON STAGES (WARM-UP, COOLER, TRANSITIONS)
    # ═════════════════════════════════════════════════════════════════════════
    if any(k in msg_lower for k in ["начать урок", "начале урока", "старт урока", "warm-up", "warm up", "разминк", "lead-in", "icebreak"]):
        reply = (
            "🎯 **Первые 3–5 минут — самые важные!** Их цель — мягко включить английский тумблер в голове без грамматического стресса.\n\n"
            "Как ты хочешь начать в этой ситуации:\n"
            "• ⚡ Быстрый блиц-опрос или визуальная загадка на 3 минуты?\n"
            "• 🗣️ Личный вопрос с забавной дилеммой (*«Would you rather...»*)?\n"
            "• 🃏 Интерактивная открывашка Peekaboo со скрытой картинкой?\n\n"
            "И под какую тему подберем разогрев?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "⚡ Быстрый блиц на 3 мин",
                "🗣️ Вопрос с дилеммой",
                "📸 Визуальная загадка"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    if any(k in msg_lower for k in ["закончить урок", "конец урока", "завершить", "cooler", "wrap-up", "exit ticket", "итоги"]):
        reply = (
            "🏁 **Отличная мысль — подвести черту и зафиксировать прогресс!** "
            "Очень важно, чтобы ученик уходил с урока с ощущением *«Я сегодня реально научился новому»*.\n\n"
            "Что лучше подойдет для твоей ситуации:\n"
            "• 🎫 Быстрый Exit Ticket («назови 3 крутых слова, которые сегодня запомнились»)\n"
            "• ⏱️ Челлендж на 30 секунд составить фразу с новым словом\n"
            "• 🌟 Шкала уверенности (оценить от 1 до 5, насколько легко было говорить)\n\n"
            "Какой формат тебе ближе?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "🎫 Быстрый Exit Ticket",
                "⏱️ Челлендж на 30 секунд",
                "🌟 Шкала уверенности"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 8. EXPLICIT TOPIC DISCUSSED
    # ═════════════════════════════════════════════════════════════════════════
    if ctx["has_explicit_topic"] or any(k in msg_lower for k in ["тема:", "поговорить про", "урок про", "тему"]):
        top_name = ctx["topic_ru"]
        if not has_level:
            reply = (
                f"🎉 **О, тема «{top_name}» — отличный выбор!** Тут можно придумать массу классных активностей.\n\n"
                f"А что именно ты бы хотел видеть в этой ситуации на доске и **для кого готовим**:\n"
                f"• 📸 **Живой фото-квиз** с необычными ситуациями и вариантами.\n"
                f"• 🗣️ **Стопку Speaking Cards** с интересными вопросами для обсуждения.\n"
                f"• 🃏 **Интерактивные открывашки Peekaboo** со скрытыми тайнами.\n\n"
                f"Назови ученика (например «для Маши») или выбери вариант кнопкой ниже:"
            )
            suggested = _get_student_or_level_chips()
        else:
            reply = (
                f"🎉 **О, тема «{top_name}» для {student_desc} — отличный выбор!**\n\n"
                f"А что именно ты бы хотел видеть в этой ситуации на доске?\n"
                f"Можем подготовить:\n"
                f"• 📸 **Живой фото-квиз** с необычными ситуациями и выбором вариантов.\n"
                f"• 🗣️ **Стопку Speaking Cards** с интересными вопросами для обсуждения.\n"
                f"• 🃏 **Интерактивные открывашки Peekaboo** со скрытыми тайнами.\n"
                f"• ✏️ **Упражнение с пропусками** для отработки ключевой лексики.\n\n"
                f"Какой формат и настрой лучше всего подойдут твоему ученику?"
            )
            suggested = [
                "📸 Фото-квиз по теме",
                "🗣️ Карточки для говорения",
                "🃏 Открывашки Peekaboo"
            ]

        return {
            "reply": reply,
            "suggested_replies": suggested,
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 9. AGE GROUPS (KIDS, TEENS, ADULTS)
    # ═════════════════════════════════════════════════════════════════════════
    if any(k in msg_lower for k in ["дети", "детям", "ребенок", "ребёнок", "подрост", "взросл"]):
        is_adult = any(k in msg_lower for k in ["взросл", "adult"])
        if is_adult:
            reply = (
                "🧑 **С взрослыми учениками лучше всего работает немедленная практическая применимость!**\n"
                "Им скучно заучивать правила ради правил, но очень интересно выражать свое мнение, обсуждать реальные кейсы, работу и путешествия.\n\n"
                "Расскажи, какой формат ты хотел бы подготовить: что-то чисто разговорное (дискуссия), разбор жизненной ситуации или интерактивный квиз?"
            )
            suggested = [
                "🗣️ Разговорная дискуссия",
                "💼 Разбор ситуации из жизни",
                "🎯 Интерактивный квиз"
            ]
        else:
            reply = (
                "👶 **С юными учениками главное — динамика и игра!**\n"
                "Внимание рассеивается через 7–10 минут, поэтому круто чередовать активности и давать визуальные опоры (картинки, котики, игры, Minecraft, Roblox).\n\n"
                "Что планируешь для него на ближайший урок: веселую визуальную разминку, фото-квиз или интерактивные открывашки?"
            )
            suggested = [
                "🎮 Веселая разминка",
                "🎯 Фото-квиз с картинками",
                "🃏 Открывашки Peekaboo"
            ]

        return {
            "reply": reply,
            "suggested_replies": suggested,
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 10. HELP & CAPABILITIES
    # ═════════════════════════════════════════════════════════════════════════
    help_triggers = [
        "умеешь", "можешь", "что это", "помоги", "help", "как работаешь",
        "кто ты", "что ты", "расскажи о себе", "команды", "возможности"
    ]
    if any(k in msg_lower for k in help_triggers):
        reply = (
            "Привет! Я твой напарник-методист и ИИ-ассистент по доскам Figma / FigJam. 😊🎓\n\n"
            "С удовольствием помогу:\n"
            "• 🎯 **Интерактивные механики**: создаю на холсте квизы с самопроверкой, карточки Speaking с дилеммами, шторки-открывашки Peekaboo, таблицы слов и комплексные уроки на 60 мин по Блуму.\n"
            "• 👤 **Досье учеников**: помню уровень, возраст, интересы и фиксирую фидбек после уроков, чтобы калибровать сложность.\n"
            "• 📑 **Управление доской**: строю и обновляю авто-оглавление (TOC), ставлю штамп времени урока, переключаю доски.\n"
            "• 💬 **Живой диалог**: со мной можно просто обсудить ход урока, методику или посоветоваться по сложным моментам.\n\n"
            "Расскажи, с кем сейчас планируешь занятие или какую тему готовим?"
        )
        return {
            "reply": reply,
            "suggested_replies": [
                "👤 Выбрать ученика",
                "💡 Идея для разминки",
                "🎯 Подобрать квиз"
            ],
            "ready_to_build": False,
            "lesson_plan": None,
            "student_id": student["id"] if student else None
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 11. GENERAL CONVERSATIONAL FALLBACK (Polite, natural, never assuming a task)
    # ═════════════════════════════════════════════════════════════════════════
    has_edu_hint = any(k in msg_lower for k in [
        "урок", "тема", "задани", "слов", "грамматик", "правил", "level",
        "a1", "a2", "b1", "b2", "упражнен", "материал", "english", "английск"
    ])
    if has_edu_hint:
        reply = (
            "💡 **Отличная мысль для занятия!**\n\n"
            "Подскажи, для кого готовим материал — выберем постоянного ученика или настроим под определённый уровень (A1, A2, B1)?\n\n"
            "И какой формат на доске предпочтителен: фото-квиз, разговорные карточки Speaking или упражнение с пропусками?"
        )
        suggested = [
            "👤 Назвать ученика",
            "🎮 Быстрая игра / квиз",
            "🗣️ Разговорная практика"
        ]
    else:
        reply = (
            "Принято! 😊 Я на связи.\n\n"
            "Если захочешь превратить эту мысль в интерактивное задание на доске FigJam (квиз, карточки, шторки или разминку) — "
            "просто скажи формат или выбери ученика.\n\n"
            "А если мы просто беседуем или обсуждаем методику — продолжай, я слушаю!"
        )
        suggested = [
            "🎯 Создать задание",
            "👤 Выбрать ученика",
            "💡 Что ты умеешь?"
        ]
    return {
        "reply": reply,
        "suggested_replies": suggested,
        "ready_to_build": False,
        "lesson_plan": None,
        "student_id": student["id"] if student else None
    }
