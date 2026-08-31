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

function run(rateLimits) {
  const fn = new Function("usageData", "C", `
    const weeklyScopeOrder = ${orderSrc};
    const blueAccent=C.blueAccent, greenAccent=C.greenAccent, purpleAccent=C.purpleAccent,
          pinkAccent=C.pinkAccent, cyanAccent=C.cyanAccent, claudeAmberLight=C.claudeAmberLight;
    ${body}
  `);
  return fn({ rateLimits }, ctx);
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

console.log("\n=== ordem estavel entre chamadas ===");
const a = run(live).map(r=>r.label).join("|"), b = run(live).map(r=>r.label).join("|");
check("ordem identica", a === b, `${a} vs ${b}`);

console.log(fail ? `\n${fail} FALHA(S)` : "\nTODAS PASSARAM");
process.exit(fail ? 1 : 0);
