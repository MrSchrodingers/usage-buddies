/* global Terminal, FitAddon */
'use strict';

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const state = {
  token: '', snapshot: null, previous: new Map(), firstSnapshot: true,
  socket: null, terminal: null, fit: null, selected: '', reconnectDelay: 800,
  launchMode: 'new', ctrlArmed: false, installPrompt: null
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[character]));
}

function tokenFromLocation() {
  const url = new URL(location.href);
  const fragment = new URLSearchParams(url.hash.replace(/^#/, ''));
  const supplied = fragment.get('token') || url.searchParams.get('token');
  if (supplied) {
    localStorage.setItem('ai-central-token', supplied);
    url.searchParams.delete('token');
    fragment.delete('token');
    const cleanFragment = fragment.toString();
    history.replaceState({}, '', url.pathname + url.search + (cleanFragment ? `#${cleanFragment}` : ''));
    return supplied;
  }
  return localStorage.getItem('ai-central-token') || '';
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('X-AI-Token', state.token);
  if (options.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, {...options, headers});
  let body = {};
  try { body = await response.json(); } catch (_) { /* response without JSON */ }
  if (!response.ok) throw new Error(body.detail || `Erro HTTP ${response.status}`);
  return body;
}

function toast(message, error = false) {
  const item = document.createElement('div');
  item.className = `toast${error ? ' error' : ''}`;
  item.textContent = message;
  $('#toastStack').append(item);
  setTimeout(() => item.remove(), 5200);
}

function formatNumber(value) {
  const number = Number(value || 0);
  if (number >= 1e6) return `${(number / 1e6).toFixed(1)}M`;
  if (number >= 1e3) return `${Math.round(number / 1e3)}k`;
  return `${number}`;
}

function clampPercent(value) { return Math.max(0, Math.min(100, Number(value || 0))); }

function renderUsage(target, label, data, provider) {
  const session = clampPercent(data.sessionPercent);
  const week = clampPercent(data.weeklyPercent);
  const detail = provider === 'claude'
    ? `${Number(data.errors || 0)} erros · ${formatNumber(data.burnPerHour)} tokens/h · ${Number(data.latency || 0).toFixed(1)}s`
    : `${Number(data.errors || 0)} erros API · ${formatNumber(data.currentThreadTokens)} tokens no chat`;
  target.classList.remove('skeleton');
  target.innerHTML = `
    <div class="usage-top"><div class="usage-provider"><i class="provider-orb"></i><span>${escapeHtml(label)}</span></div><span class="health-pill">${escapeHtml(data.health || 'Dados indisponíveis')}</span></div>
    <div class="meter-row"><span>Sessão</span><div class="meter"><i data-width="${session}"></i></div><strong>${Math.round(session)}%</strong></div>
    <div class="meter-row"><span>Semana</span><div class="meter"><i data-width="${week}"></i></div><strong>${Math.round(week)}%</strong></div>
    <div class="usage-meta"><span>Plano ${escapeHtml(data.plan || '—')} · ${escapeHtml(String(data.source || 'local').toUpperCase())}</span><span>${escapeHtml(detail)}</span></div>`;
  requestAnimationFrame(() => target.querySelectorAll('[data-width]').forEach(meter => { meter.style.width = `${meter.dataset.width}%`; }));
}

function sessionKey(item) { return `${item.external ? 'external' : 'hub'}:${item.name}:${item.pid || ''}`; }

function sendBrowserNotification(title, body) {
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification(title, {body, icon: '/icon.svg', tag: `ai-central-${title}`});
  }
}

function notifyTransitions(items) {
  const current = new Map(items.map(item => [sessionKey(item), item.state]));
  if (!state.firstSnapshot) {
    for (const item of items) {
      if (item.external) continue;
      const before = state.previous.get(sessionKey(item));
      if (!before) {
        sendBrowserNotification(`${item.name} conectado`, 'Sessão sincronizada no PC e celular.');
      } else if (before !== item.state) {
        if (['finished', 'waiting'].includes(item.state)) sendBrowserNotification(`${item.name} finalizado`, 'Turno concluído e sem workflow ativo.');
        if (item.state === 'asking') sendBrowserNotification(`${item.name} precisa de você`, 'Existe uma pergunta aguardando resposta.');
        if (item.state === 'idle') sendBrowserNotification(`${item.name} parado`, 'Continua conectado e pronto para um novo comando.');
      }
    }
  }
  state.previous = current;
  state.firstSnapshot = false;
}

function providerLabel(provider) { return provider === 'claude' ? 'CLAUDE' : provider === 'codex' ? 'CODEX' : 'SHELL'; }

function renderSessions(snapshot) {
  const query = $('#sessionSearch').value.trim().toLowerCase();
  const normal = snapshot.sessions || [];
  const external = (snapshot.externalSessions || []).map(item => ({...item, external: true}));
  const items = [...normal, ...external].filter(item => !query || `${item.name} ${item.directory} ${(item.repository || {}).group || ''}`.toLowerCase().includes(query));
  $('#sessionCount').textContent = `${normal.length}`;
  const groups = new Map();
  for (const item of items) {
    const group = item.external ? 'Fora do hub · preservados' : ((item.repository || {}).group || 'Outros');
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(item);
  }
  const list = $('#sessionList');
  list.textContent = '';
  for (const [group, sessions] of groups) {
    const heading = document.createElement('div');
    heading.className = 'repo-heading';
    heading.textContent = group;
    list.append(heading);
    for (const item of sessions) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `session-card${item.external ? ' external' : ''}${state.selected === item.name && !item.external ? ' active' : ''}`;
      button.disabled = Boolean(item.external);
      button.innerHTML = `
        <i class="state-dot ${escapeHtml(item.state)}"></i>
        <span class="session-copy"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.directory)}</small></span>
        <span class="session-side"><b class="provider-chip">${providerLabel(item.provider)}</b><small class="state-label">${escapeHtml(item.status)}</small></span>`;
      button.style.setProperty('--state-color', item.color || '#94a3b8');
      button.style.setProperty('--provider-color', item.provider === 'claude' ? '#df7d5d' : item.provider === 'codex' ? '#18b98b' : '#94a3b8');
      if (!item.external) button.addEventListener('click', () => selectWindow(item));
      list.append(button);
    }
  }
  if (!items.length) {
    const empty = document.createElement('div'); empty.className = 'repo-heading'; empty.textContent = 'Nenhuma sessão encontrada'; list.append(empty);
  }
  notifyTransitions([...normal, ...external]);
}

