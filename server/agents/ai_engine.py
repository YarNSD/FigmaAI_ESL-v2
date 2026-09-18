"""
ESL Figma AI — Unified AI Engine
Supports:
1. Google Antigravity CLI (`agy`) — local on-device agent execution (default, no API key required).
2. Google Gemini API (`google.generativeai`) — fallback via user API key.
"""
import asyncio
import json
import logging
import os
import re
import subprocess
from server import config

logger = logging.getLogger("ai_engine")


def _extract_json(text: str) -> dict:
    """Robustly extract and parse JSON from model output."""
    text = text.strip()
    # Remove markdown code blocks if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Search for first { ... } or [ ... ]
        m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        raise


# Fallback candidates if the primary model is at capacity (code 503)
CLI_FALLBACK_MODELS = [
    "gemini-3.8-flash-low",
    "gemini-3.7-flash-low",
    "gemini-3.7-flash-medium",
    "claude-sonnet-4-6",
    None,  # Default CLI model without --model
]


def is_antigravity_cli_authenticated() -> bool:
    """Check if Antigravity CLI has an active logged-in Google account."""
    acct_file = os.path.expanduser("~/.gemini/google_accounts.json")
    if os.path.exists(acct_file):
        try:
            with open(acct_file, "r", encoding="utf-8") as f:
                d = json.load(f)
                return bool(d.get("active"))
        except Exception:
            pass
    return False


async def _run_antigravity_cli(prompt: str, model: str | None = None) -> str:
    """Execute prompt via local Antigravity CLI (`agy -p <prompt>`) with 503/capacity fallback."""
    if not is_antigravity_cli_authenticated():
        raise RuntimeError("Antigravity CLI не авторизован в консоли (нет активного аккаунта в google_accounts.json)")

    # Build candidate models list
    candidates = []
    if model:
        candidates.append(model)
    for fb in CLI_FALLBACK_MODELS:
        if fb not in candidates:
            candidates.append(fb)

    # Set up proxy if local proxy is active (port 2080 / 1080)
    env = os.environ.copy()
    import socket
    proxy_port = None
    for p in [2080, 1080, 7890]:
        try:
            with socket.create_connection(("127.0.0.1", p), timeout=0.5):
                proxy_port = p
                break
        except (socket.timeout, ConnectionRefusedError, OSError):
            pass

    if proxy_port:
        proto = "socks5" if proxy_port == 2080 else "http"
        proxy_url = f"{proto}://127.0.0.1:{proxy_port}"
        env["HTTP_PROXY"] = proxy_url
        env["HTTPS_PROXY"] = proxy_url
        env["ALL_PROXY"] = proxy_url
        env["all_proxy"] = proxy_url
        env["http_proxy"] = proxy_url
        env["https_proxy"] = proxy_url

    loop = asyncio.get_event_loop()
    last_err = ""

    for target_model in candidates:
        cmd = ["agy", "-p", prompt, "--disable-slash-commands", "--print-timeout", "15s"]
        if target_model:
            cmd.extend(["--model", target_model])
        else:
            cmd.extend(["--effort", "low"])

        logger.info(f"⚡ Invoking Antigravity CLI silently (model: {target_model or 'default'})...")

        def _exec(command=cmd):
            kwargs = {}
            if os.name == "nt":
                # Ensure no console window pops up on Windows (CREATE_NO_WINDOW)
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                timeout=8,
                stdin=subprocess.DEVNULL,
                **kwargs
            )

        try:
            p = await loop.run_in_executor(None, _exec)
        except subprocess.TimeoutExpired as e:
            logger.warning(f"Antigravity CLI timed out with model {target_model}: {e}")
            last_err = "Таймаут Antigravity CLI (возможно требуется авторизация или модель недоступна)"
            break
        except Exception as e:
            logger.warning(f"Failed to execute agy with model {target_model}: {e}")
            last_err = str(e)
            break

        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()

        err_msg = (p.stderr.strip() or p.stdout.strip()) or f"agy exited with code {p.returncode}"
        last_err = err_msg

        # If authentication required, do not try other models (it will just spam browser tabs)
        if "Authentication required" in err_msg or "oauth2" in err_msg.lower() or "accounts.google.com" in err_msg:
            logger.error("Antigravity CLI requires authentication.")
            raise RuntimeError(
                "🔑 Antigravity CLI не авторизован в консоли. "
                "Чтобы создавать контент прямо сейчас, просто напишите ваш запрос мне в чат Antigravity IDE! "
                "Либо вставьте Gemini API Key в Настройках веб-панели (http://localhost:3000/ui)."
            )

        # If location eligibility failure, stop trying other models as it's an IP restriction
        if "Eligibility check failed" in err_msg:
            logger.error(f"Antigravity CLI location error: {err_msg}")
            raise RuntimeError(
                "📍 Ошибка геолокации Antigravity CLI: текущий IP-адрес не поддерживается сервисом. "
                "Включите в вашем VPN (Throne / Hiddify / V2Ray) узел США (USA) или Великобританию (UK), "
                "либо вставьте Gemini API Key в Настройках веб-панели."
            )

        # If 503 / capacity issue or verification required, try next model
        if any(w in err_msg for w in ["503", "No capacity available", "UNAVAILABLE", "Verification Required", "rate limit", "Too Many Requests"]):
            logger.warning(f"⚠️ Модель {target_model} вернула {err_msg[:60]}... Переключаюсь на следующую модель...")
            continue
        else:
            # Another error, log and break
            logger.error(f"Antigravity CLI error with model {target_model}: {err_msg}")
            break

    raise RuntimeError(f"Antigravity CLI error: {last_err}")



