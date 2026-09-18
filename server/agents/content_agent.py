"""
ESL Figma AI — Pedagogical Content Agent
Generates ESL learning content (quizzes, vocabulary, etc.) using the unified AI engine
(Google Antigravity CLI by default or Google Gemini API).
Role: Expert ESL methodologist — strict CEFR levels, no hallucinations.
"""
import json
import logging
import random
import re
from server import config
from server.agents import ai_engine
from server.agents import content_fallback

logger = logging.getLogger("content_agent")


def _normalize_and_shuffle_quiz_questions(questions: list) -> list:
    """
    Ensures every question has exactly 4 options and that options are uniformly randomized.
    Updates correct_index to point to the new shuffled position so option 1 is not constant.
    """
    natural_distractors = [
        "Take a break", "Prepare breakfast", "Check emails", "Set an alarm",
        "Wash the dishes", "Do exercise", "Catch the bus", "Pack a bag",
        "Brush teeth", "Stay up late", "Cook dinner", "Make coffee"
    ]
    for q in questions:
        # Filter out empty and robotic options like 'None of the above'
        opts = [
            str(o).strip() for o in q.get("options", [])
            if str(o).strip() and not re.search(r"^(none|all) of the above", str(o).strip(), re.IGNORECASE)
        ]
        orig_idx = q.get("correct_index", 0)
        if not (0 <= orig_idx < len(opts)):
            orig_idx = 0
        correct_answer = opts[orig_idx] if opts else "Correct Option"

        # Ensure we have at least 4 options
        d_idx = 0
        while len(opts) < 4:
            cand = natural_distractors[d_idx % len(natural_distractors)]
            d_idx += 1
            if cand not in opts:
                opts.append(cand)

        # If more than 4, trim distractors while preserving correct answer
        if len(opts) > 4:
            other_opts = [o for i, o in enumerate(opts) if i != orig_idx]
            opts = [correct_answer] + other_opts[:3]

        # Shuffle options randomly
        random.shuffle(opts)
        q["options"] = opts
        q["correct_index"] = opts.index(correct_answer)
        if "correct" in q:
            q["correct"] = correct_answer
    return questions

SYSTEM_PROMPT = """You are an expert ESL (English as a Second Language) methodologist with 15+ years of experience.

STRICT RULES:
1. ALL content (questions, options, examples) must strictly match the specified CEFR level (A1/A2/B1/B2/C1).
2. Use ONLY natural, authentic English — no machine-translated or overly formal language.
3. Options A/B/C must be plausible distractors — students should need to think, not guess randomly.
4. NEVER hallucinate facts. All information must be accurate.
5. For vocabulary tables: include IPA phonetic transcription in [brackets].
6. Questions must be about the TOPIC provided — stay focused.
7. Output ONLY valid JSON — no markdown fences, no extra text.
8. For image-based quizzes: questions should work with a relevant photo of the topic.
9. Keep language age-appropriate and culturally neutral.
10. USER RULE 20A: All student instructions in the 'instruction' field MUST start with '👉 ' and be in clear Russian (e.g. '👉 Выберите правильный вариант ответа...'). All exercise sentences, questions, options, words, and explanations MUST be 100% in natural English.
"""

LEVEL_GUIDES = {
    "A1": "Very basic: present simple, common nouns, numbers 1-100, colors, family, daily routine. Max 6-7 word sentences.",
    "A2": "Elementary: past simple, present continuous, can/can't, comparatives, common phrasal verbs. Short paragraphs.",
    "B1": "Intermediate: present perfect, conditionals (1st/2nd), passive voice, relative clauses, wider vocabulary.",
    "B2": "Upper-intermediate: all tenses, complex grammar, idioms, academic vocabulary, nuanced meanings.",
    "C1": "Advanced: sophisticated vocabulary, complex structures, idioms, implied meaning, formal/informal register.",
}


