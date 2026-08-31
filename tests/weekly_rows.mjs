import fs from "node:fs";
const QML = process.argv[3];
const src = fs.readFileSync(QML, "utf8");

// Extrai o CORPO real do weeklyRows do main.qml (nao uma copia).
const m = src.match(/readonly property var weeklyRows: \{\n([\s\S]*?)\n    \}\n/);
if (!m) { console.error("FALHA: nao achei weeklyRows no QML"); process.exit(2); }
const body = m[1];

// Cores/paleta como no root
const ctx = {
  blueAccent:"#3B82F6", greenAccent:"#10B981", purpleAccent:"#A855F7",
  pinkAccent:"#EC4899", cyanAccent:"#06B6D4", claudeAmberLight:"#F59E0B",
};
// weeklyScopeOrder tambem extraido do QML
const om = src.match(/readonly property var weeklyScopeOrder: (\[[\s\S]*?\n    \])/);
if (!om) { console.error("FALHA: nao achei weeklyScopeOrder"); process.exit(2); }
const orderSrc = om[1].replace(/\b(blueAccent|greenAccent|purpleAccent|pinkAccent|cyanAccent|claudeAmberLight)\b/g, 'C.$1');

// Tabela de providers, extraida do QML: os rotulos genericos resolvem por ela.
const bm = src.match(/readonly property var providers: \(([\s\S]*?)\)\n    readonly property var brand/);
if (!bm) { console.error("FALHA: nao achei a tabela providers"); process.exit(2); }
const PROVIDERS = new Function("return " + bm[1])();

function run(rateLimits, provider = "claude") {
  const brand = PROVIDERS[provider];
  const fn = new Function("usageData", "C", "brand", `
    const weeklyScopeOrder = ${orderSrc};
    const blueAccent=C.blueAccent, greenAccent=C.greenAccent, purpleAccent=C.purpleAccent,
          pinkAccent=C.pinkAccent, cyanAccent=C.cyanAccent, claudeAmberLight=C.claudeAmberLight;
    ${body}
  `);
  return fn({ rateLimits }, ctx, brand);
}

let fail = 0;
const check = (name, cond, extra="") => {
  console.log((cond ? "  ok   " : "  FALHA") + "  " + name + (cond ? "" : "  " + extra));
  if (!cond) fail++;
};

console.log("=== payload REAL desta maquina ===");
const live = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const rows = run(live);
rows.forEach(r => console.log(`  ${r.label.padEnd(14)} ${String(Math.round(r.pct)).padStart(3)}%  resets=${JSON.stringify(r.resetsLabel)}`));
check("nenhuma linha Sonnet morta", !rows.some(r => r.label.includes("Sonnet")), JSON.stringify(rows.map(r=>r.label)));
check("All models presente", rows.some(r => r.label === "All models"));
check("Fable aparece UMA vez", rows.filter(r => r.label.toLowerCase().includes("fable")).length === 1,
      JSON.stringify(rows.map(r=>r.label)));

console.log("\n=== modelo desconhecido so em weeklyScoped ===");
const r2 = run({ weeklyAll:{percentUsed:32,resetsLabel:"Fri"},
                 weeklyScoped:{percentUsed:77,modelName:"Quasar",resetsLabel:"Sat"} });
r2.forEach(r => console.log(`  ${r.label} ${r.pct}%`));
check("Quasar renderizado", r2.some(r => r.label === "Quasar" && r.pct === 77), JSON.stringify(r2));

console.log("\n=== sem rateLimits (cold start) ===");
check("array vazio, sem crash", JSON.stringify(run(null)) === "[]" && JSON.stringify(run(undefined)) === "[]");

console.log("\n=== rotulos seguem o provider ===");
const rlClaude = run({ weeklyAll: { percentUsed: 32, resetsLabel: "" },
                       weeklySonnet: { percentUsed: 5, resetsLabel: "" } }, "claude");
const rlCodex = run({ weeklyAll: { percentUsed: 32, resetsLabel: "" },
                      weeklySonnet: { percentUsed: 5, resetsLabel: "" } }, "codex");
console.log("  claude:", rlClaude.map(r => r.label).join(" | "));
console.log("  codex :", rlCodex.map(r => r.label).join(" | "));
check("claude usa 'All models'", rlClaude[0].label === "All models", rlClaude[0].label);
check("codex usa 'Weekly'", rlCodex[0].label === "Weekly", rlCodex[0].label);
check("secundaria difere por provider", rlClaude[1].label !== rlCodex[1].label,
      `${rlClaude[1].label} vs ${rlCodex[1].label}`);
check("nenhum rotulo vem undefined", rlCodex.every(r => typeof r.label === "string" && r.label),
      JSON.stringify(rlCodex.map(r => r.label)));

console.log("\n=== ordem estavel entre chamadas ===");
const a = run(live).map(r=>r.label).join("|"), b = run(live).map(r=>r.label).join("|");
check("ordem identica", a === b, `${a} vs ${b}`);

// ── windowPace: a marca de ritmo do anel e das barras ──
const pm = src.match(/function windowPace\(resetsAtIso, windowHours\) \{\n([\s\S]*?)\n    \}\n/);
if (!pm) { console.error("FALHA: nao achei windowPace no QML"); process.exit(2); }
const windowPace = new Function("resetsAtIso", "windowHours", pm[1]);

console.log("\n=== windowPace ===");
const H = 3600000, now = Date.now();
const iso = ms => new Date(now + ms).toISOString();
const near = (a, b) => Math.abs(a - b) < 0.02;

check("janela inteira pela frente -> 0", near(windowPace(iso(5 * H), 5), 0),
      String(windowPace(iso(5 * H), 5)));
check("metade da janela -> ~0.5", near(windowPace(iso(2.5 * H), 5), 0.5),
      String(windowPace(iso(2.5 * H), 5)));
check("quase no fim -> ~0.9", near(windowPace(iso(0.5 * H), 5), 0.9),
      String(windowPace(iso(0.5 * H), 5)));
check("reset ja passou -> 1", windowPace(iso(-H), 5) === 1);
check("janela semanal de 168h", near(windowPace(iso(84 * H), 168), 0.5),
      String(windowPace(iso(84 * H), 168)));
check("sem resetsAt -> -1 (nao inventa ritmo)", windowPace("", 5) === -1);
check("resetsAt invalido -> -1", windowPace("nao-e-data", 5) === -1);
check("windowHours zero -> -1", windowPace(iso(H), 0) === -1);
check("resetsAt alem da janela -> 0 (nao extrapola)", windowPace(iso(99 * H), 5) === 0);

console.log(fail ? `\n${fail} FALHA(S)` : "\nTODAS PASSARAM");
process.exit(fail ? 1 : 0);
