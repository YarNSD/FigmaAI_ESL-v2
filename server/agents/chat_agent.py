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


def clear_user_history(user_key: str = "shared") -> None:
    """Clear history for a specific user session."""
    if user_key in _USER_CHAT_HISTORIES:
        _USER_CHAT_HISTORIES[user_key].clear()
    if user_key == "shared":
        _SHARED_CHAT_HISTORY.clear()


CHAT_SYSTEM_PROMPT = """Ты — умный, живой, проницательный персональный ИИ-собеседник и напарник преподавателя в проекте FigmaAI.
Ты общаешься с пользователем в Telegram и веб-интерфейсе.

ПРИНЦИПЫ ОБЩЕНИЯ:
1. 🗣️ Естественный живой диалог: Общайся как умный, эмпатичный, интересный человек (настоящий напарник). Говори легко, свободно, с юмором и поддержкой. Никаких шаблонных канцелярских отписок и роботских фраз!
2. 🌐 Свобода любых тем: Пользователь может говорить с тобой О ЧЁМ УГОДНО — о настроении, о том как прошёл день, о фильмах, жизни, методике, философии или просто перекинуться парой фраз. НИКОГДА не навязывай уроки, если человек просто общается!
3. 🚫 Никаких дежурных анкет: Если тебя не просят прямо составить тест/упражнение, НИКОГДА не приставай с вопросами «Какой уровень CEFR: A1, A2, B1?». Будь интересным собеседником, а не бюрократом.
4. 🛠️ Проект FigmaAI (твоя суперсила): Ты умеешь рисовать на доске Figma интерактивные квизы с самопроверкой, карточки со словами, разминки Speaking, таблицы слов с переводом и открывашки.
5. 🚀 Создание на холсте:
   - Если пользователь прямо говорит «нарисуй на доске...», «сделай квиз на доске...» или в процессе обсуждения вы решили перенести упражнение на холст — установи "ready_to_build": true и заполни "lesson_plan".
   - В обычном разговоре всегда держи "ready_to_build": false и "lesson_plan": null.
6. 🔘 Подсказки: Не спамь кнопками! Если это открытая беседа — возвращай пустой массив "suggested_replies": [].

ФОРМАТ ОТВЕТА (желательно JSON, но если ты ответишь живым текстом, система тебя поймет):
{
  "reply": "Твой естественный, живой ответ",
  "suggested_replies": [],
  "extracted_student_facts": null,
  "ready_to_build": false,
  "lesson_plan": null
}"""


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
