"""
ESL Figma AI — Live Agent Thought & Activity Logger
Streams real-time agent thoughts, planning stages, and status updates to Web UI and Figma Plugin.
"""
import asyncio
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import logging
from typing import AsyncGenerator, Optional
import uuid

logger = logging.getLogger("agent_logger")


@dataclass
class AgentLogItem:
    id: str
    timestamp: str
    stage: str      # "analyzing", "thinking", "generating", "drawing", "indexing", "done", "error", "warning"
    icon: str       # "🔍", "🧠", "📝", "🎨", "📑", "✅", "⚠️", "❌"
    title: str      # Brief title, e.g. "Анализ запроса"
    message: str    # Simple plain-language explanation
    detail: Optional[str] = None
    agent: str = "🎯 Агент-Оркестратор"


# Ring buffer of recent logs (max 100 items)
_LOG_HISTORY: deque = deque(maxlen=100)

# Subscribers for Server-Sent Events (SSE)
_SUBSCRIBERS: list[asyncio.Queue] = []


def _resolve_agent_name(title: str, stage: str, icon: str, explicit_agent: Optional[str] = None) -> str:
    """Determine human-friendly agent title for UI."""
    if explicit_agent:
        return explicit_agent
    t = (title or "").lower()
    if any(k in t for k in ["контент", "генерац", "текст", "задани", "квиз", "слова"]):
        return "✍️ Агент-Генератор"
    if any(k in t for k in ["картинк", "фото", "иллюстрац", "image", "drawing"]) or icon == "🎨" or stage == "drawing":
        return "🎨 Агент-Иллюстратор"
    if any(k in t for k in ["диалог", "чат", "интервью", "педагог"]):
        return "🧑‍🏫 Педагогический агент"
    if any(k in t for k in ["ученик", "профиль", "досье", "crm", "crm-память"]):
        return "📁 Агент-Менеджер учеников"
    if any(k in t for k in ["оглавлен", "toc", "навигац", "меню"]) or icon == "📑" or stage == "indexing":
        return "📑 Агент-Навигатор"
    if any(k in t for k in ["проверк", "ревиз", "качеств", "валидац", "читаемост"]):
        return "🔍 Агент-Контролер качества"
    if any(k in t for k in ["анализ", "vision", "распознаван", "лист"]) or icon == "🔍":
        return "👁️ Агент-Аналитик"
    return "🎯 Агент-Оркестратор"


def emit_log(
    stage: str,
    icon: str,
    title: str,
    message: str,
    detail: Optional[str] = None,
    agent: Optional[str] = None
) -> AgentLogItem:
    """Emit a new thought/status update from an agent."""
    agent_name = _resolve_agent_name(title, stage, icon, agent)
    item = AgentLogItem(
        id=str(uuid.uuid4())[:8],
        timestamp=datetime.now().strftime("%H:%M:%S"),
        stage=stage,
        icon=icon,
        title=title,
        message=message,
        detail=detail,
        agent=agent_name,
    )
    _LOG_HISTORY.append(item)
    logger.info(f"[{item.stage.upper()}] [{item.agent}] {item.icon} {item.title}: {item.message}")

    # Broadcast to all connected SSE clients
    for q in list(_SUBSCRIBERS):
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            pass
        except Exception:
            pass

    return item


def get_recent_logs(limit: int = 30) -> list[dict]:
    """Return the most recent log items as dicts."""
    items = list(_LOG_HISTORY)
    return [asdict(item) for item in items[-limit:]]


def clear_logs():
    """Clear in-memory log history."""
    _LOG_HISTORY.clear()


async def subscribe_logs() -> AsyncGenerator[str, None]:
    """Async generator yielding SSE formatted log events."""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _SUBSCRIBERS.append(q)

    # Immediately send existing recent logs to the new client
    initial_items = list(_LOG_HISTORY)[-10:]
    for item in initial_items:
        yield f"data: {json.dumps(asdict(item), ensure_ascii=False)}\n\n"

    try:
        while True:
            try:
                item: AgentLogItem = await asyncio.wait_for(q.get(), timeout=20.0)
                yield f"data: {json.dumps(asdict(item), ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        if q in _SUBSCRIBERS:
            _SUBSCRIBERS.remove(q)
