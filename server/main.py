"""
ESL Figma AI — Main Server (FastAPI)
Serves the web panel UI and the Figma plugin WebSocket bridge.
"""
import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
import time

# ── Windows ProactorEventLoop WinError 10054 Fix ───────────────────────────
if sys.platform == "win32":
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
        _orig_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost

        def _silenced_call_connection_lost(self, exc):
            try:
                _orig_call_connection_lost(self, exc)
            except (ConnectionResetError, OSError):
                pass

        _ProactorBasePipeTransport._call_connection_lost = _silenced_call_connection_lost
    except Exception:
        pass

import tempfile
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# ── Path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from server import bridge, config, agent_logger
from server.agents import orchestrator, toc_agent, student_agent, chat_agent, feedback_agent
from server import telegram_bot
from server.services import updater

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ── Lifespan (Startup & Shutdown) ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    # Start the Figma plugin bridge on port 45678 (background thread)
    bridge.start_bridge_server(
        host=config.get("server.host", "0.0.0.0"),
        port=int(config.get("server.bridge_port", 45678))
    )
    # Watch for plugin disconnects
    disconnect_task = asyncio.create_task(bridge.watch_disconnect())

    logger.info("=" * 60)
    logger.info("  ESL Figma AI — Ready!")
    logger.info(f"  🌐 Web panel:   http://localhost:{config.get('server.port', 3000)}/ui")
    logger.info(f"  🔌 Plugin port: http://localhost:{config.get('server.bridge_port', 45678)}")
    logger.info("=" * 60)
    engine = config.ai_engine()
    if engine == "antigravity":
        logger.info(f"⚡ AI Engine: Antigravity CLI (Local Agent) — Model: {config.gemini_model()}")
    elif config.gemini_api_key():
        logger.info(f"✅ Gemini API Key ready (model: {config.gemini_model()})")
    else:
        logger.warning("⚠️  AI Engine not configured! Set it at http://localhost:3000/ui")

    # Start Telegram bot if enabled
    if config.get("telegram.enabled") and config.get("telegram.bot_token"):
        proxy_url = None
        if config.get("telegram.proxy.enabled") and config.get("telegram.proxy.host"):
            host = config.get("telegram.proxy.host")
            port = config.get("telegram.proxy.port", 1080)
            proxy_url = f"socks5://{host}:{port}"
        telegram_bot.start_bot(
            token=config.get("telegram.bot_token"),
            proxy_url=proxy_url
        )
        logger.info("🤖 Telegram bot started!")
    else:
        logger.info("ℹ️  Telegram bot disabled (configure in /ui Settings)")

    yield

    # Cleanup
    disconnect_task.cancel()

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="ESL Figma AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_main_pna_header(request: Request, call_next):
    if request.method == "OPTIONS":
        resp = Response(status_code=200)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "*"
        resp.headers["Access-Control-Allow-Private-Network"] = "true"
        return resp
    resp = await call_next(request)
    resp.headers["Access-Control-Allow-Private-Network"] = "true"
    return resp

# Serve web UI static files
web_ui_path = ROOT / "web_ui"
if web_ui_path.exists():
    app.mount("/ui", StaticFiles(directory=str(web_ui_path), html=True), name="ui")

# ── In-memory log for web panel ───────────────────────────────────────────────
_log_entries: list[dict] = []
_log_ws_clients: list[WebSocket] = []


async def _push_log(level: str, message: str):
    entry = {"level": level, "message": message}
    _log_entries.append(entry)
    if len(_log_entries) > 200:
        _log_entries.pop(0)
    for ws in list(_log_ws_clients):
        try:
            await ws.send_json(entry)
        except Exception:
            _log_ws_clients.discard(ws)


