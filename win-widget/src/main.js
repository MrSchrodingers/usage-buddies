import { invoke } from "@tauri-apps/api/core";

const CIRC = 2 * Math.PI * 52;
const el = (id) => document.getElementById(id);

// ── Cores ──────────────────────────────────────────────
function colorForPct(p) {
  if (p >= 80) return "#F87171";
  if (p >= 50) return "#FBBF24";
  return "#34D399";
}
const LEVEL_COLORS = {
  genius: "#A78BFA",
  smart: "#34D399",
  slow: "#FBBF24",
  dumb: "#FB923C",
  braindead: "#F87171",
};
function statusColor(s) {
  if (s === "operational") return "#34D399";
  if (s === "degraded_performance" || s === "partial_outage") return "#FBBF24";
  if (s === "major_outage") return "#F87171";
  return "#8b8b98";
}
function indicatorColor(ind) {
  if (ind === "critical" || ind === "major") return "#F87171";
  if (ind === "minor") return "#FBBF24";
  return "#34D399";
}

// ── Mascote: Clawd + sprite do estado (frames 0-5), intervalo por estado ──
const MASCOT = {
  genius: { prefix: "halo", interval: 250 },
  smart: { prefix: "smart", interval: 300 },
  slow: { prefix: "rain", interval: 100 },
  dumb: { prefix: "fire", interval: 120 },
  braindead: { prefix: "skull", interval: 200 },
};
let mascotFrames = [];
let mascotIdx = 0;
let currentLevel = null;
let mascotTimer = null;

function setMascot(level) {
  if (level === currentLevel) return;
  currentLevel = level;
  const cfg = MASCOT[level] || MASCOT.smart;
  mascotFrames = Array.from({ length: 6 }, (_, i) => `/sprites/${cfg.prefix}-${i}.png`);
  mascotFrames.forEach((src) => {
    const img = new Image();
    img.src = src; // pré-carrega para não piscar
  });
  mascotIdx = 0;
  el("mascot").src = mascotFrames[0];
  // Clawd some no braindead (a caveira o substitui, como no original)
  el("clawd").style.opacity = level === "braindead" ? "0" : "1";
  // reinicia a animação com o intervalo do estado
  if (mascotTimer) clearInterval(mascotTimer);
  mascotTimer = setInterval(tickMascot, cfg.interval);
}
function tickMascot() {
  if (!mascotFrames.length) return;
  mascotIdx = (mascotIdx + 1) % mascotFrames.length;
  el("mascot").src = mascotFrames[mascotIdx];
}

// ── Helpers ────────────────────────────────────────────
function clampPct(v) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : 0;
}
function fmtNum(n) {
  n = Number(n) || 0;
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "k";
  return String(Math.round(n));
}
function fmtMoney(v, cur) {
  const n = Number(v) || 0;
  const sym = cur === "BRL" ? "R$" : cur === "EUR" ? "€" : "$";
  return `${sym}${n.toFixed(2)}`;
}

// ── Countdown ──────────────────────────────────────────
let resetTarget = null;
function tickCountdown() {
  const c = el("countdown");
  if (!resetTarget) {
    c.textContent = "--:--:--";
    return;
  }
  const total = Math.floor(Math.max(0, resetTarget - Date.now()) / 1000);
  const h = String(Math.floor(total / 3600)).padStart(2, "0");
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  c.textContent = `${h}:${m}:${s}`;
}

// ── Barras semanais (dinâmico) ─────────────────────────
function weeklyRow(name, block) {
  if (!block) return null;
  const pct = clampPct(block.percentUsed);
  const row = document.createElement("div");
  row.className = "bar-row";

  const top = document.createElement("div");
  top.className = "bar-top";
  const nm = document.createElement("span");
  nm.className = "name";
  nm.textContent = name;
  const vl = document.createElement("span");
  vl.className = "val";
  vl.textContent = `${Math.round(pct)}%`;
  top.append(nm, vl);

  const bar = document.createElement("div");
  bar.className = "bar";
  const fill = document.createElement("div");
  fill.className = "bar-fill";
  bar.appendChild(fill);
  // largura animada no próximo frame
  requestAnimationFrame(() => {
    fill.style.width = `${pct}%`;
    fill.style.background = colorForPct(pct);
  });

  row.append(top, bar);
  return row;
}

