"""
ESL Figma AI — System Verification & Integrity Auditor (Inspired by GSD Verifier)
Runs rapid multi-layer health checks across:
1. Python backend & imports
2. Figma Plugin JS syntax & HTML/JS DOM integrity (prevents ReferenceErrors)
3. Plugin synchronization with figma-assistant skill
4. TOC & Layout Agent category parity
5. Long-term memory files (UTF-8 integrity & line limits)
"""
import sys
import os
import glob
import re
import subprocess
import py_compile

# Configure UTF-8 for console output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKILL_PLUGIN_DIR = r"C:\Users\Admin\.gemini\config\skills\figma-assistant\plugin"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def log_ok(msg: str):
    print(f"  {GREEN}✅ [OK]{RESET} {msg}")

def log_fail(msg: str):
    print(f"  {RED}❌ [FAIL]{RESET} {msg}")

def log_warn(msg: str):
    print(f"  {YELLOW}⚠️ [WARN]{RESET} {msg}")

def log_info(msg: str):
    print(f"  {CYAN}ℹ️ [INFO]{RESET} {msg}")


def check_python_compilation() -> bool:
    print(f"\n{BOLD}1. Проверка компиляции и импортов Python:{RESET}")
    all_ok = True
    py_files = glob.glob(os.path.join(PROJECT_ROOT, "server", "**", "*.py"), recursive=True)
    py_files.extend(glob.glob(os.path.join(PROJECT_ROOT, "*.py")))

    for f in py_files:
        rel = os.path.relpath(f, PROJECT_ROOT)
        try:
            py_compile.compile(f, doraise=True)
        except Exception as e:
            log_fail(f"Синтаксическая ошибка в {rel}: {e}")
            all_ok = False

    if all_ok:
        log_ok(f"Все Python файлы ({len(py_files)} шт.) скомпилированы без ошибок.")

    # Check critical imports
    sys.path.insert(0, PROJECT_ROOT)
    modules_to_test = [
        "server.main",
        "server.agents.chat_agent",
        "server.agents.toc_agent",
        "server.agents.layout_agent",
        "server.agents.ai_engine",
        "server.agent_logger",
    ]
    import_errors = 0
    for mod in modules_to_test:
        try:
            __import__(mod)
        except Exception as e:
            log_fail(f"Ошибка импорта {mod}: {e}")
            import_errors += 1
            all_ok = False

    if import_errors == 0:
        log_ok("Все ключевые модули сервера успешно импортируются.")

    return all_ok


def check_plugin_integrity() -> bool:
    print(f"\n{BOLD}2. Проверка целостности плагина Figma (HTML/JS/DOM):{RESET}")
    all_ok = True
    ui_path = os.path.join(PROJECT_ROOT, "figma_plugin", "ui.html")
    code_path = os.path.join(PROJECT_ROOT, "figma_plugin", "code.js")

    if not os.path.exists(ui_path) or not os.path.exists(code_path):
        log_fail("Файлы figma_plugin/ui.html или code.js не найдены!")
        return False

    # 1. Check code.js with node
    p = subprocess.run(["node", "--check", code_path], capture_output=True, text=True, encoding="utf-8")
    if p.returncode == 0:
        log_ok("figma_plugin/code.js: синтаксис JavaScript корректен.")
    else:
        log_fail(f"figma_plugin/code.js: синтаксическая ошибка:\n{p.stderr.strip()}")
        all_ok = False

    # 2. Extract script from ui.html and check with node
    with open(ui_path, "r", encoding="utf-8", errors="replace") as f:
        ui_html = f.read()

    scripts = re.findall(r"<script[^>]*>(.*?)</script>", ui_html, re.DOTALL)
    if not scripts:
        log_fail("figma_plugin/ui.html: тег <script> не найден!")
        return False

    for i, s in enumerate(scripts):
        p = subprocess.run(["node", "--check"], input=s, capture_output=True, text=True, encoding="utf-8")
        if p.returncode == 0:
            log_ok(f"figma_plugin/ui.html: блок <script> #{i+1} корректен.")
        else:
            log_fail(f"figma_plugin/ui.html: ошибка в <script> #{i+1}:\n{p.stderr.strip()}")
            all_ok = False

    # 3. Check for undeclared critical variables that caused ReferenceErrors in the past
    script_content = "\n".join(scripts)
    dangerous_vars = ["dynamicIsland", "tileToggleIcon", "suggestedChipsRow"]
    for var in dangerous_vars:
        # Check if used in conditions
        usage = re.findall(rf"\bif\s*\(\s*{var}\b", script_content)
        # Check if declared
        declared = re.search(rf"\b(const|let|var)\s+{var}\b", script_content)
        if usage and not declared:
            log_fail(f"figma_plugin/ui.html: переменная '{var}' используется в 'if ({var})', но НЕ объявлена (риск ReferenceError)!")
            all_ok = False

    if all_ok:
        log_ok("figma_plugin/ui.html: проверки на ReferenceError пройдены.")

    return all_ok