function renderAlerts(alerts) {
  const strip = $('#alertStrip');
  const messages = (alerts || []).map(item => item.message).filter(Boolean);
  strip.classList.toggle('hidden', !messages.length);
  strip.textContent = messages.length ? `ATENÇÃO  ·  ${messages.join('   ·   ')}` : '';
}

function renderSnapshot(snapshot) {
  state.snapshot = snapshot;
  renderUsage($('#claudeUsage'), 'Claude Code', (snapshot.usage || {}).claude || {}, 'claude');
  renderUsage($('#codexUsage'), 'OpenAI Codex', (snapshot.usage || {}).codex || {}, 'codex');
  renderAlerts(snapshot.alerts);
  renderSessions(snapshot);
  $('#updatedAt').textContent = `${snapshot.updated || 'agora'} · ${snapshot.clients || 0} telas`;
  $('#connectionText').textContent = snapshot.mobile ? 'PC + celular' : 'PC conectado';
  $('#connectionDot').className = 'connection-dot online';
}

async function refreshStatus() {
  try {
    renderSnapshot(await api('/api/status'));
  } catch (error) {
    $('#connectionDot').className = 'connection-dot offline';
    $('#connectionText').textContent = 'Reconectando';
    $('#updatedAt').textContent = error.message;
  }
}

function setupTerminal() {
  state.terminal = new Terminal({
    cursorBlink: true, cursorStyle: 'bar', allowProposedApi: false, convertEol: false,
    fontFamily: 'JetBrains Mono, Fira Code, ui-monospace, SFMono-Regular, Consolas, monospace',
    fontSize: innerWidth <= 520 ? 11 : 13, lineHeight: 1.16, letterSpacing: 0,
    scrollback: 8000, macOptionIsMeta: true,
    theme: {background:'#050b13', foreground:'#e7eef8', cursor:'#67e8f9', cursorAccent:'#07111f', selectionBackground:'#28506a99', black:'#07111f', red:'#fb7185', green:'#4ade80', yellow:'#fbbf24', blue:'#60a5fa', magenta:'#c084fc', cyan:'#67e8f9', white:'#e7eef8', brightBlack:'#52677f'}
  });
  state.fit = new FitAddon.FitAddon();
  state.terminal.loadAddon(state.fit);
  state.terminal.open($('#terminal'));
  state.terminal.onData(data => sendTerminal({type:'input', data}));
  new ResizeObserver(() => fitTerminal()).observe($('#terminalPanel'));
  window.visualViewport?.addEventListener('resize', () => requestAnimationFrame(fitTerminal));
  connectTerminal();
}