def _build_vision_prompt_section(vision_context: dict | None) -> str:
    if not vision_context:
        return ""
    desc = vision_context.get("scene_description", "")
    objects = ", ".join(vision_context.get("objects_found", []))
    plan = vision_context.get("pedagogical_plan", "") or vision_context.get("pedagogical_purpose", "")
    purpose = vision_context.get("pedagogical_purpose", "")
    ws_title = vision_context.get("worksheet_title", "")
    is_ws = vision_context.get("is_worksheet", False)
    vocab_list = vision_context.get("vocabulary", [])
    vocab_str = ", ".join([f"{v.get('word')}" for v in vocab_list if v.get("word")])
    return f"""
CRITICAL INSTRUCTION — VISUAL CONTEXT FROM TEACHER'S CANVAS IMAGE:
The user selected a specific image on the Figma canvas. You MUST build this activity DIRECTLY around this image!
- Is Worksheet/Exercise Sheet: {is_ws}
- Worksheet Title / Rules: {ws_title}
- Pedagogical purpose / learning goal: {purpose or plan}
- Scene description / text: {desc}
- Key objects/food/characters visible: {objects}
- Key vocabulary from image: {vocab_str}

Every question, card, or vocabulary item MUST test observation or grammar and relate directly to what is depicted on this sheet!
"""


