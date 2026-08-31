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


// ── usageZone: o que decide cor, pulso de alerta e agitacao do buddy ──
const zm = src.match(/function usageZone\(pct, pace\) \{\n([\s\S]*?)\n    \}\n/);
if (!zm) { console.error("FALHA: nao achei usageZone no QML"); process.exit(2); }
const K = {};
for (const k of ["warnAt", "alertAt", "paceTolerance"]) {
  const m = src.match(new RegExp("readonly property real " + k + ": (\\d+)"));
  if (!m) { console.error("FALHA: nao achei " + k); process.exit(2); }
  K[k] = Number(m[1]);
}
const usageZone = new Function("pct", "pace",
  `const warnAt=${K.warnAt}, alertAt=${K.alertAt}, paceTolerance=${K.paceTolerance};\n` + zm[1]);

console.log("\n=== usageZone (limiares lidos do QML: warn=" + K.warnAt + " alert=" + K.alertAt + ") ===");
const zcases = [
  [0, 0.00, "calm", "janela recem-comecada"],
  [33, 0.51, "calm", "o caso do screenshot: 33% com metade da semana"],
  [76, 0.50, "warn", "acima do limiar de aviso"],
  [91, 0.50, "alert", "acima do limiar de alerta"],
  [40, 0.10, "warn", "adiantado: 40% gastos em 10% da janela"],
  [60, 0.90, "calm", "dentro do ritmo no fim da janela"],
  [60, -1,   "warn", "sem ritmo conhecido, acima de 50%"],
  [40, -1,   "calm", "sem ritmo conhecido, abaixo de 50%"],
  [75, 0.50, "warn", "limiar exato de aviso"],
  [90, 0.50, "alert", "limiar exato de alerta"],
];
for (const [pct, pace, want, why] of zcases) {
  const got = usageZone(pct, pace);
  check(`${String(pct).padStart(3)}% pace=${String(pace).padStart(5)} -> ${want.padEnd(5)} (${why})`,
        got === want, `recebeu ${got}`);
}


// ── quirkBadges: conquistas derivadas do que ja e medido ──
const qm = src.match(/readonly property var quirkBadges: \{\n([\s\S]*?)\n    \}\n/);
if (!qm) { console.error("FALHA: nao achei quirkBadges no QML"); process.exit(2); }
const fm = src.match(/function formatTokens\(n\) \{\n([\s\S]*?)\n    \}\n/);
if (!fm) { console.error("FALHA: nao achei formatTokens"); process.exit(2); }
const quirks = new Function("usageData",
  "function formatTokens(n){" + fm[1] + "}\n" + qm[1]);

console.log("\n=== quirkBadges ===");
const full = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
const badges = quirks(full);
badges.forEach(b => console.log(`  ${b.icon} ${b.text}`));
check("produz badges com o payload real", badges.length > 0, JSON.stringify(badges));
check("todo badge tem icone e texto",
      badges.every(b => b.icon && typeof b.text === "string" && b.text.length),
      JSON.stringify(badges));

check("payload vazio -> nenhum badge", quirks({}).length === 0);
check("conta pequena nao ganha badge de ferramenta",
      quirks({ toolUse: { byTool: { Bash: 100 } } }).every(b => !b.text.includes("Bash")),
      JSON.stringify(quirks({ toolUse: { byTool: { Bash: 100 } } })));
check("dominancia de ferramenta acima de 70% vira badge",
      quirks({ toolUse: { byTool: { Bash: 900, Read: 100 } } }).some(b => b.text === "90% Bash"),
      JSON.stringify(quirks({ toolUse: { byTool: { Bash: 900, Read: 100 } } })));
check("ferramenta equilibrada nao vira badge",
      quirks({ toolUse: { byTool: { Bash: 300, Read: 300, Edit: 300 } } }).length === 0);
check("streak curta nao vira badge", quirks({ streak: { days: 2 } }).length === 0);
check("streak de 3 dias vira badge",
      quirks({ streak: { days: 3 } }).some(b => b.text === "3-day streak"));
check("madrugada so conta com volume",
      quirks({ lifetime: { peakHours: { "1": 5, "14": 5 } } }).length === 0);


// ── i18n: tabela de traducao e resolucao de idioma ──
const sm = src.match(/readonly property var strings: \(([\s\S]*?)\)\n\n    \/\/ Falls back/);
if (!sm) { console.error("FALHA: nao achei a tabela strings no QML"); process.exit(2); }
const STRINGS = new Function("return " + sm[1])();

console.log("\n=== i18n ===");
check("tem os dois idiomas", "en" in STRINGS && "pt" in STRINGS,
      JSON.stringify(Object.keys(STRINGS)));

const enKeys = Object.keys(STRINGS.en).sort();
const ptKeys = Object.keys(STRINGS.pt).sort();
const faltaPt = enKeys.filter(k => !(k in STRINGS.pt));
const faltaEn = ptKeys.filter(k => !(k in STRINGS.en));
check("nenhuma chave so em ingles", faltaPt.length === 0, JSON.stringify(faltaPt));
check("nenhuma chave so em portugues", faltaEn.length === 0, JSON.stringify(faltaEn));
check("nenhum valor vazio",
      [...enKeys, ...ptKeys].every(k => STRINGS.en[k] && STRINGS.pt[k]));
check("traducoes realmente diferem do ingles",
      enKeys.filter(k => STRINGS.pt[k] !== STRINGS.en[k]).length > enKeys.length * 0.6,
      "muitas iguais: " + enKeys.filter(k => STRINGS.pt[k] === STRINGS.en[k]).join(","));

// tr(): fallback e resolucao automatica
const trm = src.match(/function tr\(key\) \{\n([\s\S]*?)\n    \}\n/);
if (!trm) { console.error("FALHA: nao achei tr()"); process.exit(2); }
const makeTr = lang => new Function("key",
  `const strings=${JSON.stringify(STRINGS)}, lang=${JSON.stringify(lang)};\n` + trm[1]);
check("tr en", makeTr("en")("conformance") === "Conformance");
check("tr pt", makeTr("pt")("conformance") === "Conformidade");
check("chave inexistente devolve a propria chave",
      makeTr("pt")("chave-que-nao-existe") === "chave-que-nao-existe");
check("idioma desconhecido cai no ingles",
      makeTr("de")("conformance") === "Conformance");

// resolucao de "auto" a partir do locale
const lm = src.match(/readonly property string lang: \{\n([\s\S]*?)\n    \}\n/);
if (!lm) { console.error("FALHA: nao achei a resolucao de lang"); process.exit(2); }
const resolve = (setting, locale) => new Function(
  `const langSetting=${JSON.stringify(setting)};` +
  `const Qt={locale:()=>({name:${JSON.stringify(locale)}})};` + lm[1])();
check("auto + pt_BR -> pt", resolve("auto", "pt_BR") === "pt", resolve("auto", "pt_BR"));
check("auto + en_US -> en", resolve("auto", "en_US") === "en", resolve("auto", "en_US"));
check("auto + de_DE -> en", resolve("auto", "de_DE") === "en", resolve("auto", "de_DE"));
check("escolha explicita vence o locale",
      resolve("en", "pt_BR") === "en" && resolve("pt", "en_US") === "pt");

console.log(fail ? `\n${fail} FALHA(S)` : "\nTODAS PASSARAM");
process.exit(fail ? 1 : 0);