function socketUrl() {
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const params = new URLSearchParams();
  if (state.selected) params.set('window', state.selected);
  const query = params.toString();
  return `${scheme}//${location.host}/ws/terminal${query ? `?${query}` : ''}`;
}

function connectTerminal() {
  if (!state.token) return;
  if (state.socket) { state.socket.onclose = null; state.socket.close(); }
  state.terminal.write('\r\n\x1b[38;2;103;232;249mAI Central · conectando ao tmux…\x1b[0m\r\n');
  const socket = new WebSocket(socketUrl(), [`ai-central-auth.${state.token}`]);
  state.socket = socket;
  socket.binaryType = 'arraybuffer';
  socket.onopen = () => {
    state.reconnectDelay = 800;
    fitTerminal();
    state.terminal.focus();
  };
  socket.onmessage = event => {
    if (typeof event.data === 'string') {
      try { const message = JSON.parse(event.data); if (message.type === 'error') toast(message.message, true); } catch (_) { state.terminal.write(event.data); }
    } else state.terminal.write(new Uint8Array(event.data));
  };
  socket.onclose = () => {
    state.terminal.write('\r\n\x1b[38;2;251;191;36mConexão interrompida · tentando novamente…\x1b[0m\r\n');
    setTimeout(connectTerminal, state.reconnectDelay);
    state.reconnectDelay = Math.min(8000, state.reconnectDelay * 1.65);
  };
}

function sendTerminal(message) {
  if (state.socket?.readyState === WebSocket.OPEN) state.socket.send(JSON.stringify(message));
}

function fitTerminal() {
  if (!state.fit || !state.terminal) return;
  try {
    state.fit.fit();
    sendTerminal({type:'resize', cols:state.terminal.cols, rows:state.terminal.rows});
  } catch (_) { /* hidden terminal has no measurable geometry yet */ }
}

function selectWindow(item) {
  state.selected = item.name;
  $('#terminalName').textContent = item.name;
  $('#terminalProvider').textContent = providerLabel(item.provider);
  sendTerminal({type:'select', window:item.name});
  renderSessions(state.snapshot);
  state.terminal.focus();
  if (innerWidth <= 820) $('#terminalPanel').scrollIntoView({behavior:'smooth', block:'start'});
}

function openLaunch(mode) {
  state.launchMode = mode;
  const copy = {
    new: ['Nova sessão', 'Cria um agente sincronizado, controlável nas duas telas.'],
    resume: ['Retomar conversa', 'Retoma um ID conhecido sem criar uma cópia desconectada.'],
    worktree: ['Worktree isolado', 'Cria uma branch e pasta independentes para paralelismo seguro.']
  }[mode];
  $('#launchTitle').textContent = copy[0];
  $('#launchDescription').textContent = copy[1];
  $('#sessionIdGroup').classList.toggle('hidden', mode !== 'resume');
  $('#branchGroup').classList.toggle('hidden', mode !== 'worktree');
  $('#launchModal').classList.remove('hidden');
  updatePermissionCopy();
  setTimeout(() => $('#nameField').focus(), 80);
}

function closeLaunch() { $('#launchModal').classList.add('hidden'); }

function updatePermissionCopy() {
  $('#permissionCopy').textContent = $('#providerField').value === 'claude'
    ? '⚡ Controle pleno · Claude permission-mode bypassPermissions'
    : '⚡ Controle pleno · Codex sem aprovações e sem sandbox';
}

async function submitLaunch(event) {
  event.preventDefault();
  const button = $('#launchSubmit');
  const name = $('#nameField').value.trim();
  const payload = {
    mode: state.launchMode, provider: $('#providerField').value, name,
    directory: $('#directoryField').value.trim(), sessionId: $('#sessionIdField').value.trim(), branch: $('#branchField').value.trim()
  };
  button.disabled = true; button.textContent = 'Preparando…';
  try {
    await api('/api/launch', {method:'POST', body:JSON.stringify(payload)});
    toast(`${name} entrou na central`); closeLaunch();
    setTimeout(async () => { await refreshStatus(); const item = state.snapshot?.sessions?.find(session => session.name === name); if (item) selectWindow(item); }, 1400);
  } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; button.textContent = 'Criar e abrir'; }
}

