"""
ESL Figma AI — Orchestrator Agent
Entry point for all block creation requests.
Validates input, routes to content + layout agents, returns status.
"""
import json
import logging
import re
from server import config, agent_logger, bridge
from server.agents import content_agent, layout_agent, ai_engine, vision_agent, student_agent, image_agent, toc_agent, bloom_taxonomy

logger = logging.getLogger("orchestrator")


BLOCK_TYPES = {
    "bloom_lesson":      "🌟 Урок по Таксономии Блума",
    "full_lesson":       "Комплексный урок целиком",
    "quiz_photo":        "Квиз с картинками",
    "flip_cards":        "Открывашки",
    "video_quiz":        "Квиз по видео",
    "vocabulary_table":  "Словарь с переводом",
    "flashcards":        "Карточки",
    "fill_blanks":       "Таблица с пропусками",
    "speaking_cards":    "Разминка / Speaking Cards",
}

DETECT_PROMPT = """You are an ESL teaching assistant dispatcher.
The user gave a command. Extract these parameters and return ONLY JSON:
{
  "block_type": "quiz_photo|flip_cards|video_quiz|vocabulary_table|flashcards|fill_blanks|speaking_cards|full_lesson",
  "topic": "extracted topic in English",
  "level": "A1|A2|B1|B2|C1 (null if not mentioned)",
  "count": number (default 10 for quizzes, 12 for cards),
  "youtube_url": "url if mentioned, else null",
  "student_name": "student name if mentioned (e.g. Вася, Аня), else null",
  "missing": ["level"] // list parameters that were NOT in the command and need clarification
}

Block type detection rules:
- "блум", "bloom", "таксономи", "блума", "bloom lesson", "по блуму" → bloom_lesson
- "полный урок", "полное занятие", "урок целиком", "full lesson", "занятие для", "урок для" → full_lesson
- "квиз", "quiz", "вопросы" → quiz_photo (default quiz type)
- "открывашки", "flip", "карточки с картинками" → flip_cards
- "видео", "youtube", "ютуб" → video_quiz
- "словарь", "слова", "vocabulary", "перевод" → vocabulary_table
- "карточки", "flashcards" → flashcards
- "пропуски", "fill", "gaps", "заполни" → fill_blanks
- "разминка", "warmup", "warm-up", "speaking", "говорение", "обсуждение" → speaking_cards
- Default if unclear → quiz_photo
"""


class OrchestratorError(Exception):
    pass


def _detect_image_mode(command: str) -> str:
    """
    Detect what image sourcing mode the user wants based on command text.

    User rule 1A: Search web images ONLY if explicitly requested in the prompt.
    Otherwise use AI generation ('generate') or smart default.

    Returns:
      'search'   — user explicitly asked to find/search photos on the web
      'generate' — AI generation (Pollinations stickers/illustrations)
    """
    if not command:
        return "generate"
    cmd = command.lower()

    # Keywords meaning: explicitly search the web for photos
    search_kw = [
        "найди фото", "найди картинк", "из интернета", "в интернете", "реальн фото", "реальн картинк",
        "настоящ фото", "скачай", "wikipedia", "wikimedia", "internet photo",
        "real photo", "actual photo", "найди изображен", "найди в сети"
    ]

    if any(k in cmd for k in search_kw):
        return "search"
    return "generate"


def _heuristic_detect_params(command: str) -> dict:
    """Fallback rule-based heuristic parameter extractor if AI engine is offline."""
    cmd_lower = (command or "").lower()

    # 1. Detect block type
    bt = "quiz_photo"
    if any(k in cmd_lower for k in ["блум", "bloom", "комплексный урок", "полный урок", "урок целиком", "собрать урок", "создать урок", "сделай урок", "подготовь урок", "выделенный урок", "урок"]):
        bt = "bloom_lesson"
    elif any(k in cmd_lower for k in ["speaking", "разминк", "говор", "дискусс"]):
        bt = "speaking_cards"
    elif any(k in cmd_lower for k in ["словар", "vocab", "слов"]):
        bt = "vocabulary_table"
    elif any(k in cmd_lower for k in ["пропуск", "fill", "встав"]):
        bt = "fill_blanks"
    elif any(k in cmd_lower for k in ["открываш", "peekaboo", "flip"]):
        bt = "flip_cards"
    elif any(k in cmd_lower for k in ["флешкарт", "flashcard", "карточк"]):
        bt = "flashcards"
    elif any(k in cmd_lower for k in ["видео", "youtube", "video"]):
        bt = "video_quiz"

    # 2. Detect level
    m_lvl = re.search(r"\b([a-c][0-2])\b", cmd_lower, re.IGNORECASE)
    level = m_lvl.group(1).upper() if m_lvl else "A2"

    # 3. Detect count
    m_cnt = re.search(r"\b(\d{1,2})\s*(?:вопрос|слов|карточ|штук|items|questions)?\b", cmd_lower)
    count = int(m_cnt.group(1)) if m_cnt and int(m_cnt.group(1)) > 0 else (12 if bt in ("flip_cards", "flashcards", "speaking_cards") else 10)

    # 4. Detect topic
    topic = "English"
    m_quote = re.search(r'[«"“]([^»"”]+)[»"”]', command)
    if m_quote:
        topic = m_quote.group(1).strip()
    elif ":" in command:
        topic = command.split(":", 1)[1].strip()
    elif "тема" in cmd_lower or "тему" in cmd_lower:
        m_top = re.search(r"тем[ауы][: ]+([a-zA-Zа-яА-ЯёЁ\s&]+)", command, re.IGNORECASE)
        if m_top:
            topic = m_top.group(1).strip()
    else:
        cleaned = re.sub(r"^(создай|нарисуй|сделай|урок|блок|квиз|разминка|speaking|комплексный урок)\s*", "", command, flags=re.IGNORECASE).strip()
        if cleaned:
            topic = cleaned

    return {
        "block_type": bt,
        "topic": topic.capitalize() if topic else "Daily Life & Routines",
        "level": level,
        "count": count
    }


