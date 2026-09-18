"""
ESL Figma AI — Layout Agent
Converts structured content JSON into Figma draw commands.
Knows all visual rules: colors, typography, spacing, grouping.
"""
import logging
from server import config, bridge
from server.agents import toc_agent, image_agent

logger = logging.getLogger("layout_agent")


def _design() -> dict:
    return {
        "colors": config.colors(),
        "typography": config.typography(),
        "layout": config.layout_cfg(),
    }


async def draw_quiz_photo(content: dict) -> dict:
    """Draw photo quiz (Type 1). Resolves images per-question via ImageAgent."""
    logger.info(f"Drawing quiz_photo: {content.get('title')}")
    design = _design()
    image_mode = content.get("image_mode", "auto")

    has_images = content.get("has_images", False)
    questions_data = content.get("questions", [])
    if has_images:
        questions_data = await image_agent.resolve_batch_images(
            questions_data,
            topic=content.get("topic", ""),
            item_query_key="image_query",
            image_mode=image_mode,
        )

    result = await bridge.send_command("DRAW_QUIZ_PHOTO", {
        "title": content["title"],
        "level": content.get("level", "A2"),
        "instruction": content.get("instruction", "Choose the correct answer!"),
        "questions": questions_data,
        "has_images": has_images,
        "hashtags": content.get("hashtags", []),
        "design": design,
        "block_type": "quiz_photo",
        "replaceNodeId": content.get("replaceNodeId"),
    }, timeout=90.0)

    if result.get("ok") and result.get("nodeId"):
        await toc_agent.register_block("quiz_photo", content["title"], result["nodeId"])

    return result


async def draw_flip_cards(content: dict) -> dict:
    """Draw flip/reveal cards block (Type 2)."""
    logger.info(f"Drawing flip_cards: {content.get('title')}")
    design = _design()

    cards_data = content.get("cards", [])
    cards_with_images = await image_agent.resolve_batch_images(
        cards_data,
        topic=content.get("topic", "english"),
        item_query_key="image_query"
    )

    result = await bridge.send_command("DRAW_FLIP_CARDS", {
        "title": content["title"],
        "level": content.get("level", "A2"),
        "instruction": content.get("instruction", "Click a card to reveal the question!"),
        "cards": cards_with_images,
        "hashtags": content.get("hashtags", []),
        "design": design,
        "block_type": "flip_cards",
        "replaceNodeId": content.get("replaceNodeId"),
    }, timeout=90.0)

    if result.get("ok") and result.get("nodeId"):
        await toc_agent.register_block("flip_cards", content["title"], result["nodeId"])

    return result


async def draw_video_quiz(content: dict) -> dict:
    """Draw a video comprehension quiz block (Type 3)."""
    logger.info(f"Drawing video_quiz: {content.get('title')}")
    design = _design()

    result = await bridge.send_command("DRAW_VIDEO_QUIZ", {
        "title": content["title"],
        "level": content.get("level", "B1"),
        "instruction": content.get("instruction", ""),
        "youtube_url": content.get("youtube_url", ""),
        "vocabulary": content.get("vocabulary", []),
        "questions": content.get("questions", []),
        "hashtags": content.get("hashtags", []),
        "design": design,
        "block_type": "video_quiz",
        "replaceNodeId": content.get("replaceNodeId"),
    }, timeout=90.0)

    if result.get("ok") and result.get("nodeId"):
        await toc_agent.register_block("video_quiz", content["title"], result["nodeId"])

    return result


async def draw_vocabulary_table(content: dict) -> dict:
    """Draw vocabulary table with translation (Type 4). Supports images per row."""
    logger.info(f"Drawing vocabulary_table: {content.get('title')}")
    design = _design()
    image_mode = content.get("image_mode", "auto")

    rows_data = content.get("rows", [])

    # Resolve images for each vocabulary row (image in first column)
    rows_with_images = await image_agent.resolve_batch_images(
        rows_data,
        topic=content.get("topic", "english"),
        item_query_key="image_query",
        image_mode=image_mode,
    )

    result = await bridge.send_command("DRAW_VOCABULARY_TABLE", {
        "title": content["title"],
        "level": content.get("level", "A2"),
        "instruction": content.get("instruction", ""),
        "columns": content.get("columns", []),
        "rows": rows_with_images,
        "hashtags": content.get("hashtags", []),
        "design": design,
        "block_type": "vocabulary_table",
        "replaceNodeId": content.get("replaceNodeId"),
    }, timeout=90.0)

    if result.get("ok") and result.get("nodeId"):
        await toc_agent.register_block("vocabulary_table", content["title"], result["nodeId"])

    return result


async def draw_flashcards(content: dict) -> dict:
    """Draw simple flashcards (Type 5)."""
    logger.info(f"Drawing flashcards: {content.get('title')}")
    design = _design()

    result = await bridge.send_command("DRAW_FLASHCARDS", {
        "title": content["title"],
        "level": content.get("level", "A2"),
        "instruction": content.get("instruction", ""),
        "cards": content.get("cards", []),
        "hashtags": content.get("hashtags", []),
        "design": design,
        "block_type": "flashcards",
        "replaceNodeId": content.get("replaceNodeId"),
    }, timeout=90.0)

    if result.get("ok") and result.get("nodeId"):
        await toc_agent.register_block("flashcards", content["title"], result["nodeId"])

    return result


async def draw_fill_blanks(content: dict) -> dict:
    """Draw fill-in-the-blanks table (Type 6)."""
    logger.info(f"Drawing fill_blanks: {content.get('title')}")
    design = _design()

    result = await bridge.send_command("DRAW_FILL_BLANKS", {
        "title": content["title"],
        "level": content.get("level", "A2"),
        "instruction": content.get("instruction", ""),
        "word_bank": content.get("word_bank", []),
        "sentences": content.get("sentences", []),
        "hashtags": content.get("hashtags", []),
        "design": design,
        "block_type": "fill_blanks",
        "replaceNodeId": content.get("replaceNodeId"),
    }, timeout=90.0)

    if result.get("ok") and result.get("nodeId"):
        await toc_agent.register_block("fill_blanks", content["title"], result["nodeId"])

    return result


async def draw_speaking_cards(content: dict) -> dict:
    """Draw speaking/warmup cards (Type 7)."""
    logger.info(f"Drawing speaking_cards: {content.get('title')}")
    design = _design()

    cards_data = content.get("cards", [])
    cards_with_images = await image_agent.resolve_batch_images(
        cards_data,
        topic=content.get("topic", "discussion"),
        item_query_key="image_query"
    )

    result = await bridge.send_command("DRAW_SPEAKING_CARDS", {
        "title": content["title"],
        "level": content.get("level", "A2"),
        "instruction": content.get("instruction", ""),
        "cards": cards_with_images,
        "hashtags": content.get("hashtags", []),
        "design": design,
        "block_type": "speaking_cards",
        "replaceNodeId": content.get("replaceNodeId"),
    }, timeout=90.0)

    if result.get("ok") and result.get("nodeId"):
        await toc_agent.register_block("speaking_cards", content["title"], result["nodeId"])

    return result
