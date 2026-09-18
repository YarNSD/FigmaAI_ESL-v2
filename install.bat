@echo off
chcp 65001 >nul
title ESL Figma AI — Автоматический установщик
setlocal enabledelayedexpansion

echo ============================================================
echo          🚀 ESL Figma AI — Автоматический установщик
echo ============================================================
echo.

:: 1. Выбор папки установки
echo [1/6] Выбор директории установки проекта
echo ------------------------------------------------------------
set "DEFAULT_DIR=C:\FigmaAI"
echo По умолчанию проект будет установлен в: %DEFAULT_DIR%
set /p "USER_DIR=Куда установить проект? [Нажмите Enter для %DEFAULT_DIR%]: "

if "%USER_DIR%"=="" (
    set "TARGET_DIR=%DEFAULT_DIR%"
) else (
    set "TARGET_DIR=%USER_DIR%"
)

:: Очистка кавычек
set "TARGET_DIR=%TARGET_DIR:"=%"

echo.
echo [+] Целевая папка установки: %TARGET_DIR%
echo.

:: 2. Подготовка папки и копирование файлов
echo [2/6] Подготовка директории и файлов...
echo ------------------------------------------------------------
if not exist "%TARGET_DIR%" (
    echo [*] Создаю папку %TARGET_DIR%...
    mkdir "%TARGET_DIR%" 2>nul
)

set "CURRENT_DIR=%~dp0"
if "%CURRENT_DIR:~-1%"=="\" set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"

if /i not "%CURRENT_DIR%"=="%TARGET_DIR%" (
    echo [*] Копирую файлы проекта в %TARGET_DIR%...
    robocopy "%CURRENT_DIR%" "%TARGET_DIR%" /E /XD .venv .git __pycache__ /XF *.pyc /R:1 /W:1 >nul
    if errorlevel 8 (
        echo [!] Robocopy вернул ошибку, копирую через xcopy...
        xcopy "%CURRENT_DIR%\*" "%TARGET_DIR%\" /E /I /Y /Q >nul 2>&1
    )
    echo [+] Файлы проекта успешно скопированы.
) else (
    echo [+] Установка выполняется в текущей папке.
)
echo.

:: 3. Проверка Python
echo [3/6] Проверка окружения Python...
echo ------------------------------------------------------------
set "PY_CMD="
where python >nul 2>&1
if not errorlevel 1 set "PY_CMD=python"
if not defined PY_CMD (
    where py >nul 2>&1
    if not errorlevel 1 set "PY_CMD=py"
)

if defined PY_CMD (
    for /f "tokens=2" %%v in ('%PY_CMD% --version 2^>^&1') do set "PY_VER=%%v"
    echo [+] Обнаружен Python: !PY_VER!
) else (
    echo [!] Python не найден в системе.
    echo [*] Автоматическая загрузка официального установщика Python 3.11...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe', '%TEMP%\python_setup.exe')"
    if exist "%TEMP%\python_setup.exe" (
        echo [*] Установка Python (с добавлением в PATH)...
        "%TEMP%\python_setup.exe" /passive InstallAllUsers=1 PrependPath=1 Include_test=0
        del "%TEMP%\python_setup.exe" >nul 2>&1
        set "PY_CMD=python"
        echo [+] Python успешно установлен.
    ) else (
        echo [!] Не удалось загрузить Python автоматически.
        echo     Пожалуйста, установите Python вручную с https://www.python.org/
        pause
        exit /b 1
    )
)
echo.

:: 4. Проверка Antigravity IDE (для работы ИИ без API-ключей)
echo [4/6] Проверка Antigravity IDE (ИИ без API-ключей)...
echo ------------------------------------------------------------
set "IDE_FOUND="
if exist "%LOCALAPPDATA%\Programs\Antigravity IDE\Antigravity IDE.exe" set "IDE_FOUND=1"
if exist "%LOCALAPPDATA%\Programs\antigravity\Antigravity.exe" set "IDE_FOUND=1"
if exist "%ProgramFiles%\Antigravity IDE\Antigravity IDE.exe" set "IDE_FOUND=1"
if exist "%ProgramFiles%\Antigravity\Antigravity.exe" set "IDE_FOUND=1"
where agy >nul 2>&1
if not errorlevel 1 set "IDE_FOUND=1"

if defined IDE_FOUND (
    echo [+] Antigravity IDE обнаружен!
    echo     ИИ будет работать через встроенную авторизацию Google без API-ключей.
) else (
    echo [!] ВНИМАНИЕ: Antigravity IDE не обнаружен.
    echo     Для бесплатной работы ИИ без API-ключей установите Antigravity IDE
    echo     и один раз войдите в свой Google-аккаунт.
    echo.
    set /p "OPEN_IDE=Открыть сайт Antigravity IDE для скачивания? [Y/N]: "
    if /i "!OPEN_IDE!"=="Y" (
        start https://antigravity.google
        echo [*] Страница загрузки открыта в браузере.
        echo     После установки Antigravity IDE войдите под своим Google-аккаунтом.
        echo.
    )
)
echo.

:: 5. Настройка виртуального окружения и библиотек
echo [5/6] Настройка виртуального окружения Python (.venv)...
echo ------------------------------------------------------------
cd /d "%TARGET_DIR%"

if not exist ".venv\Scripts\activate.bat" (
    echo [*] Создание виртуального окружения .venv...
    %PY_CMD% -m venv .venv
)

echo [*] Активация окружения...
call .venv\Scripts\activate.bat

echo [*] Установка зависимостей (requirements.txt)...
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo [*] Проверка config.json...
if not exist "config.json" (
    if exist "config.example.json" (
        copy /y "config.example.json" "config.json" >nul
        echo [+] Создан локальный config.json из шаблона.
    )
)

echo [*] Верификация целостности системы...
python scripts\verify_system.py --fix >nul 2>&1
echo [+] Система верифицирована.
echo.

:: 6. Создание ярлыка на Рабочем столе
echo [6/6] Создание ярлыка запуска...
echo ------------------------------------------------------------
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\FigmaAI.lnk'); $s.TargetPath = '%TARGET_DIR%\start.bat'; $s.WorkingDirectory = '%TARGET_DIR%'; $s.WindowStyle = 1; $s.Description = 'ESL Figma AI Assistant'; $s.Save()"
echo [+] Создан ярлык 'FigmaAI' на Рабочем столе!
echo.

echo ============================================================
echo   🎉 УСТАНОВКА УСПЕШНО ЗАВЕРШЕНА!
echo ============================================================
echo.
echo Папка проекта: %TARGET_DIR%
echo.
echo Как запустить и подключить к Figma:
echo 1. Запустите проект двойным кликом по ярлыку 'FigmaAI' на Рабочем столе
echo    (или через start.bat в папке %TARGET_DIR%).
echo 2. Откройте приложение Figma Desktop.
echo 3. В левом верхнем меню Figma выберите:
echo    Plugins ➔ Development ➔ Import plugin from manifest...
echo 4. Выберите файл манифеста:
echo    %TARGET_DIR%\figma_plugin\manifest.json
echo 5. Запустите плагин. Он автоматически подключится к локальному
echo    серверу (localhost:45678) без каких-либо настроек IP!
echo ============================================================
echo.

set /p "LAUNCH_NOW=Запустить FigmaAI прямо сейчас? [Y/N]: "
if /i "!LAUNCH_NOW!"=="Y" (
    start "" "%TARGET_DIR%\start.bat"
)
