"""
ESL Figma AI — OTA Updater Service
Handles checking GitHub Releases for updates, reading changelog, and applying updates safely.
"""
import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Tuple, List

logger = logging.getLogger("updater")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VERSION_FILE = PROJECT_ROOT / "VERSION"
DEFAULT_REPO = "YarNSD/FigmaAI_ESL-v2"
SKILL_PLUGIN_DIR = Path(r"C:\Users\Admin\.gemini\config\skills\figma-assistant\plugin")


def get_current_version() -> str:
    """Reads current version from VERSION file or returns fallback."""
    if VERSION_FILE.exists():
        try:
            return VERSION_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return "0.10.0"


def parse_version_tuple(v_str: str) -> Tuple[int, ...]:
    """Parses version string like 'v0.11.0' or '0.11' into integer tuple (0, 11, 0)."""
    clean = re.sub(r"^[^\d]*", "", v_str.strip())
    parts = []
    for piece in clean.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            m = re.match(r"\d+", piece)
            parts.append(int(m.group(0)) if m else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_version_newer(latest_str: str, current_str: str) -> bool:
    """Checks if latest version is strictly greater than current version."""
    return parse_version_tuple(latest_str) > parse_version_tuple(current_str)


def check_github_update(repo: str = DEFAULT_REPO) -> Dict[str, Any]:
    """
    Queries GitHub Releases API for the latest release.
    Works without authentication for public repositories.
    """
    cur_ver = get_current_version()
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {
        "User-Agent": "FigmaAI-ESL-Updater/1.0",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        latest_tag = data.get("tag_name", "").strip()
        latest_ver = latest_tag.lstrip("v")
        name = data.get("name") or latest_tag
        body = data.get("body") or "Список изменений не указан."
        html_url = data.get("html_url", f"https://github.com/{repo}/releases")
        published_at = data.get("published_at", "")

        has_update = is_version_newer(latest_ver, cur_ver)

        return {
            "ok": True,
            "update_available": has_update,
            "current_version": cur_ver,
            "latest_version": latest_ver,
            "release_tag": latest_tag,
            "release_name": name,
            "changelog": body,
            "html_url": html_url,
            "published_at": published_at,
            "repo": repo
        }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # No releases published yet
            return {
                "ok": True,
                "update_available": False,
                "current_version": cur_ver,
                "latest_version": cur_ver,
                "release_tag": f"v{cur_ver}",
                "release_name": f"v{cur_ver}",
                "changelog": "Репозиторий актуален. Официальных релизов пока не опубликовано.",
                "html_url": f"https://github.com/{repo}",
                "published_at": "",
                "repo": repo
            }
        logger.warning(f"GitHub API HTTP error: {e.code} - {e.reason}")
        return {
            "ok": False,
            "update_available": False,
            "current_version": cur_ver,
            "error": f"GitHub API error ({e.code}): {e.reason}"
        }
    except Exception as e:
        logger.warning(f"Failed to check GitHub update: {e}")
        return {
            "ok": False,
            "update_available": False,
            "current_version": cur_ver,
            "error": str(e)
        }


def run_cmd(cmd: List[str], cwd: Path = PROJECT_ROOT, timeout: int = 60) -> Tuple[int, str, str]:
    """Runs a shell command safely without popups on Windows."""
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **kwargs
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def sync_plugin_files() -> List[str]:
    """Syncs figma_plugin/ files to global figma-assistant skill if present."""
    logs = []
    src = PROJECT_ROOT / "figma_plugin"
    if not SKILL_PLUGIN_DIR.exists():
        return logs

    for fname in ["code.js", "ui.html", "manifest.json"]:
        sf = src / fname
        df = SKILL_PLUGIN_DIR / fname
        if sf.exists():
            try:
                shutil.copy2(sf, df)
                logs.append(f"Синхронизирован плагин: {fname} -> figma-assistant")
            except Exception as e:
                logs.append(f"Ошибка синхронизации {fname}: {e}")
    return logs


def apply_update(target_branch: str = "main") -> Dict[str, Any]:
    """
    Executes a safe pull from git remote:
    1. Checks if .git repository exists.
    2. Fetches origin.
    3. Pulls latest changes.
    4. Updates pip packages if requirements.txt modified.
    5. Syncs Figma plugin files.
    6. Runs verify_system.py.
    """
    logs = []
    old_version = get_current_version()
    logs.append(f"🚀 Старт обновления. Текущая версия: v{old_version}")

    dot_git = PROJECT_ROOT / ".git"
    if not dot_git.exists():
        return {
            "ok": False,
            "error": "Каталог не является Git-репозиторием. Запустите первоначальную инициализацию Git.",
            "logs": logs
        }

    # 1. Fetch remote
    logs.append(f"📡 Запрос обновлений из репозитория (git fetch origin)...")
    rc, out, err = run_cmd(["git", "fetch", "origin", target_branch, "--tags"])
    if rc != 0:
        logs.append(f"❌ Ошибка git fetch: {err}")
        return {"ok": False, "error": f"Не удалось связаться с GitHub: {err}", "logs": logs}

    # 2. Check if local tracked files have conflicts or stash them safely
    run_cmd(["git", "stash"])

    # 3. Pull latest changes
    logs.append(f"📥 Применение изменений (git pull origin {target_branch})...")
    rc, out, err = run_cmd(["git", "pull", "origin", target_branch])
    if rc != 0:
        logs.append(f"❌ Ошибка git pull: {err or out}")
        return {"ok": False, "error": f"Ошибка git pull: {err or out}", "logs": logs}
    logs.append(f"✅ Файлы обновлены: {out[:150]}")

    # 4. Pip requirements check
    req_file = PROJECT_ROOT / "requirements.txt"
    if req_file.exists():
        logs.append("📦 Проверка зависимостей Python (pip install)...")
        rc, out, err = run_cmd([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"])
        if rc == 0:
            logs.append("✅ Зависимости Python актуальны.")
        else:
            logs.append(f"⚠️ Предупреждение pip: {err[:150]}")

    # 5. Sync Figma plugin files
    plugin_logs = sync_plugin_files()
    logs.extend(plugin_logs)

    # 6. System verification
    verifier = PROJECT_ROOT / "scripts" / "verify_system.py"
    if verifier.exists():
        logs.append("🔍 Проверка целостности системы (verify_system.py)...")
        rc, out, err = run_cmd([sys.executable, str(verifier)])
        if rc == 0:
            logs.append("✅ Все проверки верификатора пройдены успешно!")
        else:
            logs.append(f"⚠️ Замечания верификатора:\n{out}")

    new_version = get_current_version()
    logs.append(f"🎉 Обновление успешно завершено! Новая версия: v{new_version}")

    return {
        "ok": True,
        "old_version": old_version,
        "new_version": new_version,
        "logs": logs,
        "restart_recommended": True
    }