// ── Render principal ───────────────────────────────────
function render(data) {
  const rl = data.rateLimits || {};
  const session = rl.session || {};
  const pct = clampPct(session.percentUsed);

  // Ring de sessão
  el("sessionPct").textContent = `${Math.round(pct)}%`;
  const ring = el("ringFg");
  ring.style.strokeDashoffset = `${CIRC * (1 - pct / 100)}`;
  ring.style.stroke = colorForPct(pct);

  // Countdown
  const mins = Number(session.resetsInMinutes);
  resetTarget = Number.isFinite(mins) && mins > 0 ? Date.now() + mins * 60000 : null;
  tickCountdown();

  // Nível + mascote
  const dumb = data.dumbness || {};
  const level = String(dumb.level || "smart");
  const lvl = el("level");
  lvl.textContent = level;
  lvl.style.background = LEVEL_COLORS[level] || "#3f3f46";
  el("mascotLabel").textContent = level;
  setMascot(level);

  // Score
  el("scoreNum").textContent = dumb.score ?? "—";
  el("scoreNum").style.color = LEVEL_COLORS[level] || "#fff";
  const reasons = Array.isArray(dumb.reasons) ? dumb.reasons : [];
  el("scoreReason").textContent = reasons[0] || "tudo tranquilo";
  el("scoreCard").style.borderColor = (LEVEL_COLORS[level] || "#2c2c37") + "55";

  // Barras semanais
  const wrap = el("weeklyBars");
  wrap.textContent = "";
  // Barra por-modelo auto-rotulada pela API (rl.weeklyScoped.modelName,
  // ex.: "Fable"). Some sozinha quando a API não traz o limite escopado.
  const scoped = rl.weeklyScoped;
  const rows = [
    weeklyRow("Todos os modelos", rl.weeklyAll),
    weeklyRow(scoped?.modelName || "Por modelo", scoped),
  ].filter(Boolean);
  rows.forEach((r) => wrap.appendChild(r));

  // Atividade
  const burn = data.burnRate || {};
  el("burn").textContent = fmtNum(burn.output_per_hour);
  const errs = (data.errorRate || {}).total ?? 0;
  el("errors").textContent = errs;
  const lat = (data.latency || {}).avgSeconds ?? 0;
  el("latency").textContent = lat ? `${lat}s` : "—";
  const adaptiveOn = (data.adaptiveThinking || {}).adaptive_thinking;
  el("adaptive").textContent = adaptiveOn ? "ON" : "OFF";
  el("adaptive").style.color = adaptiveOn ? "#FBBF24" : "#34D399";

  // Saúde
  const svc = data.serviceStatus || {};
  el("healthDot").style.background = indicatorColor(svc.indicator);
  el("healthDot").style.color = indicatorColor(svc.indicator);
  el("healthText").textContent = svc.description || "—";
  const comp = el("components");
  comp.textContent = "";
  (svc.components || []).forEach((c) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    const d = document.createElement("span");
    d.className = "cdot";
    d.style.background = statusColor(c.status);
    const t = document.createElement("span");
    t.textContent = c.name;
    chip.append(d, t);
    comp.appendChild(chip);
  });

  // Hoje
  const today = data.today || {};
  el("tdTokens").textContent = fmtNum(today.totalTokens);
  const cost = Number(today.costUSD) || 0;
  el("tdCost").textContent = cost > 0 ? `$${cost.toFixed(2)}` : "$0";
  el("tdMsgs").textContent = today.messages ?? 0;
  el("tdCache").textContent = `${Math.round(today.cacheHitRate ?? 0)}%`;

  // Créditos & gasto
  const credits = rl.credits || {};
  const cur = credits.currency || "USD";
  el("creditBal").textContent = fmtMoney(credits.amount, cur);
  const life = data.lifetime || {};
  el("lifetimeCost").textContent = `$${fmtNum(life.totalCostUSD)}`;
  const eu = rl.extraUsage || {};
  if (eu.enabled && Number(eu.monthlyLimit) > 0) {
    el("extraWrap").hidden = false;
    const used = Number(eu.usedCredits) || 0;
    const lim = Number(eu.monthlyLimit) || 1;
    const p = clampPct((used / lim) * 100);
    el("extraVal").textContent = `${fmtMoney(used, eu.currency || cur)} / ${fmtMoney(lim, eu.currency || cur)}`;
    requestAnimationFrame(() => {
      el("extraBar").style.width = `${p}%`;
      el("extraBar").style.background = colorForPct(p);
    });
    el("extraStatus").textContent = "";
  } else {
    el("extraWrap").hidden = true;
    el("extraStatus").textContent = eu.outOfCredits
      ? "Extra usage indisponível (limite da org = 0)"
      : eu.enabled
        ? "Extra usage habilitado"
        : "Extra usage desativado";
  }

  // Distribuição de modelos
  const stack = el("modelStack");
  const legend = el("modelLegend");
  stack.textContent = "";
  legend.textContent = "";
  const models = Array.isArray(data.modelBreakdown) ? data.modelBreakdown : [];
  if (models.length) {
    models.forEach((m) => {
      const seg = document.createElement("div");
      seg.className = "stack-seg";
      seg.style.background = m.color || "#9CA3AF";
      requestAnimationFrame(() => (seg.style.width = `${clampPct(m.percentage)}%`));
      stack.appendChild(seg);
      const item = document.createElement("div");
      item.className = "legend-item";
      const dot = document.createElement("span");
      dot.className = "legend-dot";
      dot.style.background = m.color || "#9CA3AF";
      const lbl = document.createElement("span");
      lbl.textContent = `${m.model} ${Math.round(m.percentage)}%`;
      item.append(dot, lbl);
      legend.appendChild(item);
    });
  } else {
    legend.textContent = "sem atividade hoje";
  }

  // Trend 7 dias
  const trend = el("trend");
  trend.textContent = "";
  const dayList = Array.isArray(data.trend7d) ? data.trend7d : [];
  const maxTok = Math.max(1, ...dayList.map((d) => Number(d.tokens) || 0));
  dayList.forEach((d, i) => {
    const col = document.createElement("div");
    col.className = "trend-col";
    col.title = `${d.label}: ${fmtNum(d.tokens)} tokens · ${d.messages || 0} msgs`;
    const bar = document.createElement("div");
    bar.className = "trend-bar" + (i === dayList.length - 1 ? " today" : "");
    const h = Math.round(((Number(d.tokens) || 0) / maxTok) * 100);
    requestAnimationFrame(() => (bar.style.height = `${Math.max(4, h)}%`));
    const lbl = document.createElement("span");
    lbl.className = "trend-lbl";
    lbl.textContent = d.label || "";
    col.append(bar, lbl);
    trend.appendChild(col);
  });

  // Horários de pico (0-23)
  const peak = el("peak");
  peak.textContent = "";
  const ph = life.peakHours || {};
  const counts = Array.from({ length: 24 }, (_, h) => Number(ph[h] ?? ph[String(h)] ?? 0));
  const maxPh = Math.max(1, ...counts);
  counts.forEach((c, h) => {
    const col = document.createElement("div");
    const isWork = h >= 8 && h <= 19;
    col.className = "peak-col " + (c === 0 ? "" : isWork ? "work" : "night");
    const hh = Math.round((c / maxPh) * 100);
    requestAnimationFrame(() => (col.style.height = `${Math.max(4, hh)}%`));
    col.title = `${h}h: ${c}`;
    peak.appendChild(col);
  });

  // Rodapé
  const streak = (data.streak || {}).days ?? 0;
  const sessions = (data.today || {}).sessions ?? 0;
  el("streak").textContent = `Streak ${streak}d · ${sessions} sessão(ões) hoje`;
  el("plan").textContent = rl.plan || "—";

  el("err").hidden = true;
}

async function refresh() {
  try {
    const raw = await invoke("get_widget_data");
    render(JSON.parse(raw));
  } catch (e) {
    const err = el("err");
    err.hidden = false;
    err.textContent = `Sem dados: ${e}`;
  }
}

refresh();
setInterval(refresh, 5000);
setInterval(tickCountdown, 1000);

// Botão de minimizar no header → colapsa o painel de volta pra pílula.
const collapseBtn = document.getElementById("collapseBtn");
if (collapseBtn) collapseBtn.addEventListener("click", () => invoke("collapse_panel"));
