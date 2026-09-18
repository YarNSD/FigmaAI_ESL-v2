/* ── ESL Figma AI — Web Panel JavaScript ─────────────────────────── */

const API = '';  // same origin
let selectedLevel = 'A2';
let pendingParams = null;
let logWs = null;

// ── Init ────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  initLogWebSocket();
  pollStatus();
  setInterval(pollStatus, 5000);
  loadSettings();
  loadBoards();
  loadStudents();
  loadChatHistory();
  pollTelegramStatus();
  initBoardUrlListener();
  // Check for project updates on startup
  setTimeout(checkAppUpdate, 1500);
});

// ── Tab switching ────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const targetTab = document.getElementById('tab-' + name);
  if (targetTab) targetTab.classList.add('active');
  const targetNav = document.querySelector(`[data-tab="${name}"]`);
  if (targetNav) targetNav.classList.add('active');
  if (name === 'boards') loadBoards();
  if (name === 'telegram') pollTelegramStatus();
  if (name === 'feedback') onFeedbackStudentSelectChange();
}


// ── Status polling ───────────────────────────────────────────────────
async function pollStatus() {
  try {
    const r = await fetch(API + '/api/status');
    const s = await r.json();

    const pluginDot   = document.getElementById('pluginDot');
    const pluginLabel = document.getElementById('pluginLabel');
    const apiDot      = document.getElementById('apiDot');
    const apiLabel    = document.getElementById('apiLabel');
    const appVersion  = document.getElementById('appVersion');

    if (appVersion && s.version) {
      appVersion.textContent = 'v' + s.version;
    }

    if (s.plugin_connected) {
      pluginDot.className = 'status-dot connected';
      pluginLabel.textContent = '✅ Плагин подключён';
    } else {
      pluginDot.className = 'status-dot error';
      pluginLabel.textContent = 'Плагин не подключён';
    }

    if (s.ai_ready) {
      apiDot.className = 'status-dot ok';
      if (s.ai_engine === 'antigravity') {
        apiLabel.textContent = `⚡ Antigravity (${s.model || 'Flash'})`;
      } else {
        apiLabel.textContent = `Gemini API (${s.model || 'Ready'})`;
      }
    } else {
      apiDot.className = 'status-dot error';
      apiLabel.textContent = 'ИИ не готов';
    }
  } catch(e) {}
}


// ── Level selection ──────────────────────────────────────────────────
function setLevel(lvl) {
  selectedLevel = lvl;
  document.querySelectorAll('.level-btn').forEach(b => {
    b.classList.toggle('active', b.textContent.trim() === lvl);
  });
}

// ── Block type change ────────────────────────────────────────────────
function onBlockTypeChange() {
  const bt = document.getElementById('blockType').value;
  const ytGroup = document.getElementById('ytGroup');
  ytGroup.style.display = (bt === 'video_quiz') ? 'flex' : 'none';
}

// ── Create from command bar ──────────────────────────────────────────
async function createBlock() {
  const command = document.getElementById('commandInput').value.trim();
  if (!command) return;
  await doCreate({ command });
}

// ── Create from form ─────────────────────────────────────────────────
async function createFromForm() {
  const block_type  = document.getElementById('blockType').value;
  const board_id    = document.getElementById('boardSelect')?.value || null;
  const youtube_url = document.getElementById('ytInput')?.value?.trim() || null;
  const student_id  = document.getElementById('chatStudentSelect')?.value || null;

  let command = lastUserMessage || '';
  if (!command) {
    if (block_type === 'bloom_lesson') {
      command = `Создай комплексный урок по Таксономии Блума для уровня ${selectedLevel}`;
    } else if (block_type === 'auto') {
      command = `Создай интерактивный учебный блок для уровня ${selectedLevel}`;
    } else {
      command = `Создай учебный блок ${block_type} для уровня ${selectedLevel}`;
    }
  }

  await doCreate({
    block_type: (block_type === 'auto') ? null : block_type,
    command,
    level: selectedLevel,
    board_id,
    youtube_url,
    student_id
  });
}