async def generate_quiz_photo(
    topic: str,
    level: str,
    count: int = 10,
    vision_context: dict | None = None,
    bloom_level: str | None = None,
    bloom_instructions: str | None = None
) -> dict:
    """
    Generate a photo-based quiz (type 1 from screenshots).
    Returns structured JSON with questions, options, correct answers.
    Enforces minimum of 10 questions per user requirements.
    Supports Bloom's taxonomy cognitive levels (e.g. ANALYZE for error hunting / odd-one-out).
    """
    # Enforce minimum 10 questions for ESL quizzes
    count = max(int(count or 10), 10)

    # If vision agent already extracted questions directly from the worksheet / image:
    if vision_context and vision_context.get("questions") and len(vision_context["questions"]) >= 3:
        v_qs = vision_context["questions"]
        formatted_questions = []
        for idx, q in enumerate(v_qs[:count], 1):
            opts = q.get("options", ["A", "B", "C", "D"])
            correct_val = q.get("correct")
            correct_idx = 0
            if correct_val in opts:
                correct_idx = opts.index(correct_val)
            formatted_questions.append({
                "id": idx,
                "image_query": q.get("image_query") or q.get("object") or topic,
                "sentence": q.get("question") or q.get("sentence") or "",
                "options": opts,
                "correct_index": correct_idx,
                "explanation": q.get("explanation") or f"Correct answer is {correct_val}"
            })
        
        formatted_questions = _normalize_and_shuffle_quiz_questions(formatted_questions)
        title = vision_context.get("topic") or vision_context.get("worksheet_title") or f"🎯 {topic} Interactive Quiz"
        instruction = vision_context.get("instruction") or "Выберите правильный вариант ответа для каждого задания по картинке."
        logger.info(f"✅ Generated quiz directly from Vision Agent: {title} ({len(formatted_questions)} questions)")
        return {
            "title": title[:60],
            "topic": topic,
            "level": level,
            "instruction": instruction,
            "questions": formatted_questions,
            "hashtags": [f"#{topic.lower().replace(' ', '_')}", f"#{level.lower()}", "#worksheet", "#interactive", "#quiz"]
        }

    level_guide = LEVEL_GUIDES.get(level, LEVEL_GUIDES["A2"])
    vision_section = _build_vision_prompt_section(vision_context)

    bloom_section = ""
    if bloom_instructions or bloom_level:
        bloom_section = f"""
BLOOM'S TAXONOMY COGNITIVE FOCUS (Level: {bloom_level or 'ANALYZE'}):
{bloom_instructions or 'Design questions that foster critical thinking, error analysis, or finding the odd one out rather than simple recall.'}
"""

    prompt = f"""Create an ESL quiz about "{topic}" for level {level}.
Level guide: {level_guide}
{vision_section}
{bloom_section}

Return JSON in this EXACT format:
{{
  "title": "Quiz title with emoji (max 60 chars)",
  "topic": "{topic}",
  "level": "{level}",
  "instruction": "Short instruction for students in Russian (what to do)",
  "image_query": "English search query for a relevant photo (e.g. 'cute cats playing')",
  "questions": [
    {{
      "id": 1,
      "image_query": "2-4 word Wikipedia-searchable English noun phrase for this question's key concept. Must be a concrete THING or SCENE visible in a photo (e.g. 'yellow card football', 'cat sleeping sofa', 'library bookshelves'). NOT abstract words like 'grammar', 'verb', 'language'. Topic context MUST be included.",
      "sentence": "Sentence with ___ gap OR question text",
      "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
      "correct_index": 2,
      "explanation": "Brief explanation why this is correct (in English)"
    }}
  ],
  "hashtags": ["#topic", "#level", "#english", "#quiz", "#relevant_tags"]
}}

Generate exactly {count} questions. Make them varied and educational.
CRITICAL RULES FOR OPTIONS:
1. Every question MUST have EXACTLY 4 options (Option 1, Option 2, Option 3, Option 4).
2. Do NOT include 'A)', 'B)', 'C)', 'D)' prefixes in the options array — only the text.
3. RANDOMIZE the correct answer index across questions (e.g. questions have correct_index = 0, 1, 2, 3 in random order). NEVER make option 1 / index 0 always the correct answer!
4. Each image_query must be a specific, concrete, photo-searchable English phrase related to BOTH the question AND the topic '{topic}'.
5. NEVER generate robotic fillers like 'None of the above', 'All of the above', or 'Not mentioned'. All 4 options must be authentic, plausible English words or phrases."""

    if not (config.is_ai_ready() and ai_engine.is_antigravity_cli_authenticated()):
        logger.info(f"AI engine offline/unauthenticated, using educational fallback for quiz: {topic}")
        return content_fallback.generate_fallback_quiz_photo(topic, level, count, bloom_level)

    try:
        data = await ai_engine.generate_json(prompt, system_instruction=SYSTEM_PROMPT)
        if "questions" not in data:
            raise ValueError("Content agent returned invalid structure (missing 'questions')")
    except Exception as e:
        logger.warning(f"AI engine failed for quiz ({e}), using educational fallback")
        return content_fallback.generate_fallback_quiz_photo(topic, level, count, bloom_level)

    if len(data["questions"]) < count:
        logger.warning(f"Requested {count} questions, got {len(data['questions'])}. Supplementing from educational database...")
        fallback_data = content_fallback.generate_fallback_quiz_photo(topic, level, count, bloom_level)
        existing_sentences = {q.get("sentence", "").strip().lower() for q in data["questions"]}
        for fq in fallback_data.get("questions", []):
            if fq.get("sentence", "").strip().lower() not in existing_sentences:
                fq["id"] = len(data["questions"]) + 1
                data["questions"].append(fq)
            if len(data["questions"]) >= count:
                break

    # Normalize to exactly 4 options and shuffle options so answer position is truly randomized
    data["questions"] = _normalize_and_shuffle_quiz_questions(data["questions"])

    # If canvas image was provided, attach user's image to questions
    if vision_context and vision_context.get("image_base64"):
        img_b64 = vision_context["image_base64"]
        for q in data["questions"]:
            if not q.get("image_base64"):
                q["image_base64"] = img_b64

    logger.info(f"✅ Generated quiz: {data.get('title')} ({len(data['questions'])} questions)")
    return data