async def _detect_params(command: str) -> dict:
    """Use fast heuristic routing first to save 450 tokens, falling back to AI engine only when ambiguous."""
    heuristic = _heuristic_detect_params(command)
    cmd_strip = (command or "").strip()

    # Fast path: if topic is explicitly extracted or command is direct/short (<= 12 words)
    has_specific_topic = heuristic.get("topic") and heuristic["topic"] not in ("English", "Daily Life & Routines")
    is_direct = len(cmd_strip.split()) <= 12

    if has_specific_topic or is_direct:
        logger.info(f"⚡ Fast-path heuristic detection used for: '{cmd_strip[:50]}' (0 tokens)")
        return heuristic

    if config.is_ai_ready() and ai_engine.is_antigravity_cli_authenticated():
        try:
            prompt = f'User command: "{command}"\nExtract the block creation parameters into JSON.'
            return await ai_engine.generate_json(prompt, system_instruction=DETECT_PROMPT)
        except Exception as e:
            logger.warning(f"AI engine failed during param detection ({e}), falling back to heuristics")
    return heuristic




def _detect_board_from_command(command: str) -> str | None:
    """Check if the command mentions a board name and return its board_id.
    
    Examples:
      "на доске репетиторство создай квиз" → "репетиторство" board_id
      "сделай на радуге таблицу" → "радуга" board_id
    Returns board_id string if found, else None.
    """
    if not command:
        return None

    boards = config.get("figma.boards", {})
    command_lower = command.lower()

    # Try matching each board by id, display_name, and aliases
    for board_id, info in boards.items():
        candidates = set()
        candidates.add(board_id.lower())
        candidates.add(info.get("display_name", "").lower())
        candidates.add(info.get("name", "").lower())
        for alias in info.get("aliases", []):
            candidates.add(alias.lower())
        candidates.discard("")  # remove empty strings

        for candidate in candidates:
            if len(candidate) < 3:
                continue  # skip too-short names to avoid false positives
            if candidate in command_lower:
                logger.info(f"🎯 Board detected in command: '{board_id}' (matched '{candidate}')")
                return board_id

    return None