// ── Core create function ─────────────────────────────────────────────
async function doCreate(params) {
  hideResult();
  hideClarify();
  showProgress(0);

  const btn = document.getElementById('createBtn');
  const btnIcon = document.getElementById('createBtnIcon');
  const btnText = document.getElementById('createBtnText');
  if (btn) { btn.disabled = true; }
  if (btnIcon) { btnIcon.className = 'spinning'; btnIcon.textContent = '⏳'; }
  if (btnText) btnText.textContent = 'Создаю...';

  try {
    // Fake progress steps
    await animateProgress([
      [10, '🧠 Генерирую контент...', 'step1'],
      [50, '🎨 Рисую на доске...', 'step2'],
      [85, '📑 Обновляю оглавление...', 'step3'],
    ]);

    const r = await fetch(API + '/api/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });

    const data = await r.json();
    setProgress(100);

    if (data.needs_clarification) {
      hideProgress();
      showClarify(data.message, data.params);
      pendingParams = data.params;
    } else if (data.ok) {
      finishSteps();
      showResult('success', data.message);
    } else {
      hideProgress();
      showResult('error', `❌ ${data.message || data.detail || 'Ошибка'}`);
    }
  } catch(e) {
    hideProgress();
    showResult('error', `❌ Ошибка соединения с сервером: ${e.message}`);
  } finally {
    if (btn) btn.disabled = false;
    if (btnIcon) { btnIcon.className = ''; btnIcon.textContent = '🎨'; }
    if (btnText) btnText.textContent = 'Создать блок';
  }
}

// ── Clarification response ───────────────────────────────────────────
async function clarifyWith(level) {
  hideClarify();
  if (!pendingParams) return;
  const params = { ...pendingParams, level, missing: [] };
  pendingParams = null;
  await doCreate(params);
}

// ── Quick create from templates tab ─────────────────────────────────
function quickCreate(blockType) {
  switchTab('create');
  document.getElementById('blockType').value = blockType;
  onBlockTypeChange();
  document.getElementById('topicInput').focus();
}

// ── Progress helpers ─────────────────────────────────────────────────
function showProgress(pct) {
  const area = document.getElementById('progressArea');
  area.style.display = 'block';
  setProgress(pct);
  document.querySelectorAll('.step').forEach(s => {
    s.classList.remove('active', 'done');
    s.style.color = '';
  });
}

function setProgress(pct) {
  document.getElementById('progressFill').style.width = pct + '%';
}

async function animateProgress(steps) {
  for (const [pct, text, stepId] of steps) {
    setProgress(pct);
    const step = document.getElementById(stepId);
    if (step) { step.classList.add('active'); }
    await sleep(800);
  }
}

function finishSteps() {
  setProgress(100);
  document.querySelectorAll('.step').forEach(s => {
    s.classList.remove('active');
    s.classList.add('done');
  });
  setTimeout(hideProgress, 2000);
}

function hideProgress() {
  document.getElementById('progressArea').style.display = 'none';
}

// ── Result helpers ───────────────────────────────────────────────────
function showResult(type, msg) {
  const area = document.getElementById('resultArea');
  area.style.display = 'block';
  area.className = 'result-area ' + type;
  area.textContent = msg;
}

function hideResult() {
  document.getElementById('resultArea').style.display = 'none';
}

function showClarify(msg, params) {
  const area = document.getElementById('clarifyArea');
  document.getElementById('clarifyMessage').textContent = msg;
  area.style.display = 'block';
}

function hideClarify() {
  document.getElementById('clarifyArea').style.display = 'none';
}

// ── Settings ─────────────────────────────────────────────────────────
function toggleEngineSettings() {
  const notice = document.getElementById('engineNotice');
  if (notice) {
    notice.innerHTML = '✅ 100% On-Device: Все агенты работают строго локально на вашем компьютере. Никаких внешних API-ключей и облачных запросов!';
    notice.style.color = 'var(--accent-light)';
  }
}

async function loadSettings() {
  try {
    const r = await fetch(API + '/api/config');
    const cfg = await r.json();

    const v = (id, val) => { const el = document.getElementById(id); if(el && val) el.value = val; };
    const engineEl = document.getElementById('engineSelect');
    if (engineEl) engineEl.value = 'antigravity';
    toggleEngineSettings();

    v('modelSelect', cfg.ai?.model);
    v('tutoringUrl', cfg.figma?.boards?.tutoring?.url);
    v('radugaUrl', cfg.figma?.boards?.raduga?.url);

    const tgEn = document.getElementById('tgEnabled');
    if (tgEn) tgEn.checked = cfg.telegram?.enabled || false;
    toggleTelegram();

    v('proxyHost', cfg.telegram?.proxy?.host);
    v('proxyPort', cfg.telegram?.proxy?.port);

    const tgIds = cfg.telegram?.allowed_user_ids || [];
    const tgIdsEl = document.getElementById('tgIds');
    if (tgIdsEl) tgIdsEl.value = tgIds.join(', ');
  } catch(e) {}
}

async function saveSettings() {
  const payload = {
    engine: 'antigravity',
    model: document.getElementById('modelSelect')?.value,
    tutoring_board_url: document.getElementById('tutoringUrl')?.value,
    raduga_board_url: document.getElementById('radugaUrl')?.value,
    telegram_enabled: document.getElementById('tgEnabled')?.checked,
    telegram_proxy_host: document.getElementById('proxyHost')?.value,
    telegram_proxy_port: parseInt(document.getElementById('proxyPort')?.value) || 1080,
  };

  const tgToken = document.getElementById('tgToken')?.value?.trim();
  if (tgToken && !tgToken.startsWith('***')) payload.telegram_bot_token = tgToken;

  const tgIdsRaw = document.getElementById('tgIds')?.value || '';
  payload.allowed_user_ids = tgIdsRaw.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n));

  try {
    const r = await fetch(API + '/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    const res = document.getElementById('settingsResult');
    res.textContent = data.ok ? '✅ Сохранено!' : ('❌ ' + data.message);
    res.className = 'inline-result ' + (data.ok ? 'success' : 'error');
    setTimeout(() => { res.textContent = ''; res.className = 'inline-result'; }, 3000);
    await pollStatus();
  } catch(e) {
    document.getElementById('settingsResult').textContent = '❌ Ошибка: ' + e.message;
  }
}

function toggleTelegram() {
  const enabled = document.getElementById('tgEnabled')?.checked;
  const settings = document.getElementById('tgSettings');
  if (settings) settings.style.display = enabled ? 'block' : 'none';
}

function toggleVisibility(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.type = el.type === 'password' ? 'text' : 'password';
}

async function testTelegram() {
  alert('Функция проверки Telegram будет доступна после настройки токена.');
}

// ── TOC Refresh ───────────────────────────────────────────────────────
async function refreshTOC() {
  try {
    const r = await fetch(API + '/api/toc/refresh', { method: 'POST' });
    const data = await r.json();
    if (data.ok) alert('✅ Оглавление обновлено!');
    else alert('❌ ' + (data.error || data.message || 'Ошибка'));
  } catch(e) {
    alert('❌ Ошибка: ' + e.message);
  }
}

// ── Log Streaming (SSE & WebSocket) ──────────────────────────────────
const seenWebLogIds = new Set();

function initLogWebSocket() {
  // 1. Primary: Server-Sent Events stream for rich thought logs
  try {
    const es = new EventSource('/api/logs/stream');
    es.onmessage = (e) => {
      try {
        const item = JSON.parse(e.data);
        appendThoughtToLiveStream(item);
        appendLog(item.stage === 'error' ? 'error' : (item.stage === 'done' ? 'success' : 'info'), `${item.icon || ''} ${item.title}: ${item.message}`);
      } catch(err) {}
    };
    es.onerror = () => {
      es.close();
      setTimeout(initLogWebSocket, 3000);
    };
  } catch(e) {
    // Fallback to WebSocket
    const wsUrl = `ws://${location.host}/ws/logs`;
    logWs = new WebSocket(wsUrl);
    logWs.onmessage = (e) => {
      try {
        const entry = JSON.parse(e.data);
        if (entry.title) appendThoughtToLiveStream(entry);
        appendLog(entry.level || 'info', entry.message);
      } catch(err) {}
    };
    logWs.onclose = () => {
      setTimeout(initLogWebSocket, 3000);
    };
  }
}

function appendThoughtToLiveStream(item) {
  if (!item || !item.message) return;
  if (item.id && seenWebLogIds.has(item.id)) return;
  if (item.id) seenWebLogIds.add(item.id);

  const stream = document.getElementById('agentThoughtsStream');
  if (!stream) return;

  const placeholder = document.getElementById('thoughtPlaceholder');
  if (placeholder) placeholder.style.display = 'none';

  const card = document.createElement('div');
  card.className = `thought-card stage-${item.stage || 'analyzing'}`;

  const time = item.timestamp || new Date().toLocaleTimeString();
  const icon = item.icon || '💡';
  const title = item.title || 'Мысль агента';
  const msg = item.message || '';

  card.innerHTML = `
    <span class="thought-card-time">${escapeHtml(time)}</span>
    <span class="thought-card-icon">${icon}</span>
    <div class="thought-card-main">
      <div class="thought-card-title">${escapeHtml(title)}</div>
      <div class="thought-card-msg">${escapeHtml(msg)}</div>
    </div>
  `;

  stream.appendChild(card);
  stream.scrollTop = stream.scrollHeight;

  // Update status badge & pulse
  const badge = document.getElementById('agentStatusBadge');
  const pulse = document.getElementById('agentLivePulse');
  if (badge) badge.textContent = title;

  if (pulse) {
    if (item.stage === 'done' || item.stage === 'error') {
      pulse.classList.remove('active');
    } else {
      pulse.classList.add('active');
    }
  }
}

function clearLiveThoughts() {
  const stream = document.getElementById('agentThoughtsStream');
  if (stream) {
    stream.innerHTML = `
      <div class="thought-placeholder" id="thoughtPlaceholder">
        <span>💡 Ожидание команды — здесь в реальном времени отобразится ход мыслей агента.</span>
      </div>
    `;
  }
  const badge = document.getElementById('agentStatusBadge');
  if (badge) badge.textContent = 'Очищено';
  const pulse = document.getElementById('agentLivePulse');
  if (pulse) pulse.classList.remove('active');
  fetch('/api/logs', { method: 'DELETE' }).catch(() => {});
}

