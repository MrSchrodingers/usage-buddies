import { invoke } from "@tauri-apps/api/core";

const el = (id) => document.getElementById(id);

const LEVEL_COLORS = {
  genius: "#A78BFA",
  smart: "#34D399",
  slow: "#FBBF24",
  dumb: "#FB923C",
  braindead: "#F87171",
};
function colorForPct(p) {
  if (p >= 80) return "#F87171";
  if (p >= 50) return "#FBBF24";
  return "#34D399";
}

// ── Mascote animado (Clawd + sprite do estado), igual ao painel ──
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
    img.src = src;
  });
  mascotIdx = 0;
  el("pillSprite").src = mascotFrames[0];
  el("pillClawd").style.opacity = level === "braindead" ? "0" : "1";
  if (mascotTimer) clearInterval(mascotTimer);
  mascotTimer = setInterval(tickMascot, cfg.interval);
}
function tickMascot() {
  if (!mascotFrames.length) return;
  mascotIdx = (mascotIdx + 1) % mascotFrames.length;
  el("pillSprite").src = mascotFrames[mascotIdx];
}

async function refresh() {
  try {
    const d = JSON.parse(await invoke("get_widget_data"));
    const s = (d.rateLimits || {}).session || {};
    const pct = Math.max(0, Math.min(100, Number(s.percentUsed) || 0));
    el("pillPct").textContent = `${Math.round(pct)}%`;
    el("pillPct").style.color = colorForPct(pct);
    const lvl = String((d.dumbness || {}).level || "smart");
    const lvlEl = el("pillLevel");
    lvlEl.textContent = lvl;
    lvlEl.style.background = LEVEL_COLORS[lvl] || "#3f3f46";
    setMascot(lvl);
  } catch (e) {
    el("pillPct").textContent = "--";
  }
}

// Clicar na pílula abre o painel completo (comando no Rust).
el("pill").addEventListener("click", () => {
  invoke("open_panel");
});

refresh();
setInterval(refresh, 5000);
