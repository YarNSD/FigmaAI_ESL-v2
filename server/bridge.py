"""
ESL Figma AI — HTTP Long-Poll Bridge
Compatible with the existing Figma plugin that uses fetch /poll + /result.

Protocol:
  Plugin → GET /poll   (every 500ms) → server returns {command: {...}} or {}
  Plugin → POST /result → server stores result, resolves waiting futures

This runs on port 45678 (existing plugin port).
Main FastAPI server runs on port 3000 (web panel).
"""
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from typing import Optional

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

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logger = logging.getLogger("bridge")

# ── State ───────────────────────────────────────────────────────────────────

# Queue of pending commands waiting to be picked up by the plugin
_command_queue: asyncio.Queue = asyncio.Queue()

# Futures awaiting results from the plugin, keyed by cmd_id
_result_futures: dict[str, asyncio.Future] = {}

# Last seen plugin info
_plugin_last_seen: float = 0.0
_plugin_tab_id: Optional[str] = None
_plugin_title: Optional[str] = None
_plugin_file_key: Optional[str] = None

# Status callbacks (called when plugin connects/disconnects)
_status_callbacks: list = []


def is_connected() -> bool:
    """Plugin is considered connected if it polled within 12 seconds (allows for tab throttling)."""
    return (time.time() - _plugin_last_seen) < 12.0


def get_plugin_info() -> dict:
    return {
        "connected": is_connected(),
        "title": _plugin_title,
        "file_key": _plugin_file_key,
        "tab_id": _plugin_tab_id,
    }


def add_status_callback(cb):
    _status_callbacks.append(cb)


async def _fire_status(connected: bool):
    for cb in _status_callbacks:
        try:
            result = cb(connected)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass


# ── Command sending ─────────────────────────────────────────────────────────