async def generate_full_lesson(
    topic: str,
    level: str,
    student_id: str = None,
    blocks: list = None,
    lesson_format: str = "game",
    goal: str = "",
    command: str = "",
    replace_node_id: str = None
) -> dict:
    """Generate a multi-block interconnected full lesson package with Teacher Guide."""
    # Clean topic from trailing level tags like (A0) or [A0]
    topic_clean = re.sub(r"\s*[\(\[]([a-cA-C][0-2])[\)\]]\s*$", "", topic or "", flags=re.IGNORECASE).strip()
    topic = topic_clean if topic_clean else (topic or "English Lesson")

    # If student is not set, extract from conversation context
    student = student_agent.get_student(student_id) if student_id else None
    
    from server.agents import chat_agent
    hist = chat_agent.get_shared_history()
    full_ctx_str = (command + " " + " ".join(m.get("content", "") for m in hist)).lower()
    
    student_name = student.get("name", "Ученик") if student else "Ученик"
    student_age = student.get("age", "") if student else ""
    
    if not student_age:
        m_age = re.search(r"\b(\d{1,2})\s*(?:лет|года|yo|years?)\b", full_ctx_str)
        if m_age:
            student_age = int(m_age.group(1))
            if student_name == "Ученик":
                student_name = f"Ученик ({student_age} лет)"
        elif "ребенок" in full_ctx_str or "дети" in full_ctx_str:
            student_age = 10
            if student_name == "Ученик":
                student_name = "Ученик (10 лет)"

    if not level or level.upper() in ("A2", "A1"):
        if "a0" in full_ctx_str or "стартер" in full_ctx_str or "starter" in full_ctx_str:
            level = "A0"

    student_profile = {
        "id": student_id,
        "name": student_name,
        "age": int(student_age) if str(student_age).isdigit() else 14,
        "level": level,
        "interests": student.get("interests", []) if student else []
    }

    # Build pedagogical learning arc based on Bloom's Taxonomy
    bloom_arc = bloom_taxonomy.build_bloom_learning_arc(
        topic=topic,
        level=level,
        student_profile=student_profile,
        duration_minutes=45
    )
    bloom_summary = bloom_taxonomy.format_teacher_guide_bloom_section(bloom_arc)

    sub_blocks = []

    is_child = (int(student_age) <= 14 if str(student_age).isdigit() else False) or "ребенок" in full_ctx_str or "дети" in full_ctx_str

    # Extract custom quantities if specified by teacher in command or history
    m_quiz_count = re.search(r"(?:квиз\w*|вопрос\w*)\s*[:\-]?\s*(\d{1,2})", full_ctx_str)
    if not m_quiz_count:
        m_quiz_count = re.search(r"(\d{1,2})\s*(?:вопрос\w*|задани\w* в квиз\w*)", full_ctx_str)

    m_vocab_count = re.search(r"(?:словар\w*|слов\w*)\s*[:\-]?\s*(\d{1,2})", full_ctx_str)
    if not m_vocab_count:
        m_vocab_count = re.search(r"(\d{1,2})\s*(?:слов\w*)", full_ctx_str)

    m_fill_count = re.search(r"(?:пропуск\w*|предложен\w*)\s*[:\-]?\s*(\d{1,2})", full_ctx_str)
    if not m_fill_count:
        m_fill_count = re.search(r"(\d{1,2})\s*(?:предложен\w*|пропуск\w*)", full_ctx_str)

    m_cards_count = re.search(r"(?:карточ\w*|говорен\w*|speaking)\s*[:\-]?\s*(\d{1,2})", full_ctx_str)
    if not m_cards_count:
        m_cards_count = re.search(r"(\d{1,2})\s*(?:карточ\w*)", full_ctx_str)

    block_counts = {
        "quiz": int(m_quiz_count.group(1)) if m_quiz_count else 10,
        "vocab": int(m_vocab_count.group(1)) if m_vocab_count else 8,
        "fill": int(m_fill_count.group(1)) if m_fill_count else 10,
        "cards": int(m_cards_count.group(1)) if m_cards_count else 5,
    }

    # 1. Attempt High-Efficiency Unified Bloom Lesson Generation (1 single cohesive LLM call)
    unified_success = False
    teacher_guide_text = ""

    agent_logger.emit_log(
        stage="generating",
        icon="🧠",
        title="Таксономия Блума (Learning Arc)",
        message=f"Генерирую комплексный урок (Remember ➔ Apply ➔ Evaluate ➔ Create) для {student_name} ({level})..."
    )

    try:
        unified_lesson = await content_agent.generate_unified_bloom_lesson(
            topic=topic,
            level=level,
            student_profile=student_profile,
            bloom_arc=bloom_arc,
            counts=block_counts
        )
        if unified_lesson and isinstance(unified_lesson, dict):
            teacher_guide_text = unified_lesson.get("teacher_guide", "")
            action_map = {
                "speaking_cards": "DRAW_SPEAKING_CARDS",
                "vocabulary_table": "DRAW_VOCAB_TABLE",
                "quiz_photo": "DRAW_QUIZ_PHOTO",
                "fill_blanks": "DRAW_FILL_BLANKS",
                "flip_cards": "DRAW_FLIP_CARDS"
            }
            temp_blocks = []
            for stage in bloom_arc:
                b_type = stage["block_type"]
                b_level = stage["bloom_level"]
                b_badge = stage["badge_text"]
                b_color = stage["badge_color"]

                cnt = unified_lesson.get(b_type)
                if not cnt:
                    continue

                cnt["bloom_badge"] = b_badge
                cnt["bloom_color"] = b_color

                if b_type == "quiz_photo":
                    cnt["has_images"] = True
                    cnt["image_mode"] = "generate"
                    questions = cnt.get("questions", [])
                    queries = [q.get("image_query", q.get("question", q.get("sentence", ""))) for q in questions]
                    images_b64 = await image_agent.get_quiz_images(queries, topic=topic, is_child=is_child)
                    for q, img in zip(questions, images_b64):
                        q["image_base64"] = img
                    cnt["questions"] = questions
                elif b_type == "speaking_cards" and is_child:
                    cards = cnt.get("cards", [])
                    queries = [f"{c.get('question', '')} {topic}" for c in cards]
                    imgs = await image_agent.get_quiz_images(queries, topic=topic, is_child=True)
                    for c, img in zip(cards, imgs):
                        if img:
                            c["image_base64"] = img

                temp_blocks.append({
                    "action": action_map.get(b_type, f"DRAW_{b_type.upper()}"),
                    "data": cnt,
                    "bloom_badge": b_badge,
                    "bloom_color": b_color,
                    "bloom_level": b_level
                })

            if len(temp_blocks) >= 2:
                sub_blocks = temp_blocks
                unified_success = True
                logger.info(f"✅ Fast unified Bloom lesson successfully assembled ({len(sub_blocks)} sub-blocks, 1 LLM call)")
    except Exception as e:
        logger.warning(f"Unified Bloom generation failed ({e}), falling back to sequential stage generation: {e}")
        sub_blocks = []
        unified_success = False

    # 2. Sequential fallback if unified generation was not applicable or failed
    if not unified_success:
        guide_prompt = f"""Ученик: {student_name} ({student_age} лет, {level})
Интересы: {', '.join(student.get('interests', [])) if student else 'не указаны'}
Слабые стороны: {', '.join(student.get('weaknesses', [])) if student else 'не указаны'}
Тема: {topic}
Цель: {goal or 'Развитие коммуникативных навыков и закрепление лексики'}
Формат: {lesson_format}

МЕТОДИЧЕСКАЯ ТРАЕКТОРИЯ ПО БЛУМУ:
{bloom_summary}

Напиши КРАТКУЮ ШПАРГАЛКУ ПРЕПОДАВАТЕЛЯ (Teacher Cheat Sheet) для карточки в Figma.
СТРОГИЕ ТРЕБОВАНИЯ:
1. МАКСИМАЛЬНО КРАТКО, БЕЗ ВОДЫ! Только тезисы и конкретные действия (прочитать за 15 секунд).
2. СТРОГО БЕЗ РАЗМЕТКИ MARKDOWN! ЗАПРЕЩЕНЫ: **, ###, решетки, звездочки, таблицы с палочками |---|, кавычки `.
3. Используй только эмодзи и символ маркера '•' для списков.
4. Раздели строго на 4 коротких раздела:

🎯 ЭТАПЫ ПО БЛУМУ (Тайминг 25-35 мин)
• Разминка / Remember (5-7 мин): активировать ключевую лексику с опорой на визуал.
• Применение / Apply (8-10 мин): отработка в контекстных предложениях и диалогах.
• Анализ и Оценка / Evaluate (10-12 мин): дилемма, поиск ошибок, аргументация.
• Творчество / Create (5-8 мин): ролевой кейс или открытый мини-проект.

💡 МЕТОДИЧЕСКИЙ ФОКУС
• Опора на визуал: показывать карточки, избегать абстрактных правил.
• Реакция на ошибки: не перебивать, мягко повторять правильную форму (Echoing).
• Темп: поддерживать динамику и активное говорение ученика.

🗣️ СТАРТОВЫЙ АЙСБРЕЙКЕР
• Простая вводная реплика для легкого старта урока.

🏠 ДОМАШНЕЕ ЗАДАНИЕ
• 1 быстрое микро-задание на закрепление (1 строка).
"""
        try:
            teacher_guide_text = await ai_engine.generate(
                system_prompt="Ты — опытный методист ESL. Составь краткую тезисную шпаргалку для преподавателя. Строго без markdown-разметки (без звёздочек, решеток и таблиц). Только чистый текст с маркерами '•'.",
                prompt=guide_prompt,
                temperature=0.3
            )
        except Exception as e:
            logger.warning(f"Failed to generate teacher guide via AI: {e}")
            is_kid = (student_profile.get("age", 14) < 12) or "ребенок" in student_name.lower()
            teacher_guide_text = (
                f"🎯 ЭТАПЫ ЗАНЯТИЯ (Тайминг: 45 мин | Уровень: {level})\n"
                f"• 00–08 мин | Разминка и счет (Remember): активировать числа (10–100) и первичные предлоги с опорой на картинки.\n"
                f"• 08–18 мин | Отработка предлогов (Apply): поиск предметов в комнате (in, on, under, behind, next to).\n"
                f"• 18–30 мин | Описание людей и фото-квиз (Analyze): сопоставление номеров агентов, цвета глаз и роста (tall/short).\n"
                f"• 30–40 мин | Игровая миссия и речь (Create): детективная игра «Найди секретного агента» со спонтанным говорением.\n"
                f"• 40–45 мин | Рефлексия (Cooler): назвать 3 числа, 2 предлога и 1 слово внешности.\n\n"
                f"💡 МЕТОДИЧЕСКИЙ ФОКУС ({student_name}, {level})\n"
                f"• {'Частая смена микро-активностей каждые 7–10 минут для удержания концентрации.' if is_kid else 'Практическая направленность и максимум спонтанного говорения.'}\n"
                f"• Опора на наглядные визуальные карточки, минимизация абстрактных грамматических правил.\n"
                f"• Реакция на ошибки: не перебивать, использовать метод мягкого повторения (Echoing).\n\n"
                f"🗣️ СТАРТОВЫЙ АЙСБРЕЙКЕР\n"
                f"• «Hello! Look around your room: what is on your desk right now? Can you name 3 things in English?»\n\n"
                f"🏠 ДОМАШНЕЕ ЗАДАНИЕ\n"
                f"• Нарисовать свою комнату и спрятать в ней 3 секретных предмета с подписями на английском."
            )

        for stage in bloom_arc:
            b_type = stage["block_type"]
            b_level = stage["bloom_level"]
            b_instr = stage["content_prompt_instructions"]
            b_badge = stage["badge_text"]
            b_color = stage["badge_color"]
            try:
                if b_type == "speaking_cards":
                    c_num = block_counts.get("cards") or 5
                    cnt = await content_agent.generate_speaking_cards(
                        topic, level, c_num,
                        bloom_level=b_level,
                        bloom_instructions=b_instr
                    )
                    if is_child:
                        cards = cnt.get("cards", [])
                        queries = [f"{c.get('question', '')} {topic}" for c in cards]
                        imgs = await image_agent.get_quiz_images(queries, topic=topic, is_child=True)
                        for c, img in zip(cards, imgs):
                            if img:
                                c["image_base64"] = img
                    cnt["bloom_badge"] = b_badge
                    cnt["bloom_color"] = b_color
                    sub_blocks.append({
                        "action": "DRAW_SPEAKING_CARDS",
                        "data": cnt,
                        "bloom_badge": b_badge,
                        "bloom_color": b_color,
                        "bloom_level": b_level
                    })
                elif b_type == "vocabulary_table":
                    v_num = block_counts.get("vocab") or 8
                    cnt = await content_agent.generate_vocabulary_table(
                        topic, level, v_num,
                        bloom_level=b_level,
                        bloom_instructions=b_instr
                    )
                    cnt["bloom_badge"] = b_badge
                    cnt["bloom_color"] = b_color
                    sub_blocks.append({
                        "action": "DRAW_VOCAB_TABLE",
                        "data": cnt,
                        "bloom_badge": b_badge,
                        "bloom_color": b_color,
                        "bloom_level": b_level
                    })
                elif b_type == "quiz_photo":
                    q_num = max(int(block_counts.get("quiz") or 10), 10)
                    cnt = await content_agent.generate_quiz_photo(
                        topic, level, q_num,
                        bloom_level=b_level,
                        bloom_instructions=b_instr
                    )
                    cnt["has_images"] = True
                    cnt["image_mode"] = "generate"
                    cnt["bloom_badge"] = b_badge
                    cnt["bloom_color"] = b_color
                    questions = cnt.get("questions", [])
                    queries = [q.get("image_query", q.get("question", "")) for q in questions]
                    images_b64 = await image_agent.get_quiz_images(queries, topic=topic, is_child=is_child)
                    for q, img in zip(questions, images_b64):
                        q["image_base64"] = img
                    cnt["questions"] = questions
                    sub_blocks.append({
                        "action": "DRAW_QUIZ_PHOTO",
                        "data": cnt,
                        "bloom_badge": b_badge,
                        "bloom_color": b_color,
                        "bloom_level": b_level
                    })
                elif b_type == "flip_cards":
                    cnt = await content_agent.generate_flip_cards(topic, level, 6)
                    cnt["bloom_badge"] = b_badge
                    cnt["bloom_color"] = b_color
                    sub_blocks.append({
                        "action": "DRAW_FLIP_CARDS",
                        "data": cnt,
                        "bloom_badge": b_badge,
                        "bloom_color": b_color,
                        "bloom_level": b_level
                    })
                elif b_type == "fill_blanks":
                    f_num = max(int(block_counts.get("fill") or 10), 10)
                    cnt = await content_agent.generate_fill_blanks(
                        topic, level, f_num,
                        bloom_level=b_level,
                        bloom_instructions=b_instr
                    )
                    cnt["bloom_badge"] = b_badge
                    cnt["bloom_color"] = b_color
                    sub_blocks.append({
                        "action": "DRAW_FILL_BLANKS",
                        "data": cnt,
                        "bloom_badge": b_badge,
                        "bloom_color": b_color,
                        "bloom_level": b_level
                    })
            except Exception as err:
                logger.warning(f"Failed to generate Bloom sub-block {b_type} ({b_level}): {err}")

    # Ensure teacher guide text is never empty
    if not teacher_guide_text or not teacher_guide_text.strip():
        is_kid = (student_profile.get("age", 14) < 12) or "ребенок" in student_name.lower()
        teacher_guide_text = (
            f"🎯 ЭТАПЫ ЗАНЯТИЯ (Тайминг: 45 мин | Уровень: {level})\n"
            f"• 00–08 мин | Разминка и счет (Remember): активировать ключевую лексику с опорой на картинки.\n"
            f"• 08–18 мин | Отработка структур (Apply): контекстные предложения и практические задания.\n"
            f"• 18–30 мин | Анализ и оценка (Analyze): фото-квиз, выбор вариантов и поиск закономерностей.\n"
            f"• 30–40 мин | Игровая речь (Create): свободное говорение и обсуждение открытых вопросов.\n"
            f"• 40–45 мин | Рефлексия: подведение итогов и закрепление.\n\n"
            f"💡 МЕТОДИЧЕСКИЙ ФОКУС ({student_name}, {level})\n"
            f"• {'Частая смена микро-активностей каждые 7–10 минут для удержания концентрации.' if is_kid else 'Практическая направленность и максимум спонтанного говорения.'}\n"
            f"• Опора на наглядные визуальные карточки, минимизация абстрактных грамматических правил.\n"
            f"• Реакция на ошибки: не перебивать, использовать метод мягкого повторения (Echoing).\n\n"
            f"🗣️ СТАРТОВЫЙ АЙСБРЕЙКЕР\n"
            f"• «Hello! Let's start our lesson: how are you today and what interesting things happened?»\n\n"
            f"🏠 ДОМАШНЕЕ ЗАДАНИЕ\n"
            f"• Повторить изученные слова и составить 3 собственных предложения по теме «{topic}»."
        )

    # 3. Assemble full lesson package command
    lesson_cmd = {
        "action": "DRAW_FULL_LESSON",
        "topic": topic,
        "level": level,
        "student_name": student_name,
        "student_age": student_age,
        "teacher_guide": teacher_guide_text,
        "bloom_arc": bloom_arc,
        "sub_blocks": sub_blocks,
        "replaceNodeId": replace_node_id
    }

    agent_logger.emit_log(
        stage="drawing",
        icon="🎨",
        title="Отрисовка комплексного урока",
        message=f"Размещаю урок целиком в единой секции FigJam и прикрепляю методическую записку..."
    )

    # Execute drawESLFullLesson directly from latest code.js to guarantee updated layout
    try:
        from pathlib import Path
        code_js_path = Path(__file__).resolve().parent.parent.parent / "figma_plugin" / "code.js"
        if code_js_path.exists():
            code_content = code_js_path.read_text(encoding="utf-8")
            eval_payload = json.dumps(lesson_cmd, ensure_ascii=False)
            eval_script = f"""
{code_content}
return await drawESLFullLesson({eval_payload});
"""
            draw_result = await bridge.send_command("eval", {"code": eval_script})
            if draw_result.get("result"):
                draw_result = {**draw_result["result"], **draw_result}
        else:
            draw_result = await bridge.send_command("DRAW_FULL_LESSON", lesson_cmd)
    except Exception as e:
        logger.warning(f"Fallback to standard DRAW_FULL_LESSON: {e}")
        draw_result = await bridge.send_command("DRAW_FULL_LESSON", lesson_cmd)

    if not draw_result.get("ok", True) and not draw_result.get("success", False):
        err = draw_result.get("error", "Не удалось отрисовать урок в плагине")
        agent_logger.emit_log(
            stage="error",
            icon="❌",
            title="Ошибка отрисовки урока",
            message=err
        )
        return {
            "ok": False,
            "message": err,
            "draw_result": draw_result
        }

    agent_logger.emit_log(
        stage="done",
        icon="🎉",
        title="Комплексный урок готов!",
        message=f"Урок для {student_name} по теме «{topic}» ({len(sub_blocks)} блоков) успешно создан на доске!"
    )

    # 4. Register complete lesson in Table of Contents
    node_id = draw_result.get("nodeId") or draw_result.get("node_id")
    if node_id:
        try:
            await toc_agent.register_block("full_lesson", f"🌟 Урок: {topic} — {student_name}", node_id)
        except Exception as e:
            logger.warning(f"Could not register full lesson in TOC: {e}")

    # 5. Record completed lesson in student CRM
    if student:
        student_agent.record_lesson(student["id"], {
            "topic": topic,
            "goal": goal,
            "format": lesson_format,
            "blocks": blocks,
            "summary": f"Комплексный урок из {len(sub_blocks)} блоков по теме «{topic}» ({level})"
        })

    return {
        "ok": True,
        "success": True,
        "message": f"Комплексный урок «{topic}» для {student_name} успешно создан!",
        "topic": topic,
        "student_name": student_name,
        "teacher_guide": teacher_guide_text,
        "draw_result": draw_result
    }