bridge.add_status_callback(
    lambda connected: _push_log(
        "success" if connected else "warning",
        "✅ Плагин Figma подключён" if connected else "⚠️ Плагин Figma отключился"
    )
)

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Redirect to web panel."""
    return HTMLResponse('<meta http-equiv="refresh" content="0; url=/ui">')


@app.get("/api/status")
async def api_status():
    return {
        "version": updater.get_current_version(),
        "plugin_connected": bridge.is_connected(),
        "active_board": config.active_board(),
        "board_info": config.board_info(),
        "ai_ready": config.is_ai_ready(),
        "ai_engine": config.ai_engine(),
        "api_key_set": config.is_ai_ready(),
        "model": config.gemini_model(),
    }


# ── System Update API (OTA) ────────────────────────────────────────────────────
@app.get("/api/system/version")
async def api_system_version():
    return {
        "version": updater.get_current_version(),
        "repo": updater.DEFAULT_REPO,
    }


@app.get("/api/system/check-update")
async def api_system_check_update():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, updater.check_github_update)


@app.post("/api/system/apply-update")
async def api_system_apply_update():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, updater.apply_update)


@app.get("/api/config")
async def api_get_config():
    cfg = config._config.copy()
    # Mask sensitive values
    if cfg.get("ai", {}).get("gemini_api_key"):
        cfg["ai"]["gemini_api_key"] = "***" + cfg["ai"]["gemini_api_key"][-4:]
    if cfg.get("telegram", {}).get("bot_token"):
        cfg["telegram"]["bot_token"] = "***" + cfg["telegram"]["bot_token"][-6:]
    return cfg


class ConfigUpdate(BaseModel):
    engine: Optional[str] = None
    gemini_api_key: Optional[str] = None
    model: Optional[str] = None
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_proxy_enabled: Optional[bool] = None
    telegram_proxy_host: Optional[str] = None
    telegram_proxy_port: Optional[int] = None
    allowed_user_ids: Optional[list[int]] = None


@app.post("/api/config")
async def api_save_config(update: ConfigUpdate):
    if update.engine:
        config.set_value("ai.engine", update.engine)
    if update.gemini_api_key and not update.gemini_api_key.startswith("***"):
        config.set_value("ai.gemini_api_key", update.gemini_api_key)
    if update.model:
        config.set_value("ai.model", update.model)
    if update.telegram_enabled is not None:
        config.set_value("telegram.enabled", update.telegram_enabled)
    if update.telegram_bot_token and not update.telegram_bot_token.startswith("***"):
        config.set_value("telegram.bot_token", update.telegram_bot_token)
    if update.telegram_proxy_enabled is not None:
        config.set_value("telegram.proxy.enabled", update.telegram_proxy_enabled)
    if update.telegram_proxy_host:
        config.set_value("telegram.proxy.host", update.telegram_proxy_host)
    if update.telegram_proxy_port:
        config.set_value("telegram.proxy.port", update.telegram_proxy_port)
    if update.allowed_user_ids is not None:
        config.set_value("telegram.allowed_user_ids", update.allowed_user_ids)
    config.save(config._config)
    return {"ok": True, "message": "Настройки сохранены"}


# ── Student Backup & Restore API ─────────────────────────────────────────────

@app.get("/api/backup/download")
async def api_backup_download():
    from server.services import backup_service
    archive_path, manifest = backup_service.create_backup_archive()
    filename = manifest.get("archive_name", "students_backup.zip")
    return FileResponse(archive_path, media_type="application/zip", filename=filename)


@app.post("/api/backup/create")
async def api_backup_create():
    from server.services import backup_service
    archive_path, manifest = backup_service.create_backup_archive()
    return {"ok": True, "manifest": manifest, "path": archive_path}


@app.post("/api/backup/restore")
async def api_backup_restore(file: UploadFile = File(...)):
    from server.services import backup_service
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    try:
        content = await file.read()
        temp_zip.write(content)
        temp_zip.close()
        res = backup_service.restore_from_archive(temp_zip.name)
        return res
    finally:
        if os.path.exists(temp_zip.name):
            try:
                os.remove(temp_zip.name)
            except Exception:
                pass


# ── Telegram Bot Management API ───────────────────────────────────────────────

@app.get("/api/telegram/status")
async def api_telegram_status():
    """Get active Telegram bot lifecycle status."""
    return telegram_bot.get_status()


class TelegramConfigUpdate(BaseModel):
    enabled: bool
    bot_token: Optional[str] = None
    allowed_user_ids: Optional[list] = None
    proxy_enabled: Optional[bool] = None
    proxy_protocol: Optional[str] = None
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None


@app.post("/api/telegram/config")
async def api_telegram_config(update: TelegramConfigUpdate):
    """Save Telegram bot settings and dynamically start or stop the bot with proxy support."""
    config.set_value("telegram.enabled", update.enabled)
    if update.bot_token and not update.bot_token.startswith("***"):
        config.set_value("telegram.bot_token", update.bot_token.strip())
    if update.allowed_user_ids is not None:
        parsed_ids = []
        for x in update.allowed_user_ids:
            try:
                if str(x).strip():
                    parsed_ids.append(int(x))
            except Exception:
                pass
        config.set_value("telegram.allowed_user_ids", parsed_ids)

    # Proxy configuration
    if update.proxy_enabled is not None:
        config.set_value("telegram.proxy.enabled", update.proxy_enabled)
    if update.proxy_protocol:
        config.set_value("telegram.proxy.protocol", update.proxy_protocol.strip().lower())
    if update.proxy_host:
        config.set_value("telegram.proxy.host", update.proxy_host.strip())
    if update.proxy_port:
        config.set_value("telegram.proxy.port", int(update.proxy_port))
    if update.proxy_username is not None:
        config.set_value("telegram.proxy.username", update.proxy_username.strip())
    if update.proxy_password is not None and not update.proxy_password.startswith("***"):
        config.set_value("telegram.proxy.password", update.proxy_password.strip())

    config.save(config._config)

    # Build proxy URL if enabled
    proxy_url = None
    if config.get("telegram.proxy.enabled"):
        proto = config.get("telegram.proxy.protocol", "socks5").lower()
        host = config.get("telegram.proxy.host", "127.0.0.1")
        port = config.get("telegram.proxy.port", 1080)
        user = config.get("telegram.proxy.username", "")
        pwd = config.get("telegram.proxy.password", "")
        if user and pwd:
            proxy_url = f"{proto}://{user}:{pwd}@{host}:{port}"
        else:
            proxy_url = f"{proto}://{host}:{port}"

    # Apply lifecycle dynamically
    token = config.get("telegram.bot_token", "")
    if update.enabled and token:
        telegram_bot.restart_bot(token, proxy_url=proxy_url)
    else:
        telegram_bot.stop_bot()

    status = telegram_bot.get_status()
    status["proxy"] = config.get("telegram.proxy", {})
    return {"ok": True, "message": "Настройки Telegram бота успешно применены", **status}



# ── Board Management API ───────────────────────────────────────────────────────

def _extract_file_key(url: str) -> tuple[str, str]:
    """Extract file key and board type (figjam/design) from Figma URL."""
    import re
    # FigJam: /board/XXXX/ or /jam/XXXX/
    m = re.search(r'/board/([a-zA-Z0-9_-]+)', url)
    if m:
        return m.group(1), 'figjam'
    # Figma Design: /design/XXXX/ or /file/XXXX/
    m = re.search(r'/(?:design|file)/([a-zA-Z0-9_-]+)', url)
    if m:
        return m.group(1), 'design'
    return '', 'unknown'


@app.get("/api/boards")
async def api_get_boards():
    """Get all configured boards."""
    boards = config.get("figma.boards", {})
    active = config.active_board()
    result = []
    for board_id, info in boards.items():
        result.append({
            "id": board_id,
            "display_name": info.get("display_name", info.get("name", board_id)),
            "url": info.get("url", ""),
            "file_key": info.get("file_key", ""),
            "board_type": info.get("board_type", "unknown"),
            "aliases": info.get("aliases", []),
            "is_active": board_id == active,
        })
    return {"boards": result, "active": active}


class BoardCreate(BaseModel):
    display_name: str           # e.g. "Репетиторство"
    url: str                    # Figma board URL
    aliases: Optional[list[str]] = []  # e.g. ["репет", "tutoring"]


@app.post("/api/boards")
async def api_create_board(board: BoardCreate):
    """Add a new board."""
    import re
    # Generate board_id from display_name
    board_id = re.sub(r'[^a-zA-Z0-9а-яёА-ЯЁ_]', '_', board.display_name.lower()).strip('_')
    if not board_id:
        raise HTTPException(status_code=400, detail="Некорректное название доски")

    file_key, board_type = _extract_file_key(board.url)

    # Build aliases list — always include display_name and its lowercase
    aliases = list(board.aliases or [])
    name_lower = board.display_name.lower()
    if name_lower not in aliases:
        aliases.insert(0, name_lower)

    board_data = {
        "display_name": board.display_name,
        "name": board.display_name,
        "url": board.url,
        "file_key": file_key,
        "board_type": board_type,
        "aliases": aliases,
    }
    config.set_value(f"figma.boards.{board_id}", board_data)
    logger.info(f"✅ Board added: {board_id} ({board_type}) — {board.display_name}")
    return {"ok": True, "id": board_id, "board_type": board_type, "file_key": file_key}


class BoardUpdate(BaseModel):
    display_name: Optional[str] = None
    url: Optional[str] = None
    aliases: Optional[list[str]] = None


@app.put("/api/boards/{board_id}")
async def api_update_board(board_id: str, update: BoardUpdate):
    """Update an existing board."""
    boards = config.get("figma.boards", {})
    if board_id not in boards:
        raise HTTPException(status_code=404, detail=f"Доска '{board_id}' не найдена")

    board_data = boards[board_id].copy()
    if update.display_name:
        board_data["display_name"] = update.display_name
        board_data["name"] = update.display_name
    if update.url:
        board_data["url"] = update.url
        file_key, board_type = _extract_file_key(update.url)
        board_data["file_key"] = file_key
        board_data["board_type"] = board_type
    if update.aliases is not None:
        board_data["aliases"] = update.aliases

    config.set_value(f"figma.boards.{board_id}", board_data)
    return {"ok": True}


@app.delete("/api/boards/{board_id}")
async def api_delete_board(board_id: str):
    """Delete a board configuration."""
    boards = config.get("figma.boards", {})
    if board_id not in boards:
        raise HTTPException(status_code=404, detail="Доска не найдена")
    active = config.active_board()
    del boards[board_id]
    config.set_value("figma.boards", boards)
    if active == board_id:
        # Switch to first available
        remaining = list(boards.keys())
        config.set_value("figma.active_board", remaining[0] if remaining else "")
    return {"ok": True}


@app.post("/api/boards/{board_id}/activate")
async def api_activate_board(board_id: str):
    """Set a board as the active board."""
    boards = config.get("figma.boards", {})
    if board_id not in boards:
        raise HTTPException(status_code=404, detail="Доска не найдена")
    config.set_value("figma.active_board", board_id)
    board_info = boards[board_id]
    logger.info(f"🎯 Active board switched to: {board_id} ({board_info.get('display_name', board_id)})")
    await _push_log("info", f"🎯 Активная доска: {board_info.get('display_name', board_id)}")
    return {"ok": True, "active": board_id, "display_name": board_info.get("display_name", board_id)}


class CreateBlockRequest(BaseModel):
    command: Optional[str] = None
    block_type: Optional[str] = None
    topic: Optional[str] = None
    level: Optional[str] = None
    count: Optional[int] = 10
    youtube_url: Optional[str] = None
    board_id: Optional[str] = None
    selection: Optional[dict] = None
    image_base64: Optional[str] = None
    images: Optional[list] = None
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    lesson_plan: Optional[dict] = None
    blocks: Optional[list] = None
    lesson_format: Optional[str] = None
    goal: Optional[str] = None


@app.post("/api/create")
async def api_create_block(req: CreateBlockRequest):
    if not bridge.is_connected():
        raise HTTPException(
            status_code=503,
            detail="Плагин Figma не подключён. Откройте Figma / FigJam, запустите плагин и попробуйте снова."
        )
    if not config.is_ai_ready():
        raise HTTPException(
            status_code=400,
            detail="AI движок не готов. Проверьте настройки в веб-панели."
        )

    scope_str = "🌐 вся доска"
    if req.selection and req.selection.get("count", 0) > 0:
        scope_str = f"🎯 элемент: «{req.selection.get('name', 'блок')}»"
    if req.image_base64:
        scope_str += " + 🖼️ изображение с холста"
    if req.images:
        scope_str += f" + 📸 {len(req.images)} фото"

    await _push_log("info", f"🚀 Задача ({scope_str}): {req.topic or req.command}")

    result = await orchestrator.process_command(
        command=req.command or "",
        block_type=req.block_type,
        topic=req.topic,
        level=req.level,
        count=req.count,
        youtube_url=req.youtube_url,
        board_id=req.board_id,
        selection=req.selection,
        image_base64=req.image_base64,
        images=req.images,
        student_id=req.student_id,
        student_name=req.student_name,
        lesson_plan=req.lesson_plan,
        blocks=req.blocks,
        lesson_format=req.lesson_format,
        goal=req.goal,
    )

    level_str = f"({result.get('level', '')})" if result.get("level") else ""
    if result.get("ok"):
        msg = result.get("message") or f"Блок «{result.get('topic', 'Урок')}» успешно создан!"
        await _push_log("success", f"✅ {msg}")
    else:
        await _push_log("error", f"❌ {result.get('message', 'Unknown error')}")

    return result


@app.post("/api/eval")
async def api_eval(req: Request):
    """Execute JavaScript code inside the connected Figma plugin."""
    data = await req.json()
    code = data.get("code", "")
    if not code:
        return {"ok": False, "error": "No code provided"}
    return await bridge.send_command({"action": "eval", "code": code})


@app.post("/api/transcribe")
async def api_transcribe():
    """Stub endpoint: local faster-whisper disabled to optimize disk space."""
    return {"ok": False, "error": "Локальное распознавание речи отключено для экономии памяти"}



@app.post("/api/toc/refresh")
async def api_refresh_toc():
    if not bridge.is_connected():
        raise HTTPException(status_code=503, detail="Плагин не подключён")
    result = await toc_agent.refresh_toc()
    return result


@app.post("/api/debug/eval")
async def api_debug_eval(req: dict):
    if not bridge.is_connected():
        raise HTTPException(status_code=503, detail="Плагин не подключён")
    code = req.get("code", "")
    return await bridge.send_command("eval", {"code": code})


@app.get("/api/canvas/selected-images")
@app.post("/api/canvas/selected-images")
async def api_get_selected_images(limit: int = 15):
    """Fetch images currently selected on the canvas by the teacher."""
    if not bridge.is_connected():
        raise HTTPException(status_code=503, detail="Плагин не подключён")
    images = await bridge.get_selected_images(limit=limit)
    return {"ok": True, "count": len(images), "images": images}


@app.post("/api/canvas/capture")
async def api_canvas_capture(req: dict = None):
    """
    Export an image/snapshot of a specific node, lesson block, or board area.
    Saves the image to artifacts/screenshots/ and returns file path and base64.
    """
    if not bridge.is_connected():
        raise HTTPException(status_code=503, detail="Плагин не подключён")

    req = req or {}
    export_cmd = {
        "nodeId": req.get("node_id") or req.get("nodeId"),
        "role": req.get("role"),
        "query": req.get("query"),
        "width": req.get("width", 1600),
        "format": req.get("format", "PNG")
    }

    result = await bridge.send_command("EXPORT_NODE_IMAGE", export_cmd)
    if not result.get("ok") and not result.get("success"):
        # Fallback to dynamic eval execution directly on canvas
        target_id_json = json.dumps(export_cmd["nodeId"])
        role_json = json.dumps(export_cmd["role"])
        query_json = json.dumps(export_cmd["query"])
        fmt_json = json.dumps(export_cmd["format"])
        w_val = int(export_cmd["width"])

        code = f"""
        let target = null;
        const targetId = {target_id_json};
        const role = {role_json};
        const query = {query_json};

        if (targetId) {{
            target = figma.getNodeById(targetId);
        }}
        if (!target && role) {{
            target = figma.currentPage.children.find(n => n.getPluginData && n.getPluginData("role") === role);
        }}
        if (!target && query) {{
            const qLower = String(query).toLowerCase();
            target = figma.currentPage.children.find(n => n.name && n.name.toLowerCase().includes(qLower));
        }}
        if (!target) {{
            target = figma.currentPage.children.find(n => 
                (n.getPluginData && n.getPluginData("role") === "full_lesson") ||
                (n.name && (n.name.includes("УРОК") || n.name.includes("DIAGNOSTIC")))
            );
        }}
        if (!target) {{
            const sel = figma.currentPage.selection;
            if (sel && sel.length > 0) target = sel[0];
            else target = figma.currentPage.children.find(n => n.name && n.name.includes("ОГЛАВЛЕНИЕ")) || figma.currentPage.children[figma.currentPage.children.length - 1];
        }}

        if (!target) {{
            return {{ success: false, ok: false, error: "На холсте не найдено объектов для визуального снимка" }};
        }}

        const bytes = await target.exportAsync({{
            format: {fmt_json} === "JPG" ? "JPG" : "PNG",
            constraint: {{ type: "WIDTH", value: {w_val} }}
        }});

        let b64 = "";
        if (typeof figma.base64Encode === "function") {{
            b64 = figma.base64Encode(bytes);
        }} else {{
            let binary = "";
            const len = bytes.byteLength;
            for (let i = 0; i < len; i++) {{
                binary += String.fromCharCode(bytes[i]);
            }}
            b64 = (typeof btoa === "function") ? btoa(binary) : "";
        }}

        return {{
            ok: true,
            success: true,
            nodeId: target.id,
            nodeName: target.name,
            width: Math.round(target.width || 0),
            height: Math.round(target.height || 0),
            bytesCount: bytes.byteLength,
            image_base64: b64
        }};
        """
        eval_res = await bridge.send_command("eval", {"code": code})
        result = eval_res.get("result") or eval_res

    if not result.get("ok") and not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Ошибка захвата снимка"))

    b64 = result.get("image_base64", "")
    file_path = None
    if b64:
        try:
            import base64
            from pathlib import Path
            raw_bytes = base64.b64decode(b64)
            out_dir = Path("artifacts/screenshots")
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            safe_name = "".join(c for c in (result.get("nodeName") or "canvas") if c.isalnum() or c in ("-", "_")).strip() or "canvas"
            file_path = str(out_dir / f"snapshot_{safe_name}_{ts}.png")
            with open(file_path, "wb") as f:
                f.write(raw_bytes)
            # Also keep latest_canvas.png
            latest_path = str(out_dir / "latest_canvas.png")
            with open(latest_path, "wb") as f:
                f.write(raw_bytes)
        except Exception as e:
            logger.warning(f"Could not save snapshot file to disk: {e}")

    return {
        "ok": True,
        "success": True,
        "nodeId": result.get("nodeId"),
        "nodeName": result.get("nodeName"),
        "width": result.get("width"),
        "height": result.get("height"),
        "file_path": file_path,
        "bytesCount": len(b64) if b64 else 0,
        "image_base64": b64
    }


@app.get("/api/logs")
async def api_logs():
    """Return recent structured agent thoughts and activity logs."""
    return agent_logger.get_recent_logs(50)


@app.get("/api/logs/stream")
async def api_logs_stream():
    """Server-Sent Events (SSE) stream for live agent thoughts."""
    return StreamingResponse(
        agent_logger.subscribe_logs(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.delete("/api/logs")
async def api_clear_logs():
    """Clear in-memory agent thoughts and logs."""
    agent_logger.clear_logs()
    return {"ok": True}


class LogEmitRequest(BaseModel):
    stage: str = "generating"
    icon: str = "📝"
    title: str
    message: str
    detail: Optional[str] = None
    agent: Optional[str] = None


@app.post("/api/logs")
async def api_post_log(req: LogEmitRequest):
    """Emit an agent thought or action log entry."""
    item = agent_logger.emit_log(
        stage=req.stage,
        icon=req.icon,
        title=req.title,
        message=req.message,
        detail=req.detail,
        agent=req.agent,
    )
    return {"ok": True, "log": {"id": item.id, "stage": item.stage, "agent": item.agent, "title": item.title}}


@app.websocket("/ws/logs")
async def ws_logs(ws: WebSocket):
    """Web panel connects here to receive live log updates."""
    await ws.accept()
    _log_ws_clients.append(ws)
    # Send recent history on connect
    for entry in agent_logger.get_recent_logs(25):
        await ws.send_json(entry)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        if ws in _log_ws_clients:
            _log_ws_clients.remove(ws)

class ChatRequest(BaseModel):
    message: str
    student_id: Optional[str] = None
    history: Optional[list] = None
    selection: Optional[dict] = None
    image_base64: Optional[str] = None
    images: Optional[list] = None


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    """Process message in dialog mode with pedagogical context."""
    try:
        res = await chat_agent.process_chat_message(
            message=req.message,
            student_id=req.student_id,
            history=req.history,
            selection=req.selection,
            image_base64=req.image_base64,
            source="web"
        )
        return {"ok": True, **res}
    except Exception as e:
        logger.error(f"Chat processing error: {e}", exc_info=True)
        return {
            "ok": False,
            "reply": "Произошла ошибка при обработке сообщения. Попробуйте еще раз.",
            "suggested_replies": ["Попробовать снова", "Создать квиз"],
            "ready_to_build": False
        }


@app.get("/api/chat/history")
async def api_get_chat_history():
    """Return shared conversation history across Web and Telegram."""
    return {"ok": True, "history": chat_agent.get_shared_history()}


@app.delete("/api/chat/history")
async def api_clear_chat_history():
    """Clear shared conversation history."""
    chat_agent.clear_shared_history()
    return {"ok": True}


@app.get("/api/students")
async def api_list_students():
    """Return all registered students for the dropdown."""
    return {"ok": True, "students": student_agent.list_students()}


@app.get("/api/students/{student_id}")
async def api_get_student(student_id: str):
    """Return specific student profile and lesson history."""
    s = student_agent.get_student(student_id)
    if not s:
        raise HTTPException(status_code=404, detail="Ученик не найден")
    return {"ok": True, "student": s}


@app.post("/api/students")
async def api_save_student(data: dict):
    """Create or update a student profile."""
    try:
        saved = student_agent.save_student(data)
        return {"ok": True, "student": saved}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/students/{student_id}/lessons")
async def api_record_student_lesson(student_id: str, data: dict):
    """Record a completed lesson in student history."""
    ok = student_agent.record_lesson(student_id, data)
    return {"ok": ok}


@app.post("/api/students/{student_id}/level")
async def api_update_student_level(student_id: str, data: dict):
    """Update student's permanent CEFR level in profile."""
    new_lvl = data.get("level")
    if not new_lvl:
        raise HTTPException(status_code=400, detail="Missing level field")
    updated = student_agent.update_student_level(student_id, new_lvl)
    if not updated:
        raise HTTPException(status_code=404, detail="Student not found")
    await _push_log("info", f"🎓 Уровень ученика {updated.get('name')} обновлен на {new_lvl}")
    return {"ok": True, "student": updated}


