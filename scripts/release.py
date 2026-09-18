"""
ESL Figma AI — Release Automation Script
Publishes a new release to GitHub (YarNSD/FigmaAI_ESL-v2) in 1 command:
1. Runs verify_system.py (GSD verifier)
2. Bumps version in VERSION
3. Commits & pushes to main
4. Creates official GitHub Release with changelog via gh CLI
"""
import os
import sys
import subprocess
import re
from pathlib import Path

# Configure UTF-8 for console output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = PROJECT_ROOT / "VERSION"
VERIFIER_SCRIPT = PROJECT_ROOT / "scripts" / "verify_system.py"
DEFAULT_REPO = "YarNSD/FigmaAI_ESL-v2"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def run_command(cmd, check=True):
    print(f"  {CYAN}▸ {' '.join(cmd)}{RESET}")
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and res.returncode != 0:
        print(f"{RED}❌ Ошибка выполнения команды: {' '.join(cmd)}{RESET}")
        print(res.stderr or res.stdout)
        sys.exit(1)
    return res


def main():
    if len(sys.argv) < 2:
        print(f"\n{BOLD}Использование:{RESET}")
        print("  python scripts/release.py <версия> [список_изменений]")
        print("\nПримеры:")
        print("  python scripts/release.py 0.11 \"Добавлена поддержка новых карточек и ускорена генерация\"")
        print("  python scripts/release.py 0.12.0\n")
        sys.exit(1)

    raw_ver = sys.argv[1].strip().lstrip("v")
    if not re.match(r"^\d+\.\d+(\.\d+)?$", raw_ver):
        print(f"{RED}❌ Некорректный формат версии: '{raw_ver}'. Используйте формат 0.11 или 0.11.0{RESET}")
        sys.exit(1)

    tag = f"v{raw_ver}"
    changelog = sys.argv[2] if len(sys.argv) > 2 else f"Обновление FigmaAI ESL {tag}"

    print(f"\n{BOLD}{CYAN}============================================================{RESET}")
    print(f"{BOLD}  🚀 Публикация нового релиза: {GREEN}{tag}{RESET}")
    print(f"{BOLD}{CYAN}============================================================{RESET}\n")

    # 1. Verification
    print(f"{BOLD}1. Запуск верификатора системы:{RESET}")
    res = subprocess.run([sys.executable, str(VERIFIER_SCRIPT)], cwd=str(PROJECT_ROOT))
    if res.returncode != 0:
        print(f"\n{RED}❌ Верификатор выявил ошибки! Исправьте их перед выпуском релиза.{RESET}")
        sys.exit(1)

    # 2. Bump VERSION
    print(f"\n{BOLD}2. Обновление файла VERSION -> {raw_ver}{RESET}")
    VERSION_FILE.write_text(raw_ver, encoding="utf-8")

    # 3. Git commit & push
    print(f"\n{BOLD}3. Фиксация изменений в Git:{RESET}")
    run_command(["git", "add", "."])
    
    commit_res = run_command(["git", "commit", "-m", f"Release {tag}: {changelog[:60]}"], check=False)
    if commit_res.returncode == 0:
        print(f"  {GREEN}✅ Коммит успешно создан.{RESET}")
    else:
        print(f"  {YELLOW}ℹ️ Изменений для нового коммита нет (файлы уже закоммичены).{RESET}")

    print(f"\n{BOLD}4. Отправка изменений в GitHub (main):{RESET}")
    run_command(["git", "push", "origin", "main"])
    print(f"  {GREEN}✅ Ветка main успешно отправлена на GitHub.{RESET}")

    # 5. Create GitHub Release
    print(f"\n{BOLD}5. Создание GitHub Release ({tag}):{RESET}")
    gh_cmd = [
        "gh", "release", "create", tag,
        "--repo", DEFAULT_REPO,
        "--title", f"Версия {tag}",
        "--notes", changelog
    ]
    res_gh = run_command(gh_cmd, check=False)
    if res_gh.returncode == 0:
        print(f"  {GREEN}🎉 GitHub Release {tag} успешно создан!{RESET}")
    else:
        if "already exists" in res_gh.stderr:
            print(f"  {YELLOW}⚠️ Тег/релиз {tag} уже существует. Обновляем описание...{RESET}")
            run_command(["gh", "release", "edit", tag, "--repo", DEFAULT_REPO, "--notes", changelog], check=False)
        else:
            print(f"  {RED}⚠️ Замечание gh: {res_gh.stderr.strip()}{RESET}")

    print(f"\n{BOLD}{GREEN}============================================================{RESET}")
    print(f"{BOLD}{GREEN}  ✅ РЕЛИЗ {tag} УСПЕШНО ОПУБЛИКОВАН НА GITHUB!{RESET}")
    print(f"  🌐 Страница релиза: https://github.com/{DEFAULT_REPO}/releases/tag/{tag}")
    print(f"  💻 Все клиентские ПК теперь увидят уведомление в Web UI.")
    print(f"{BOLD}{GREEN}============================================================{RESET}\n")


if __name__ == "__main__":
    main()