function appendLog(level, message) {
  const container = document.getElementById('logContainer');
  if (!container) return;

  const div = document.createElement('div');
  div.className = `log-entry ${level}`;

  const time = new Date().toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  div.innerHTML = `<span class="log-time">${time}</span>${escapeHtml(message)}`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;

  const count = container.children.length;
  const countEl = document.getElementById('logCount');
  if (countEl) countEl.textContent = count + ' записей';
}

function clearLogs() {
  clearLiveThoughts();
  const container = document.getElementById('logContainer');
  if (container) container.innerHTML = '';
  const countEl = document.getElementById('logCount');
  if (countEl) countEl.textContent = '0 записей';
}

// ── Utilities ─────────────────────────────────────────────────────────
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ── Board Management ──────────────────────────────────────────────────
let boardsData = [];

function initBoardUrlListener() {
  const urlInput = document.getElementById('newBoardUrl');
  const hint = document.getElementById('boardTypeHint');
  if (!urlInput || !hint) return;

  urlInput.addEventListener('input', () => {
    const val = urlInput.value.trim();
    if (val.includes('/board/')) {
      hint.textContent = '✨ Обнаружена доска FigJam (бесконечный интерактивный холст)';
    } else if (val.includes('/design/') || val.includes('/file/')) {
      hint.textContent = '🎨 Обнаружен Figma Design файл';
    } else if (val) {
      hint.textContent = 'ℹ️ Проверьте правильность ссылки на Figma / FigJam';
    } else {
      hint.textContent = '';
    }
  });
}

async function loadBoards() {
  try {
    const r = await fetch(API + '/api/boards');
    if (!r.ok) throw new Error('Ошибка сервера ' + r.status);
    const data = await r.json();
    boardsData = data.boards || [];
    const activeId = data.active;

    renderBoardsList(boardsData, activeId);
    updateActiveBoardBanner(boardsData, activeId);
    populateBoardSelect(boardsData, activeId);
  } catch(e) {
    const list = document.getElementById('boardsList');
    if (list) {
      list.innerHTML = `<div class="boards-empty"><p style="color:var(--red)">❌ Ошибка загрузки досок: ${escapeHtml(e.message)}</p></div>`;
    }
  }
}

function renderBoardsList(boards, activeId) {
  const list = document.getElementById('boardsList');
  if (!list) return;

  if (!boards || boards.length === 0) {
    list.innerHTML = `
      <div class="boards-empty">
        <div class="boards-empty-icon">📂</div>
        <p><b>Нет добавленных досок</b></p>
        <p style="font-size:12px;color:var(--text-3);margin-top:4px">
          Добавьте ссылку на вашу доску FigJam выше, чтобы создавать на ней учебные блоки.
        </p>
      </div>`;
    return;
  }

  let html = '';
  for (const b of boards) {
    const isActive = b.id === activeId;
    const isFigJam = b.board_type === 'figjam';
    const icon = isFigJam ? '🟡' : '🎨';
    const typeLabel = isFigJam ? 'FigJam' : (b.board_type === 'design' ? 'Figma Design' : 'Figma');
    const typeClass = isFigJam ? 'figjam' : (b.board_type === 'design' ? 'design' : 'unknown');

    const aliasesStr = (b.aliases && b.aliases.length > 0)
      ? `<div class="board-card-aliases">Псевдонимы: ${escapeHtml(b.aliases.join(', '))}</div>`
      : '';

    html += `
      <div class="board-card ${isActive ? 'active-card' : ''}" id="board-card-${escapeHtml(b.id)}">
        <div class="board-card-icon">${icon}</div>
        <div class="board-card-info">
          <div class="board-card-name">
            ${escapeHtml(b.display_name)}
            ${isActive ? '<span class="board-active-tag">АКТИВНА</span>' : ''}
            <span class="board-type-badge ${typeClass}">${typeLabel}</span>
          </div>
          <div class="board-card-url" title="${escapeHtml(b.url)}">${escapeHtml(b.url || 'Ссылка не указана')}</div>
          ${aliasesStr}
        </div>
        <div class="board-card-actions">
          <button class="btn-activate" ${isActive ? 'disabled' : ''} onclick="activateBoard('${escapeHtml(b.id)}')">
            ${isActive ? '✓ Активна' : 'Сделать активной'}
          </button>
          <button class="btn-del" title="Удалить доску" onclick="deleteBoard('${escapeHtml(b.id)}', '${escapeHtml(b.display_name)}')">
            🗑️
          </button>
        </div>
      </div>
    `;
  }
  list.innerHTML = html;
}

function updateActiveBoardBanner(boards, activeId) {
  const nameEl = document.getElementById('activeBoardName');
  const typeEl = document.getElementById('activeBoardType');
  const activeBoard = boards.find(b => b.id === activeId);

  if (activeBoard && nameEl) {
    nameEl.textContent = `Активная доска: ${activeBoard.display_name}`;
    if (typeEl) {
      const isFigJam = activeBoard.board_type === 'figjam';
      typeEl.textContent = isFigJam ? 'FigJam' : 'Figma Design';
      typeEl.className = `board-type-badge ${isFigJam ? 'figjam' : 'design'}`;
      typeEl.style.display = 'inline-block';
    }
  } else if (nameEl) {
    nameEl.textContent = 'Нет активной доски (добавьте доску ниже)';
    if (typeEl) typeEl.style.display = 'none';
  }
}

function populateBoardSelect(boards, activeId) {
  const sel = document.getElementById('boardSelect');
  if (!sel) return;

  sel.innerHTML = '';
  if (!boards || boards.length === 0) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = '— Нет досок (добавьте во вкладке «Мои доски») —';
    sel.appendChild(opt);
    return;
  }

  for (const b of boards) {
    const opt = document.createElement('option');
    opt.value = b.id;
    const isFigJam = b.board_type === 'figjam';
    opt.textContent = `${isFigJam ? '🟡 ' : '🎨 '}${b.display_name}${b.id === activeId ? ' (текущая)' : ''}`;
    if (b.id === activeId) opt.selected = true;
    sel.appendChild(opt);
  }
}