@app.get("/api/students/{student_id}/check_level")
async def api_check_level(student_id: str, level: str):
    """Check if the system should suggest updating student's profile level."""
    suggestion = student_agent.check_level_suggestion(student_id, level)
    return {"ok": True, "suggestion": suggestion}


# ── Debriefing & Lesson Feedback Endpoints ────────────────────────────────────

class FeedbackStepRequest(BaseModel):
    user_id: str = "web_teacher"
    text: str


@app.post("/api/feedback/step")
async def api_feedback_step(req: FeedbackStepRequest):
    """Process a single turn in the guided feedback interview."""
    try:
        res = await feedback_agent.process_feedback_step(req.user_id, req.text)
        return {"ok": True, **res}
    except Exception as e:
        logger.error(f"Feedback step error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/feedback/voice")
async def api_feedback_voice(file: UploadFile = File(...), user_id: str = "web_teacher"):
    """Accept voice recording from browser or client, transcribe via Gemini, and process step."""
    try:
        voice_bytes = await file.read()
        transcribed_text = await feedback_agent.transcribe_and_analyze_voice(voice_bytes)
        res = await feedback_agent.process_feedback_step(user_id, transcribed_text)
        return {"ok": True, "transcribed_text": transcribed_text, **res}
    except Exception as e:
        logger.error(f"Voice feedback error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/feedback/reset")
async def api_feedback_reset(data: dict):
    """Reset debriefing session."""
    user_id = data.get("user_id", "web_teacher")
    feedback_agent.clear_feedback_session(user_id)
    return {"ok": True}


@app.get("/api/feedback/session/{user_id}")
async def api_feedback_get_session(user_id: str):
    """Get active debriefing session status."""
    session = feedback_agent.get_feedback_session(user_id)
    return {"ok": True, "session": session}



if __name__ == "__main__":
    port = config.get("server.port", 3000)
    uvicorn.run(
        "server.main:app",
        host=config.get("server.host", "0.0.0.0"),
        port=int(port),
        reload=False,
        log_level="info",
    )
