"""
ESL Figma AI — Vision Agent
Dedicated multimodal agent for analyzing images selected on the Figma/FigJam canvas.
Extracts visual details, objects, context, and generates pedagogical lesson plans/content.
"""
import base64
import json
import logging
import os
import time
from pathlib import Path
from server import config, agent_logger
from server.agents import ai_engine

logger = logging.getLogger("vision_agent")

CACHE_DIR = Path(__file__).parent.parent / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


VISION_PROMPT_TEMPLATE = """You are an expert ESL pedagogical Vision Agent.
Analyze the provided image file located at:
{image_path}

The teacher provided this image (uploaded or selected on canvas) and gave the instruction:
Teacher's prompt: "{command}"
Target CEFR Level: {level}

CRITICAL PEDAGOGICAL RULE:
- If this image contains an existing exercise, textbook page, or worksheet (e.g. fill in the blanks, grammar sentences, multiple choice test, vocabulary list):
  DO NOT invent fictional questions! DO NOT invent abstract stories!
  TRANSCRIBE THE EXACT EXERCISES AND SENTENCES DIRECTLY FROM THE IMAGE 1-TO-1!
  Extract all sentences, blanks, target grammar words, and word banks faithfully.
- If it is an authentic photo or illustration (not a worksheet):
  Identify all key objects, characters, actions, and details to design a lively game based on what is visible.

Return ONLY valid JSON adhering to this schema:
{{
  "topic": "Title for the activity with emoji (e.g. ✏️ Present Simple • Textbook Exercise 3)",
  "is_worksheet": true,
  "worksheet_title": "Original title or exercise heading from the sheet",
  "pedagogical_purpose": "Exact grammar rule or skill being practiced",
  "scene_description": "Summary of what is depicted in 1-2 sentences",
  "objects_found": ["item1", "item2", "item3"],
  "recommended_block_type": "fill_blanks|quiz_photo|vocabulary_table|flip_cards",
  "instruction": "Instruction in Russian for the student (e.g. '👉 Вставьте пропущенные слова в предложения')",
  "word_bank": ["word1", "word2", "word3", "word4"],
  "worksheet_sentences": [
    {{
      "sentence_with_blank": "1. She _____ to school every morning.",
      "answer": "walks",
      "hint": "Present Simple (walk)"
    }}
  ],
  "questions": [
    {{
      "id": 1,
      "question": "Exact question or sentence from sheet (e.g. '1. Where does Mark live?')",
      "options": ["In London", "In Paris", "In New York"],
      "correct": "In London",
      "image_query": "specific concrete English phrase for photo search (e.g. 'London red bus Big Ben')",
      "explanation": "Pedagogical explanation of the rule"
    }}
  ],
  "vocabulary": [
    {{"word": "word", "transcription": "[...]", "translation": "перевод", "context": "example sentence"}}
  ]
}}
"""


