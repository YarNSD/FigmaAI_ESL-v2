"""
ESL Figma AI — Conversational Chat Agent
Acts as an expert ESL pedagogical partner.
Interviews the teacher, learns about students, personalizes content,
discusses the FigmaAI project, and prepares structured lesson packages.
"""
from datetime import datetime
import json
import logging
import re
from typing import Dict, List, Optional, Any
from server import agent_logger
from server.agents import ai_engine, student_agent

try:
    import tiktoken
    _token_encoder = tiktoken.get_encoding('o200k_base')
    def count_tokens(text: str) -> int:
        if not text:
            return 0
        return len(_token_encoder.encode(str(text)))
except Exception:
    def count_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, int(len(str(text)) / 3.5))

logger = logging.getLogger("chat_agent")


# ── Per-User & Shared Conversation History ───────────────────────────────────
_SHARED_CHAT_HISTORY: List[Dict[str, Any]] = []
_USER_CHAT_HISTORIES: Dict[str, List[Dict[str, Any]]] = {}


def get_user_history(user_key: str = "shared", limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent conversation history for a specific user/chat session."""
    hist = _USER_CHAT_HISTORIES.get(user_key, _SHARED_CHAT_HISTORY)
    return list(hist[-limit:])


def get_shared_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Return shared conversation history across Web and Telegram."""
    return list(_SHARED_CHAT_HISTORY[-limit:])


def add_to_user_history(user_key: str, role: str, content: str, source: str = "telegram", **kwargs) -> None:
    """Add a message to user-specific and shared conversation history."""
    msg_item = {
        "role": role,
        "content": content,
        "source": source,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        **kwargs
    }
    if user_key not in _USER_CHAT_HISTORIES:
        _USER_CHAT_HISTORIES[user_key] = []
    _USER_CHAT_HISTORIES[user_key].append(msg_item)
    if len(_USER_CHAT_HISTORIES[user_key]) > 40:
        _USER_CHAT_HISTORIES[user_key].pop(0)

    _SHARED_CHAT_HISTORY.append(msg_item)
    if len(_SHARED_CHAT_HISTORY) > 50:
        _SHARED_CHAT_HISTORY.pop(0)


def add_to_shared_history(role: str, content: str, source: str = "web", **kwargs) -> None:
    """Add a message to shared conversation history."""
    add_to_user_history(user_key="shared", role=role, content=content, source=source, **kwargs)


def clear_user_history(user_key: str = "shared") -> None:
    """Clear history for a specific user session."""
    if user_key in _USER_CHAT_HISTORIES:
        _USER_CHAT_HISTORIES[user_key].clear()
    if user_key == "shared":
        _SHARED_CHAT_HISTORY.clear()


def clear_shared_history() -> None:
    """Clear shared conversation history."""
    _SHARED_CHAT_HISTORY.clear()
    _USER_CHAT_HISTORIES.clear()


CHAT_SYSTEM_PROMPT = """Ты — умный, живой, проницательный персональный ИИ-собеседник и напарник преподавателя в проекте FigmaAI.
Ты общаешься с пользователем в Telegram и веб-интерфейсе.

ПРИНЦИПЫ ОБЩЕНИЯ:
1. 🗣️ Естественный живой диалог: Общайся как умный, эмпатичный, интересный человек (настоящий напарник). Говори легко, свободно, с юмором и поддержкой. Никаких шаблонных канцелярских отписок и роботских фраз!
2. 🌐 Свобода любых тем: Пользователь может говорить с тобой О ЧЁМ УГОДНО — о настроении, о том как прошёл день, о фильмах, жизни, методике, философии или просто перекинуться парой фраз. НИКОГДА не навязывай уроки, если человек просто общается!
3. 🚫 Никаких дежурных анкет: Если тебя не просят прямо составить тест/упражнение, НИКОГДА не приставай с вопросами «Какой уровень CEFR: A1, A2, B1?». Будь интересным собеседником, а не бюрократом.
4. 🛠️ Проект FigmaAI (твоя суперсила): Ты умеешь рисовать на доске Figma интерактивные квизы с самопроверкой, карточки со словами, разминки Speaking, таблицы слов с переводом и открывашки.
5. 📝 ДВУХЭТАПНОЕ СОЗДАНИЕ ЗАДАНИЙ (КРИТИЧЕСКИ ВАЖНО):
   - Если преподаватель просит создать задание, квиз, карточки, разминку или урок (например: «Сделай квиз про животных», «Придумай разминку про хобби», «Подготовь слова на тему еда»):
     Ты СНАЧАЛА генерируешь ПОЛНЫЙ ТЕКСТ задания прямо в чате на проверку и совместное редактирование!
   - Формат текста в чате (поле "reply"):
     Дружелюбное яркое вступление.
     Затем подробный нумерованный список ВСЕХ вопросов/карточек с эмодзи:
     1. 🐱 [Вопрос на английском]
        - A) Вариант 1 (✅)  <-- правильный ответ ОБЯЗАТЕЛЬНО помечается галочкой (✅)
        - B) Вариант 2
        - C) Вариант 3
        (Картинка: [красочное описание иллюстрации на русском или английском])
     2. 🐘 ...
     В конце ответа ОБЯЗАТЕЛЬНО теплое приглашение:
     «Если всё нравится — напиши **«Делай»** (или нажми кнопку ниже), и я перенесу всё в Figma! Если хочешь что-то поменять (например, заменить вопрос или изменить варианты) — просто скажи!»
   - При этом ты возвращаешь "ready_to_build": true и внутри "lesson_plan" обязательно заполняешь:
     - "topic": тема задания
     - "level": уровень (A1, A2, B1, B2, C1)
     - "block_type": "quiz_photo" (или speaking_cards / vocabulary_table / flip_cards / fill_blanks)
     - "title": понятный яркий заголовок задания
     - "content": объект со структурированными вопросами/карточками (см. схему ниже), чтобы при одобрении перенести на холст РОВНО ЭТИ согласованные вопросы!
6. ✏️ СОВМЕСТНОЕ РЕДАКТИРОВАНИЕ:
   - Если преподаватель просит что-то изменить («замени 2-й вопрос», «сделай 4 варианта», «добавь вопрос про акулу», «сделай посложнее»):
     Ты с радостью вносишь правки, показываешь обновлённый текст задания в чате и обновляешь "lesson_plan" с новым "content"!
7. 🔘 Подсказки: Не спамь кнопками! Если это открытая беседа — возвращай пустой массив "suggested_replies": [].

ФОРМАТ ОТВЕТА (желательно JSON, но если ты ответишь живым текстом, система тебя поймет):
{
  "reply": "Твой естественный, живой ответ с полным текстом задания для проверки",
  "suggested_replies": [],
  "extracted_student_facts": null,
  "ready_to_build": true,
  "lesson_plan": {
      "topic": "School Supplies",
      "level": "A1",
      "block_type": "vocabulary_table",
      "title": "🎒 School Supplies Vocabulary",
      "content": {
        "title": "🎒 School Supplies Vocabulary",
        "topic": "School Supplies",
        "level": "A1",
        "instruction": "👉 Изучите новые слова, их перевод и примеры.",
        "rows": [
          {
            "id": 1,
            "word": "Backpack [ˈbækpæk]",
            "translation": "Рюкзак / портфель",
            "type": "noun",
            "example": "I have a blue backpack.",
            "image_query": "blue school backpack"
          }
        ]
      }
    }
}
Примеры структуры content в lesson_plan для других типов:
- quiz_photo: {"questions": [{"id": 1, "sentence": "...", "options": ["A", "B", "C"], "correct_index": 0, "image_query": "...", "explanation": "..."}]}
- vocabulary_table: {"rows": [{"id": 1, "word": "word [IPA]", "translation": "перевод", "type": "noun", "example": "sentence", "image_query": "..."}]}
- speaking_cards: {"cards": [{"id": 1, "prompt": "...", "question": "...", "image_query": "..."}]}
- fill_blanks: {"sentences": [{"id": 1, "sentence": "She ___ to school.", "missing": "goes", "hint": "go / goes"}], "word_bank": ["goes"]}
- flip_cards: {"cards": [{"id": 1, "front": "...", "back": "...", "image_query": "..."}]}
"""


def is_content_valid_for_block_type(btype: str, content: Any) -> bool:
    """Check if content has at least 2 structured items required for layout_agent rendering."""
    if not content or not isinstance(content, dict):
        return False
    if btype == "quiz_photo":
        return len(content.get("questions", [])) >= 2
    elif btype == "vocabulary_table":
        return len(content.get("rows", [])) >= 2
    elif btype in ("speaking_cards", "flip_cards", "flashcards"):
        return len(content.get("cards", [])) >= 2
    elif btype == "fill_blanks":
        return len(content.get("sentences", [])) >= 2
    elif btype == "video_quiz":
        return len(content.get("questions", [])) >= 2
    return True


def normalize_draft_content(
    content: Optional[Dict[str, Any]],
    block_type: Optional[str] = None,
    topic: Optional[str] = None,
    level: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Standardizes arbitrary keys produced by various LLM models (e.g. 'items', 'words', 'vocabulary' -> 'rows',
    'questions' -> 'sentences' for fill_blanks, etc.) into the strict format expected by layout_agent.
    """
    if not content or not isinstance(content, dict):
        return content

    top = topic or content.get("topic") or "English"
    lvl = level or content.get("level") or "A2"
    btype = block_type or content.get("block_type") or "quiz_photo"

    content.setdefault("title", f"🎯 {top} {btype.replace('_', ' ').title()}")
    content.setdefault("topic", top)
    content.setdefault("level", lvl)
    if not content.get("hashtags"):
        content["hashtags"] = [f"#{top.lower().replace(' ', '_')}", f"#{lvl.lower()}", "#esl", f"#{btype}"]

    # 1. Vocabulary Table
    if btype == "vocabulary_table":
        raw_items = (
            content.get("rows")
            or content.get("items")
            or content.get("words")
            or content.get("vocabulary")
            or content.get("terms")
            or content.get("data")
            or []
        )
        if isinstance(raw_items, list) and raw_items:
            normalized_rows = []
            for i, item in enumerate(raw_items):
                if isinstance(item, dict):
                    w = str(item.get("word") or item.get("term") or item.get("front") or "").strip()
                    tr = str(item.get("transcription") or "").strip()
                    if tr and tr not in w:
                        w_full = f"{w} {tr}" if (tr.startswith("[") or tr.startswith("/")) else f"{w} [{tr}]"
                    else:
                        w_full = w

                    trans = str(item.get("translation") or item.get("meaning") or item.get("back") or item.get("russian") or "").strip()
                    pos = str(item.get("type") or item.get("pos") or item.get("role") or "").strip()
                    ex = str(item.get("example") or item.get("sentence") or item.get("sample") or "").strip()
                    img = str(item.get("image_query") or item.get("image") or f"{top} {w}").strip()

                    normalized_rows.append({
                        "id": i + 1,
                        "word": w_full,
                        "translation": trans,
                        "type": pos,
                        "example": ex,
                        "image_query": img
                    })
                elif isinstance(item, str) and "—" in item:
                    parts = [p.strip() for p in item.split("—", 1)]
                    normalized_rows.append({
                        "id": i + 1,
                        "word": parts[0],
                        "translation": parts[1] if len(parts) > 1 else "",
                        "type": "",
                        "example": "",
                        "image_query": f"{top} {parts[0]}"
                    })
            if normalized_rows:
                content["rows"] = normalized_rows
                content.setdefault("instruction", "👉 Изучите новые слова, их перевод и примеры в речи.")
                content.setdefault("columns", ["Картинка", "№ / Слово (Word)", "Перевод (Russian)", "Тип / Роль (Role)", "Пример в речи (Example Sentence)"])

    # 2. Fill in the Blanks
    elif btype == "fill_blanks":
        raw_items = (
            content.get("sentences")
            or content.get("questions")
            or content.get("items")
            or content.get("blanks")
            or content.get("data")
            or []
        )
        if isinstance(raw_items, list) and raw_items:
            normalized_sentences = []
            word_bank = list(content.get("word_bank") or [])
            for i, item in enumerate(raw_items):
                if isinstance(item, dict):
                    sent = str(item.get("sentence") or item.get("text") or item.get("question") or "").strip()
                    missing = str(item.get("missing") or item.get("answer") or item.get("correct") or "").strip()
                    opts = item.get("options") or []
                    c_idx = item.get("correct_index", 0)

                    if not missing and opts and isinstance(opts, list) and 0 <= c_idx < len(opts):
                        missing = str(opts[c_idx]).strip()

                    hint = str(item.get("hint") or "").strip()
                    if not hint and opts and isinstance(opts, list):
                        hint = " / ".join(str(o) for o in opts)

                    if "___" not in sent and missing:
                        sent = re.sub(rf"\b{re.escape(missing)}\b", "___", sent, count=1, flags=re.IGNORECASE)

                    if missing and missing not in word_bank:
                        word_bank.append(missing)

                    normalized_sentences.append({
                        "id": i + 1,
                        "sentence": sent,
                        "missing": missing,
                        "hint": hint
                    })
            if normalized_sentences:
                content["sentences"] = normalized_sentences
                content.setdefault("word_bank", word_bank)
                content.setdefault("instruction", "👉 Заполните пропуски подходящими по смыслу словами.")

    # 3. Speaking Cards
    elif btype == "speaking_cards":
        raw_items = (
            content.get("cards")
            or content.get("questions")
            or content.get("items")
            or content.get("prompts")
            or content.get("data")
            or []
        )
        if isinstance(raw_items, list) and raw_items:
            normalized_cards = []
            for i, item in enumerate(raw_items):
                if isinstance(item, dict):
                    q = str(item.get("question") or item.get("prompt") or item.get("title") or "").strip()
                    prompt = str(item.get("prompt") or item.get("title") or q).strip()
                    img = str(item.get("image_query") or item.get("image") or f"{top} {q[:30]}").strip()
                    follow_up = str(item.get("follow_up") or item.get("explanation") or "").strip()
                    normalized_cards.append({
                        "id": i + 1,
                        "prompt": prompt,
                        "question": q,
                        "image_query": img,
                        "follow_up": follow_up
                    })
                elif isinstance(item, str):
                    normalized_cards.append({
                        "id": i + 1,
                        "prompt": item.strip(),
                        "question": item.strip(),
                        "image_query": f"{top} {item[:30]}"
                    })
            if normalized_cards:
                content["cards"] = normalized_cards
                content.setdefault("instruction", "👉 Обсудите вопросы с партнером или преподавателем.")

    # 4. Flip Cards
    elif btype == "flip_cards":
        raw_items = (
            content.get("cards")
            or content.get("pairs")
            or content.get("items")
            or content.get("questions")
            or content.get("data")
            or []
        )
        if isinstance(raw_items, list) and raw_items:
            normalized_cards = []
            for i, item in enumerate(raw_items):
                if isinstance(item, dict):
                    front = str(item.get("front") or item.get("question") or item.get("prompt") or item.get("word") or "").strip()
                    back = str(item.get("back") or item.get("answer") or item.get("translation") or item.get("meaning") or "").strip()
                    img = str(item.get("image_query") or item.get("image") or f"{top} {front}").strip()
                    normalized_cards.append({
                        "id": i + 1,
                        "front": front,
                        "back": back,
                        "image_query": img
                    })
            if normalized_cards:
                content["cards"] = normalized_cards
                content.setdefault("instruction", "👉 Нажмите на карточку, чтобы узнать ответ или перевод!")

    # 5. Quiz Photo
    elif btype == "quiz_photo":
        raw_items = (
            content.get("questions")
            or content.get("items")
            or content.get("quiz")
            or content.get("data")
            or []
        )
        if isinstance(raw_items, list) and raw_items:
            normalized_questions = []
            for i, item in enumerate(raw_items):
                if isinstance(item, dict):
                    sentence = str(item.get("sentence") or item.get("question") or item.get("text") or "").strip()
                    opts = item.get("options") or []
                    if isinstance(opts, str):
                        opts = [o.strip() for o in opts.split(",")]
                    c_idx = item.get("correct_index", 0)
                    try:
                        c_idx = int(c_idx)
                    except (ValueError, TypeError):
                        c_idx = 0
                    img = str(item.get("image_query") or item.get("image") or f"{top} {sentence[:30]}").strip()
                    expl = str(item.get("explanation") or (f"Correct answer is {opts[c_idx]}" if (opts and 0 <= c_idx < len(opts)) else "")).strip()

                    if len(opts) >= 2:
                        normalized_questions.append({
                            "id": i + 1,
                            "sentence": sentence,
                            "options": [str(o).strip() for o in opts],
                            "correct_index": max(0, min(c_idx, len(opts) - 1)),
                            "image_query": img,
                            "explanation": expl
                        })
            if normalized_questions:
                content["questions"] = normalized_questions
                content.setdefault("instruction", "👉 Выберите правильный вариант ответа.")

    return content


def parse_draft_content_from_text(
    reply_text: str,
    block_type: Optional[str] = None,
    topic: Optional[str] = None,
    level: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Robust universal fallback parser: extracts questions, vocabulary rows, fill-blanks,
    speaking cards, and flip cards from markdown LLM responses.
    Ensures that even if LLM responds in plain text, structured content is ready for Figma canvas.
    """
    if not reply_text or len(reply_text) < 30:
        return None

    top = topic or "English"
    lvl = level or "A2"
    btype = block_type

    # Detect topic from text if generic
    if top in ("English", "Урок", None):
        m_top = re.search(r"(?:про|тема|topic|о)\s+([а-яА-ЯёЁa-zA-Z\s]{3,25})", reply_text, re.IGNORECASE)
        if m_top:
            top = m_top.group(1).strip().capitalize()

    # Detect level if mentioned
    m_lvl = re.search(r"\b([A-C][1-2])\b", reply_text, re.IGNORECASE)
    if m_lvl:
        lvl = m_lvl.group(1).upper()

    img_regex = re.compile(
        r"(?:\(|\[)?\s*(?:Картинка|Иллюстрация|Image|Photo|Visual)\s*[:—\-]\s*([^\]\)]+)(?:\)|\])?",
        re.IGNORECASE
    )

    q_chunks = re.split(r"(?:\n|^)\s*(?:(?:\d{1,2}\.|\d{1,2}\)|№\s*\d{1,2}|Question\s+\d{1,2}[:.]?|Card\s+\d{1,2}[:.]?)\s*)", reply_text)

    # 1. Parse Multiple Choice Quiz Questions
    opt_regex = re.compile(r"^(?:[-*•]\s*)?(?:[A-Fa-f0-9][\).:-]|\d[\).:-])\s*(.*)$")
    questions = []
    for chunk in q_chunks[1:]:
        lines = [line.strip() for line in chunk.strip().split("\n") if line.strip()]
        if not lines:
            continue
        raw_sentence = lines[0]
        sentence = re.sub(r"^[\W\d_]*[^\w\s]*\s*", "", raw_sentence).strip() or raw_sentence
        options = []
        correct_idx = 0
        image_query = ""

        for line in lines[1:]:
            m_img = img_regex.search(line)
            if m_img:
                image_query = m_img.group(1).strip()
                continue
            m_opt = opt_regex.match(line)
            if m_opt:
                opt_text = m_opt.group(1).strip()
                is_correct = False
                if any(marker in opt_text for marker in ("(✅)", "✅", "[x]", "[X]", "(+)", "(верно)", "(правильно)", "(correct)")):
                    is_correct = True
                    opt_text = re.sub(r"\s*(?:\(✅\)|✅|\[x\]|\[X\]|\(\+\)|\(верно\)|\(правильно\)|\(correct\))\s*", "", opt_text).strip()
                if is_correct:
                    correct_idx = len(options)
                options.append(opt_text)

        if len(options) >= 2:
            correct_val = options[correct_idx] if (0 <= correct_idx < len(options)) else options[0]
            if not image_query:
                image_query = f"{top} {sentence[:30]} {correct_val}"

            questions.append({
                "id": len(questions) + 1,
                "sentence": sentence,
                "options": options,
                "correct_index": correct_idx,
                "image_query": image_query,
                "explanation": f"Correct answer is {correct_val}"
            })

    if len(questions) >= 2 and (not btype or btype == "quiz_photo"):
        res = {
            "title": f"🎯 {top} Quiz",
            "topic": top,
            "level": lvl,
            "instruction": "👉 Выберите правильный вариант ответа для каждого задания.",
            "questions": questions,
            "hashtags": [f"#{top.lower().replace(' ', '_')}", f"#{lvl.lower()}", "#quiz", "#interactive", "#esl"]
        }
        return normalize_draft_content(res, "quiz_photo", top, lvl)

    # 2. Parse Vocabulary Table
    vocab_rows = []
    table_lines = [l.strip() for l in reply_text.split("\n") if l.strip().startswith("|") and not l.strip().startswith("|---")]
    if len(table_lines) >= 3:
        for line in table_lines[1:]:
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) >= 2:
                w_col = cols[1] if cols[0].isdigit() and len(cols) > 2 else cols[0]
                tr_col = cols[2] if cols[0].isdigit() and len(cols) > 2 else cols[1]
                role_col = cols[3] if len(cols) > 3 else ""
                ex_col = cols[4] if len(cols) > 4 else ""
                vocab_rows.append({
                    "id": len(vocab_rows) + 1,
                    "word": w_col,
                    "translation": tr_col,
                    "type": role_col,
                    "example": ex_col,
                    "image_query": f"{top} {w_col}"
                })
    if not vocab_rows:
        for chunk in q_chunks[1:]:
            lines = [l.strip() for l in chunk.strip().split("\n") if l.strip()]
            if not lines:
                continue
            first_line = lines[0]
            clean = re.sub(r"[*_`]", "", first_line).strip()
            clean = re.sub(r"^[\d\.\)\s]*[^\w\s]*\s*", "", clean).strip()
            parts = re.split(r"\s*[\—–\-:]\s*", clean, maxsplit=1)
            if len(parts) == 2 and any(c in parts[1] for c in "абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"):
                word_part = parts[0].strip()
                trans_part = parts[1].strip()

                role = ""
                m_role = re.search(r"\((noun|verb|adjective|adverb|prep|phrase|сущ|глаг|прил)\w*\)", trans_part, re.IGNORECASE)
                if m_role:
                    role = m_role.group(1).lower()
                    trans_part = re.sub(r"\s*\([^)]+\)\s*", "", trans_part).strip()

                example = ""
                image_query = f"{top} {word_part}"
                for line in lines[1:]:
                    m_ex = re.search(r"(?:Пример|Example|Sample|Ex)\s*[:—\-]\s*(.+)", line, re.IGNORECASE)
                    if m_ex:
                        example = m_ex.group(1).strip()
                    m_im = img_regex.search(line)
                    if m_im:
                        image_query = m_im.group(1).strip()

                vocab_rows.append({
                    "id": len(vocab_rows) + 1,
                    "word": word_part,
                    "translation": trans_part,
                    "type": role,
                    "example": example,
                    "image_query": image_query
                })

    if len(vocab_rows) >= 2 and (not btype or btype == "vocabulary_table" or any(k in reply_text.lower() for k in ("словарь", "слова", "лексик", "таблиц", "vocabulary"))):
        res = {
            "title": f"🎒 {top} Vocabulary",
            "topic": top,
            "level": lvl,
            "instruction": "👉 Изучите новые слова, перевод и примеры использования в речи.",
            "columns": ["Картинка", "№ / Слово (Word)", "Перевод (Russian)", "Тип / Роль (Role)", "Пример в речи (Example Sentence)"],
            "rows": vocab_rows,
            "hashtags": [f"#{top.lower().replace(' ', '_')}", f"#{lvl.lower()}", "#vocabulary", "#esl", "#table"]
        }
        return normalize_draft_content(res, "vocabulary_table", top, lvl)

    # 3. Parse Fill in the Blanks
    blank_sentences = []
    for chunk in q_chunks[1:]:
        lines = [l.strip() for l in chunk.strip().split("\n") if l.strip()]
        if not lines:
            continue
        first_line = lines[0]
        if re.search(r"(?:_{2,}|\[\s*\]|\(\s*\)|\.{3,})", first_line):
            clean_sent = re.sub(r"^[\W\d_]*[^\w\s]*\s*", "", first_line).strip()
            clean_sent = re.sub(r"(?:_{2,}|\[\s*\]|\(\s*\)|\.{3,})", "___", clean_sent)
            m_hint = re.search(r"\(([^)]+)\)", clean_sent)
            hint = m_hint.group(1).strip() if m_hint else ""
            missing = ""
            if "/" in hint:
                opts = [o.strip() for o in hint.split("/")]
                missing = opts[0]
            elif hint:
                missing = hint

            clean_sent = re.sub(r"\s*\([^)]+\)\s*", " ", clean_sent).strip()
            clean_sent = re.sub(r"\s+", " ", clean_sent)
            if "___" not in clean_sent:
                clean_sent = f"{clean_sent} ___"

            blank_sentences.append({
                "id": len(blank_sentences) + 1,
                "sentence": clean_sent,
                "missing": missing or "answer",
                "hint": hint
            })

    if len(blank_sentences) >= 2 and (not btype or btype == "fill_blanks" or any(k in reply_text.lower() for k in ("пропуск", "вставь", "blank", "fill"))):
        w_bank = [s["missing"] for s in blank_sentences if s.get("missing")]
        res = {
            "title": f"✍️ {top} Fill in the Blanks",
            "topic": top,
            "level": lvl,
            "instruction": "👉 Заполните пропуски подходящими по смыслу словами.",
            "word_bank": w_bank,
            "sentences": blank_sentences,
            "hashtags": [f"#{top.lower().replace(' ', '_')}", f"#{lvl.lower()}", "#grammar", "#fill_blanks", "#esl"]
        }
        return normalize_draft_content(res, "fill_blanks", top, lvl)

    # 4. Parse Flip Cards
    flip_cards = []
    for chunk in q_chunks[1:]:
        lines = [l.strip() for l in chunk.strip().split("\n") if l.strip()]
        if not lines:
            continue
        front = ""
        back = ""
        img_q = top
        for line in lines:
            m_f = re.search(r"^(?:Лицевая|Front|Вопрос|Question|Word)\s*[:—\-]\s*(.+)", line, re.IGNORECASE)
            if m_f:
                front = m_f.group(1).strip()
            m_b = re.search(r"^(?:Оборот|Back|Ответ|Answer|Translation|Перевод)\s*[:—\-]\s*(.+)", line, re.IGNORECASE)
            if m_b:
                back = m_b.group(1).strip()
            m_img = img_regex.search(line)
            if m_img:
                img_q = m_img.group(1).strip()

        if front and back:
            flip_cards.append({
                "id": len(flip_cards) + 1,
                "front": front,
                "back": back,
                "image_query": img_q
            })

    if len(flip_cards) >= 2 and (not btype or btype == "flip_cards" or any(k in reply_text.lower() for k in ("секрет", "переворот", "открывашк", "flip", "карточк"))):
        res = {
            "title": f"🃏 {top} Flip Cards",
            "topic": top,
            "level": lvl,
            "instruction": "👉 Нажмите на карточку, чтобы узнать ответ или перевод!",
            "cards": flip_cards,
            "hashtags": [f"#{top.lower().replace(' ', '_')}", f"#{lvl.lower()}", "#flip_cards", "#memory", "#esl"]
        }
        return normalize_draft_content(res, "flip_cards", top, lvl)

    # 5. Parse Speaking Cards
    speaking_cards = []
    for chunk in q_chunks[1:]:
        lines = [line.strip() for line in chunk.strip().split("\n") if line.strip()]
        if not lines:
            continue
        first_line = re.sub(r"^[\W\d_]*[^\w\s]*\s*", "", lines[0]).strip() or lines[0]
        first_line = re.sub(r"[*_`]", "", first_line).strip()
        img_q = top
        for line in lines:
            m_img = img_regex.search(line)
            if m_img:
                img_q = m_img.group(1).strip()
                break
        speaking_cards.append({
            "id": len(speaking_cards) + 1,
            "prompt": first_line,
            "question": first_line,
            "image_query": img_q
        })

    if len(speaking_cards) >= 2 and (not btype or btype == "speaking_cards" or any(k in reply_text.lower() for k in ("speaking", "бесед", "разминк", "вопрос", "дискусс", "обсужд"))):
        res = {
            "title": f"🗣️ {top} Speaking Cards",
            "topic": top,
            "level": lvl,
            "instruction": "👉 Обсудите вопросы с партнёром или преподавателем.",
            "cards": speaking_cards,
            "hashtags": [f"#{top.lower().replace(' ', '_')}", f"#{lvl.lower()}", "#speaking", "#discussion", "#esl"]
        }
        return normalize_draft_content(res, "speaking_cards", top, lvl)

    return None


async def process_chat_message(
    message: str,
    student_id: Optional[str] = None,
    user_key: str = "shared",
    history: Optional[List[Dict[str, str]]] = None,
    selection: Optional[Dict[str, Any]] = None,
    image_base64: Optional[str] = None,
    source: str = "web"
) -> Dict[str, Any]:
    """
    Process a message from the teacher, update student profile if facts are mentioned,
    analyze any attached textbook or canvas images, and return an interactive reply.
    """
    if history is None:
        history = get_user_history(user_key, limit=10)

    # Record incoming user message
    add_to_user_history(user_key=user_key, role="user", content=message, source=source)

    student_context = student_agent.format_student_prompt_context(student_id) if student_id else ""
    active_student = student_agent.get_student(student_id) if student_id else None

    # Analyze attached image if provided
    vision_context = None
    if image_base64:
        try:
            from server.agents import vision_agent
            st_lvl = active_student.get("level", "A2") if active_student else "A2"
            vision_context = await vision_agent.analyze_image(image_base64, command=message, level=st_lvl)
        except Exception as e:
            logger.warning(f"Failed to analyze attached chat image: {e}")

    # Construct context for LLM
    context_parts = []
    if student_context:
        context_parts.append(student_context)
    else:
        context_parts.append("Ученик на данный момент НЕ выбран. Преподаватель может вести свободный диалог о проекте, методике или на любые отвлеченные темы.")

    if selection and selection.get("count", 0) > 0:
        context_parts.append(f"На холсте выделен элемент: {selection.get('name', 'Элемент')} (isImage={selection.get('isImage')})")

    if vision_context:
        v_title = vision_context.get("worksheet_title") or vision_context.get("topic") or "Учебный материал"
        v_desc = vision_context.get("scene_description", "")
        v_type = vision_context.get("recommended_block_type", "fill_blanks")
        v_sents = vision_context.get("worksheet_sentences") or vision_context.get("questions") or []
        context_parts.append(
            f"🖼️ К сообщению прикреплено изображение: «{v_title}». "
            f"Описание/сюжет: {v_desc}. "
            f"Распознано заданий/предложений: {len(v_sents)}. "
            f"Рекомендованный интерактивный блок: {v_type}."
        )

    # History summary (last 8 turns)
    history_lines = []
    for turn in history[-8:]:
        role = "Учитель" if turn.get("role") == "user" else "Ассистент"
        history_lines.append(f"{role}: {turn.get('content', '')}")

    user_prompt = f"""
КОНТЕКСТ СЕССИИ:
{chr(10).join(context_parts)}

ИСТОРИЯ ДИАЛОГА:
{chr(10).join(history_lines) if history_lines else "(Начало диалога)"}

НОВОЕ СООБЩЕНИЕ УЧИТЕЛЯ:
"{message}"

Ответь свободно и живо.
"""

    prompt_tokens = count_tokens(CHAT_SYSTEM_PROMPT) + count_tokens(user_prompt)
    completion_tokens = 0
    try:
        raw_response = await ai_engine.generate_text(
            prompt=user_prompt,
            system_instruction=CHAT_SYSTEM_PROMPT,
            model="gemini-3.8-flash-low"
        )
        completion_tokens = count_tokens(raw_response)
    except Exception as e:
        logger.info(f"Chat AI engine failed ({e}). Utilizing pedagogical partner fallback...")
        from server.agents import pedagogical_knowledge
        expert_res = pedagogical_knowledge.analyze_and_respond(
            message=message,
            student=active_student,
            history=history
        )
        expert_res["student_id"] = student_id
        expert_res["detected_student"] = active_student
        expert_res.setdefault("ok", True)
        expert_res.setdefault("tokens", {"prompt": prompt_tokens, "completion": 0, "total": prompt_tokens})
        add_to_user_history(user_key=user_key, role="assistant", content=expert_res["reply"], source="system")
        return expert_res

    # Parse JSON or fallback gracefully to raw text as reply
    parsed = None
    try:
        clean_json = raw_response.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()

        s_idx = clean_json.find("{")
        e_idx = clean_json.rfind("}")
        if s_idx != -1 and e_idx != -1:
            clean_json = clean_json[s_idx:e_idx + 1]
            parsed = json.loads(clean_json)
    except Exception:
        parsed = None

    # If not JSON, use the generated text directly — NEVER substitute with canned template!
    if not parsed or not isinstance(parsed, dict) or "reply" not in parsed:
        cleaned_text = raw_response.strip()
        # Clean any leftover markdown blocks or tokens
        cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text)
        cleaned_text = re.sub(r"\s*```$", "", cleaned_text).strip()
        parsed = {
            "reply": cleaned_text or "Я на связи! Чем могу помочь?",
            "suggested_replies": [],
            "ready_to_build": False,
            "lesson_plan": None
        }

    reply_str = parsed.get("reply", "")

    # Robust ensure: normalize and validate lesson_plan.content
    lp = parsed.get("lesson_plan")
    if parsed.get("ready_to_build") or lp:
        if not isinstance(lp, dict):
            lp = {}
            parsed["lesson_plan"] = lp
        top = lp.get("topic") or "English"
        lvl = lp.get("level") or (active_student.get("level") if active_student else "A2")
        btype = lp.get("block_type") or "quiz_photo"

        # 1. Normalize whatever LLM returned in content
        if lp.get("content"):
            lp["content"] = normalize_draft_content(lp["content"], block_type=btype, topic=top, level=lvl)

        # 2. If content is still missing or has fewer than 2 items, extract from reply text
        if not is_content_valid_for_block_type(btype, lp.get("content")):
            parsed_content = parse_draft_content_from_text(reply_str, block_type=btype, topic=top, level=lvl)
            if parsed_content:
                lp["content"] = normalize_draft_content(parsed_content, block_type=btype, topic=top, level=lvl)
                if not lp.get("title"):
                    lp["title"] = lp["content"].get("title")

        # 3. Ensure title and ready_to_build flag if content is valid
        if lp.get("content") and is_content_valid_for_block_type(btype, lp.get("content")):
            parsed["ready_to_build"] = True
            if not lp.get("title"):
                lp["title"] = lp["content"].get("title")
    else:
        # Check if reply_str contains an exercise draft of any type
        parsed_content = parse_draft_content_from_text(reply_str)
        if parsed_content:
            b_type = (
                "vocabulary_table" if parsed_content.get("rows")
                else "fill_blanks" if parsed_content.get("sentences")
                else "flip_cards" if ("flip" in (parsed_content.get("title") or "").lower())
                else "speaking_cards" if parsed_content.get("cards")
                else "quiz_photo"
            )
            normalized = normalize_draft_content(parsed_content, block_type=b_type)
            if is_content_valid_for_block_type(b_type, normalized):
                parsed["ready_to_build"] = True
                parsed["lesson_plan"] = {
                    "title": normalized.get("title", "🎯 Interactive Exercise"),
                    "topic": normalized.get("topic", "English"),
                    "level": normalized.get("level", "A2"),
                    "block_type": b_type,
                    "content": normalized
                }

    # Extract student facts and update database if found
    extracted = parsed.get("extracted_student_facts")
    target_student_id = student_id
    if extracted and isinstance(extracted, dict):
        s_name = extracted.get("name")
        if not s_name and active_student:
            s_name = active_student.get("name")

        if s_name:
            interests_val = extracted.get("interests") or []
            strengths_val = extracted.get("strengths") or []
            weaknesses_val = extracted.get("weaknesses") or []

            update_data = {
                "name": s_name,
                "id": active_student.get("id") if active_student else None,
                "age": extracted.get("age"),
                "level": extracted.get("level"),
                "interests": [i for i in interests_val if i] if interests_val else None,
                "strengths": [s for s in strengths_val if s] if strengths_val else None,
                "weaknesses": [w for w in weaknesses_val if w] if weaknesses_val else None
            }
            update_data = {k: v for k, v in update_data.items() if v is not None}
            saved_student = student_agent.save_student(update_data)
            target_student_id = saved_student["id"]
            parsed["student"] = saved_student
            agent_logger.emit_log(
                stage="analyzing",
                icon="📁",
                title="Досье ученика",
                message=f"Синхронизировал досье ученика {s_name}: уровень {saved_student.get('level')}",
                agent="📁 Агент-Менеджер учеников"
            )
    elif active_student:
        parsed["student"] = active_student

    if parsed.get("ready_to_build"):
        plan_title = (parsed.get("lesson_plan") or {}).get("title", "Комплексный урок")
        agent_logger.emit_log(
            stage="generating",
            icon="🎯",
            title="План занятия",
            message=f"Сформировал структуру урока: «{plan_title}»",
            agent="🎯 Агент-Оркестратор"
        )
    else:
        agent_logger.emit_log(
            stage="done",
            icon="🧑‍🏫",
            title="Педагогический диалог",
            message="Подготовил ответ преподавателю и уточняющие вопросы",
            agent="🧑‍🏫 Педагогический агент"
        )

    reply_text = parsed.get("reply", "Готов помочь с материалами для урока!")

    # Record assistant reply in user and shared history
    add_to_user_history(user_key=user_key, role="assistant", content=reply_text, source=source)

    return {
        "reply": reply_text,
        "suggested_replies": parsed.get("suggested_replies", []),
        "ready_to_build": parsed.get("ready_to_build", False),
        "lesson_plan": parsed.get("lesson_plan"),
        "student_id": target_student_id,
        "detected_student": parsed.get("student"),
        "vision_context": vision_context,
        "image_base64": image_base64,
        "tokens": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": prompt_tokens + completion_tokens
        }
    }