async def generate_flip_cards(topic: str, level: str, count: int = 12, vision_context: dict | None = None) -> dict:
    """
    Generate flip/reveal cards (type 2 from screenshots).
    Each card has a label + hidden question revealed on click.
    """
    level_guide = LEVEL_GUIDES.get(level, LEVEL_GUIDES["A2"])
    vision_section = _build_vision_prompt_section(vision_context)

    prompt = f"""Create ESL flip cards about "{topic}" for level {level}.
Level guide: {level_guide}
{vision_section}

Each card shows a label/role (e.g. "STRIKER", "GOALKEEPER") with an image,
and when clicked reveals a speaking/discussion question.

Return JSON:
{{
  "title": "Activity title with emoji",
  "topic": "{topic}",
  "level": "{level}",
  "instruction": "Instruction in Russian (click to reveal and describe the image)",
  "cards": [
    {{
      "id": 1,
      "label": "WORD OR ROLE IN CAPS",
      "image_query": "specific image search for this card",
      "color": "#hex_color",
      "question": "Speaking question revealed on click (full sentence)",
      "bonus_question": "Optional follow-up question"
    }}
  ],
  "hashtags": ["#tags"]
}}

Generate {count} cards. Use VARIED colors from this palette:
["#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#be185d", "#65a30d"]"""

    if not (config.is_ai_ready() and ai_engine.is_antigravity_cli_authenticated()):
        logger.info(f"AI engine offline/unauthenticated, using educational fallback for flip cards: {topic}")
        return content_fallback.generate_fallback_flip_cards(topic, level, count)

    try:
        data = await ai_engine.generate_json(prompt, system_instruction=SYSTEM_PROMPT)
    except Exception as e:
        logger.warning(f"AI engine failed for flip cards ({e}), using educational fallback")
        return content_fallback.generate_fallback_flip_cards(topic, level, count)

    if vision_context and vision_context.get("image_base64"):
        img_b64 = vision_context["image_base64"]
        for c in data.get("cards", []):
            if not c.get("image_base64"):
                c["image_base64"] = img_b64

    logger.info(f"✅ Generated flip cards: {data.get('title')} ({len(data.get('cards', []))} cards)")
    return data


async def generate_video_quiz(youtube_url: str, topic: str, level: str, count: int = 10) -> dict:
    """
    Generate a video comprehension quiz (type 3 from screenshots).
    """
    level_guide = LEVEL_GUIDES.get(level, LEVEL_GUIDES["B1"])

    prompt = f"""Create an ESL video comprehension quiz for level {level}.
Topic: "{topic}"
YouTube URL: {youtube_url}
Level guide: {level_guide}

Return JSON:
{{
  "title": "Quiz title with emoji",
  "topic": "{topic}",
  "level": "{level}",
  "youtube_url": "{youtube_url}",
  "instruction": "Instruction in Russian (watch video, answer questions)",
  "vocabulary": [
    {{
      "word": "English word",
      "transcription": "[IPA]",
      "translation": "Russian translation",
      "definition": "Short English definition"
    }}
  ],
  "questions": [
    {{
      "id": 1,
      "emoji": "relevant emoji",
      "question": "Comprehension question",
      "options": ["Option A", "Option B", "Option C"],
      "correct_index": 0
    }}
  ],
  "hashtags": ["#tags"]
}}

Generate {count} questions and 6-8 key vocabulary items from the topic."""

    data = await ai_engine.generate_json(prompt, system_instruction=SYSTEM_PROMPT)
    data["youtube_url"] = youtube_url  # ensure it's preserved
    logger.info(f"✅ Generated video quiz: {data.get('title')}")
    return data