async def send_command(action: str | dict, params: Optional[dict] = None, timeout: float = 90.0) -> dict:
    """
    Send a command to the Figma plugin and wait for its result.
    Accepts either (action, params) or a single dict {"action": ..., ...}.
    The plugin picks it up on next poll, executes it, and POSTs back to /result.
    """
    if isinstance(action, dict):
        d = action
        action_name = d.get("action", "")
        params_dict = {k: v for k, v in d.items() if k != "action"}
    else:
        action_name = action
        params_dict = params if params is not None else {}

    if not is_connected():
        # Give it up to 2.5s in case a poll is momentarily in-flight
        for _ in range(5):
            await asyncio.sleep(0.5)
            if is_connected():
                break
        else:
            return {
                "ok": False,
                "error": "Плагин Figma не подключён. Откройте Figma, запустите плагин и попробуйте снова."
            }

    cmd_id = str(uuid.uuid4())[:12]
    command = {"id": cmd_id, "action": action_name, "params": params_dict}
    if "code" in params_dict:
        command["code"] = params_dict["code"]

    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    _result_futures[cmd_id] = fut

    # Put command in queue — plugin will pick it up on next poll
    await _command_queue.put(command)
    logger.info(f"→ Queued command [{cmd_id}] {action_name}")

    try:
        result = await asyncio.wait_for(fut, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        _result_futures.pop(cmd_id, None)
        logger.error(f"Timeout waiting for [{cmd_id}] {action}")
        return {"ok": False, "error": f"Плагин не ответил за {timeout}с. Попробуйте снова."}
    except Exception as e:
        _result_futures.pop(cmd_id, None)
        return {"ok": False, "error": str(e)}


async def ping() -> bool:
    """Quick connectivity check."""
    return is_connected()


async def get_selected_images(limit: int = 15, max_dim: int = 800) -> list[dict]:
    """
    Fetch image/card nodes currently selected by the teacher on the active Figma canvas.
    Returns a list of dicts: [{"id": ..., "name": ..., "image_base64": ..., "width": ..., "height": ...}].
    """
    if not is_connected():
        return []
    try:
        res = await send_command("GET_SELECTED_IMAGES", {"limit": limit, "width": max_dim}, timeout=12.0)
        if res and res.get("ok") and isinstance(res.get("items"), list) and len(res["items"]) > 0:
            return res["items"]
    except Exception as e:
        logger.warning(f"GET_SELECTED_IMAGES command failed ({e}), trying fallback eval...")

    # Resilient fallback: evaluate directly in Figma context
    fallback_code = f"""
    const sel = figma.currentPage.selection || [];
    const limit = {limit};
    const maxDim = {max_dim};
    const existingBackup = (typeof findBoardBackupGroup === "function") ? findBoardBackupGroup() : null;
    const candidates = sel.filter(n => n !== existingBackup && !(n.getPluginData && n.getPluginData("role") === "board_backup"));
    const nodes = candidates.slice(0, limit);
    const items = [];
    for (const node of nodes) {{
      try {{
        const bytes = await node.exportAsync({{ format: "JPG", constraint: {{ type: "WIDTH", value: maxDim }} }});
        let b64 = "";
        if (typeof figma.base64Encode === "function") {{
          b64 = figma.base64Encode(bytes);
        }} else {{
          let binary = "";
          for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
          b64 = (typeof btoa === "function") ? btoa(binary) : "";
        }}
        items.push({{
          id: node.id,
          name: node.name || "Image",
          width: Math.round(node.width || 0),
          height: Math.round(node.height || 0),
          image_base64: b64,
          size: bytes.byteLength
        }});
      }} catch(e) {{}}
    }}
    return {{ count: items.length, items: items }};
    """
    try:
        eval_res = await send_command("eval", {"code": fallback_code}, timeout=15.0)
        if eval_res and eval_res.get("ok"):
            r = eval_res.get("result")
            if isinstance(r, dict) and isinstance(r.get("items"), list):
                return r["items"]
    except Exception as eval_err:
        logger.error(f"get_selected_images fallback eval error: {eval_err}")

    return []



# ── Bridge HTTP App (port 45678) ─────────────────────────────────────────────

bridge_app = FastAPI(title="ESL Bridge", docs_url=None, redoc_url=None)

bridge_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@bridge_app.middleware("http")
async def add_pna_header(request: Request, call_next):
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


@bridge_app.get("/")
@bridge_app.get("/health")
async def bridge_health():
    return {
        "status": "ok",
        "service": "antigravity-figma-bridge",
        "port": 45678,
        "is_connected": is_connected(),
        "active_board": _plugin_title,
    }


@bridge_app.post("/poll")
async def bridge_poll(request: Request):
    """
    Called by the Figma plugin every 500ms.
    Returns the next queued command if any, otherwise {}.
    """
    global _plugin_last_seen, _plugin_tab_id, _plugin_title, _plugin_file_key

    was_connected = is_connected()
    _plugin_last_seen = time.time()

    try:
        body = await request.json()
        _plugin_tab_id = body.get("tab_id", _plugin_tab_id)
        _plugin_title = body.get("title", _plugin_title)
        _plugin_file_key = body.get("fileKey", _plugin_file_key)
    except Exception:
        pass

    if not was_connected:
        logger.info(f"✅ Plugin connected: {_plugin_title}")
        await _fire_status(True)

    # Serve next command if available
    try:
        command = _command_queue.get_nowait()
        logger.info(f"← Serving command [{command['id']}] {command['action']} to tab [{_plugin_tab_id}] ({_plugin_title})")
        return JSONResponse({
            "is_active": True,
            "command": command,
        })
    except asyncio.QueueEmpty:
        pass

    return JSONResponse({"is_active": True})


@bridge_app.post("/result")
async def bridge_result(request: Request):
    """
    Called by the Figma plugin after executing a command.
    Resolves the waiting future in send_command().
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": True})

    cmd_id = data.get("cmd_id") or data.get("id")
    inner = data.get("result") if isinstance(data.get("result"), dict) else {}

    ok_val = data.get("ok")
    if ok_val is None:
        ok_val = data.get("success")
    if ok_val is None and inner:
        ok_val = inner.get("ok")
    if ok_val is None and inner:
        ok_val = inner.get("success")
    if ok_val is None:
        ok_val = True

    node_id = data.get("nodeId") or data.get("node_id") or inner.get("nodeId") or inner.get("node_id")
    err_val = data.get("error") or inner.get("error")

    logger.info(f"✓ Result received [{cmd_id}] from tab [{_plugin_tab_id}] ({_plugin_title}): ok={ok_val} node={node_id} err={err_val}")

    if cmd_id and cmd_id in _result_futures:
        fut = _result_futures.pop(cmd_id)
        if not fut.done():
            result = {
                **inner,
                **data,
                "ok": bool(ok_val),
                "nodeId": node_id,
                "error": err_val,
            }
            fut.set_result(result)

    return JSONResponse({"ok": True})


@bridge_app.get("/status")
async def bridge_status():
    return JSONResponse(get_plugin_info())


# ── Backup File Storage Endpoints ───────────────────────────────────────────

@bridge_app.post("/backup/save")
async def bridge_backup_save(req: Request):
    """Save backup JSON to a specified folder on the machine."""
    try:
        body = await req.json()
        directory = (body.get("directory") or "").strip()
        filename = (body.get("filename") or "").strip() or "board_backup.json"
        content = body.get("content")

        if not directory or directory.lower() in ["downloads", "загрузки"]:
            directory = os.path.join(os.path.expanduser("~"), "Downloads")
        elif directory.lower() in ["default", "c:\\figmabackups", "figmabackups"]:
            directory = os.path.join(os.path.expanduser("~"), "FigmaAI", "Backups")

        os.makedirs(directory, exist_ok=True)
        full_path = os.path.join(directory, filename)

        with open(full_path, "w", encoding="utf-8") as f:
            if isinstance(content, str):
                f.write(content)
            else:
                json.dump(content, f, ensure_ascii=False, indent=2)

        logger.info(f"📦 Backup saved successfully to {full_path}")
        return JSONResponse({"ok": True, "saved_path": full_path, "filename": filename})
    except Exception as e:
        logger.error(f"Failed to save backup: {e}", exc_info=True)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@bridge_app.get("/backup/list")
async def bridge_backup_list(directory: str = ""):
    """List backup files from a directory."""
    try:
        dir_clean = directory.strip()
        if not dir_clean or dir_clean.lower() in ["default", "c:\\figmabackups", "figmabackups"]:
            dir_clean = os.path.join(os.path.expanduser("~"), "FigmaAI", "Backups")
        elif dir_clean.lower() in ["downloads", "загрузки"]:
            dir_clean = os.path.join(os.path.expanduser("~"), "Downloads")

        if not os.path.exists(dir_clean):
            return JSONResponse({"ok": True, "files": [], "directory": dir_clean})

        files = []
        for fn in sorted(os.listdir(dir_clean), reverse=True):
            if fn.endswith(".json") and "backup" in fn.lower():
                fp = os.path.join(dir_clean, fn)
                try:
                    st = os.stat(fp)
                    files.append({
                        "name": fn,
                        "path": fp,
                        "size": st.st_size,
                        "mtime": st.st_mtime
                    })
                except Exception:
                    pass

        return JSONResponse({"ok": True, "files": files, "directory": dir_clean})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@bridge_app.post("/backup/load")
async def bridge_backup_load(req: Request):
    """Load backup JSON by file path."""
    try:
        body = await req.json()
        path = (body.get("path") or "").strip()
        if not path or not os.path.exists(path):
            return JSONResponse({"ok": False, "error": f"Файл не найден: {path}"}, status_code=404)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return JSONResponse({"ok": True, "data": data, "path": path})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ── Disconnect detector ─────────────────────────────────────────────────────

async def watch_disconnect():
    """Background task that detects plugin disconnect."""
    was_connected = False
    while True:
        await asyncio.sleep(2.0)
        now_connected = is_connected()
        if was_connected and not now_connected:
            logger.warning("⚠️ Plugin disconnected (no poll for 3s)")
            await _fire_status(False)
        was_connected = now_connected


def start_bridge_server(host: str = "0.0.0.0", port: int = 45678):
    """Start the bridge server in a thread (called from main.py)."""
    import threading

    def run():
        uvicorn.run(bridge_app, host=host, port=port, log_level="warning")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    logger.info(f"🔌 Bridge server started on {host}:{port}")
    return t