async def process_command(
    command: str,
    block_type: str = None,
    topic: str = None,
    level: str = None,
    count: int = None,
    youtube_url: str = None,
    board_id: str = None,
    selection: dict = None,
    image_base64: str = None,
    images: list = None,
    student_id: str = None,
    student_name: str = None,
    lesson_plan: dict = None,
    blocks: list = None,
    lesson_format: str = None,
    goal: str = None,
) -> dict:
    """
    Main entry point. Accepts either:
    - A natural language command (parsed automatically)
    - Explicit params (block_type, topic, level, count)
    Returns a result dict with ok, message, and optional clarification prompt.
    """
    logger.info(f"process_command: '{command}' bt={block_type} topic={topic} level={level} sel={selection} has_img={bool(image_base64)} imgs_cnt={len(images) if images else 0}")

    if block_type in ("auto", "undefined", "none", "None", ""):
        block_type = None

    if lesson_plan and isinstance(lesson_plan, dict):
        if not topic: topic = lesson_plan.get("topic") or lesson_plan.get("title")
        if not level: level = lesson_plan.get("level")
        if not blocks: blocks = lesson_plan.get("blocks")
        if not lesson_format: lesson_format = lesson_plan.get("format")
        if not goal: goal = lesson_plan.get("goal")
        if not student_id: student_id = lesson_plan.get("student_id")
        if not student_name: student_name = lesson_plan.get("student_name")
        if not images and lesson_plan.get("staged_photos"):
            images = lesson_plan.get("staged_photos")

    # ── 0. Vision Agent: Batch Images or Canvas Image ──────────────────
    vision_context = None
    if images and isinstance(images, list) and len(images) > 0:
        try:
            vision_context = await vision_agent.analyze_batch_images(
                images=images,
                command=command or "",
                level=level or "A2"
            )
            if vision_context:
                if not topic and vision_context.get("topic"):
                    topic = vision_context["topic"]
                if not block_type and vision_context.get("recommended_block_type"):
                    block_type = vision_context["recommended_block_type"]
        except Exception as e:
            logger.error(f"Batch vision agent analysis failed in orchestrator: {e}", exc_info=True)
    elif image_base64:
        try:
            vision_context = await vision_agent.analyze_image(
                image_base64=image_base64,
                command=command or "",
                level=level or "A2"
            )
            if vision_context:
                if not topic and vision_context.get("topic"):
                    topic = vision_context["topic"]
                if not block_type and vision_context.get("recommended_block_type"):
                    block_type = vision_context["recommended_block_type"]
        except Exception as e:
            logger.error(f"Vision agent analysis failed in orchestrator: {e}", exc_info=True)

    # ── 0. Selection Scope ─────────────────────────────────────────────────
    if selection and selection.get("count", 0) > 0:
        sel_name = selection.get("name") or "Выделенный элемент"
        sel_type = selection.get("type") or ""
        agent_logger.emit_log(
            stage="analyzing",
            icon="🎯",
            title="Область применения",
            message=f"Запрос применяется к выделенному: «{sel_name}»" + (" (с анализом изображения 👁️)" if image_base64 else ""),
            detail=f"Тип: {sel_type} | ID: {selection.get('id')}"
        )
        if command and sel_name.lower() not in command.lower():
            command = f"{command} (для выделенного объекта «{sel_name}»)"
    else:
        agent_logger.emit_log(
            stage="analyzing",
            icon="🌐",
            title="Область применения",
            message="Вся доска (создание нового блока на свободном месте)" + (" (по выделенной картинке 👁️)" if image_base64 else "")
        )

    # ── 1. Board switching from command text ────────────────────────────────
    detected_board = _detect_board_from_command(command)
    if detected_board and detected_board != config.active_board():
        config.set_value("figma.active_board", detected_board)
        board_name = config.get(f"figma.boards.{detected_board}.display_name",
                                config.get(f"figma.boards.{detected_board}.name", detected_board))
        logger.info(f"🎯 Switched active board to: {detected_board} ({board_name})")

    if board_id and board_id != config.active_board():
        boards = config.get("figma.boards", {})
        if board_id in boards:
            config.set_value("figma.active_board", board_id)

    # --- Step 1: Parse parameters ---
    needs_clarification = []

    agent_logger.emit_log(
        stage="analyzing",
        icon="🔍",
        title="Анализ запроса",
        message=f"Получена задача: «{command or topic}»",
        detail=f"Уровень: {level or 'автоопределение'}"
    )

    if block_type and topic and level:
        # Came from the structured form — use as-is
        params = {
            "block_type": block_type,
            "topic": topic,
            "level": level,
            "count": count or 10,
            "youtube_url": youtube_url,
            "missing": [],
            "student_id": student_id,
            "student_name": student_name,
            "blocks": blocks,
            "format": lesson_format or "game",
            "goal": goal or "",
        }
    else:
        # Natural language command — use AI to parse
        try:
            agent_logger.emit_log(
                stage="analyzing",
                icon="🧠",
                title="Распознавание параметров",
                message="Определяю тип учебного блока, тему и уровень языка..."
            )
            params = await _detect_params(command)
            # Merge explicit overrides
            if block_type: params["block_type"] = block_type
            if topic: params["topic"] = topic
            if level: params["level"] = level
            if count: params["count"] = count
            if youtube_url: params["youtube_url"] = youtube_url
            if student_id: params["student_id"] = student_id
            if student_name: params["student_name"] = student_name
            if blocks: params["blocks"] = blocks
            if lesson_format: params["format"] = lesson_format
            if goal: params["goal"] = goal
            if vision_context and vision_context.get("topic"):
                generic_topics = {"picture", "photo", "image", "картинка", "фото", "изображение", "рисунок", "с картинками", "картинки"}
                current_top = (params.get("topic") or "").lower().strip()
                if not current_top or current_top in generic_topics:
                    params["topic"] = vision_context["topic"]
            if vision_context and vision_context.get("recommended_block_type"):
                if not block_type or params.get("block_type") in ("unknown", None):
                    params["block_type"] = vision_context["recommended_block_type"]
        except Exception as e:
            err_str = str(e)
            agent_logger.emit_log(
                stage="error",
                icon="❌",
                title="Ошибка разбора команды",
                message=err_str,
            )
            return {"ok": False, "message": f"Failed to parse command: {e}"}

    if selection and selection.get("count", 0) > 0:
        sel_name = selection.get("name", "")
        if "УРОК:" in sel_name:
            m_top = re.search(r"УРОК:\s*([^\—\-]+)", sel_name)
            if m_top and (params.get("topic") in ("English", "Daily Life & Routines", None, "")):
                params["topic"] = m_top.group(1).strip()
            m_stud = re.search(r"[—\-]\s*([^\(]+)", sel_name)
            if m_stud and not params.get("student_name"):
                params["student_name"] = m_stud.group(1).strip()
            if any(k in (command or "").lower() for k in ["урок", "переделай", "откорректируй", "обнови", "исправь"]):
                params["block_type"] = "bloom_lesson"
            if not params.get("level"):
                params["level"] = "A1"

    missing = params.get("missing", [])
    if "level" in missing and not params.get("level"):
        needs_clarification.append("level")

    # Return clarification request if needed
    if needs_clarification:
        msg = f"Уточни уровень языка (A1 / A2 / B1 / B2 / C1) для темы «{params.get('topic', '?')}»"
        agent_logger.emit_log(
            stage="warning",
            icon="❓",
            title="Требуется уточнение",
            message=msg
        )
        return {
            "ok": False,
            "needs_clarification": True,
            "missing": needs_clarification,
            "params": params,
            "message": msg,
        }

    # ── Check for in-place image update on selected block ──
    is_image_update = selection and selection.get("count", 0) > 0 and any(
        k in command.lower() for k in ["замени фото", "заменить фото", "поменяй фото", "поменяй картинки", "замени картинки", "сгенерируй картинки", "сгенерируй вместо", "новые фото", "новые картинки", "pinterest"]
    )
    if is_image_update:
        sel_id = selection.get("id")
        logger.info(f"Detected image update intent for selected node: {sel_id}")
        img_mode = "generate" if "сгенерируй" in command.lower() else "pinterest"
        queries = [f"{params.get('topic', 'English')} {i}" for i in range(1, 11)]
        b64_imgs = await image_agent.get_quiz_images(queries, topic=params.get("topic", "English"), image_mode=img_mode)
        update_res = await bridge.send_command("UPDATE_BLOCK_IMAGES", {
            "nodeId": sel_id,
            "images": b64_imgs
        })
        return {
            "ok": True,
            "success": True,
            "message": f"Изображения в выделенном блоке успешно обновлены ({img_mode})!",
            "updatedCount": update_res.get("updatedCount", 0)
        }

    bt = params.get("block_type", "quiz_photo")
    tp = params.get("topic", "English")
    lv = params.get("level", "A2")
    default_cnt = 12 if bt in ("flip_cards", "flashcards", "speaking_cards") else 10
    cnt = int(params.get("count") or default_cnt)
    if bt == "quiz_photo":
        cnt = max(cnt, 10)  # User rule: Quizzes must have at least 10 questions!
    yt = params.get("youtube_url")

    replace_node_id = selection.get("id") if (selection and any(k in command.lower() for k in ["замени", "поменяй", "обнови", "переделай", "откорректируй", "исправь", "скорректируй"])) else None

    bt_name = BLOCK_TYPES.get(bt, bt)
    logger.info(f"Dispatching: type={bt}, topic={tp}, level={lv}, count={cnt}")
    agent_logger.emit_log(
        stage="thinking",
        icon="📋",
        title="План создания",
        message=f"Тип: «{bt_name}» | Уровень: {lv} | Тема: «{tp}» | Элементов: {cnt}"
    )

    if bt in ("full_lesson", "bloom_lesson"):
        return await generate_full_lesson(
            topic=tp,
            level=lv,
            student_id=params.get("student_id") or params.get("student_name") or student_id or student_name,
            blocks=params.get("blocks") or blocks,
            lesson_format=params.get("format") or lesson_format or "game",
            goal=params.get("goal") or goal or "",
            command=command,
            replace_node_id=replace_node_id
        )

    # --- Step 2: Generate content ---
    agent_logger.emit_log(
        stage="generating",
        icon="📝",
        title="Генерация учебного контента",
        message=f"Составляю вопросы, лексику и отвлекающие варианты по стандарту CEFR {lv}..."
    )
    try:
        if bt == "quiz_photo":
            # Images are ON by default — only disable if user explicitly says so
            no_images = any(k in (command or "").lower() for k in [
                "без картинок", "без фото", "без иллюстраций", "без изображений",
                "no image", "no photo", "text only", "только текст"
            ])
            wants_images = not no_images  # DEFAULT = True (always include images)
            cnt = max(int(cnt or 10), 10)
            content = await content_agent.generate_quiz_photo(tp, lv, cnt, vision_context=vision_context)
            content["has_images"] = wants_images
            content["image_mode"] = _detect_image_mode(command)
            if vision_context and vision_context.get("image_base64"):
                content["canvas_image_base64"] = vision_context["image_base64"]
        elif bt == "flip_cards":
            content = await content_agent.generate_flip_cards(tp, lv, cnt, vision_context=vision_context)
            if vision_context and vision_context.get("image_base64"):
                content["canvas_image_base64"] = vision_context["image_base64"]
        elif bt == "video_quiz":
            if not yt:
                return {"ok": False, "message": "Для квиза по видео нужна ссылка на YouTube."}
            content = await content_agent.generate_video_quiz(yt, tp, lv, cnt)
        elif bt == "vocabulary_table":
            content = await content_agent.generate_vocabulary_table(tp, lv, cnt, vision_context=vision_context)
            content["image_mode"] = _detect_image_mode(command)
        elif bt == "flashcards":
            content = await content_agent.generate_flashcards(tp, lv, cnt)
        elif bt == "fill_blanks":
            cnt = max(int(cnt or 10), 10)
            content = await content_agent.generate_fill_blanks(tp, lv, cnt, vision_context=vision_context)
        elif bt == "speaking_cards":
            content = await content_agent.generate_speaking_cards(tp, lv, cnt, vision_context=vision_context)
        else:
            return {"ok": False, "message": f"Unknown block type: {bt}"}

        # If batch images were provided (from Telegram upload or canvas selection),
        # distribute images to questions, cards, or vocabulary rows
        if images and isinstance(images, list) and len(images) > 0 and isinstance(content, dict):
            content["has_images"] = True
            items = content.get("questions") or content.get("cards") or content.get("rows") or []
            for idx, item in enumerate(items):
                if isinstance(item, dict) and not item.get("image_base64"):
                    src_img = images[idx % len(images)]
                    item["image_base64"] = src_img.get("image_base64")
                    if not item.get("image_query"):
                        item["image_query"] = src_img.get("name") or f"photo_{idx+1}"
    except Exception as e:
        err_msg = str(e)
        logger.error(f"Content generation error: {e}", exc_info=True)
        if "503" in err_msg or "No capacity available" in err_msg:
            agent_logger.emit_log(
                stage="error",
                icon="⚠️",
                title="Сервер Google перегружен (503)",
                message="Сервер модели временно перегружен. Попробуйте еще раз через несколько секунд или переключите модель.",
                detail=err_msg
            )
        elif "Eligibility" in err_msg or "location" in err_msg:
            agent_logger.emit_log(
                stage="error",
                icon="📍",
                title="Ограничение по локации",
                message="Регион заблокирован сервисом. Включите в VPN узел США/Великобритания или укажите Gemini API Key в Настройках.",
                detail=err_msg
            )
        else:
            agent_logger.emit_log(
                stage="error",
                icon="❌",
                title="Ошибка генерации",
                message=err_msg,
            )
        return {"ok": False, "message": f"Content generation failed: {e}"}

    # --- Step 3: Draw on Figma board ---
    if replace_node_id:
        content["replaceNodeId"] = replace_node_id
        logger.info(f"Setting replaceNodeId on content: {replace_node_id}")

    agent_logger.emit_log(
        stage="drawing",
        icon="🎨",
        title="Отрисовка в FigJam",
        message="Формирую подложку, раскладываю карточки и передаю команды в плагин..."
    )
    try:
        if bt == "quiz_photo":
            draw_result = await layout_agent.draw_quiz_photo(content)
        elif bt == "flip_cards":
            draw_result = await layout_agent.draw_flip_cards(content)
        elif bt == "video_quiz":
            draw_result = await layout_agent.draw_video_quiz(content)
        elif bt == "vocabulary_table":
            draw_result = await layout_agent.draw_vocabulary_table(content)
        elif bt == "flashcards":
            draw_result = await layout_agent.draw_flashcards(content)
        elif bt == "fill_blanks":
            draw_result = await layout_agent.draw_fill_blanks(content)
        elif bt == "speaking_cards":
            draw_result = await layout_agent.draw_speaking_cards(content)
    except Exception as e:
        logger.error(f"Layout/draw error: {e}", exc_info=True)
        agent_logger.emit_log(
            stage="error",
            icon="❌",
            title="Ошибка отрисовки",
            message=str(e),
        )
        return {"ok": False, "message": f"Drawing failed: {e}"}

    if not draw_result.get("ok"):
        err = draw_result.get("error", "Unknown draw error")
        agent_logger.emit_log(
            stage="error",
            icon="❌",
            title="Ошибка плагина",
            message=err,
        )
        return {
            "ok": False,
            "message": err,
        }

    title = content.get("title", tp)
    agent_logger.emit_log(
        stage="done",
        icon="✅",
        title="Задание готово!",
        message=f"Блок «{title}» ({bt_name}) успешно создан на доске и добавлен в оглавление!"
    )
    return {
        "ok": True,
        "message": f"✅ Блок «{title}» создан и добавлен в оглавление!",
        "nodeId": draw_result.get("nodeId"),
        "title": title,
        "block_type": bt,
        "level": lv,
    }