async def generate_vocabulary_table(
    topic: str,
    level: str,
    count: int = 10,
    vision_context: dict | None = None,
    bloom_level: str | None = None,
    bloom_instructions: str | None = None
) -> dict:
    """
    Generate a vocabulary table with translation (type 4 from screenshots).
    Supports Bloom's taxonomy: REMEMBER (core foundation terms, phonetics, memorable examples).
    """
    level_guide = LEVEL_GUIDES.get(level, LEVEL_GUIDES["A2"])
    vision_section = _build_vision_prompt_section(vision_context)

    bloom_section = ""
    if bloom_instructions or bloom_level:
        bloom_section = f"""
BLOOM'S TAXONOMY COGNITIVE FOCUS (Level: {bloom_level or 'REMEMBER'}):
{bloom_instructions or 'Focus on high-frequency core vocabulary, memorable examples, and clear IPA phonetic transcriptions.'}
"""

    prompt = f"""Create an ESL vocabulary table about "{topic}" for level {level}.
Level guide: {level_guide}
{vision_section}
{bloom_section}

Return JSON:
{{
  "title": "Table title with emoji",
  "topic": "{topic}",
  "level": "{level}",
  "instruction": "Instruction in Russian",
  "columns": ["Картинка", "№ / Слово (Word)", "Перевод (Russian)", "Тип / Роль (Role)", "Пример в речи (Example Sentence)"],
  "rows": [
    {{
      "id": 1,
      "word": "word [IPA transcription]",
      "translation": "Russian translation",
      "type": "grammatical role / type",
      "example": "English sentence only. NO Russian translation here.",
      "image_query": "2-4 word concrete English noun phrase for a photo of this word"
    }}
  ],
  "hashtags": ["#tags"]
}}

Generate exactly {count} vocabulary items, ordered from most common/simple to more complex.
IMPORTANT: Each image_query must picture the WORD itself as a concrete, photographable object or scene related to topic '{topic}'."""

    if not (config.is_ai_ready() and ai_engine.is_antigravity_cli_authenticated()):
        logger.info(f"AI engine offline/unauthenticated, using educational fallback for vocabulary: {topic}")
        return content_fallback.generate_fallback_vocabulary_table(topic, level, count, bloom_level)

    try:
        data = await ai_engine.generate_json(prompt, system_instruction=SYSTEM_PROMPT)
    except Exception as e:
        logger.warning(f"AI engine failed for vocabulary ({e}), using educational fallback")
        return content_fallback.generate_fallback_vocabulary_table(topic, level, count, bloom_level)

    logger.info(f"✅ Generated vocabulary table: {data.get('title')} ({len(data.get('rows', []))} items)")
    return data


async def generate_flashcards(topic: str, level: str, count: int = 12) -> dict:
    """Generate simple flashcards (type 5)."""
    level_guide = LEVEL_GUIDES.get(level, LEVEL_GUIDES["A2"])

    prompt = f"""Create ESL flashcards about "{topic}" for level {level}.
Level guide: {level_guide}

Return JSON:
{{
  "title": "Title with emoji",
  "topic": "{topic}",
  "level": "{level}",
  "instruction": "Instruction in Russian",
  "cards": [
    {{
      "id": 1,
      "front": "English word or phrase",
      "back": "Russian translation",
      "transcription": "[IPA]",
      "example": "Example sentence"
    }}
  ],
  "hashtags": ["#tags"]
}}

Generate {count} flashcards."""

    if not (config.is_ai_ready() and ai_engine.is_antigravity_cli_authenticated()):
        logger.info(f"AI engine offline/unauthenticated, using educational fallback for flashcards: {topic}")
        return content_fallback.generate_fallback_flashcards(topic, level, count)

    try:
        data = await ai_engine.generate_json(prompt, system_instruction=SYSTEM_PROMPT)
    except Exception as e:
        logger.warning(f"AI engine failed for flashcards ({e}), using educational fallback")
        return content_fallback.generate_fallback_flashcards(topic, level, count)

    logger.info(f"✅ Generated flashcards: {data.get('title')}")
    return data


