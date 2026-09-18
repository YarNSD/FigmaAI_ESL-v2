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

logger = logging.getLogger("chat_agent")


# ── Shared Server Conversation History ───────────────────────────────────────
_SHARED_CHAT_HISTORY: List[Dict[str, Any]] = []


def get_shared_history(limit: int = 30) -> List[Dict[str, Any]]:
    """Return the shared recent conversation history."""
    return list(_SHARED_CHAT_HISTORY[-limit:])


def add_to_shared_history(role: str, content: str, source: str = "web", **kwargs) -> None:
    """Add a message to the shared conversation history."""
    _SHARED_CHAT_HISTORY.append({
        "role": role,
        "content": content,
        "source": source,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        **kwargs
    })
    if len(_SHARED_CHAT_HISTORY) > 50:
        _SHARED_CHAT_HISTORY.pop(0)


def clear_shared_history() -> None:
    """Clear all shared history."""
    _SHARED_CHAT_HISTORY.clear()


CHAT_SYSTEM_PROMPT = """Ты — дружелюбный напарник-методист учителя английского в FigmaAI (FigJam).
Общайся тепло, легко и кратко (1–2 коротких абзаца, живые эмодзи).

ПРАВИЛА:
1. 🚫 Без непрошенных планов: не вываливай поминутные сетки и тайминги без прямой просьбы.
2. ❓ Уточняй детали: задавай 1–2 метких вопроса (механика, фокус: fluency/accuracy, интересы, тайминг).
3. 🔘 Всегда давай 2–3 умные кнопки-подсказки в "suggested_replies".
4. 🚀 "ready_to_build": false по умолчанию. Ставь true ТОЛЬКО если учитель прямо попросил создать/нарисовать или подтвердил согласованный план.
5. 📊 CEFR: если уровень ученика не указан и ученик не выбран — ОБЯЗАТЕЛЬНО спроси уровень (предложи кнопки: "🟢 A1", "🟡 A2", "🔵 B1") и не навязывай A2 молча.
6. 🧠 Память: фиксируй упомянутые факты об ученике в "extracted_student_facts".

ФОРМАТ СТРОГО JSON:
{
  "reply": "Живой ответ коллеге с вопросом",
  "suggested_replies": ["Вариант 1", "Вариант 2", "Вариант 3"],
  "extracted_student_facts": {"name": null, "age": null, "level": null, "interests": null, "weaknesses": null, "strengths": null},
  "ready_to_build": false,
  "lesson_plan": null
}"""


async def process_chat_message(
    message: str,
    student_id: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    selection: Optional[Dict[str, Any]] = None,
    image_base64: Optional[str] = None,
    source: str = "web"
) -> Dict[str, Any]:
    """
    Process a message from the teacher, update student profile if facts are mentioned,
    analyze any attached textbook or canvas images, and return an interactive reply with suggested chips.
    """
    if history is None:
        history = get_shared_history(limit=8)

    # Record incoming user message in shared history
    add_to_shared_history(role="user", content=message, source=source)

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
        context_parts.append("Ученик на данный момент НЕ выбран. Преподаватель может вести свободный диалог о проекте, методике или конкретном ученике.")

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
            f"Рекомендованный интерактивный блок: {v_type}. "
            f"ПРАВИЛО: Если на картинке есть готовое упражнение из учебника — используй его 1-в-1 без выдумывания лишнего!"
        )

    # History summary (last 6 turns)
    history_lines = []
    for turn in history[-6:]:
        role = "Учитель" if turn.get("role") == "user" else "Ассистент"
        history_lines.append(f"{role}: {turn.get('content', '')}")

    user_prompt = f"""
КОНТЕКСТ СЕССИИ:
{chr(10).join(context_parts)}

ИСТОРИЯ ДИАЛОГА:
{chr(10).join(history_lines) if history_lines else "(Начало диалога)"}

НОВОЕ СООБЩЕНИЕ УЧИТЕЛЯ:
"{message}"

Ответь строго в формате JSON, как указано в системных инструкциях.
"""

    target_desc = active_student.get("name", "ученика") if active_student else "запроса"
    agent_logger.emit_log(
        stage="thinking",
        icon="🧑‍🏫",
        title="Педагогический анализ",
        message=f"Анализирует запрос ({target_desc}): «{message[:60]}»",
        agent="🧑‍🏫 Педагогический агент"
    )

    try:
        raw_response = await ai_engine.generate_text(
            prompt=user_prompt,
            system_instruction=CHAT_SYSTEM_PROMPT
        )
    except Exception as e:
        logger.info(f"Chat AI engine offline or unconfigured ({e}). Utilizing pedagogical expert knowledge engine...")
        agent_logger.emit_log(
            stage="thinking",
            icon="🧑‍🏫",
            title="Педагогический эксперт",
            message="Формирую развернутый методический ответ и идеи материалов",
            agent="🧑‍🏫 Педагогический агент"
        )
        from server.agents import pedagogical_knowledge
        expert_res = pedagogical_knowledge.analyze_and_respond(
            message=message,
            student=active_student,
            history=history
        )
        expert_res["student_id"] = student_id
        expert_res["detected_student"] = active_student
        add_to_shared_history(role="assistant", content=expert_res["reply"], source="system")
        return expert_res

    # Parse JSON
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
    except Exception as e:
        logger.warning(f"Failed to parse LLM chat JSON: {e}. Raw: {raw_response[:200]}")
        parsed = {
            "reply": raw_response if len(raw_response) < 400 else "Отлично! Давайте уточним детали для урока или обсудим проект.",
            "suggested_replies": ["Продолжить", "Сделать квиз", "Разминка Speaking"],
            "ready_to_build": False
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

    # Record assistant reply in shared history
    add_to_shared_history(role="assistant", content=reply_text, source=source)

    return {
        "reply": reply_text,
        "suggested_replies": parsed.get("suggested_replies", []),
        "ready_to_build": parsed.get("ready_to_build", False),
        "lesson_plan": parsed.get("lesson_plan"),
        "student_id": target_student_id,
        "detected_student": parsed.get("student"),
        "vision_context": vision_context,
        "image_base64": image_base64
    }