async function enableNotifications() {
  if (!('Notification' in window)) return toast('Notificações exigem abrir a central pelo HTTPS do Tailscale.', true);
  const permission = await Notification.requestPermission();
  toast(permission === 'granted' ? 'Alertas ativados neste dispositivo' : 'Permissão de alertas não concedida', permission !== 'granted');
}

function sendSpecialKey(name, button) {
  const sequences = {menu:'\x02w', tab:'\t', escape:'\x1b', left:'\x1b[D', down:'\x1b[B', up:'\x1b[A', right:'\x1b[C', enter:'\r'};
  if (name === 'keyboard') {
    state.terminal.focus();
    state.terminal.textarea?.focus({preventScroll:true});
    navigator.virtualKeyboard?.show?.();
    return;
  }
  if (name === 'ctrl') {
    state.ctrlArmed = !state.ctrlArmed; button.classList.toggle('armed', state.ctrlArmed); return;
  }
  let sequence = sequences[name] || '';
  if (state.ctrlArmed && sequence.length === 1) {
    sequence = String.fromCharCode(sequence.toUpperCase().charCodeAt(0) & 31);
    state.ctrlArmed = false; $('.modifier')?.classList.remove('armed');
  }
  sendTerminal({type:'input', data:sequence}); state.terminal.focus();
}

function bindEvents() {
  $$('[data-open-launch]').forEach(button => button.addEventListener('click', () => openLaunch(button.dataset.openLaunch)));
  $$('[data-close-modal]').forEach(button => button.addEventListener('click', closeLaunch));
  $('#launchModal').addEventListener('click', event => { if (event.target === $('#launchModal')) closeLaunch(); });
  $('#providerField').addEventListener('change', updatePermissionCopy);
  $('#nameField').addEventListener('input', () => { if (!$('#branchField').dataset.touched) $('#branchField').value = `ai/${$('#nameField').value.trim()}`; });
  $('#branchField').addEventListener('input', () => { $('#branchField').dataset.touched = '1'; });
  $('#launchForm').addEventListener('submit', submitLaunch);
  $('#sessionSearch').addEventListener('input', () => state.snapshot && renderSessions(state.snapshot));
  $('#notifyButton').addEventListener('click', enableNotifications);
  $('#mobileKeyboard').addEventListener('pointerdown', event => {
    event.preventDefault();
    $('#terminalPanel').scrollIntoView({behavior:'smooth', block:'start'});
    sendSpecialKey('keyboard', event.currentTarget);
  });
  $$('[data-scroll-target]').forEach(button => button.addEventListener('click', () => $(button.dataset.scrollTarget)?.scrollIntoView({behavior:'smooth', block:'start'})));
  $$('[data-mobile-launch]').forEach(button => button.addEventListener('click', () => openLaunch(button.dataset.mobileLaunch)));
  $('#fitButton').addEventListener('click', fitTerminal);
  $('#keyboardButton').addEventListener('pointerdown', event => { event.preventDefault(); sendSpecialKey('keyboard', event.currentTarget); });
  $('#fullscreenButton').addEventListener('click', () => $('#terminalPanel').requestFullscreen?.());
  $('#restoreButton').addEventListener('click', async event => {
    event.currentTarget.disabled = true;
    try { const result = await api('/api/restore', {method:'POST'}); toast(`${result.events.length} decisões de restauração processadas`); await refreshStatus(); }
    catch (error) { toast(error.message, true); }
    finally { event.currentTarget.disabled = false; }
  });
  $$('.key-deck button').forEach(button => button.addEventListener('pointerdown', event => { event.preventDefault(); sendSpecialKey(button.dataset.sequence, button); }));
  $('#pairButton').addEventListener('click', () => {
    const token = $('#tokenInput').value.trim(); if (!token) return;
    localStorage.setItem('ai-central-token', token); state.token = token; $('#pairing').classList.add('hidden'); setupTerminal(); refreshStatus();
  });
  addEventListener('beforeinstallprompt', event => { event.preventDefault(); state.installPrompt = event; $('#installButton').classList.remove('hidden'); });
  $('#installButton').addEventListener('click', async () => { await state.installPrompt?.prompt(); state.installPrompt = null; $('#installButton').classList.add('hidden'); });
  document.addEventListener('fullscreenchange', () => setTimeout(fitTerminal, 120));
}

async function boot() {
  bindEvents();
  state.token = tokenFromLocation();
  if (!state.token) { $('#pairing').classList.remove('hidden'); return; }
  setupTerminal();
  await refreshStatus();
  setInterval(refreshStatus, 5000);
  if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {});
}

boot();