async def generate_fill_blanks(
    topic: str,
    level: str,
    count: int = 10,
    vision_context: dict | None = None,
    bloom_level: str | None = None,
    bloom_instructions: str | None = None
) -> dict:
    """Generate fill-in-the-blanks table (type 6). Enforces minimum 10 sentences."""
    count = max(int(count or 10), 10)

    # If vision agent extracted original worksheet sentences from textbook image:
    if vision_context and (vision_context.get("worksheet_sentences") or vision_context.get("sentences")):
        raw_sents = vision_context.get("worksheet_sentences") or vision_context.get("sentences")
        if len(raw_sents) >= 2:
            formatted_sentences = []
            for idx, s in enumerate(raw_sents[:count], 1):
                formatted_sentences.append({
                    "id": idx,
                    "sentence_with_blank": s.get("sentence_with_blank") or s.get("sentence") or "",
                    "answer": s.get("answer") or "",
                    "translation": s.get("hint") or s.get("translation") or ""
                })
            wb = vision_context.get("word_bank") or [s["answer"] for s in formatted_sentences if s.get("answer")]
            title = vision_context.get("topic") or vision_context.get("worksheet_title") or f"✏️ {topic} Fill in the Blanks"
            instruction = vision_context.get("instruction") or "👉 Вставьте подходящие слова из банка слов в пропуски предложений."
            logger.info(f"✅ Generated fill_blanks directly from Vision Agent: {title} ({len(formatted_sentences)} sentences)")
            return {
                "title": title[:60],
                "topic": topic,
                "level": level,
                "instruction": instruction,
                "word_bank": wb,
                "sentences": formatted_sentences,
                "hashtags": [f"#{topic.lower().replace(' ', '_')}", f"#{level.lower()}", "#fillblanks", "#worksheet", "#english"]
            }

    level_guide = LEVEL_GUIDES.get(level, LEVEL_GUIDES["A2"])
    vision_section = _build_vision_prompt_section(vision_context)

    bloom_section = ""
    if bloom_instructions or bloom_level:
        bloom_section = f"""
BLOOM'S TAXONOMY COGNITIVE FOCUS (Level: {bloom_level or 'APPLY'}):
{bloom_instructions or 'Sentences must model authentic, realistic situations where the learner applies the targeted grammar or vocabulary.'}
"""

    prompt = f"""Create ESL fill-in-the-blank sentences about "{topic}" for level {level}.
Level guide: {level_guide}
{vision_section}
{bloom_section}

Return JSON:
{{
  "title": "Title with emoji",
  "topic": "{topic}",
  "level": "{level}",
  "instruction": "Instruction in Russian",
  "word_bank": ["word1", "word2", "word3"],
  "sentences": [
    {{
      "id": 1,
      "sentence_with_blank": "I ___ my cat every day.",
      "answer": "feed",
      "translation": "Russian translation of full sentence"
    }}
  ],
  "hashtags": ["#tags"]
}}

Generate exactly {count} sentences (NOT fewer than 10). Include all answers in the word bank (shuffled)."""

    if not (config.is_ai_ready() and ai_engine.is_antigravity_cli_authenticated()):
        logger.info(f"AI engine offline/unauthenticated, using educational fallback for fill blanks: {topic}")
        return content_fallback.generate_fallback_fill_blanks(topic, level, count, bloom_level)

    try:
        data = await ai_engine.generate_json(prompt, system_instruction=SYSTEM_PROMPT)
    except Exception as e:
        logger.warning(f"AI engine failed for fill blanks ({e}), using educational fallback")
        return content_fallback.generate_fallback_fill_blanks(topic, level, count, bloom_level)

    if not data or "sentences" not in data:
        data = content_fallback.generate_fallback_fill_blanks(topic, level, count, bloom_level)

    if len(data.get("sentences", [])) < count:
        logger.warning(f"Requested {count} fill_blanks, got {len(data.get('sentences', []))}. Supplementing from educational database...")
        fallback_data = content_fallback.generate_fallback_fill_blanks(topic, level, count, bloom_level)
        existing_s = {s.get("sentence_with_blank", "").strip().lower() for s in data.get("sentences", [])}
        for fs in fallback_data.get("sentences", []):
            if fs.get("sentence_with_blank", "").strip().lower() not in existing_s:
                fs["id"] = len(data["sentences"]) + 1
                data["sentences"].append(fs)
                if fs.get("answer") and fs["answer"] not in data.get("word_bank", []):
                    data.setdefault("word_bank", []).append(fs["answer"])
            if len(data["sentences"]) >= count:
                break

    # Shuffle word bank
    if "word_bank" in data and isinstance(data["word_bank"], list):
        random.shuffle(data["word_bank"])

    logger.info(f"✅ Generated fill-blanks: {data.get('title')} ({len(data.get('sentences', []))} sentences)")
    return data