async function addBoard() {
  const nameInput = document.getElementById('newBoardName');
  const urlInput = document.getElementById('newBoardUrl');
  const aliasesInput = document.getElementById('newBoardAliases');
  const resultEl = document.getElementById('boardAddResult');

  const name = nameInput?.value?.trim();
  const url = urlInput?.value?.trim();
  const aliasesRaw = aliasesInput?.value?.trim() || '';

  if (!name) {
    if (resultEl) {
      resultEl.textContent = '❌ Укажите название доски!';
      resultEl.className = 'inline-result error';
    }
    nameInput?.focus();
    return;
  }

  if (!url) {
    if (resultEl) {
      resultEl.textContent = '❌ Укажите ссылку на доску Figma/FigJam!';
      resultEl.className = 'inline-result error';
    }
    urlInput?.focus();
    return;
  }

  const aliases = aliasesRaw.split(',').map(s => s.trim()).filter(Boolean);

  if (resultEl) {
    resultEl.textContent = '⏳ Добавление...';
    resultEl.className = 'inline-result';
  }

  try {
    const r = await fetch(API + '/api/boards', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: name, url, aliases }),
    });

    const data = await r.json();
    if (r.ok && data.ok) {
      if (nameInput) nameInput.value = '';
      if (urlInput) urlInput.value = '';
      if (aliasesInput) aliasesInput.value = '';
      const hint = document.getElementById('boardTypeHint');
      if (hint) hint.textContent = '';

      if (resultEl) {
        resultEl.textContent = `✅ Доска «${name}» успешно добавлена!`;
        resultEl.className = 'inline-result success';
        setTimeout(() => { if (resultEl) resultEl.textContent = ''; }, 4000);
      }

      await loadBoards();
    } else {
      if (resultEl) {
        resultEl.textContent = '❌ ' + (data.detail || data.message || 'Ошибка добавления');
        resultEl.className = 'inline-result error';
      }
    }
  } catch(e) {
    if (resultEl) {
      resultEl.textContent = '❌ Ошибка сети: ' + e.message;
      resultEl.className = 'inline-result error';
    }
  }
}

async function activateBoard(boardId) {
  try {
    const r = await fetch(`${API}/api/boards/${encodeURIComponent(boardId)}/activate`, {
      method: 'POST',
    });
    const data = await r.json();
    if (data.ok) {
      await loadBoards();
    } else {
      alert('❌ Ошибка активации: ' + (data.detail || data.message));
    }
  } catch(e) {
    alert('❌ Ошибка: ' + e.message);
  }
}

async function deleteBoard(boardId, displayName) {
  if (!confirm(`Удалить доску «${displayName || boardId}»?`)) return;

  try {
    const r = await fetch(`${API}/api/boards/${encodeURIComponent(boardId)}`, {
      method: 'DELETE',
    });
    const data = await r.json();
    if (data.ok) {
      await loadBoards();
    } else {
      alert('❌ Ошибка удаления: ' + (data.detail || data.message));
    }
  } catch(e) {
    alert('❌ Ошибка: ' + e.message);
  }
}

// ── Voice Dictation (Web Speech API) ──────────────────────────────────
let webRecognition = null;
let isWebRecording = false;

function toggleWebVoice() {
  const SpeechClass = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechClass) {
    alert("Голосовой ввод не поддерживается в этом браузере.");
    return;
  }
  const btn = document.getElementById('webMicBtn');
  const input = document.getElementById('commandInput');

  if (isWebRecording) {
    if (webRecognition) webRecognition.stop();
    isWebRecording = false;
    if (btn) btn.style.background = '';
    return;
  }

  if (!webRecognition) {
    webRecognition = new SpeechClass();
    webRecognition.lang = 'ru-RU';
    webRecognition.continuous = false;
    webRecognition.interimResults = false;
    webRecognition.onresult = (e) => {
      const text = e.results[0][0].transcript;
      if (input) input.value = (input.value ? input.value + ' ' : '') + text;
      isWebRecording = false;
      if (btn) btn.style.background = '';
    };
    webRecognition.onerror = () => {
      isWebRecording = false;
      if (btn) btn.style.background = '';
    };
    webRecognition.onend = () => {
      isWebRecording = false;
      if (btn) btn.style.background = '';
    };
  }

  try {
    webRecognition.start();
    isWebRecording = true;
    if (btn) btn.style.background = 'rgba(220, 38, 38, 0.25)';
  } catch(e) {}
}



// ── Toast Notifications ──────────────────────────────────────────────
function showToast(msg, type = 'info', duration = 3500) {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = msg;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px) scale(0.95)';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ── Fast Actions Execution ───────────────────────────────────────────
async function fastInsertTimestamp() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  const dateStr = now.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
  const shortDate = now.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });

  showToast(`🕒 Вставляю отметку времени ${timeStr}...`, 'info');
  try {
    const code = `drawTimestampBlock({ time: '${timeStr}', date: '${dateStr}', short_date: '${shortDate}' })`;
    const res = await fetch('/api/eval', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    });
    const d = await res.json();
    if (d.ok !== false) {
      showToast(`✅ Отметка времени ${timeStr} вставлена на холст!`, 'success');
    } else {
      showToast(`❌ Ошибка: ${d.error || 'Плагин не ответил'}`, 'error');
    }
  } catch (e) {
    showToast(`❌ Ошибка сети: ${e.message}`, 'error');
  }
}

async function fastRefreshTOC() {
  showToast('📑 Обновляю меню оглавления...', 'info');
  try {
    const code = `refreshTableOfContents()`;
    const res = await fetch('/api/eval', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    });
    const d = await res.json();
    if (d.ok !== false) {
      showToast('✅ Оглавление доски успешно обновлено!', 'success');
    } else {
      showToast(`❌ Ошибка: ${d.error || 'Плагин не ответил'}`, 'error');
    }
  } catch (e) {
    showToast(`❌ Ошибка сети: ${e.message}`, 'error');
  }
}

async function fastToggleTOC() {
  try {
    const code = `
try {
  const tocs = figma.currentPage.children.filter(n => (n.getPluginData && n.getPluginData('role') === 'table_of_contents') || (n.name && n.name.includes('ОГЛАВЛЕНИЕ')));
  if (tocs.length > 0) {
    const anyVis = tocs.some(n => n.visible);
    tocs.forEach(n => n.visible = !anyVis);
    return !anyVis;
  }
} catch(e) {}
`;
    const res = await fetch('/api/eval', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    });
    const d = await res.json();
    showToast('✓ Видимость меню переключена!', 'success');
  } catch (e) {
    showToast(`❌ Ошибка: ${e.message}`, 'error');
  }
}

async function fastOpenBoard() {
  try {
    const res = await fetch('/api/status');
    const s = await res.json();
    if (s.board_info && s.board_info.url) {
      window.open(s.board_info.url, '_blank');
      showToast('🌐 Открываю доску в браузере...', 'info');
    } else {
      showToast('⚠️ URL активной доски не найден', 'warning');
    }
  } catch (e) {
    showToast('Ошибка получения URL доски', 'error');
  }
}

// ── Interactive Chat Logic ───────────────────────────────────────────
let chatHistory = [];
let lastUserMessage = '';

function handleChatKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendChatMessage();
  }
}

function sendSuggestion(text) {
  const input = document.getElementById('chatInputText');
  if (input) {
    input.value = text;
    sendChatMessage();
  }
}

