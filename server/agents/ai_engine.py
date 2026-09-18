"""
ESL Figma AI — Local On-Device AI Engine
100% Local execution via Google Antigravity CLI (`agy`) and local expert engines.
Zero external API keys and zero cloud calls.
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


def _clean_token_stats(text: str) -> str:
    """Strip token tracker footer if injected by global rules."""
    if "📊 **Расход токенов" in text:
        return text.split("📊 **Расход токенов")[0].strip()
    if "📊 Токены задачи:" in text:
        return text.split("📊 Токены задачи:")[0].strip()
    return text.strip()


# Fallback candidates if the primary model is at capacity (code 503)
CLI_FALLBACK_MODELS = [
    "gemini-3.8-flash-medium",
    "gemini-3.7-flash-medium",
    "gemini-3.8-flash-high",
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
    return True


async def _run_antigravity_cli(prompt: str, model: str | None = None) -> str:
    """Execute prompt via local Antigravity CLI (`agy -p <prompt>`) with 503/capacity fallback."""
    # Build candidate models list
    candidates = []
    if model:
        candidates.append(model)
    for fb in CLI_FALLBACK_MODELS:
        if fb not in candidates:
            candidates.append(fb)

    # Prepare environment for agy (inherit clean environment without forced SOCKS proxy unless explicitly enabled in ai config)
    env = os.environ.copy()
    ai_proxy = config.get("ai.proxy")
    if ai_proxy and config.get("ai.proxy_enabled"):
        env["HTTP_PROXY"] = ai_proxy
        env["HTTPS_PROXY"] = ai_proxy
        env["ALL_PROXY"] = ai_proxy

    loop = asyncio.get_event_loop()
    last_err = ""

    for target_model in candidates:
        cmd = ["agy", "-p", prompt, "--disable-slash-commands", "--print-timeout", "60s"]
        if target_model:
            cmd.extend(["--model", target_model])
        else:
            cmd.extend(["--effort", "low"])

        logger.info(f"⚡ Invoking Antigravity CLI silently (model: {target_model or 'default'})...")

        def _exec(command=cmd):
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                timeout=65,
                stdin=subprocess.DEVNULL,
                **kwargs
            )

        try:
            p = await loop.run_in_executor(None, _exec)
        except subprocess.TimeoutExpired as e:
            logger.warning(f"Antigravity CLI timed out with model {target_model}: {e}")
            last_err = "Таймаут Antigravity CLI"
            continue
        except Exception as e:
            logger.warning(f"Failed to execute agy with model {target_model}: {e}")
            last_err = str(e)
            continue

        raw_out = p.stdout.strip()
        if p.returncode == 0 and raw_out:
            return _clean_token_stats(raw_out)

        err_msg = (p.stderr.strip() or raw_out) or f"agy exited with code {p.returncode}"
        last_err = err_msg

        # If authentication or account verification required, stop trying models immediately
        if any(k in err_msg for k in ["Authentication required", "Verification Required", "oauth2", "accounts.google.com"]):
            logger.error(f"Antigravity CLI requires authentication/verification: {err_msg}")
            raise RuntimeError(
                "🔑 Antigravity CLI требует авторизации или подтверждения Google-аккаунта (Verification Required). "
                "Запустите в терминале 'agy' для проверки аккаунта."
            )

        # If location eligibility failure, stop trying other models as it's an IP restriction
        if "Eligibility check failed" in err_msg:
            logger.error(f"Antigravity CLI location error: {err_msg}")
            raise RuntimeError(
                "📍 Ошибка геолокации Antigravity CLI: текущий IP-адрес не поддерживается сервисом. "
                "Включите в вашем VPN узел США (USA) или Великобританию (UK)."
            )

        # For any other failure (503, timeout, print timeout, capacity, syntax), try next model candidate
        logger.warning(f"⚠️ Модель {target_model} не ответила ({err_msg[:80]})... Пробую резервную модель...")
        continue

    raise RuntimeError(f"Antigravity CLI error: {last_err}")


async def generate_text(prompt: str, system_instruction: str = "") -> str:
    """Generate text strictly using local Antigravity CLI (100% on-device)."""
    model = config.gemini_model()
    full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
    return await _run_antigravity_cli(full_prompt, model=model)


async def generate_json(prompt: str, system_instruction: str = "") -> dict:
    """Generate structured JSON using active AI engine."""
    enforced_prompt = prompt + "\n\nCRITICAL: Output ONLY valid JSON. No conversational filler, no markdown fences."
    raw = await generate_text(enforced_prompt, system_instruction=system_instruction)
    return _extract_json(raw)


async def generate(prompt: str, system_prompt: str = "", system_instruction: str = "", **kwargs) -> str:
    """Convenience alias for generate_text with flexible kwargs."""
    sys_ins = system_prompt or system_instruction
    return await generate_text(prompt, system_instruction=sys_ins)

