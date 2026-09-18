"""
ESL Figma AI — TOC (Table of Contents) Agent
Manages the auto-updating navigation index on the Figma board.
"""
import logging
from server import bridge, config

logger = logging.getLogger("toc_agent")

# Category column mapping by block type
CATEGORY_MAP = {
    "quiz_photo":        "🎯 Квизы",
    "flip_cards":        "🃏 Открывашки",
    "video_quiz":        "🎬 Видео",
    "vocabulary_table":  "📚 Словари",
    "flashcards":        "🗂 Карточки",
    "fill_blanks":       "✏️ Упражнения",
    "speaking_cards":    "🏃 Разминка",
    "timestamp":         "🕒 Таймлайн",
    "full_lesson":       "🌟 Уроки",
    "custom":            "📌 Разное",
}


async def ensure_toc_exists(board_id: str = None) -> dict:
    """
    Check if a TOC frame exists on the board. If not, create it.
    Returns info about the TOC node.
    """
    result = await bridge.send_command("FIND_TOC", {
        "marker": "__ESL_TOC__",
    })
    if result.get("ok") and result.get("nodeId"):
        return {"exists": True, "nodeId": result["nodeId"]}

    # Create new TOC
    logger.info("Creating new Table of Contents on board...")
    colors = config.colors()
    toc_result = await bridge.send_command("CREATE_TOC", {
        "marker": "__ESL_TOC__",
        "title": "📑 ОГЛАВЛЕНИЕ / TABLE OF CONTENTS",
        "categories": list(CATEGORY_MAP.values()),
        "colors": colors,
        "typography": config.typography(),
        "layout": config.layout_cfg(),
    })
    if toc_result.get("ok"):
        logger.info(f"✅ TOC created: {toc_result.get('nodeId')}")
    return toc_result


async def register_block(block_type: str, block_title: str, block_node_id: str, board_id: str = None) -> dict:
    """
    Add a new entry to the TOC for a newly created block.
    Creates TOC if it doesn't exist yet.
    """
    # Ensure TOC exists
    toc_info = await ensure_toc_exists(board_id)
    if not toc_info.get("ok", True) and not toc_info.get("exists"):
        logger.warning("Could not find or create TOC, skipping registration")
        return {"ok": False, "error": "TOC not available"}

    category = CATEGORY_MAP.get(block_type, CATEGORY_MAP["custom"])

    result = await bridge.send_command("ADD_TOC_ENTRY", {
        "category": category,
        "title": block_title,
        "target_node_id": block_node_id,
        "marker": "__ESL_TOC__",
    })

    if result.get("ok"):
        logger.info(f"✅ TOC entry added: [{category}] {block_title}")
    else:
        logger.warning(f"TOC entry failed: {result.get('error')}")

    return result


async def refresh_toc() -> dict:
    """Rebuild the entire TOC by scanning all blocks on the page."""
    logger.info("Refreshing TOC from all page blocks...")
    result = await bridge.send_command("REFRESH_TOC", {
        "marker": "__ESL_TOC__",
        "category_map": CATEGORY_MAP,
        "colors": config.colors(),
        "typography": config.typography(),
    })
    return result