function appendChatBubble(sender, text, isAi = false, actions = null) {
  const container = document.getElementById('chatMessages');
  if (!container) return;

  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${isAi ? 'chat-bubble-ai' : 'chat-bubble-user'}`;

  const avatar = document.createElement('div');
  avatar.className = 'chat-avatar';
  avatar.textContent = isAi ? '🎓' : '👤';

  const content = document.createElement('div');
  content.className = 'chat-content';

  const senderLabel = document.createElement('div');
  senderLabel.className = 'chat-sender';
  senderLabel.textContent = sender;

  const body = document.createElement('div');
  body.className = 'chat-body';
  body.textContent = text;

  content.appendChild(senderLabel);
  content.appendChild(body);

  if (actions && Array.isArray(actions) && actions.length > 0) {
    const actRow = document.createElement('div');
    actRow.style.display = 'flex';
    actRow.style.gap = '8px';
    actRow.style.marginTop = '8px';
    actions.forEach(a => {
      const btn = document.createElement('button');
      btn.className = 'btn btn-xs btn-primary';
      btn.textContent = a.label;
      btn.onclick = a.onClick;
      actRow.appendChild(btn);
    });
    content.appendChild(actRow);
  }

  bubble.appendChild(avatar);
  bubble.appendChild(content);
  container.appendChild(bubble);

  // Auto-scroll to bottom
  container.scrollTop = container.scrollHeight;
}

async function sendChatMessage() {
  const input = document.getElementById('chatInputText');
  if (!input) return;
  const message = input.value.trim();
  if (!message) return;

  lastUserMessage = message;
  input.value = '';

  // Append user bubble
  appendChatBubble('Вы', message, false);
  chatHistory.push({ role: 'user', content: message });

  const student_id = document.getElementById('chatStudentSelect')?.value || null;

  // Show typing indicator
  const typingIndicator = document.createElement('div');
  typingIndicator.id = 'chatTyping';
  typingIndicator.className = 'chat-bubble chat-bubble-ai';
  typingIndicator.innerHTML = `
    <div class="chat-avatar">🎓</div>
    <div class="chat-content">
      <div class="chat-sender">ИИ-методист</div>
      <div class="chat-body" style="color:var(--text-3);font-style:italic">Печатает ответ...</div>
    </div>
  `;
  const container = document.getElementById('chatMessages');
  container.appendChild(typingIndicator);
  container.scrollTop = container.scrollHeight;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        student_id,
        history: chatHistory.slice(-8)
      })
    });
    const data = await res.json();
    typingIndicator.remove();

    if (data.ok && data.reply) {
      chatHistory.push({ role: 'assistant', content: data.reply });

      let actions = [];
      if (data.ready_to_build && data.lesson_plan) {
        actions.push({
          label: '🚀 Нарисовать на доске',
          onClick: () => {
            const plan = data.lesson_plan;
            doCreate({
              command: `Создай урок на тему ${plan.topic}`,
              lesson_plan: plan,
              level: plan.level || selectedLevel,
              topic: plan.topic,
              student_id
            });
          }
        });
      }

      appendChatBubble('ИИ-методист', data.reply, true, actions);

      // Update suggested chips
      if (data.suggested_replies && data.suggested_replies.length > 0) {
        updateSuggestions(data.suggested_replies);
      }
    } else {
      appendChatBubble('ИИ-методист', data.reply || 'Произошла ошибка при получении ответа.', true);
    }
  } catch (e) {
    typingIndicator.remove();
    appendChatBubble('ИИ-методист', `❌ Ошибка сети: ${e.message}`, true);
  }
}

function updateSuggestions(suggestions) {
  const bar = document.getElementById('chatSuggestions');
  if (!bar) return;
  bar.innerHTML = '';
  suggestions.forEach(s => {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.textContent = s;
    btn.onclick = () => sendSuggestion(s);
    bar.appendChild(btn);
  });
}

async function loadChatHistory() {
  try {
    const res = await fetch('/api/chat/history');
    const d = await res.json();
    if (d.ok && d.history && d.history.length > 0) {
      const container = document.getElementById('chatMessages');
      if (!container) return;
      container.innerHTML = '';
      chatHistory = [];
      d.history.forEach(item => {
        const isAi = item.role === 'assistant';
        let sender = 'ИИ-методист';
        if (!isAi) {
          sender = item.source === 'telegram' ? 'Вы (Telegram)' : 'Вы';
        }
        chatHistory.push({ role: item.role, content: item.content });
        appendChatBubble(sender, item.content, isAi);
      });
    }
  } catch (e) {
    console.warn('Could not load chat history:', e);
  }
}

async function clearChatHistory() {
  chatHistory = [];
  lastUserMessage = '';
  try {
    await fetch('/api/chat/history', { method: 'DELETE' });
  } catch (e) {
    console.warn('Could not clear server chat history:', e);
  }
  const container = document.getElementById('chatMessages');
  if (container) {
    container.innerHTML = `
      <div class="chat-bubble chat-bubble-ai">
        <div class="chat-avatar">🎓</div>
        <div class="chat-content">
          <div class="chat-sender">ИИ-методист</div>
          <div class="chat-body">
            Чат очищен. Расскажите, какой урок вы хотите подготовить, для какого ученика, или задайте вопрос!
          </div>
        </div>
      </div>
    `;
  }
  showToast('История переписки очищена', 'info');
}

async function loadStudents() {
  try {
    const res = await fetch('/api/students');
    const d = await res.json();
    const chatSelect = document.getElementById('chatStudentSelect');
    const fbSelect = document.getElementById('feedbackStudentSelect');
    if (!d.students) return;

    if (chatSelect) {
      chatSelect.innerHTML = '<option value="">👤 Общий диалог</option>';
      d.students.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = `👤 ${s.name || s.id} (${s.level || 'A1-C1'}, ${s.age || '?'} лет)`;
        chatSelect.appendChild(opt);
      });
    }

    if (fbSelect) {
      fbSelect.innerHTML = '<option value="">👤 Выберите ученика</option>';
      d.students.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = `👤 ${s.name || s.id} (${s.level || 'A1-C1'})`;
        fbSelect.appendChild(opt);
      });
      if (d.students.length > 0 && !fbSelect.value) {
        fbSelect.value = d.students[0].id;
        onFeedbackStudentSelectChange();
      }
    }
  } catch (e) {}
}

function onStudentSelectChange() {
  const select = document.getElementById('chatStudentSelect');
  if (!select) return;
  const sid = select.value;
  if (sid) {
    showToast(`Выбран профиль ученика: ${sid}`, 'info');
    appendChatBubble('Система', `🎯 Переключен контекст ученика: ${sid}. Теперь ИИ помнит его уровень и историю уроков!`, true);
  }
}

// ── Feedback & Debriefing Web UI Logic ───────────────────────────────
let feedbackMediaRecorder = null;
let feedbackAudioChunks = [];
let isFeedbackRecording = false;

function formatMarkdownMini(text) {
  if (!text) return '';
  let h = escapeHtml(text);
  h = h.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
  h = h.replace(/\*(.*?)\*/g, '<i>$1</i>');
  h = h.replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,0.1);padding:2px 4px;border-radius:4px">$1</code>');
  h = h.replace(/\n/g, '<br>');
  return h;
}

async function onFeedbackStudentSelectChange() {
  const sel = document.getElementById('feedbackStudentSelect');
  if (!sel) return;
  const sid = sel.value;
  if (!sid) return;

  try {
    const res = await fetch(`/api/students/${sid}`);
    const d = await res.json();
    if (d.ok && d.student) {
      const s = d.student;
      const nameEl = document.getElementById('dossierName');
      const lvlEl = document.getElementById('dossierLevel');
      if (nameEl) nameEl.textContent = s.name || sid;
      if (lvlEl) lvlEl.textContent = s.level || 'A1';

      // Strengths
      const strUl = document.getElementById('dossierStrengths');
      if (strUl) {
        if (s.strengths && s.strengths.length > 0) {
          strUl.innerHTML = s.strengths.map(x => `<li>🌟 ${escapeHtml(x)}</li>`).join('');
        } else {
          strUl.innerHTML = '<li style="color:var(--text-3)">Пока нет записей</li>';
        }
      }

      // Weaknesses
      const wUl = document.getElementById('dossierWeaknesses');
      if (wUl) {
        if (s.weaknesses && s.weaknesses.length > 0) {
          wUl.innerHTML = s.weaknesses.map(x => `<li>🎯 ${escapeHtml(x)}</li>`).join('');
        } else {
          wUl.innerHTML = '<li style="color:var(--text-3)">Пока нет записей</li>';
        }
      }

      // History
      const hDiv = document.getElementById('dossierHistory');
      if (hDiv) {
        if (s.recent_lessons && s.recent_lessons.length > 0) {
          hDiv.innerHTML = s.recent_lessons.map(les => `
            <div class="history-item">
              <div class="history-date">${les.date || 'Недавно'} • ${escapeHtml(les.topic || 'Урок')}</div>
              <div>${escapeHtml(les.notes || 'Без заметок')}</div>
            </div>
          `).join('');
        } else {
          hDiv.innerHTML = '<div style="color:var(--text-3);font-size:12px">История уроков появится здесь</div>';
        }
      }
    }
  } catch (e) {}
}

function appendFeedbackBubble(sender, text, isAi = true) {
  const container = document.getElementById('feedbackMessages');
  if (!container) return;

  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${isAi ? 'chat-bubble-ai' : 'chat-bubble-user'}`;
  
  const icon = isAi ? '🎓' : '👤';
  const senderLabel = isAi ? 'ИИ-методист' : 'Вы';
  const formattedText = isAi ? formatMarkdownMini(text) : escapeHtml(text).replace(/\n/g, '<br>');

  bubble.innerHTML = `
    <div class="chat-avatar">${icon}</div>
    <div class="chat-content">
      <div class="chat-sender">${senderLabel}</div>
      <div class="chat-body">${formattedText}</div>
    </div>
  `;
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
}

function handleFeedbackKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendFeedbackMessage();
  }
}

async function sendFeedbackMessage(directText = null) {
  const input = document.getElementById('feedbackInputText');
  const text = directText || (input ? input.value.trim() : '');
  if (!text) return;
  if (input && !directText) input.value = '';

  appendFeedbackBubble('Вы', text, false);

  const bar = document.getElementById('feedbackSuggestions');
  if (bar) bar.innerHTML = '<div style="color:var(--text-3);font-size:11px">Загрузка ответа...</div>';

  try {
    const res = await fetch('/api/feedback/step', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: 'web_teacher',
        text: text
      })
    });
    const d = await res.json();
    if (d.ok) {
      appendFeedbackBubble('ИИ-методист', d.reply, true);
      if (d.suggested_replies && bar) {
        bar.innerHTML = '';
        d.suggested_replies.forEach(s => {
          const btn = document.createElement('button');
          btn.className = 'chip';
          btn.textContent = s;
          btn.onclick = () => sendFeedbackSuggestion(s);
          bar.appendChild(btn);
        });
      }
      if (d.is_finished) {
        onFeedbackStudentSelectChange();
        showToast('Итоги урока сохранены в профиль ученика!', 'success');
      }
    } else {
      appendFeedbackBubble('ИИ-методист', `❌ Ошибка: ${d.detail || 'Не удалось обработать ответ'}`, true);
    }
  } catch (e) {
    appendFeedbackBubble('ИИ-методист', `❌ Ошибка сети: ${e.message}`, true);
  }
}

function sendFeedbackSuggestion(text) {
  sendFeedbackMessage(text);
}

async function resetFeedbackSession() {
  try {
    await fetch('/api/feedback/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: 'web_teacher' })
    });
    const container = document.getElementById('feedbackMessages');
    if (container) {
      container.innerHTML = `
        <div class="chat-bubble chat-bubble-ai">
          <div class="chat-avatar">🎓</div>
          <div class="chat-content">
            <div class="chat-sender">ИИ-методист</div>
            <div class="chat-body">
              📝 <b>Давай подведем итоги занятия заново!</b> ☕️<br><br>
              По какому ученику и какому номеру блока/урока сейчас пройдемся?<br>
              <i>(Например: <b>«Маша, блок 1.1»</b> или <b>«Вася, 5.2»</b>)</i>
            </div>
          </div>
        </div>
      `;
    }
    const bar = document.getElementById('feedbackSuggestions');
    if (bar) {
      bar.innerHTML = `
        <button class="chip" onclick="sendFeedbackSuggestion('Маша, блок 1.1')">👤 Маша: Блок 1.1</button>
        <button class="chip" onclick="sendFeedbackSuggestion('Вася, блок 5.2')">👤 Вася: Блок 5.2</button>
        <button class="chip" onclick="sendFeedbackSuggestion('Урок целиком')">🎓 Урок целиком</button>
      `;
    }
    showToast('Дебрифинг начат с чистого листа', 'info');
  } catch (e) {}
}

async function toggleFeedbackRecording() {
  const btn = document.getElementById('feedbackRecordBtn');
  const icon = document.getElementById('feedbackRecordIcon');
  const text = document.getElementById('feedbackRecordText');

  if (isFeedbackRecording) {
    if (feedbackMediaRecorder && feedbackMediaRecorder.state !== 'inactive') {
      feedbackMediaRecorder.stop();
    }
    isFeedbackRecording = false;
    if (btn) btn.classList.remove('btn-recording');
    if (icon) icon.textContent = '🎙️';
    if (text) text.textContent = 'Голос';
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    feedbackAudioChunks = [];
    feedbackMediaRecorder = new MediaRecorder(stream);

    feedbackMediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) feedbackAudioChunks.push(e.data);
    };

    feedbackMediaRecorder.onstop = async () => {
      const audioBlob = new Blob(feedbackAudioChunks, { type: 'audio/ogg; codecs=opus' });
      stream.getTracks().forEach(track => track.stop());

      appendFeedbackBubble('Вы', '🎙️ [Голосовое сообщение обрабатывается...]', false);
      const fd = new FormData();
      fd.append('file', audioBlob, 'voice.ogg');

      try {
        const res = await fetch('/api/feedback/voice?user_id=web_teacher', {
          method: 'POST',
          body: fd
        });
        const d = await res.json();
        if (d.ok) {
          if (d.transcribed_text) {
            appendFeedbackBubble('Вы (расшифровка)', `🗣️ *«${d.transcribed_text}»*`, false);
          }
          appendFeedbackBubble('ИИ-методист', d.reply, true);
          if (d.suggested_replies) {
            const bar = document.getElementById('feedbackSuggestions');
            if (bar) {
              bar.innerHTML = '';
              d.suggested_replies.forEach(s => {
                const b = document.createElement('button');
                b.className = 'chip';
                b.textContent = s;
                b.onclick = () => sendFeedbackSuggestion(s);
                bar.appendChild(b);
              });
            }
          }
          if (d.is_finished) {
            onFeedbackStudentSelectChange();
            showToast('Итоги урока сохранены в профиль ученика!', 'success');
          }
        } else {
          appendFeedbackBubble('ИИ-методист', `❌ Ошибка: ${d.detail || 'Не удалось распознать голос'}`, true);
        }
      } catch (e) {
        appendFeedbackBubble('ИИ-методист', `❌ Ошибка сети: ${e.message}`, true);
      }
    };

    feedbackMediaRecorder.start();
    isFeedbackRecording = true;
    if (btn) btn.classList.add('btn-recording');
    if (icon) icon.textContent = '⏹️';
    if (text) text.textContent = 'Стоп';
    showToast('Идет запись голоса... Нажмите Стоп по окончании', 'info');
  } catch (err) {
    showToast(`Не удалось получить доступ к микрофону: ${err.message}`, 'error');
  }
}

