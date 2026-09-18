"""
ESL Figma AI — Configuration Manager
Loads and saves config.json, provides typed access to all settings.
"""
import json
import os
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).parent.parent / "config.json"
EXAMPLE_CONFIG_PATH = Path(__file__).parent.parent / "config.example.json"

_config: dict = {}


def load() -> dict:
    global _config
    if not CONFIG_PATH.exists() and EXAMPLE_CONFIG_PATH.exists():
        import shutil
        try:
            shutil.copy2(EXAMPLE_CONFIG_PATH, CONFIG_PATH)
        except Exception:
            pass
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _config = json.load(f)
    else:
        _config = {}
    return _config



def save(data: dict) -> None:
    global _config
    _config = data
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get(path: str, default=None):
    """Dot-notation getter: get('figma.active_board')"""
    parts = path.split(".")
    val = _config
    for part in parts:
        if not isinstance(val, dict):
            return default
        val = val.get(part)
        if val is None:
            return default
    return val


def set_value(path: str, value) -> None:
    """Dot-notation setter, auto-saves."""
    parts = path.split(".")
    d = _config
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value
    save(_config)


def ai_engine() -> str:
    return get("ai.engine", "antigravity")


def gemini_api_key() -> str:
    return get("ai.gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")


def gemini_model() -> str:
    return get("ai.model", "gemini-3.7-flash-medium")


def is_ai_ready() -> bool:
    if ai_engine() == "antigravity":
        return True
    return bool(gemini_api_key())



def active_board() -> str:
    return get("figma.active_board", "tutoring")


def board_info(board_id: Optional[str] = None) -> dict:
    bid = board_id or active_board()
    return get(f"figma.boards.{bid}", {})


def design() -> dict:
    return get("design", {})


def colors() -> dict:
    return get("design.colors", {})


def typography() -> dict:
    return get("design.typography", {})


def layout_cfg() -> dict:
    return get("design.layout", {})


# Load on import
load()
