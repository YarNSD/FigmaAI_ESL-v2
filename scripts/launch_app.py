"""
ESL Figma AI — Standalone Desktop Window Launcher
Launches the web control panel in chromeless native desktop app mode (Edge/Chrome App Mode).
"""
import os
import shutil
import subprocess
import sys
import webbrowser

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

APP_URL = "http://localhost:3000"
WINDOW_SIZE = "1040,780"

def find_browser():
    # 1. Edge App Mode (default on Windows 10/11)
    edge_candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in edge_candidates:
        if os.path.exists(p):
            return p

    which_edge = shutil.which("msedge") or shutil.which("msedge.exe")
    if which_edge:
        return which_edge

    # 2. Chrome App Mode
    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in chrome_candidates:
        if os.path.exists(p):
            return p

    which_chrome = shutil.which("chrome") or shutil.which("chrome.exe")
    if which_chrome:
        return which_chrome

    return None

def main():
    browser = find_browser()
    if browser:
        cmd = [
            browser,
            f"--app={APP_URL}",
            f"--window-size={WINDOW_SIZE}",
            "--app-id=FigmaAIControlPanel"
        ]
        try:
            subprocess.Popen(cmd)
            print(f"[OK] Запущено нативное окно панели управления: {os.path.basename(browser)}")
            return
        except Exception as e:
            print(f"[WARN] Ошибка запуска app mode: {e}")

    # Fallback to default browser
    webbrowser.open(APP_URL)
    print("[OK] Открыта панель управления в браузере по умолчанию")

if __name__ == "__main__":
    main()