// ── Telegram Bot Management Logic ────────────────────────────────────
function toggleProxyFields() {
  const toggle = document.getElementById('tgToggleProxy');
  const fields = document.getElementById('proxyFieldsContainer');
  const auth = document.getElementById('proxyAuthContainer');
  const isEnabled = toggle ? toggle.checked : false;

  if (fields) fields.style.opacity = isEnabled ? '1' : '0.45';
  if (auth) auth.style.opacity = isEnabled ? '1' : '0.45';
}

async function pollTelegramStatus() {
  try {
    const res = await fetch('/api/telegram/status');
    const s = await res.json();

    const dot = document.getElementById('tgBannerDot');
    const title = document.getElementById('tgBannerTitle');
    const sub = document.getElementById('tgBannerSub');
    const toggle = document.getElementById('tgToggleEnabled');
    const inputToken = document.getElementById('tgInputToken');
    const inputIds = document.getElementById('tgInputAllowedIds');

    // Proxy elements
    const toggleProxy = document.getElementById('tgToggleProxy');
    const selProto = document.getElementById('tgProxyProtocol');
    const inputHost = document.getElementById('tgProxyHost');
    const inputPort = document.getElementById('tgProxyPort');
    const inputUser = document.getElementById('tgProxyUser');
    const inputPass = document.getElementById('tgProxyPassword');

    if (toggle && s.enabled !== undefined) {
      toggle.checked = s.enabled;
    }

    if (inputIds && s.allowed_user_ids && s.allowed_user_ids.length > 0) {
      inputIds.value = s.allowed_user_ids.join(', ');
    }

    if (inputToken && s.has_token && !inputToken.value) {
      inputToken.placeholder = '••••••••••••••••••••••••• (токен сохранён)';
    }

    // Populate proxy settings
    if (s.proxy) {
      if (toggleProxy) toggleProxy.checked = !!s.proxy.enabled;
      if (selProto && s.proxy.protocol) selProto.value = s.proxy.protocol.toLowerCase();
      if (inputHost && s.proxy.host) inputHost.value = s.proxy.host;
      if (inputPort && s.proxy.port) inputPort.value = s.proxy.port;
      if (inputUser && s.proxy.username) inputUser.value = s.proxy.username;
      if (inputPass && s.proxy.password && !inputPass.value) {
        inputPass.placeholder = '•••••••• (пароль сохранён)';
      }
    }
    toggleProxyFields();

    if (s.running) {
      if (dot) dot.className = 'status-dot ok';
      let infoStr = '🟢 Telegram-бот работает и принимает сообщения';
      if (s.proxy && s.proxy.enabled) {
        infoStr += ` (через ${s.proxy.protocol?.toUpperCase() || 'SOCKS5'} ${s.proxy.host}:${s.proxy.port})`;
      }
      if (title) title.textContent = infoStr;
      if (sub) sub.textContent = s.allowed_user_ids?.length 
        ? `Разрешён доступ ${s.allowed_user_ids.length} пользователям` 
        : 'Доступ открыт (рекомендуется указать ID в Безопасности)';
    } else if (s.enabled && !s.has_token) {
      if (dot) dot.className = 'status-dot warning';
      if (title) title.textContent = '⚠️ Бот включён, но токен не указан';
      if (sub) sub.textContent = 'Укажите HTTP API токен от @BotFather ниже и нажмите Сохранить';
    } else if (s.status === 'error') {
      if (dot) dot.className = 'status-dot error';
      if (title) title.textContent = '❌ Ошибка запуска Telegram бота';
      if (sub) sub.textContent = s.error || 'Проверьте токен и подключение к сети (или укажите прокси)';
    } else {
      if (dot) dot.className = 'status-dot';
      if (title) title.textContent = '⚪ Telegram-бот остановлен (выключен)';
      if (sub) sub.textContent = 'Включите тумблер выше, чтобы бот начал слушать команды';
    }
  } catch (e) {}
}

function onTelegramToggleChange() {
  const toggle = document.getElementById('tgToggleEnabled');
  if (toggle && toggle.checked) {
    showToast('Бот включен. Не забудьте нажать «Сохранить и применить»', 'info');
  } else {
    showToast('Бот выключен', 'info');
  }
}