def optimize_image_for_vision(raw_bytes: bytes, max_dim: int = 1024, quality: int = 85) -> bytes:
    """Downscales image to max_dim and compresses to JPEG to save LLM multimodal tokens while preserving OCR clarity."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(raw_bytes))
        w, h = img.size
        if max(w, h) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = buf.getvalue()
        if len(compressed) < len(raw_bytes):
            return compressed
    except Exception as e:
        logger.debug(f"Vision image optimization skipped: {e}")
    return raw_bytes


async def analyze_image(image_base64: str, command: str = "", level: str = "A2") -> dict:
    """
    Save image to cache, analyze it using multimodal AI, and produce structured pedagogical context.
    """
    if not image_base64:
        return {}

    # Strip any data URI header
    clean_b64 = image_base64.strip()
    if "," in clean_b64:
        clean_b64 = clean_b64.split(",", 1)[1]

    # Save to disk cache
    img_filename = f"canvas_selection_{int(time.time() * 1000)}.jpg"
    img_path = CACHE_DIR / img_filename
    try:
        raw_bytes = base64.b64decode(clean_b64)
        vision_bytes = optimize_image_for_vision(raw_bytes, max_dim=1024, quality=85)
        with open(img_path, "wb") as f:
            f.write(vision_bytes)
    except Exception as e:
        logger.error(f"Failed to save selected canvas image: {e}")
        return {}


    norm_path = str(img_path).replace("\\", "/")

    agent_logger.emit_log(
        stage="analyzing",
        icon="👁️",
        title="Vision Agent: Анализ картинки",
        message="Анализирую изображение с холста Figma/FigJam...",
        detail=f"Файл: {img_filename} ({len(raw_bytes):,} байт)"
    )

    prompt = VISION_PROMPT_TEMPLATE.format(
        image_path=norm_path,
        command=command or "Создай интерактивное задание по этой картинке",
        level=level or "A2"
    )

    # First attempt: if user has Gemini API key, use direct multimodal call with PIL Image
    vision_result = None
    if config.gemini_api_key():
        try:
            import google.generativeai as genai
            from PIL import Image
            import io

            genai.configure(api_key=config.gemini_api_key())
            pil_img = Image.open(io.BytesIO(raw_bytes))
            model = genai.GenerativeModel("gemini-2.0-flash")
            loop = ai_engine.asyncio.get_event_loop()

            def _call_gemini():
                res = model.generate_content([
                    pil_img,
                    f"You are an expert ESL teacher. The teacher asked: '{command}'. Level: {level}.\n"
                    "Analyze this image and return valid JSON adhering to:\n"
                    '{"topic": "...", "scene_description": "...", "objects_found": [...], '
                    '"recommended_block_type": "quiz_photo", "pedagogical_plan": "...", '
                    '"vocabulary": [{"word": "...", "transcription": "...", "translation": "...", "context": "..."}], '
                    '"questions": [{"question": "...", "options": ["A", "B", "C"], "correct": "A", "explanation": "..."}]}'
                ])
                return res.text.strip()

            raw_text = await loop.run_in_executor(None, _call_gemini)
            vision_result = ai_engine._extract_json(raw_text)
            logger.info("Vision Agent: successfully analyzed via Gemini API")
        except Exception as e:
            logger.warning(f"Gemini API vision failed ({e}), falling back to Antigravity CLI...")

    # Second attempt: Antigravity CLI with file viewing inspection
    if not vision_result:
        try:
            logger.info(f"Vision Agent: analyzing image via Antigravity CLI on {norm_path}...")
            vision_result = await ai_engine.generate_json(
                prompt,
                system_instruction=(
                    "You are an expert ESL Vision Agent. You have access to local file viewing tools. "
                    "View and inspect the provided image file carefully, analyze its contents, and return valid JSON."
                )
            )
        except Exception as e:
            logger.error(f"Vision Agent CLI analysis failed: {e}")
            return {
                "topic": "Visual Game",
                "scene_description": "Картинка с холста",
                "objects_found": [],
                "recommended_block_type": "quiz_photo",
                "image_base64": image_base64,
                "image_path": norm_path,
            }

    # Extract insights
    desc = vision_result.get("scene_description", "")
    objects = vision_result.get("objects_found", [])
    rec_type = vision_result.get("recommended_block_type", "quiz_photo")
    plan = vision_result.get("pedagogical_plan", "")
    topic = vision_result.get("topic", "Picture Discovery")

    agent_logger.emit_log(
        stage="thinking",
        icon="🔍",
        title="Vision Agent: Распознавание сюжета",
        message=f"Найдено: {desc[:90]}...",
        detail=f"Объекты: {', '.join(objects[:6]) if objects else 'детали сюжета'}"
    )

    agent_logger.emit_log(
        stage="thinking",
        icon="💡",
        title="Vision Agent: Педагогический план",
        message=f"Рекомендован формат «{rec_type}»: {plan[:100]}",
        detail=f"Уровень: {level} | Тема: {topic}"
    )

    vision_result["image_base64"] = image_base64
    vision_result["image_path"] = norm_path
    return vision_result


async def analyze_batch_images(images: list[dict], command: str = "", level: str = "A2") -> dict:
    """
    Analyze multiple images simultaneously (from Telegram upload or Figma canvas selection).
    Uses multimodal Gemini 2.0 or Antigravity CLI to create a cohesive pedagogical activity
    mapping each image 1-to-1 to quiz questions, speaking prompts, or vocabulary rows.
    """
    if not images or not isinstance(images, list):
        return {}

    # Limit batch to maximum 15 images to avoid token overload
    images = images[:15]
    total_imgs = len(images)

    agent_logger.emit_log(
        stage="analyzing",
        icon="📸",
        title=f"Vision Agent: Пакетный анализ ({total_imgs} фото)",
        message=f"Обрабатываю коллекцию из {total_imgs} изображений для создания упражнения...",
        detail=f"Запрос: {command or 'Интерактивное задание'} | Уровень: {level}"
    )

    # Save all images to local cache
    saved_files = []
    ts = int(time.time() * 1000)
    for i, item in enumerate(images):
        b64 = item.get("image_base64", "").strip()
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        try:
            raw_bytes = base64.b64decode(b64)
            vision_bytes = optimize_image_for_vision(raw_bytes, max_dim=800, quality=80)
            img_name = f"batch_{ts}_{i}_{item.get('name', 'img')[:15].replace(' ', '_')}.jpg"
            img_path = CACHE_DIR / img_name
            with open(img_path, "wb") as f:
                f.write(vision_bytes)
            saved_files.append({
                "index": i,
                "name": item.get("name") or f"Photo {i+1}",
                "path": str(img_path).replace("\\", "/"),
                "bytes": vision_bytes,
                "image_base64": b64
            })

        except Exception as e:
            logger.warning(f"Failed to decode batch image #{i}: {e}")

    if not saved_files:
        return {}

    prompt_instructions = f"""You are an expert ESL pedagogical Vision Agent.