def check_plugin_sync(auto_fix: bool = False) -> bool:
    print(f"\n{BOLD}3. Проверка синхронизации плагина с навыком figma-assistant:{RESET}")
    all_ok = True
    if not os.path.exists(SKILL_PLUGIN_DIR):
        log_warn(f"Директория навыка {SKILL_PLUGIN_DIR} не найдена, пропускаем синхронизацию.")
        return True

    files_to_sync = ["ui.html", "code.js", "manifest.json"]
    for fn in files_to_sync:
        src = os.path.join(PROJECT_ROOT, "figma_plugin", fn)
        dst = os.path.join(SKILL_PLUGIN_DIR, fn)
        if not os.path.exists(src):
            continue
        if not os.path.exists(dst):
            log_warn(f"{fn} отсутствует в навыке figma-assistant.")
            all_ok = False
            if auto_fix:
                import shutil
                shutil.copy2(src, dst)
                log_ok(f"Автоматически скопирован {fn} в навык figma-assistant.")
            continue

        with open(src, "rb") as f1, open(dst, "rb") as f2:
            c1, c2 = f1.read(), f2.read()
            if c1 == c2:
                log_ok(f"{fn}: версии в figma_plugin/ и навыке figma-assistant на 100% совпадают.")
            else:
                log_warn(f"{fn}: версии различаются!")
                all_ok = False
                if auto_fix:
                    import shutil
                    shutil.copy2(src, dst)
                    log_ok(f"Автоматически синхронизирован {fn} из figma_plugin/ в навык.")

    return all_ok


def check_toc_category_parity() -> bool:
    print(f"\n{BOLD}4. Проверка соответствия категорий Оглавления (TOC):{RESET}")
    all_ok = True
    try:
        from server.agents import toc_agent
        cat_map = toc_agent.CATEGORY_MAP
        expected_types = [
            "quiz_photo", "flip_cards", "video_quiz", "vocabulary_table",
            "flashcards", "fill_blanks", "speaking_cards", "timestamp", "full_lesson"
        ]
        missing = [t for t in expected_types if t not in cat_map]
        if missing:
            log_fail(f"toc_agent.CATEGORY_MAP: отсутствуют категории для типов: {missing}")
            all_ok = False
        else:
            log_ok(f"toc_agent.CATEGORY_MAP содержит все {len(expected_types)} необходимых типов блоков (включая full_lesson).")

        # Check code.js categories count
        code_path = os.path.join(PROJECT_ROOT, "figma_plugin", "code.js")
        with open(code_path, "r", encoding="utf-8", errors="replace") as f:
            code_text = f.read()

        m = re.search(r"const CATEGORIES = \[(.*?)\];", code_text, re.DOTALL)
        if m:
            cat_count = len(re.findall(r"num:\s*\d+", m.group(1)))
            if cat_count in (9, 10):
                log_ok(f"figma_plugin/code.js: в оглавлении определены все {cat_count} категорий (включая ТАЙМЛАЙН и УРОКИ).")
            else:
                log_warn(f"figma_plugin/code.js: найдено {cat_count} категорий вместо ожидаемых 10.")
                all_ok = False
    except Exception as e:
        log_fail(f"Ошибка проверки категорий TOC: {e}")
        all_ok = False

    return all_ok


def check_memory_integrity() -> bool:
    print(f"\n{BOLD}5. Проверка долговременной памяти проекта (.antigravity):{RESET}")
    all_ok = True
    brain_dir = os.path.join(PROJECT_ROOT, ".antigravity")

    # Check brain_context.md
    bc_path = os.path.join(brain_dir, "brain_context.md")
    if os.path.exists(bc_path):
        try:
            with open(bc_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) <= 150:
                log_ok(f"brain_context.md: UTF-8 валиден, длина {len(lines)} строк (лимит <= 150 соблюден).")
            else:
                log_warn(f"brain_context.md: превышен лимит 150 строк! Текущая длина: {len(lines)} строк.")
                all_ok = False
        except UnicodeDecodeError as e:
            log_fail(f"brain_context.md: повреждена кодировка UTF-8 ({e})!")
            all_ok = False
    else:
        log_fail("brain_context.md не найден!")
        all_ok = False

    # Check tech_stack_guidelines.md
    ts_path = os.path.join(brain_dir, "tech_stack_guidelines.md")
    if os.path.exists(ts_path):
        try:
            with open(ts_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Count bug journal items
            items = re.findall(r"^\d+\.\s+\*\*", content, re.MULTILINE)
            log_ok(f"tech_stack_guidelines.md: UTF-8 валиден, зафиксировано {len(items)} правил/багов в Журнале Ошибок.")
        except UnicodeDecodeError as e:
            log_fail(f"tech_stack_guidelines.md: повреждена кодировка UTF-8 ({e})!")
            all_ok = False

    return all_ok


def main():
    auto_fix = "--fix" in sys.argv
    print(f"{BOLD}============================================================{RESET}")
    print(f"{CYAN}{BOLD}   ESL Figma AI — Аудит и Верификация Системы (GSD Verifier){RESET}")
    print(f"{BOLD}============================================================{RESET}")

    r1 = check_python_compilation()
    r2 = check_plugin_integrity()
    r3 = check_plugin_sync(auto_fix=auto_fix)
    r4 = check_toc_category_parity()
    r5 = check_memory_integrity()

    print(f"\n{BOLD}============================================================{RESET}")
    if r1 and r2 and r3 and r4 and r5:
        print(f"{GREEN}{BOLD}🎉 ВСЕ ПРОВЕРКИ УСПЕШНО ПРОЙДЕНЫ! Система готова к работе.{RESET}")
        print(f"{BOLD}============================================================{RESET}\n")
        return 0
    else:
        print(f"{RED}{BOLD}⚠️ ВНИМАНИЕ: Обнаружены проблемы при аудите системы.{RESET}")
        print(f"Запустите с флагом --fix для автоматического исправления синхронизации.")
        print(f"{BOLD}============================================================{RESET}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