async def clarify_missing_params(command: str, missing: list[str]) -> dict:
    """Ask the AI to extract or suggest missing parameters from a vague command."""
    prompt = f"""The user gave this command: "{command}"
Missing parameters: {missing}

Based on the command, suggest values for the missing parameters.
Return ONLY JSON: {{"level": "A2", "count": 10, "topic": "..."}}
Use reasonable ESL teaching defaults if you can't determine from context."""

    return await ai_engine.generate_json(prompt, system_instruction=SYSTEM_PROMPT)


async def generate_speaking_cards(
    topic: str,
    level: str,
    count: int = 12,
    vision_context: dict | None = None,
    bloom_level: str | None = None,
    bloom_instructions: str | None = None
) -> dict:
    """Generate speaking / discussion cards (type 7).
    
    Each card has a speaking prompt/question with an image for visual stimulus.
    Supports Bloom's taxonomy:
    - EVALUATE: dilemmas, rating scales, debate questions.
    - CREATE: roleplay scenarios, missions, storytelling.
    - REMEMBER/APPLY: warm-up prompts, personal application.
    """
    level_guide = LEVEL_GUIDES.get(level, LEVEL_GUIDES["A2"])
    vision_section = _build_vision_prompt_section(vision_context)

    bloom_section = ""
    if bloom_instructions or bloom_level:
        bloom_section = f"""
BLOOM'S TAXONOMY COGNITIVE FOCUS (Level: {bloom_level or 'EVALUATE/CREATE'}):
{bloom_instructions or 'Create engaging, deep prompts encouraging evaluation, critical defense of opinions, or creative roleplay.'}
"""

    prompt = f"""Create ESL speaking/discussion cards for an activity about "{topic}" for level {level}.
Level guide: {level_guide}
{vision_section}
{bloom_section}

Each card contains a speaking prompt or discussion question that students can respond to.
Cards should encourage authentic, spontaneous speech production.

Return JSON:
{{
  "title": "Speaking activity title with emoji",
  "topic": "{topic}",
  "level": "{level}",
  "instruction": "Instruction in Russian (discuss questions with your partner)",
  "cards": [
    {{
      "id": 1,
      "emoji": "relevant emoji for the question",
      "question": "Open-ended speaking question in English (simple, engaging)",
      "follow_up": "Optional follow-up question for deeper discussion",
      "color": "#hex_color (choose from palette below)"
    }}
  ],
  "hashtags": ["#warmup", "#speaking", "#level_tag", "#topic_tag", "#esl"]
}}

Generate exactly {count} cards. Use VARIED, vibrant colors from this palette:
["#7c3aed", "#0891b2", "#16a34a", "#d97706", "#dc2626", "#2563eb", "#be185d", "#65a30d", "#0d9488", "#7c2d12"]

Make questions:
- Open-ended (not yes/no)
- Age-appropriate and culturally neutral
- Progressively increasing in complexity (simple first, complex last)
- Personally engaging (about the student's experience/opinions)"""

    if not (config.is_ai_ready() and ai_engine.is_antigravity_cli_authenticated()):
        logger.info(f"AI engine offline/unauthenticated, using educational fallback for speaking cards: {topic}")
        return content_fallback.generate_fallback_speaking_cards(topic, level, count, bloom_level)

    try:
        data = await ai_engine.generate_json(prompt, system_instruction=SYSTEM_PROMPT)
    except Exception as e:
        logger.warning(f"AI engine failed for speaking cards ({e}), using educational fallback")
        return content_fallback.generate_fallback_speaking_cards(topic, level, count, bloom_level)

    logger.info(f"✅ Generated speaking cards: {data.get('title')} ({len(data.get('cards', []))} cards)")
    return data