The teacher provided {len(saved_files)} authentic images and gave this instruction:
Teacher's prompt: "{command or 'Создай увлекательное задание по этим картинкам'}"
Target CEFR Level: {level}

CRITICAL RULES:
1. Examine EACH of the {len(saved_files)} images individually.
2. Formulate a cohesive lesson activity (e.g. Quiz, Speaking Discussion Cards, or Vocabulary Table).
3. For each question or card, link it to the exact image (use 0-based image_index from 0 to {len(saved_files)-1}).
4. Keep questions engaging, communicative, age-appropriate, and strictly true to what is visible in that specific image.
5. In quiz questions, provide 4 options (A, B, C, D) with realistic choices and 1 correct answer.

Output ONLY valid JSON adhering to:
{{
  "topic": "Creative Emoji Title (e.g. 📸 Family Life & Weekend Activities)",
  "shared_theme": "General theme connecting the pictures",
  "recommended_block_type": "quiz_photo|speaking_cards|vocabulary_table|flip_cards",
  "pedagogical_purpose": "Grammar rule, vocabulary domain, or speaking goal",
  "scenes": [
    {{"image_index": 0, "title": "...", "description": "1 sentence summary of image 0", "key_words": ["word1", "word2"]}}
  ],
  "questions": [
    {{
      "id": 1,
      "image_index": 0,
      "question": "Clear English question about what is happening or visible in Image 0",
      "options": ["Correct Answer", "Distractor 1", "Distractor 2", "Distractor 3"],
      "correct": "Correct Answer",
      "explanation": "Why this answer is correct based on the picture"
    }}
  ],
  "speaking_cards": [
    {{
      "id": 1,
      "image_index": 0,
      "title": "Short title",
      "question": "Engaging speaking prompt for the student based on Image 0",
      "follow_up": "Follow-up question"
    }}
  ],
  "vocabulary": [
    {{
      "image_index": 0,
      "word": "Target Word",
      "transcription": "[...]",
      "translation": "Перевод на русский",
      "context": "Short sentence illustrating the word in context of the photo"
    }}
  ]
}}
"""

    result = None

    # 1. Direct Multimodal Gemini API call with PIL images
    if config.gemini_api_key():
        try:
            import google.generativeai as genai
            from PIL import Image
            import io

            genai.configure(api_key=config.gemini_api_key())
            model_name = config.gemini_model() or "gemini-2.0-flash"
            if "flash" not in model_name:
                model_name = "gemini-2.0-flash"
            model = genai.GenerativeModel(model_name)
            loop = ai_engine.asyncio.get_event_loop()

            contents = []
            for f_info in saved_files:
                pil_img = Image.open(io.BytesIO(f_info["bytes"]))
                contents.append(f"--- Image {f_info['index']} (File: {f_info['name']}) ---")
                contents.append(pil_img)
            contents.append(prompt_instructions)

            def _call_gemini():
                res = model.generate_content(contents)
                return res.text.strip()

            raw_text = await loop.run_in_executor(None, _call_gemini)
            result = ai_engine._extract_json(raw_text)
            logger.info(f"Vision Agent: successfully analyzed {len(saved_files)} images via Gemini API")
        except Exception as e:
            logger.warning(f"Gemini API batch vision failed ({e}), falling back to Antigravity CLI...")

    # 2. Antigravity CLI fallback
    if not result:
        try:
            file_paths_str = "\n".join([f"- Image {f['index']}: {f['path']} (Name: {f['name']})" for f in saved_files])
            cli_prompt = f"Available images on disk:\n{file_paths_str}\n\n{prompt_instructions}"
            result = await ai_engine.generate_json(
                cli_prompt,
                system_instruction="You are an expert ESL Vision Agent. Inspect the provided image files and generate structured JSON."
            )
        except Exception as cli_err:
            logger.error(f"Antigravity CLI batch vision failed: {cli_err}")

    # 3. Fallback generator if LLM is unavailable
    if not result or not isinstance(result, dict):
        result = _generate_batch_fallback(saved_files, command, level)

    # 4. Bind original image_base64 to each generated question, card, and vocab item!
    if "questions" in result and isinstance(result["questions"], list):
        for q in result["questions"]:
            idx = q.get("image_index", 0)
            if 0 <= idx < len(saved_files):
                q["image_base64"] = saved_files[idx]["image_base64"]
                q["image_query"] = saved_files[idx]["name"]

    if "speaking_cards" in result and isinstance(result["speaking_cards"], list):
        for c in result["speaking_cards"]:
            idx = c.get("image_index", 0)
            if 0 <= idx < len(saved_files):
                c["image_base64"] = saved_files[idx]["image_base64"]
                c["image_query"] = saved_files[idx]["name"]

    if "vocabulary" in result and isinstance(result["vocabulary"], list):
        for v in result["vocabulary"]:
            idx = v.get("image_index", 0)
            if 0 <= idx < len(saved_files):
                v["image_base64"] = saved_files[idx]["image_base64"]

    result["staged_images"] = saved_files
    result["total_images"] = len(saved_files)

    agent_logger.emit_log(
        stage="thinking",
        icon="✨",
        title="Vision Agent: Анализ завершён",
        message=f"Сформирован педагогический план: «{result.get('topic', 'Фото-урок')}»",
        detail=f"Вопросов/карточек: {len(result.get('questions', [])) or len(result.get('speaking_cards', []))} шт."
    )

    return result


def _generate_batch_fallback(saved_files: list[dict], command: str, level: str) -> dict:
    """Generate reliable pedagogical content for batch images when LLM is unavailable."""
    questions = []
    speaking_cards = []
    vocab = []
    scenes = []

    for i, f in enumerate(saved_files):
        clean_name = f["name"].replace("_", " ").split(".")[0].strip()
        scenes.append({
            "image_index": i,
            "title": f"Scene {i+1}: {clean_name}",
            "description": f"Photograph depicting {clean_name}.",
            "key_words": [clean_name, "scene", "action"]
        })
        questions.append({
            "id": i + 1,
            "image_index": i,
            "question": f"Look at photo {i+1} ({clean_name}). What is the most noticeable detail?",
            "options": [f"Details related to {clean_name}", "Empty room", "Night sky", "Ancient ruins"],
            "correct": f"Details related to {clean_name}",
            "explanation": f"The photograph clearly illustrates {clean_name}."
        })
        speaking_cards.append({
            "id": i + 1,
            "image_index": i,
            "title": f"Photo #{i+1}: {clean_name}",
            "question": f"Describe what you see in this picture. How does this scene make you feel?",
            "follow_up": "Have you ever experienced something similar?"
        })
        vocab.append({
            "image_index": i,
            "word": clean_name.capitalize(),
            "transcription": "[...]",
            "translation": clean_name,
            "context": f"This photograph shows {clean_name} in everyday life."
        })

    return {
        "topic": f"📸 Picture Discovery • {len(saved_files)} Photos [{level}]",
        "shared_theme": "Visual English Practice",
        "recommended_block_type": "quiz_photo",
        "pedagogical_purpose": "Describing authentic pictures and developing visual vocabulary",
        "scenes": scenes,
        "questions": questions,
        "speaking_cards": speaking_cards,
        "vocabulary": vocab
    }

