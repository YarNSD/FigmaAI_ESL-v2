# 🛡️ GSD Verification & Engineering Integrity Rules for FigmaAI

## 1. Обязательный аудит после изменений (GSD Verifier)
При любых изменениях в коде плагина (`figma_plugin/`), серверной части (`server/`), оглавлении (`toc_agent.py`) или файлах памяти:
- **Всегда запускать экспресс-аудит**:
  `python scripts/verify_system.py --fix`
- Задача считается выполненной **только тогда**, когда скрипт возвращает `🎉 ВСЕ ПРОВЕРКИ УСПЕШНО ПРОЙДЕНЫ!`.

## 2. Безусловная синхронизация плагина
- Файлы плагина в проекте (`figma_plugin/`) и в глобальном навыке (`C:\Users\Admin\.gemini\config\skills\figma-assistant\plugin/`) должны быть идентичны на 100%.
- Запуск `python scripts/verify_system.py --fix` гарантирует автоматическую синхронизацию.

## 3. Защита от ReferenceError и падений DOM в плагине
- Запрещено использовать необъявленные переменные в условиях (`if (someVar)`) без предварительного объявления `const someVar = document.getElementById("someVar");`.
- Все обработчики событий `.addEventListener` обязаны проверяться на существование элемента в DOM (`if (el) el.addEventListener(...)`).

## 4. Паритет категорий Оглавления (TOC Parity)
- Любой новый тип образовательного блока в `server/agents/layout_agent.py` обязан иметь соответствующую запись в `server/agents/toc_agent.py` (`CATEGORY_MAP`) и категорию в `figma_plugin/code.js`.

## 5. Журнал Ошибок (Bug Journaling)
- Любой устраненный баг фиксируется в `.antigravity/tech_stack_guidelines.md` с описанием причины и архитектурного решения.