async def generate_unified_bloom_lesson(
    topic: str,
    level: str,
    student_profile: dict,
    bloom_arc: list,
    counts: dict = None
) -> dict:
    """
    Generates an entire coherent Bloom lesson package in a SINGLE LLM call.
    Saves ~5,000 tokens and reduces latency by 3-4x compared to 5 sequential calls.
    Vocabulary words directly align across all 4 activities for superior pedagogical cohesion.
    """
    counts = counts or {"cards": 5, "vocab": 8, "quiz": 10, "fill": 10}
    c_cards = counts.get("cards", 5)
    c_vocab = counts.get("vocab", 8)
    c_quiz = max(counts.get("quiz", 10), 10)
    c_fill = max(counts.get("fill", 10), 10)

    st_name = student_profile.get("name", "Student")
    st_age = student_profile.get("age", 12)
    interests = ", ".join(student_profile.get("interests", [])) or "general topics"
    level_guide = LEVEL_GUIDES.get(level, LEVEL_GUIDES["A2"])

    prompt = f"""Create a COMPLETE, UNIFIED ESL LESSON PACKAGE on "{topic}" for student {st_name} ({st_age} y.o., level {level}).
Interests: {interests}. Level guide: {level_guide}.

RULE 20A: All 'instruction' fields MUST start with '👉 ' and be in clear Russian.
RULE: All questions, sentences, and options MUST be 100% in natural, authentic English.
RULE: Quiz MUST have exactly 4 plausible options (A, B, C, D) per question.
RULE: Cohesion — vocabulary words from the table MUST be actively reused in the fill-in-blanks and quiz!

Generate a SINGLE cohesive JSON with:
{{
  "teacher_guide": "Brief bulleted teacher cheat sheet (Remember, Apply, Evaluate, Create, Focus, Icebreaker, HW) with emoji and '•', strictly NO markdown formatting (no **, ###, pipes)",
  "speaking_cards": {{
    "title": "🗣️ {topic} Warm-up & Discussion",
    "topic": "{topic}",
    "level": "{level}",
    "instruction": "👉 Обсудите вопросы с преподавателем или одногруппником",
    "cards": [
      {{"id": 1, "emoji": "💬", "question": "Open-ended speaking prompt", "follow_up": "Follow-up question", "color": "#7c3aed"}}
    ]
  }},
  "vocabulary_table": {{
    "title": "📚 {topic} Vocabulary",
    "topic": "{topic}",
    "level": "{level}",
    "instruction": "👉 Изучите новые слова, транскрипцию и примеры в контексте",
    "words": [
      {{"id": 1, "word": "target word", "transcription": "[IPA]", "translation": "перевод", "context": "example sentence"}}
    ]
  }},
  "quiz_photo": {{
    "title": "🎯 {topic} Interactive Quiz",
    "topic": "{topic}",
    "level": "{level}",
    "instruction": "👉 Выберите один правильный вариант ответа для каждого вопроса",
    "questions": [
      {{"id": 1, "sentence": "Question or sentence with ___", "options": ["opt1", "opt2", "opt3", "opt4"], "correct_index": 0, "image_query": "English photo search phrase", "explanation": "Why correct"}}
    ]
  }},
  "fill_blanks": {{
    "title": "✏️ {topic} Fill in the Blanks",
    "topic": "{topic}",
    "level": "{level}",
    "instruction": "👉 Вставьте подходящие слова из банка слов в пропуски",
    "word_bank": ["word1", "word2", "word3"],
    "sentences": [
      {{"id": 1, "text": "Sentence with ___ gap", "answer": "correct_word", "options": ["correct_word", "distractor1", "distractor2", "distractor3"]}}
    ]
  }}
}}
Generate exactly: {c_cards} speaking cards, {c_vocab} vocabulary words, {c_quiz} quiz questions, and {c_fill} fill-in sentences.
"""
    if not (config.is_ai_ready() and ai_engine.is_antigravity_cli_authenticated()):
        raise RuntimeError("AI engine offline for unified lesson generation")

    data = await ai_engine.generate_json(prompt, system_instruction=SYSTEM_PROMPT)

    if "quiz_photo" in data and "questions" in data["quiz_photo"]:
        data["quiz_photo"]["questions"] = _normalize_and_shuffle_quiz_questions(data["quiz_photo"]["questions"])

    logger.info(f"✅ Generated UNIFIED lesson package for {topic} (1 LLM call)")
    return data

