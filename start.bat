@echo off
chcp 65001 >nul
title ESL Figma AI — Launcher
cd /d "%~dp0"

echo ============================================================
echo           ESL Figma AI — Запуск сервера
echo ============================================================
echo.

:: 0. Автоматическая очистка старых процессов (порты 3000 и 45678)
echo [*] Проверка занятости портов...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000 " ^| findstr LISTENING') do (
    echo [i] Обнаружен старый процесс на порту 3000 [PID %%a]. Завершаю...
    taskkill /f /pid %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":45678 " ^| findstr LISTENING') do (
    echo [i] Обнаружен старый процесс на порту 45678 [PID %%a]. Завершаю...
    taskkill /f /pid %%a >nul 2>&1
)
ping -n 2 127.0.0.1 >nul
echo [+] Порты свободны.
echo.

:: 1. Проверка Python
set "PY_CMD="
where python >nul 2>&1
if not errorlevel 1 set "PY_CMD=python"
if defined PY_CMD goto :python_found

where py >nul 2>&1
if not errorlevel 1 set "PY_CMD=py"
if defined PY_CMD goto :python_found

echo [!] Ошибка: Python не найден в системе!
echo [*] Пожалуйста, установите Python 3.10+ с сайта https://www.python.org/
echo     и обязательно отметьте галочку "Add Python to PATH".
echo.
pause
exit /b 1

:python_found

:: 2. Проверка Antigravity CLI (agy)
where agy >nul 2>&1
if errorlevel 1 goto :no_agy
echo [+] Antigravity CLI обнаружен в системе.
goto :after_agy

:no_agy
echo [i] Antigravity CLI (agy) не найден в PATH.
echo     Будет использоваться Gemini API Key или запущенная Antigravity IDE.

:after_agy

:: 3. Активация виртуального окружения (.venv)
if exist ".venv\Scripts\activate.bat" goto :activate_venv

echo [*] Создание виртуального окружения .venv...
%PY_CMD% -m venv .venv
if errorlevel 1 goto :venv_failed
goto :activate_venv

:venv_failed
echo [!] Не удалось создать .venv, запуск через системный Python...
goto :install_deps

:activate_venv
call .venv\Scripts\activate.bat

:: 3.1 Проверка целостности и авто-синхронизация плагина
echo [*] Экспресс-аудит целостности системы (GSD Verifier)...
python scripts\verify_system.py --fix
if errorlevel 1 (
    echo.
    echo [!] Предупреждение: обнаружены проблемы при аудите системы.
)

:start_server
echo.
echo ============================================================
echo [+] Сервер успешно запущен!
echo [*] Панель управления:  Нативное окно Desktop App (Edge/Chrome)
echo [*] Веб-панель (fallback): http://localhost:3000/ui
echo [*] Мост FigJam / Figma: порт 45678
echo ============================================================
echo.

:: 4. Запуск сверхплавной нативной панели управления (Desktop App Mode)
echo [*] Запуск панели управления ESL Figma AI...
start "" "%PY_CMD%" scripts\launch_app.py

:: 6. Запуск FastAPI сервера
python -m server.main

if not errorlevel 1 goto :end
echo.
echo [!] Сервер завершил работу с ошибкой.
pause

:end