"""
ESL Figma AI — Bloom's Taxonomy Pedagogical Framework
Provides cognitive progression modeling for ESL lesson generation.

Hierarchy of cognitive domains (Revised Bloom's Taxonomy):
1. REMEMBER  (Запоминание) — Recall facts, basic terms, vocabulary recognition.
2. UNDERSTAND (Понимание)   — Explain ideas, categorize, paraphrase, interpret.
3. APPLY     (Применение)   — Use information in new situations, real-life context.
4. ANALYZE   (Анализ)       — Draw connections, distinguish, spot errors, odd one out.
5. EVALUATE  (Оценка)       — Justify a stand or decision, dilemmas, debate, rating.
6. CREATE    (Создание)     — Produce new work, roleplay, storytelling, project mission.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Any


@dataclass
class BloomLevelInfo:
    code: str
    name_ru: str
    name_en: str
    emoji: str
    badge_color: str  # Hex for UI/Figma badge
    recommended_blocks: List[str]
    verbs: List[str]
    pedagogical_focus: str


BLOOM_LEVELS: Dict[str, BloomLevelInfo] = {
    "REMEMBER": BloomLevelInfo(
        code="REMEMBER",
        name_ru="Запоминание",
        name_en="Remember",
        emoji="🧠",
        badge_color="#3b82f6",  # Blue
        recommended_blocks=["vocabulary_table", "flashcards", "flip_cards"],
        verbs=["recall", "name", "list", "identify", "repeat", "match"],
        pedagogical_focus="Активация фоновых знаний, первичное знакомство с лексикой, фонетика и зрительные ассоциации."
    ),
    "UNDERSTAND": BloomLevelInfo(
        code="UNDERSTAND",
        name_ru="Понимание",
        name_en="Understand",
        emoji="💡",
        badge_color="#0ea5e9",  # Sky Blue
        recommended_blocks=["flip_cards", "fill_blanks", "video_quiz"],
        verbs=["explain", "describe", "categorize", "paraphrase", "interpret"],
        pedagogical_focus="Осмысление значений, понимание контекста, карточки со скрытыми пояснениями (Peekaboo)."
    ),
    "APPLY": BloomLevelInfo(
        code="APPLY",
        name_ru="Применение",
        name_en="Apply",
        emoji="⚙️",
        badge_color="#10b981",  # Emerald Green
        recommended_blocks=["fill_blanks", "quiz_photo", "speaking_cards"],
        verbs=["use", "complete", "practice", "solve", "roleplay_guided"],
        pedagogical_focus="Использование конструкций и лексики в конкретных практических ситуациях и диалогах."
    ),
    "ANALYZE": BloomLevelInfo(
        code="ANALYZE",
        name_ru="Анализ",
        name_en="Analyze",
        emoji="🔍",
        badge_color="#f59e0b",  # Amber
        recommended_blocks=["quiz_photo", "speaking_cards"],
        verbs=["compare", "contrast", "distinguish", "find_error", "odd_one_out"],
        pedagogical_focus="Поиск ошибок, выявление закономерностей, сравнение вариантов и поиск логических несоответствий."
    ),
    "EVALUATE": BloomLevelInfo(
        code="EVALUATE",
        name_ru="Оценка",
        name_en="Evaluate",
        emoji="⚖️",
        badge_color="#8b5cf6",  # Purple
        recommended_blocks=["speaking_cards", "quiz_photo"],
        verbs=["judge", "rate", "choose", "justify", "debate", "critique"],
        pedagogical_focus="Этическая или практическая дилемма, ранжирование, аргументация своей точки зрения."
    ),
    "CREATE": BloomLevelInfo(
        code="CREATE",
        name_ru="Творчество",
        name_en="Create",
        emoji="🚀",
        badge_color="#ec4899",  # Rose Pink
        recommended_blocks=["speaking_cards"],
        verbs=["design", "compose", "invent", "roleplay_open", "solve_mission"],
        pedagogical_focus="Свободное речевое продуцирование: открытая ролевая игра, решение миссии, создание своей истории."
    ),
}


def build_bloom_learning_arc(
    topic: str,
    level: str = "A2",
    student_profile: Optional[Dict[str, Any]] = None,
    duration_minutes: int = 45
) -> List[Dict[str, Any]]:
    """
    Constructs an optimal pedagogical learning arc based on Bloom's Taxonomy.
    Adapts cognitive depth to student age, CEFR level, and lesson duration.

    Returns a list of stages:
    [
      {
        "stage_num": 1,
        "bloom_level": "REMEMBER",
        "badge_text": "🧠 1. REMEMBER",
        "badge_color": "#3b82f6",
        "title": "...",
        "block_type": "vocabulary_table",
        "goal": "...",
        "content_prompt_instructions": "..."
      },
      ...
    ]
    """
    student_profile = student_profile or {}
    age = student_profile.get("age") or 14
    interests = student_profile.get("interests", [])
    interests_str = ", ".join(interests[:3]) if interests else ""

    is_child = age < 12

    stages: List[Dict[str, Any]] = []

    # ── Stage 1: Foundation (Remember & Activate) ─────────────────────────────
    stages.append({
        "stage_num": 1,
        "bloom_level": "REMEMBER",
        "badge_text": "🧠 1. REMEMBER",
        "badge_color": BLOOM_LEVELS["REMEMBER"].badge_color,
        "title": f"Foundation Vocabulary: {topic}",
        "block_type": "vocabulary_table" if not is_child else "flip_cards",
        "goal": f"Активировать ключевую лексику по теме «{topic}», закрепить произношение и зрительные образы.",
        "content_prompt_instructions": (
            f"Bloom Level 1 (Remember): Focus strictly on 6-8 core high-frequency words/phrases for topic '{topic}'. "
            "Include IPA transcription and memorable Russian translation. "
            + (f"Connect to student interests ({interests_str}) where possible." if interests_str else "")
        )
    })

    # ── Stage 2: Application (Apply in Realistic Context) ────────────────────
    stages.append({
        "stage_num": 2,
        "bloom_level": "APPLY",
        "badge_text": "⚙️ 2. APPLY",
        "badge_color": BLOOM_LEVELS["APPLY"].badge_color,
        "title": f"Context in Action: {topic}",
        "block_type": "fill_blanks",
        "goal": f"Отработать изученную лексику в связных жизненных предложениях и мини-диалогах.",
        "content_prompt_instructions": (
            f"Bloom Level 3 (Apply): Create 6 contextual sentences/mini-dialogues testing correct application of the vocabulary. "
            "Sentences must depict realistic, authentic situations students can encounter in real life."
        )
    })

    # ── Stage 3: Higher Order Thinking (Analyze or Evaluate) ─────────────────
    if is_child:
        stages.append({
            "stage_num": 3,
            "bloom_level": "ANALYZE",
            "badge_text": "🔍 3. ANALYZE",
            "badge_color": BLOOM_LEVELS["ANALYZE"].badge_color,
            "title": f"Visual Challenge & Analysis: {topic}",
            "block_type": "quiz_photo",
            "goal": "Развить аналитическое мышление: сравнение картинок, поиск логических несоответствий.",
            "content_prompt_instructions": (
                f"Bloom Level 4 (Analyze): Create 4-6 fun visual questions testing observation and critical deduction. "
                "Instead of trivial definitions, ask 'What is missing?', 'Which doesn't fit?', or 'Why is this wrong?'."
            )
        })
    else:
        stages.append({
            "stage_num": 3,
            "bloom_level": "EVALUATE",
            "badge_text": "⚖️ 3. EVALUATE",
            "badge_color": BLOOM_LEVELS["EVALUATE"].badge_color,
            "title": f"Critical Deduction & Quiz: {topic}",
            "block_type": "quiz_photo",
            "goal": "Побудить ученика анализировать контекст, делать обоснованный выбор и выявлять нюансы.",
            "content_prompt_instructions": (
                f"Bloom Level 5 (Evaluate): Generate 4-6 analytical multiple-choice dilemma questions related to '{topic}'. "
                "Require evaluating evidence, identifying best solutions, and distinguishing subtle differences."
            )
        })

    # ── Stage 4: Synthesis & Creation (Create / Roleplay Arena) ──────────────
    stages.append({
        "stage_num": 4,
        "bloom_level": "CREATE",
        "badge_text": "🚀 4. CREATE",
        "badge_color": BLOOM_LEVELS["CREATE"].badge_color,
        "title": f"Real-World Roleplay Mission: {topic}",
        "block_type": "speaking_cards",
        "goal": "Творческое речевое продуцирование: открытая ролевая ситуация, решение кейса или проектная миссия.",
        "content_prompt_instructions": (
            f"Bloom Level 6 (Create): Generate 4-6 mission-driven speaking prompts or roleplay scenarios. "
            "Examples: 'You are an airport manager handling a lost cat', 'Design the ultimate holiday itinerary', "
            "'Negotiate with the hotel clerk'. Require spontaneous creative communication."
        )
    })

    return stages


def format_teacher_guide_bloom_section(arc: List[Dict[str, Any]]) -> str:
    """
    Formats the Teacher Guide pedagogical section structured by Bloom's cognitive stages.
    """
    lines = ["🧠 МЕТОДИЧЕСКАЯ ТРАЕКТОРИЯ ПО БЛУМУ (BLOOM'S LEARNING ARC)"]
    for s in arc:
        b_info = BLOOM_LEVELS.get(s["bloom_level"])
        emoji = b_info.emoji if b_info else "🎯"
        ru_name = b_info.name_ru if b_info else s["bloom_level"]
        lines.append(f"• Этап {s['stage_num']} — {emoji} {ru_name} ({s['title']}): {s['goal']}")
    return "\n".join(lines)