async function saveTelegramSettings() {
  const toggle = document.getElementById('tgToggleEnabled');
  const inputToken = document.getElementById('tgInputToken');
  const inputIds = document.getElementById('tgInputAllowedIds');
  const btn = document.getElementById('btnSaveTelegram');

  // Proxy elements
  const toggleProxy = document.getElementById('tgToggleProxy');
  const selProto = document.getElementById('tgProxyProtocol');
  const inputHost = document.getElementById('tgProxyHost');
  const inputPort = document.getElementById('tgProxyPort');
  const inputUser = document.getElementById('tgProxyUser');
  const inputPass = document.getElementById('tgProxyPassword');

  if (btn) btn.disabled = true;

  const enabled = toggle ? toggle.checked : false;
  const token = inputToken ? inputToken.value.trim() : '';
  const rawIds = inputIds ? inputIds.value.trim() : '';

  const allowed_user_ids = rawIds
    ? rawIds.split(',').map(x => x.trim()).filter(x => x && !isNaN(x)).map(x => parseInt(x))
    : [];

  try {
    const payload = { 
      enabled,
      allowed_user_ids,
      proxy_enabled: toggleProxy ? toggleProxy.checked : false,
      proxy_protocol: selProto ? selProto.value : 'socks5',
      proxy_host: inputHost ? (inputHost.value.trim() || '127.0.0.1') : '127.0.0.1',
      proxy_port: inputPort ? (parseInt(inputPort.value, 10) || 2080) : 2080,
      proxy_username: inputUser ? inputUser.value.trim() : ''
    };

    if (token) payload.bot_token = token;
    if (inputPass && inputPass.value) {
      payload.proxy_password = inputPass.value;
    }

    const res = await fetch('/api/telegram/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const d = await res.json();

    if (d.ok) {
      showToast('✅ Настройки Telegram бота применены!', 'success');
      pollTelegramStatus();
    } else {
      showToast(`❌ Ошибка: ${d.message || 'Не удалось сохранить'}`, 'error');
    }
  } catch (e) {
    showToast(`❌ Ошибка сохранения: ${e.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── OTA Updater (GitHub Releases) ──────────────────────────────────
let currentUpdateInfo = null;

async function checkAppUpdate(isManual = false) {
  const checkBtn = document.getElementById('checkUpdateBtn');
  if (isManual && checkBtn) {
    checkBtn.textContent = '⏳ ...';
    checkBtn.disabled = true;
  }

  try {
    const res = await fetch('/api/system/check-update');
    const data = await res.json();

    if (!data.ok) {
      if (isManual) {
        showToast(data.error || 'Не удалось проверить обновления', 'warning');
      }
      return;
    }

    currentUpdateInfo = data;
    const banner = document.getElementById('updateBanner');
    const titleEl = document.getElementById('updateBannerTitle');
    const subEl = document.getElementById('updateBannerSub');
    const verEl = document.getElementById('appVersion');

    if (verEl && data.current_version) {
      verEl.textContent = 'v' + data.current_version;
    }

    if (data.update_available) {
      if (checkBtn) {
        checkBtn.textContent = '🔔 v' + data.latest_version;
        checkBtn.classList.add('version-badge-update');
      }

      if (titleEl) {
        titleEl.textContent = `Доступно обновление v${data.latest_version}! 🎉`;
      }
      if (subEl) {
        subEl.textContent = `Текущая версия: v${data.current_version} • Нажмите, чтобы обновить`;
      }
      if (banner) {
        banner.style.display = 'flex';
      }

      if (isManual) {
        showChangelogModal();
      }
    } else {
      if (banner) banner.style.display = 'none';
      if (checkBtn) {
        checkBtn.textContent = 'Обновить';
        checkBtn.classList.remove('version-badge-update');
      }
      if (isManual) {
        showToast(`✅ У вас установлена актуальная версия v${data.current_version}!`, 'success');
      }
    }
  } catch (e) {
    console.warn('Check update error:', e);
    if (isManual) {
      showToast('Ошибка связи с сервером при проверке обновлений', 'error');
    }
  } finally {
    if (isManual && checkBtn) {
      checkBtn.disabled = false;
    }
  }
}

function manualCheckUpdate() {
  checkAppUpdate(true);
}

function dismissUpdateBanner() {
  const banner = document.getElementById('updateBanner');
  if (banner) banner.style.display = 'none';
}

function showChangelogModal() {
  const modal = document.getElementById('updateModal');
  const verInfo = document.getElementById('updateModalVersionInfo');
  const changelogText = document.getElementById('updateChangelogText');
  const progressSection = document.getElementById('updateProgressSection');
  const changelogSection = document.getElementById('updateChangelogSection');
  const confirmBtn = document.getElementById('updateConfirmBtn');
  const reloadBtn = document.getElementById('updateReloadBtn');
  const cancelBtn = document.getElementById('updateCancelBtn');

  if (!modal) return;

  if (progressSection) progressSection.style.display = 'none';
  if (changelogSection) changelogSection.style.display = 'block';
  if (confirmBtn) {
    confirmBtn.style.display = 'inline-block';
    confirmBtn.disabled = false;
  }
  if (reloadBtn) reloadBtn.style.display = 'none';
  if (cancelBtn) cancelBtn.style.display = 'inline-block';

  if (currentUpdateInfo) {
    if (verInfo) {
      verInfo.textContent = `Версия: v${currentUpdateInfo.current_version} ➔ v${currentUpdateInfo.latest_version}`;
    }
    if (changelogText) {
      changelogText.textContent = currentUpdateInfo.changelog || 'Список изменений не указан.';
    }
  } else {
    if (changelogText) changelogText.textContent = 'Загрузка информации...';
  }

  modal.style.display = 'flex';
}

function closeUpdateModal() {
  const modal = document.getElementById('updateModal');
  if (modal) modal.style.display = 'none';
}

async function startUpdateProcess() {
  const modal = document.getElementById('updateModal');
  const progressSection = document.getElementById('updateProgressSection');
  const changelogSection = document.getElementById('updateChangelogSection');
  const confirmBtn = document.getElementById('updateConfirmBtn');
  const reloadBtn = document.getElementById('updateReloadBtn');
  const cancelBtn = document.getElementById('updateCancelBtn');
  const consoleBox = document.getElementById('updateConsoleLogs');
  const statusText = document.getElementById('updateStatusText');
  const spinner = document.getElementById('updateSpinner');

  if (changelogSection) changelogSection.style.display = 'none';
  if (progressSection) progressSection.style.display = 'block';
  if (confirmBtn) confirmBtn.style.display = 'none';
  if (cancelBtn) cancelBtn.style.display = 'none';

  if (statusText) statusText.textContent = 'Подключение к репозиторию и скачивание обновлений...';
  if (consoleBox) {
    consoleBox.innerHTML = '<div style="color:#94a3b8">▸ Запуск OTA обновления...</div>';
  }

  try {
    const res = await fetch('/api/system/apply-update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();

    if (consoleBox && data.logs && data.logs.length) {
      consoleBox.innerHTML = data.logs.map(line => {
        const color = line.includes('❌') ? '#f87171' : (line.includes('✅') || line.includes('🎉') ? '#4ade80' : '#a5f3fc');
        return `<div style="color:${color}">${escapeHtml(line)}</div>`;
      }).join('');
      consoleBox.scrollTop = consoleBox.scrollHeight;
    }

    if (data.ok) {
      if (spinner) spinner.style.display = 'none';
      if (statusText) {
        statusText.style.color = '#10b981';
        statusText.textContent = `✅ Проект успешно обновлен до v${data.new_version}!`;
      }
      if (reloadBtn) reloadBtn.style.display = 'inline-block';
      showToast(`🎉 Обновление до v${data.new_version} успешно установлено!`, 'success');

      // Update local version in UI
      const verEl = document.getElementById('appVersion');
      if (verEl && data.new_version) {
        verEl.textContent = 'v' + data.new_version;
      }
      dismissUpdateBanner();
    } else {
      if (spinner) spinner.style.display = 'none';
      if (statusText) {
        statusText.style.color = '#ef4444';
        statusText.textContent = `❌ Ошибка: ${data.error || 'Не удалось обновить'}`;
      }
      if (cancelBtn) cancelBtn.style.display = 'inline-block';
      showToast(`Ошибка обновления: ${data.error}`, 'error');
    }
  } catch (e) {
    if (spinner) spinner.style.display = 'none';
    if (statusText) {
      statusText.style.color = '#ef4444';
      statusText.textContent = `❌ Ошибка сети: ${e.message}`;
    }
    if (cancelBtn) cancelBtn.style.display = 'inline-block';
    showToast(`Ошибка сети: ${e.message}`, 'error');
  }
}