async def _run_gemini_api(prompt: str, system_instruction: str = "") -> str:
    """Execute prompt via Google Generative AI API with automatic model mapping."""
    import google.generativeai as genai
    api_key = config.gemini_api_key()
    if not api_key:
        raise ValueError("Gemini API key not configured")

    # Set up proxy if configured
    proxy = config.get("telegram.proxy", {})
    if proxy.get("enabled"):
        host = proxy.get("host", "127.0.0.1")
        port = proxy.get("port", 2080)
        proto = proxy.get("protocol", "socks5")
        proxy_str = f"{proto}://{host}:{port}"
        os.environ["HTTP_PROXY"] = proxy_str
        os.environ["HTTPS_PROXY"] = proxy_str
        os.environ["ALL_PROXY"] = proxy_str

    genai.configure(api_key=api_key)
    kwargs = {}
    if system_instruction:
        kwargs["system_instruction"] = system_instruction

    # Map CLI model names to valid Google AI Studio public models
    raw_model = config.gemini_model() or "gemini-2.0-flash"
    if any(k in raw_model for k in ["3.8", "3.7", "3.6", "3.1", "claude", "oss"]):
        mapped_model = "gemini-2.0-flash"
    else:
        mapped_model = raw_model

    loop = asyncio.get_event_loop()
    try:
        model = genai.GenerativeModel(mapped_model, **kwargs)
        resp = await loop.run_in_executor(None, lambda: model.generate_content(prompt))
        return resp.text.strip()
    except Exception as e:
        err_str = str(e)
        if "503" in err_str or "UNAVAILABLE" in err_str or "ResourceExhausted" in err_str:
            logger.warning(f"Model {mapped_model} at capacity, falling back to gemini-1.5-flash...")
            fallback_model = genai.GenerativeModel("gemini-1.5-flash", **kwargs)
            resp = await loop.run_in_executor(None, lambda: fallback_model.generate_content(prompt))
            return resp.text.strip()
        raise


async def generate_text(prompt: str, system_instruction: str = "") -> str:
    """Generate text using active AI engine with fallback support."""
    engine = config.ai_engine()
    model = config.gemini_model()

    if engine == "antigravity":
        full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
        try:
            return await _run_antigravity_cli(full_prompt, model=model)
        except Exception as e:
            # If Antigravity fails due to location or capacity, check if user provided a Gemini API Key as backup
            if config.gemini_api_key():
                logger.warning(f"Antigravity CLI failed ({e}). Auto-falling back to Gemini API key...")
                return await _run_gemini_api(prompt, system_instruction=system_instruction)
            raise
    else:
        return await _run_gemini_api(prompt, system_instruction=system_instruction)


async def generate_json(prompt: str, system_instruction: str = "") -> dict:
    """Generate structured JSON using active AI engine."""
    enforced_prompt = prompt + "\n\nCRITICAL: Output ONLY valid JSON. No conversational filler, no markdown fences."
    raw = await generate_text(enforced_prompt, system_instruction=system_instruction)
    return _extract_json(raw)


async def generate(prompt: str, system_prompt: str = "", system_instruction: str = "", **kwargs) -> str:
    """Convenience alias for generate_text with flexible kwargs."""
    sys_ins = system_prompt or system_instruction
    return await generate_text(prompt, system_instruction=sys_ins)

