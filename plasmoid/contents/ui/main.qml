import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.plasma.plasma5support as P5Support
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    property var usageData: ({})
    property bool hasData: Object.keys(usageData).length > 0
    property var activeIncidents: {
        var inc = usageData.serviceStatus?.active_incidents ?? [];
        return inc.length > 0 ? [inc[0]] : [];
    }
    property int dumbScore: usageData.dumbness?.score ?? 0
    property string dumbLevel: usageData.dumbness?.level ?? "genius"
    // 5-state mascot flags
    property bool isGenius: dumbLevel === "genius"
    property bool isSmart: dumbLevel === "smart"
    property bool isSlow: dumbLevel === "slow"
    property bool isDumb: dumbLevel === "dumb"
    property bool isBraindead: dumbLevel === "braindead"
    property bool isHealthy: isGenius || isSmart
    property bool isDegraded: isSlow || isDumb || isBraindead

    // Live countdown — session (5h rolling)
    property int countdownMinutes: usageData.rateLimits?.session?.resetsInMinutes ?? 0
    property int countdownSeconds: 0

    // Weekly countdown — derived from resetsAt ISO timestamp
    property int weeklyCountdownSeconds: {
        var resetsAt = usageData.rateLimits?.weeklyAll?.resetsAt ?? "";
        if (!resetsAt) return 0;
        var target = new Date(resetsAt);
        if (isNaN(target.getTime())) return 0;
        var delta = Math.max(0, Math.floor((target.getTime() - new Date().getTime()) / 1000));
        return delta;
    }
    property int weeklyCountdownLive: weeklyCountdownSeconds

    // Display mode — persisted per-instance via Plasmoid.configuration (KConfigXT)
    property string displayMode: Plasmoid.configuration.displayMode || "full"

    readonly property int refreshInterval: 30000

    // ─── Provider ───
    // Every brand-specific value in this file resolves through `brand`, so a
    // second provider is a row in this table — the layout is untouched.
    readonly property string provider: Plasmoid.configuration.provider || "claude"
    readonly property var providers: ({
        "claude": {
            "name": "Claude",
            "vendor": "Anthropic",
            "logo": "claude-logo.svg",
            "mascot": "clawd.svg",
            "collector": "usage-buddies-collector.py",
            "dataFile": "$HOME/.claude/widget-data.json",
            "siteLabel": "claude.ai",
            "siteUrl": "https://claude.ai",
            "statusUrl": "https://status.claude.com",
            "downDetectorUrl": "https://downdetector.com/status/claude-ai/",
            "weeklyAllLabel": "All models",
            "weeklySecondaryLabel": "Sonnet only",
            "accent": "#D97706",
            "accentLight": "#F59E0B",
            "accentDim": "#92400E",
            "accentBlue": "#3B82F6"
        },
        "codex": {
            "name": "Codex",
            "vendor": "OpenAI",
            "logo": "codex-logo.svg",
            "mascot": "rex.svg",
            "collector": "codex-usage-collector.py",
            "dataFile": "$HOME/.codex/widget-data.json",
            "siteLabel": "chatgpt.com",
            "siteUrl": "https://chatgpt.com/codex",
            "statusUrl": "https://status.openai.com",
            "downDetectorUrl": "https://downdetector.com/status/openai/",
            "weeklyAllLabel": "Weekly",
            "weeklySecondaryLabel": "Secondary window",
            "accent": "#0EA5E9",
            "accentLight": "#38BDF8",
            "accentDim": "#0369A1",
            "accentBlue": "#2563EB"
        }
    })
    readonly property var brand: providers[provider] ?? providers["claude"]

    // Switching provider must not leave the previous one's numbers on screen
    // under the new one's labels while the next poll is pending: drop the stale
    // payload and read again immediately.
    onProviderChanged: {
        usageData = ({});
        countdownMinutes = 0;
        countdownSeconds = 0;
        dataLoader.readData();
    }

    // Brand palette
    // Global font scale — multiplier applied to every `pixelSize` binding.
    // Default 1.20 bumps the UI one step up from Plasma's system font size
    // without needing user intervention. Safe to tweak live.
    readonly property real fontScale: 1.20

    // Accent ramp of the active provider. The `claudeAmber*` names are kept
    // because ~60 bindings below reference them; only the values follow `brand`.
    readonly property color claudeAmber: root.brand.accent
    readonly property color claudeAmberLight: root.brand.accentLight
    readonly property color claudeAmberDim: root.brand.accentDim
    readonly property color blueAccent: root.brand.accentBlue
    readonly property color greenAccent: "#10B981"
    readonly property color redAlert: "#EF4444"
    readonly property color purpleAccent: "#A855F7"    // Opus
    readonly property color pinkAccent: "#EC4899"      // Claude Design
    readonly property color cyanAccent: "#06B6D4"      // Cowork / OAuth apps
    readonly property color cardBg: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.05)
    readonly property color subtleBorder: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.08)

    switchWidth: Kirigami.Units.gridUnit * 24
    switchHeight: Kirigami.Units.gridUnit * 32

    toolTipMainText: "Usage Buddies · " + root.brand.name
    toolTipSubText: {
        if (!hasData) return tr("loading");
        var p = usageData.rateLimits?.session?.percentUsed ?? 0;
        var base = "Session: " + Math.round(p) + "% | Weekly: " +
                   Math.round(usageData.rateLimits?.weeklyAll?.percentUsed ?? 0) + "%";
        var status = usageData.serviceStatus?.description ?? "";
        var text = (status && status !== "All Systems Operational")
                 ? base + "\n⚠ " + status : base;
        // The adaptive panel is the one that changes shape without being
        // asked, so it has to be able to say why it looks the way it does.
        // Otherwise the only way to find out is to open the popup and guess.
        if (displayMode === "adaptive")
            text += "\n" + tr("panelMode") + ": " + tr(adaptiveReasonKey);
        return text;
    }

    // ─── Language ───
    //
    // A table rather than Qt's .po machinery: the widget ships a handful of
    // strings, and a translation file would need a build step and a catalogue
    // installed alongside the plasmoid for two languages.
    //
    // "auto" follows the desktop locale, so a pt-BR session gets Portuguese
    // without configuring anything; the explicit settings exist because a
    // machine's locale and the language its owner reads are not always the same.
    readonly property string langSetting: Plasmoid.configuration.language || "auto"
    readonly property string lang: {
        if (langSetting === "pt" || langSetting === "en") return langSetting;
        return Qt.locale().name.toLowerCase().indexOf("pt") === 0 ? "pt" : "en";
    }

    readonly property var strings: ({
        "en": {
            "rolling5h": "rolling 5h",
            "onPace": "on pace", "aheadOfPace": "ahead of pace", "underPace": "under pace",
            "currentSession": "Current session", "weeklyLimits": "Weekly limits",
            "allModels": "All models", "credits": "Credits", "autoReload": "Auto-reload",
            "extraUsage": "Extra Usage", "monthlyLimit": "Monthly limit", "used": "Used",
            "on": "On", "off": "Off", "active": "Active",
            "creditRunway": "Credit runway", "daysLeft": "d left", "limitIn": "limit in",
            "valueExtracted": "Value extracted", "apiEquivalent": "API-equivalent",
            "today": "Today", "perHour": "Per hour", "lifetime": "Lifetime",
            "sessions": "sessions", "refresh": "Refresh", "panelMode": "Panel mode",
            "clickToCycle": "Click to cycle", "loading": "Loading...",
            "panelAdaptive": "Adaptive - shows what matters now",
            "adaptiveIncident": "service incident",
            "adaptiveQuota": "quota in the red",
            "adaptiveEta": "limit approaching",
            "adaptiveNormal": "nothing to report",
            "harness": "Harness", "backToUsage": "Back to usage",
            "installed": "Installed", "enforced": "Enforced", "conformant": "Conformant",
            "componentsInManifest": "components in the manifest",
            "policyWins": "managed policy wins the precedence chain",
            "notEnforced": "policy present but not enforced",
            "notCheckedYet": "not checked yet",
            "conformance": "Conformance", "hooks": "Hooks",
            "acrossEvents": "across", "events": "events",
            "lastSessionStart": "Last session start",
            "hookTimings": "Hook timings", "notMeasured": "not measured by Tollens",
            "userScope": "User scope", "managedScope": "Managed scope",
            "ok": "ok", "divergent": "divergent", "missing": "missing", "orphans": "orphans",
            "components": "components", "wrongOwner": "wrong owner", "writable": "writable",
            "matchesManifest": "installed matches the manifest",
            "userDrift": "user projection diverges from the manifest",
            "managedMissing": "managed policy is not deployed",
            "managedWritable": "managed policy is writable by the actor",
            "managedDrift": "managed policy diverges from the manifest",
            "history": "history", "live": "live",
            "switchTo": "Switch to", "followingLocale": "currently following the desktop locale",
            "justNow": "just now", "minutesAgo": "m ago", "hoursAgo": "h ago", "daysAgo": "d ago",
            "stale": "stale",
            "buddy": "Buddy", "buddy_off": "silent", "buddy_alerts": "alerts only", "buddy_chatty": "chatty",
            "focusSession": "Focus session", "focusStart": "start", "focusStop": "end",
            "liveSessions": "Live sessions", "goThere": "go there",
            "st_asking": "asking you", "st_waiting": "done", "st_idle": "idle", "st_working": "working",
            "cacheSaved": "Cache saved", "hit": "hit", "readPerOutput": "Read per output",
            "produced": "produced", "planPayback": "Plan paid back", "thisMonth": "This month",
            "daysShort": "d", "efficiency": "Efficiency", "costliestSessions": "Costliest sessions",
            "serviceHealth": "Service health", "normal": "normal for you", "degraded": "worse than usual",
            "unknownHealth": "not enough history", "uncachedWouldBe": "uncached would be",
            "divergentComponents": "What diverged", "conformanceTrend": "7-day trend",
            "activity": "Activity", "agents": "Agents", "skills": "Skills",
            "tools": "Tools", "runningTotals": "running totals, no time window",
            "activation": "Activation", "activationNote": "which layer of the precedence chain instructions came from",
            "verifyGate": "Verify gate", "passRate": "pass rate", "invocations": "invocations",
            "distinctSessions": "sessions", "noneRecorded": "none recorded",
            "weeklyForecast": "Weekly forecast", "noPaceToProject": "no pace to project from",
            "resetComesFirst": "the reset comes first", "ceilingAround": "ceiling around",
            "ceilingReached": "weekly ceiling reached", "atWeekPace": "at this week's pace",
            "noWindow": "no window to project in",
            "part_night": "night", "part_morning": "morning",
            "part_afternoon": "afternoon", "part_evening": "evening",
            "wd0": "Sun", "wd1": "Mon", "wd2": "Tue", "wd3": "Wed",
            "wd4": "Thu", "wd5": "Fri", "wd6": "Sat",
            "costByProject": "Cost by project", "projects": "projects",
            "oneSessionEach": "one session each",
            "todayVsUsual": "Today vs your usual",
            "aboveYourRange": "above your range", "withinYourRange": "within your range",
            "belowYourRange": "below your range",
            "medianOf": "median of", "activeDays": "active days",
            "adjustedForHour": "scaled to the hour",
            "tooEarlyToCompare": "too early in the day to compare",
            "needMoreDays": "not enough days to compare"
        },
        "pt": {
            "rolling5h": "janela de 5h",
            "onPace": "no ritmo", "aheadOfPace": "adiantado", "underPace": "abaixo do ritmo",
            "currentSession": "Sessão atual", "weeklyLimits": "Limites semanais",
            "allModels": "Todos os modelos", "credits": "Créditos", "autoReload": "Recarga automática",
            "extraUsage": "Uso extra", "monthlyLimit": "Limite mensal", "used": "Usado",
            "on": "Ligado", "off": "Desligado", "active": "Ativo",
            "creditRunway": "Crédito restante", "daysLeft": "d restantes", "limitIn": "limite em",
            "valueExtracted": "Valor extraído", "apiEquivalent": "equivalente API",
            "today": "Hoje", "perHour": "Por hora", "lifetime": "Total",
            "sessions": "sessões", "refresh": "Atualizar", "panelMode": "Modo do painel",
            "clickToCycle": "Clique para alternar", "loading": "Carregando...",
            "panelAdaptive": "Adaptativo - mostra o que importa agora",
            "adaptiveIncident": "incidente no serviço",
            "adaptiveQuota": "cota no vermelho",
            "adaptiveEta": "limite se aproximando",
            "adaptiveNormal": "nada a relatar",
            "harness": "Harness", "backToUsage": "Voltar ao uso",
            "installed": "Instalado", "enforced": "Imposto", "conformant": "Conforme",
            "componentsInManifest": "componentes no manifesto",
            "policyWins": "a política managed vence a precedência",
            "notEnforced": "política presente mas não imposta",
            "notCheckedYet": "ainda não verificado",
            "conformance": "Conformidade", "hooks": "Hooks",
            "acrossEvents": "em", "events": "eventos",
            "lastSessionStart": "Último início de sessão",
            "hookTimings": "Tempo de hook", "notMeasured": "não medido pelo Tollens",
            "userScope": "Escopo do usuário", "managedScope": "Escopo managed",
            "ok": "ok", "divergent": "divergentes", "missing": "ausentes", "orphans": "órfãos",
            "components": "componentes", "wrongOwner": "com dono errado", "writable": "graváveis",
            "matchesManifest": "o instalado bate com o manifesto",
            "userDrift": "a projeção do usuário diverge do manifesto",
            "managedMissing": "a política managed não está implantada",
            "managedWritable": "a política managed é gravável pelo ator",
            "managedDrift": "a política managed diverge do manifesto",
            "history": "histórico", "live": "ao vivo",
            "switchTo": "Mudar para", "followingLocale": "seguindo o locale da área de trabalho",
            "justNow": "agora", "minutesAgo": "min atrás", "hoursAgo": "h atrás", "daysAgo": "d atrás",
            "stale": "desatualizado",
            "buddy": "Buddy", "buddy_off": "calado", "buddy_alerts": "só alertas", "buddy_chatty": "tagarela",
            "focusSession": "Sessão de foco", "focusStart": "iniciar", "focusStop": "encerrar",
            "liveSessions": "Sessões vivas", "goThere": "ir para lá",
            "st_asking": "perguntou", "st_waiting": "terminou", "st_idle": "ocioso", "st_working": "trabalhando",
            "cacheSaved": "Cache economizou", "hit": "de acerto", "readPerOutput": "Lido por produzido",
            "produced": "produzidos", "planPayback": "Plano se pagou", "thisMonth": "Este mês",
            "daysShort": "d", "efficiency": "Eficiência", "costliestSessions": "Sessões mais caras",
            "serviceHealth": "Saúde do serviço", "normal": "normal para você", "degraded": "pior que o normal",
            "unknownHealth": "histórico insuficiente", "uncachedWouldBe": "sem cache seria",
            "divergentComponents": "O que divergiu", "conformanceTrend": "Tendência de 7 dias",
            "activity": "Atividade", "agents": "Agentes", "skills": "Skills",
            "tools": "Ferramentas", "runningTotals": "totais acumulados, sem janela de tempo",
            "activation": "Ativação", "activationNote": "de qual camada da precedência vieram as instruções",
            "verifyGate": "Verify gate", "passRate": "taxa de aprovação", "invocations": "invocações",
            "distinctSessions": "sessões", "noneRecorded": "nada registrado",
            "weeklyForecast": "Previsão semanal", "noPaceToProject": "sem ritmo para projetar",
            "resetComesFirst": "o reset chega antes", "ceilingAround": "teto por volta de",
            "ceilingReached": "teto semanal atingido", "atWeekPace": "no ritmo desta semana",
            "noWindow": "sem janela para projetar",
            "part_night": "de madrugada", "part_morning": "de manhã",
            "part_afternoon": "à tarde", "part_evening": "à noite",
            "wd0": "Dom", "wd1": "Seg", "wd2": "Ter", "wd3": "Qua",
            "wd4": "Qui", "wd5": "Sex", "wd6": "Sáb",
            "costByProject": "Custo por projeto", "projects": "projetos",
            "oneSessionEach": "uma sessão cada",
            "todayVsUsual": "Hoje vs o seu normal",
            "aboveYourRange": "acima da sua faixa", "withinYourRange": "dentro da sua faixa",
            "belowYourRange": "abaixo da sua faixa",
            "medianOf": "mediana de", "activeDays": "dias ativos",
            "adjustedForHour": "escalado para a hora",
            "tooEarlyToCompare": "cedo demais no dia para comparar",
            "needMoreDays": "dias insuficientes para comparar"
        }
    })

    // Age of a timestamp, in words. The heartbeat's whole point is that it can
    // be old; "2026-08-31T19:23:20Z" does not say that and "2h ago" does. The
    // absolute value stays available in the tooltip.
    function relativeAge(iso) {
        if (!iso) return "";
        var t = Date.parse(iso);
        if (isNaN(t)) return iso;
        var mins = Math.max(0, Math.floor((Date.now() - t) / 60000));
        if (mins < 1) return tr("justNow");
        if (mins < 60) return mins + tr("minutesAgo");
        var hours = Math.floor(mins / 60);
        if (hours < 24) return hours + tr("hoursAgo");
        return Math.floor(hours / 24) + tr("daysAgo");
    }

    // Falls back to English, then to the key itself — a missing translation
    // should show something legible, not an empty label.
    function tr(key) {
        var table = strings[lang] ?? strings["en"];
        return table[key] ?? strings["en"][key] ?? key;
    }

    // ─── The buddy talks ───
    //
    // What ruined Clippy was speaking without having anything to say. Every
    // line here is bound to a measured trigger and reports a real number; if
    // nothing crosses a threshold, the buddy stays quiet.
    //
    // Off by default, three settings: off / alerts only / chatty. "alerts"
    // fires solely on states that need the human, which is the mode worth
    // leaving on.
    readonly property string buddyMode: Plasmoid.configuration.buddyMode || "off"
    readonly property string buddyVoice: Plasmoid.configuration.buddyVoice || "table"

    // Everything below is passed on the companion's command line, so each one
    // is clamped to the values the companion accepts. `Plasmoid.configuration`
    // is a text file on disk: a value read from it and pasted into a shell
    // command is untrusted input, and an unknown word would reach the process
    // as an argument nobody parses — or worse, as shell syntax.
    //
    // `||` cannot express a boolean default: `false || true` is true, so a
    // switch turned off would keep reporting on. Booleans compare explicitly,
    // and the comparison also covers the undefined the configuration returns
    // before it is readable.
    readonly property int buddyFocusMinutes: {
        var v = parseInt(Plasmoid.configuration.buddyFocusMinutes);
        if (isNaN(v) || v < 1) return 25;
        return Math.min(v, 240);
    }
    readonly property string buddyInsistence: {
        var v = Plasmoid.configuration.buddyInsistence || "walk";
        return ["off", "speak", "walk", "wave", "pointer"].indexOf(v) >= 0 ? v : "walk";
    }
    readonly property bool buddyQuietHours: Plasmoid.configuration.buddyQuietHours !== false
    readonly property string buddyMemes: {
        var v = Plasmoid.configuration.buddyMemes || "light";
        return ["off", "light", "full"].indexOf(v) >= 0 ? v : "light";
    }
    readonly property bool buddyShadow: Plasmoid.configuration.buddyShadow !== false
    readonly property bool buddyEscort: Plasmoid.configuration.buddyEscort === true

    property var sessionsData: ({})
    readonly property var attentionSession: sessionsData.attention ?? null

    Timer {
        interval: 20000
        running: root.buddyMode !== "off"
        repeat: true; triggeredOnStart: true
        onTriggered: sessionsLoader.readData()
    }

    // The companion is a separate process: a Plasma applet lives inside the
    // panel's window and cannot wander the screen. The widget owns its
    // lifecycle so the header button governs both — one control, not two.
    P5Support.DataSource {
        id: companionCtl
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) { disconnectSource(source); }
    }

    function syncCompanion() {
        // Through companion-ctl.sh, never `pkill -f`: that pattern matches the
        // shell running the command, which then kills itself before the start
        // can happen. The script matches the process properly, looks past the
        // interpreter in argv[0], and skips its own pid.
        var ctl = "$HOME/.local/bin/companion-ctl.sh";
        if (buddyMode === "off") {
            companionCtl.connectSource(ctl + " stop");
            return;
        }
        // Restart rather than reconfigure: the flags are read at startup, so a
        // companion already running with the old ones would ignore them.
        //
        // And a restart ends any focus block, because the new process rejects
        // the command file it finds on disk — issuedAt is older than the start
        // it just recorded, which is the guard that stops yesterday's request
        // re-entering a block nobody asked for twice. The widget's record has
        // to go with it, or the header keeps offering to end a block that is
        // gone and the button does nothing when pressed. onBuddyModeChanged
        // already does this for the off switch; every setting that reaches the
        // command line needs it too, so it lives here rather than in each of
        // the six handlers.
        focusRequested = false;
        focusExpiry.stop();
        companionCtl.connectSource(ctl + " start" +
            (brand.name === "Codex" ? " --codex" : "") +
            (lang === "pt" ? " --pt" : "") +
            (buddyMode === "alerts" ? " --alerts-only" : "") +
            (buddyVoice === "claude" ? " --live" : "") +
            " --focus-minutes " + buddyFocusMinutes +
            " --insistence " + buddyInsistence +
            (buddyQuietHours ? "" : " --no-quiet-hours") +
            " --memes " + buddyMemes +
            (buddyShadow ? "" : " --no-shadow") +
            (buddyEscort ? " --escort" : ""));
    }

    // Only stop on a real change away from a mode that was on. Unguarded, this
    // fired during creation as buddyMode resolved to its default, and sent
    // `stop` — which killed the companion the *other* applet instance had just
    // started. Two instances in one panel share one companion process, and the
    // one with the buddy switched off was silently switching it off for both.
    property string previousBuddyMode: ""
    onBuddyModeChanged: {
        var was = previousBuddyMode;
        previousBuddyMode = buddyMode;
        if (buddyMode === "off") {
            // The process is going away, so the widget's record of what it was
            // asked to do goes with it; otherwise switching the companion back
            // on offers to end a focus session that no longer exists.
            focusRequested = false;
            focusExpiry.stop();
            if (was !== "" && was !== "off") syncCompanion();   // a real switch-off
            return;
        }
        syncCompanion();
    }
    onLangChanged: if (buddyMode !== "off") syncCompanion()
    onBuddyVoiceChanged: if (buddyMode !== "off") syncCompanion()
    // One handler per setting that appears on the command line above. Without
    // them the option changes, the running companion keeps the flags it was
    // started with, and nothing happens until the widget is reloaded — a bug
    // nobody reports, because it reads as the setting doing nothing.
    onBuddyFocusMinutesChanged: if (buddyMode !== "off") syncCompanion()
    onBuddyInsistenceChanged: if (buddyMode !== "off") syncCompanion()
    onBuddyQuietHoursChanged: if (buddyMode !== "off") syncCompanion()
    onBuddyMemesChanged: if (buddyMode !== "off") syncCompanion()
    onBuddyShadowChanged: if (buddyMode !== "off") syncCompanion()
    onBuddyEscortChanged: if (buddyMode !== "off") syncCompanion()

    // The companion's flags are read once, at startup, so it has to be started
    // with the settings already resolved. Plasmoid.configuration is not
    // readable during component creation: starting there picked langSetting
    // "auto", fell back to the system locale — en_US on the machine this was
    // found on — and launched an English companion for a widget set to
    // Portuguese. Wait for the configuration to answer, then start.
    Timer {
        id: companionBoot
        interval: 300; repeat: true; running: true
        onTriggered: {
            if (Plasmoid.configuration.buddyMode === undefined) return;
            running = false;
            root.previousBuddyMode = root.buddyMode;
            // Same reason this timer exists: the thresholds are read off
            // Plasmoid.configuration, which is not readable during creation.
            // Pushed on every start and not only on change, so an install
            // whose push failed once — no collector on PATH yet, a full disk —
            // repairs itself the next time the panel comes up instead of
            // leaving a dialog that shows a pair nothing acts on.
            root.pushThresholds();
            if (root.buddyMode !== "off") root.syncCompanion();
        }
    }
    // One handler, because QML rejects a second assignment to the same property
    // with "Property value set multiple times" — and it rejects it by refusing
    // to load the applet at all, which is a blank panel rather than a warning.
    //
    // The readData call is here as well as on the timer: the timer's
    // triggeredOnStart fires during creation, when brand is not yet readable,
    // and readData's guard turns that into a skipped read. Skipped, the widget
    // would stay empty for a whole refresh interval. onCompleted runs after
    // every property is set, so this is the read certain to find a provider.
    // The companion is started by companionBoot above, once the configuration
    // is readable; starting it here would use unresolved settings.
    Component.onCompleted: dataLoader.readData()

    // ─── Telling the companion something while it is running ───
    //
    // Its flags are read once, at startup, so a restart is the only way to
    // change them — and restarting to begin a focus session throws away
    // everything the process has accumulated. Commands travel instead through
    // a file the companion watches:
    //
    //     ~/.cache/usage-buddies/companion-command.json
    //     {"command": "focus.start", "minutes": 25, "issuedAt": "<ISO 8601 UTC>"}
    //     {"command": "focus.stop", "issuedAt": "<ISO 8601 UTC>"}
    //
    // `issuedAt` is what keeps the file from being an order that stands
    // forever. The companion also reads it while starting up, and with no
    // timestamp a mascot restarted the next morning would re-enter the focus
    // session asked for yesterday. It also keeps two identical commands apart:
    // the executable engine keys sources by their command string and ignores a
    // connect for one already connected, so a second "focus.stop" would never
    // be written.
    P5Support.DataSource {
        id: companionCommand
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) { disconnectSource(source); }
    }

    // Written to a temporary file in the same directory, then renamed over the
    // target. Writing in place is not atomic: the watcher on the other side
    // wakes on the first write and reads truncated JSON, which it can only
    // throw away — the command is lost with no trace on either side. A rename
    // within one filesystem is atomic, so the reader sees either the previous
    // file or the whole new one.
    function sendCompanionCommand(payload) {
        payload.issuedAt = new Date().toISOString();
        var dir = "\"${XDG_CACHE_HOME:-$HOME/.cache}\"/usage-buddies";
        // The temporary is created in the target's own directory so the move
        // is a rename within one filesystem, which is what makes it atomic —
        // a reader woken by a watcher mid-write would otherwise read half a
        // document. It is also removed when any step after its creation
        // fails: an && chain that stops at a full disk leaves the temporary
        // behind, and since the companion watches the directory as well as
        // the file, every leftover is both dead weight and a spurious wake.
        companionCommand.connectSource(
            "mkdir -p " + dir + " && " +
            "t=$(mktemp " + dir + "/.companion-command.XXXXXX) && " +
            "{ printf %s " + shellQuote(JSON.stringify(payload)) + " > \"$t\" && " +
            "mv \"$t\" " + dir + "/companion-command.json; } || rm -f \"$t\"");
    }

    // Single quotes suspend everything the shell would otherwise interpret.
    // The one character that cannot appear between them is the quote itself,
    // which is closed, escaped and reopened.
    function shellQuote(s) {
        return "'" + String(s).replace(/'/g, "'\\''") + "'";
    }

    // The companion never answers, so this is the widget's record of what it
    // last asked for, not an observation of the other process. The timer drops
    // it when the session it requested would have ended.
    property bool focusRequested: false

    Timer {
        id: focusExpiry
        interval: root.buddyFocusMinutes * 60000
        onTriggered: root.focusRequested = false
    }

    function toggleFocusSession() {
        if (focusRequested) {
            sendCompanionCommand({"command": "focus.stop"});
            focusRequested = false;
            focusExpiry.stop();
            return;
        }
        sendCompanionCommand({"command": "focus.start", "minutes": buddyFocusMinutes});
        focusRequested = true;
        focusExpiry.restart();
    }

    P5Support.DataSource {
        id: focusHelper
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) { disconnectSource(source); }
    }

    P5Support.DataSource {
        id: sessionsLoader
        engine: "executable"
        connectedSources: []
        function readData() {
            // --announce lets the probe raise a desktop notification for a
            // session that needs attention; the widget being open is not the
            // same as the user looking at it.
            connectSource("$HOME/.local/bin/sessions-probe.py --announce" +
                          (root.lang === "pt" ? " --pt" : "") +
                          " 2>/dev/null; cat \"${XDG_CACHE_HOME:-$HOME/.cache}\"/usage-buddies/sessions.json 2>/dev/null");
        }
        onNewData: function(source, data) {
            var out = (data && data.stdout) ? String(data.stdout).trim() : "";
            if (out) {
                try {
                    root.sessionsData = JSON.parse(out);
                } catch(e) {
                    console.warn("usage-buddies: bad sessions.json:", e);
                }
            }
            disconnectSource(source);
        }
    }

    // Lines, worst-first. `when` is evaluated in order and the first match
    // wins, so an idle session outranks a joke about bash.
    readonly property var buddyLines: ({
        "en": {
            "asking":      ["{name} asked you something and is just sitting there.",
                            "{name} needs a decision. It will wait forever, which is the problem."],
            "waiting":     ["{name} finished. Go look before you forget it existed.",
                            "{name} is done and idling. Your move.",
                            "{name} wrapped up {idle} ago. Still waiting."],
            "idle":        ["{name} has done nothing for {idle}. Existential, really.",
                            "{name} is idle. Contemplating the void, presumably."],
            "twoRed":      ["Two quotas in the red. This is fine.",
                            "Both limits are burning. Bold strategy."],
            "compaction":  ["{n} compactions today. You keep forgetting things and calling it progress.",
                            "Memory wiped {n} times. Ship of Theseus, but worse."],
            "readRatio":   ["{n}:1 read per output. Reading a library to write a postcard.",
                            "{n} tokens in, one out. Efficient is not the word."],
            "bashHeavy":   ["{n}% of your calls are Bash. There are other tools. Allegedly.",
                            "{n}% Bash. The other tools are right there, unused."],
            "cacheDrop":   ["Cache hit down to {n}%. Something is invalidating the prefix.",
                            "{n}% cache hit. Your prefix is leaking somewhere."],
            "nightOwl":    ["It is late. The commit will still be broken tomorrow.",
                            "Past midnight. Nothing good gets merged at this hour."],
            "reset":       ["Window reset. A clean slate, briefly.",
                            "Fresh limits. Try to make them last past lunch."],
            "allQuiet":    ["Everything is fine. Suspiciously so.",
                            "Nothing needs you. Enjoy it while it lasts."]
        },
        "pt": {
            "asking":      ["{name} te perguntou algo e está lá, parado.",
                            "{name} precisa de uma decisão. Ele espera pra sempre — esse é o problema."],
            "waiting":     ["{name} terminou. Vai lá conferir antes de esquecer que existe.",
                            "{name} acabou e está de bobeira. É sua vez.",
                            "{name} fechou há {idle}. Continua esperando."],
            "idle":        ["{name} não faz nada há {idle}. Existencial, no fundo.",
                            "{name} está ocioso. Contemplando o vazio, presumo."],
            "twoRed":      ["Duas cotas no vermelho. This is fine.",
                            "Os dois limites queimando. Estratégia ousada."],
            "compaction":  ["{n} compactações hoje. Você esquece tudo e chama de progresso.",
                            "Memória apagada {n} vezes. Barco de Teseu, só que pior."],
            "readRatio":   ["{n}:1 de leitura por saída. Lendo uma biblioteca pra escrever um bilhete.",
                            "{n} tokens entram, um sai. Eficiente não é a palavra."],
            "bashHeavy":   ["{n}% das suas chamadas são Bash. Existem outras ferramentas. Dizem.",
                            "{n}% Bash. As outras ferramentas estão bem ali, intactas."],
            "cacheDrop":   ["Cache caiu pra {n}%. Alguma coisa está invalidando o prefixo.",
                            "{n}% de acerto no cache. Seu prefixo está vazando."],
            "nightOwl":    ["Tá tarde. O commit vai continuar quebrado amanhã.",
                            "Passou da meia-noite. Nada bom entra em produção nessa hora."],
            "reset":       ["Janela renovada. Página em branco, por pouco tempo.",
                            "Limites novos. Tenta fazer durar até o almoço."],
            "allQuiet":    ["Tudo certo. Suspeitamente certo.",
                            "Ninguém precisa de você. Aproveita."]
        }
    })

    function _fmtIdle(seconds) {
        if (seconds < 60) return seconds + "s";
        if (seconds < 3600) return Math.floor(seconds / 60) + "min";
        return Math.floor(seconds / 3600) + "h";
    }

    // The current thing worth saying, or null. Ordered by how much it matters,
    // not by how funny it is.
    readonly property var buddySays: {
        if (buddyMode === "off") return null;

        var alertsOnly = buddyMode === "alerts";
        var a = attentionSession;
        var pick = function (key, vars) {
            var table = (buddyLines[lang] ?? buddyLines["en"])[key] ?? [];
            if (!table.length) return null;
            // Stable within a minute so the text does not flicker on refresh.
            var idx = Math.floor(Date.now() / 60000) % table.length;
            var text = table[idx];
            for (var k in vars) text = text.replace("{" + k + "}", vars[k]);
            return { key: key, text: text };
        };

        if (a && a.state === "asking")
            return pick("asking", { name: a.name });
        if (a && a.state === "waiting")
            return pick("waiting", { name: a.name, idle: _fmtIdle(a.idleSeconds) });

        var idle = (sessionsData.sessions ?? []).filter(function (s) { return s.state === "idle"; });
        if (idle.length)
            return pick("idle", { name: idle[0].name, idle: _fmtIdle(idle[0].idleSeconds) });

        if (quotasInAlert >= 2) return pick("twoRed", {});
        if (alertsOnly) return null;

        var eff = usageData.efficiency ?? {};
        var hit = eff.cacheHitRate ?? 1;
        if (hit > 0 && hit < 0.3) return pick("cacheDrop", { n: Math.round(hit * 100) });

        var comp = usageData.compaction?.count ?? 0;
        if (comp >= 5) return pick("compaction", { n: comp });

        var ratio = eff.readPerOutput ?? 0;
        if (ratio >= 300) return pick("readRatio", { n: Math.round(ratio) });

        var tools = usageData.toolUse?.byTool ?? ({});
        var total = 0, top = 0, topName = "";
        for (var k in tools) { total += tools[k]; if (tools[k] > top) { top = tools[k]; topName = k; } }
        if (total > 200 && top / total > 0.7 && topName === "Bash")
            return pick("bashHeavy", { n: Math.round(100 * top / total) });

        var hour = new Date().getHours();
        if (hour >= 0 && hour < 5) return pick("nightOwl", {});

        return pick("allQuiet", {});
    }

    // ─── Tollens (optional second page) ───
    //
    // Tollens governs the global Claude Code configuration. Its own thesis is
    // INSTALLED != ENFORCED != ACTIVATED, so the page shows those separately
    // instead of collapsing them into one light.
    //
    // The probe writes to ~/.cache, not ~/.claude: that tree is what Tollens
    // audits, and a widget file inside it is a candidate orphan the moment
    // their scan widens.
    property var tollens: ({})
    readonly property bool hasTollens: (tollens.present ?? false) === true
    property int page: 0

    Timer {
        interval: root.refreshInterval
        running: true; repeat: true; triggeredOnStart: true
        onTriggered: tollensLoader.readData()
    }

    P5Support.DataSource {
        id: tollensLoader
        engine: "executable"
        connectedSources: []
        function readData() {
            connectSource("$HOME/.local/bin/tollens-probe.py 2>/dev/null; " +
                          "cat \"${XDG_CACHE_HOME:-$HOME/.cache}\"/usage-buddies/tollens.json 2>/dev/null");
        }
        onNewData: function(source, data) {
            var out = (data && data.stdout) ? String(data.stdout).trim() : "";
            if (out) {
                try {
                    root.tollens = JSON.parse(out);
                } catch(e) {
                    console.warn("usage-buddies: bad tollens.json:", e);
                }
            }
            disconnectSource(source);
        }
    }

    // ─── Data ───
    Timer {
        interval: root.refreshInterval
        running: true; repeat: true; triggeredOnStart: true
        onTriggered: dataLoader.readData()
    }


    // Polled by the Timer above rather than by DataSource.interval, because the
    // command itself depends on the selected provider. Each read connects a
    // fresh source and disconnects it on delivery, so nothing accumulates.
    //
    // The systemd timer refreshes widget-data.json independently, so the widget
    // only needs to `cat` it (fast, atomic via os.replace); running the
    // collector here is the fallback for when that timer is disabled.

    P5Support.DataSource {
        id: dataLoader
        engine: "executable"
        // The command depends on the provider, which changes at runtime, so the
        // source is connected per read instead of being a static binding.
        connectedSources: []
        function readData() {
            // brand resolves through Plasmoid.configuration, which is not
            // readable when the timer's triggeredOnStart fires during component
            // creation. Dereferencing it there threw
            // "Cannot read property 'collector' of undefined" and the first read
            // was lost — so the widget showed nothing until the next tick.
            var b = root.brand || root.providers["claude"];
            if (!b || !b.collector) return;
            connectSource("$HOME/.local/bin/" + b.collector +
                          " 1>/dev/null 2>/dev/null; cat " + b.dataFile);
        }
        onNewData: function(source, data) {
            // Gated on the output parsing, not on the exit code. The engine's
            // key for that is a string with a space in it, and if it ever
            // stops being spelled exactly "exit code" the comparison is
            // undefined === 0, which is false — so every read is discarded in
            // silence while the source keeps cycling, and the widget shows the
            // number it had when the panel started, for as long as the panel
            // is up. Whether that is what happened here or not, the exit code
            // adds nothing: output that parses into the shape we want is the
            // thing we actually need.
            var out = (data && data.stdout) ? String(data.stdout).trim() : "";
            if (out) {
                try {
                    var parsed = JSON.parse(out);
                    root.usageData = parsed;
                    root.countdownMinutes = parsed.rateLimits?.session?.resetsInMinutes ?? 0;
                    root.countdownSeconds = 0;
                } catch(e) {
                    console.warn("usage-buddies: failed to parse widget-data.json:", e);
                }
            }
            // Load-bearing, and it was missing. connectSource on a string that
            // is already connected does nothing, and the command here is the
            // same on every read — so without this the widget read the file
            // once at startup and then displayed that number forever. It looked
            // like a slow refresh rather than a dead one, because the countdown
            // beside it ticks on its own timer and kept moving.
            //
            // The neighbouring sources disconnect and did keep refreshing;
            // measured by watching plasmashell's children, the tollens and
            // session probes ran every 20-30s while this one never ran twice.
            disconnectSource(source);
        }
    }

    // Live countdown (ticks every second)
    Timer {
        interval: 1000
        running: root.countdownMinutes > 0 || root.countdownSeconds > 0
        repeat: true
        onTriggered: {
            if (root.countdownSeconds > 0) root.countdownSeconds--;
            else if (root.countdownMinutes > 0) { root.countdownMinutes--; root.countdownSeconds = 59; }
        }
    }

    // Weekly countdown — ticks every second, re-syncs on data refresh
    Timer {
        interval: 1000
        running: root.weeklyCountdownLive > 0
        repeat: true
        onTriggered: { if (root.weeklyCountdownLive > 0) root.weeklyCountdownLive--; }
    }
    // Re-sync weeklyCountdownLive when fresh data arrives
    onWeeklyCountdownSecondsChanged: { root.weeklyCountdownLive = root.weeklyCountdownSeconds; }

    // Helper: format a total-seconds value as "Xd Yh Zm" / "Xh Ym Zs" / "Ym Zs" / "Zs"
    function formatCountdown(totalSeconds) {
        if (totalSeconds <= 0) return "--";
        var d = Math.floor(totalSeconds / 86400);
        var h = Math.floor((totalSeconds % 86400) / 3600);
        var m = Math.floor((totalSeconds % 3600) / 60);
        var s = totalSeconds % 60;
        if (d > 0) return d + "d " + h + "h " + m + "m";
        if (h > 0) return h + "h " + m + "m " + s + "s";
        if (m > 0) return m + "m " + s + "s";
        return s + "s";
    }

    // Clipboard helper
    P5Support.DataSource {
        id: clipHelper
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) { disconnectSource(source); }
    }

    // ─── Helpers ───
    function formatTokens(n) {
        if (!n) return "0";
        if (n >= 1e9) return (n/1e9).toFixed(1) + "B";
        if (n >= 1e6) return (n/1e6).toFixed(1) + "M";
        if (n >= 1e3) return (n/1e3).toFixed(0) + "K";
        return n.toString();
    }

    // ── Pace ──────────────────────────────────────────────
    //
    // A rolling window has two coordinates: how much of the quota is spent, and
    // how far through the window you are. 60% spent in the first hour of a 5h
    // window is trouble; the same 60% in the fifth hour is fine. Showing usage
    // alone cannot tell those apart, so every gauge here also carries where
    // even burn would have put you by now.
    //
    // Returns 0..1, or -1 when the window boundary is unknown (offline
    // estimates carry no reset timestamp) so callers can fall back to
    // threshold-only colouring instead of inventing a pace.
    function windowPace(resetsAtIso, windowHours) {
        if (!resetsAtIso || windowHours <= 0) return -1;
        var reset = Date.parse(resetsAtIso);
        if (isNaN(reset)) return -1;
        var span = windowHours * 3600000;
        var remaining = reset - Date.now();
        if (remaining < 0) return 1;
        if (remaining > span) return 0;
        return 1 - (remaining / span);
    }

    // Ahead of pace by this many points before the gauge warms up. Below it the
    // difference is noise: a burst at the start of a window is normal.
    readonly property real paceTolerance: 15

    // ── Zone boundaries ───────────────────────────────────
    //
    // These were two literals here and two constants in the collector, kept in
    // step by a test that compared them. That test could only ever check the
    // defaults: the moment the pair became configurable, one number changed
    // and the other did not, and the failure is silent in the worst possible
    // way — the bar goes red and no notification arrives, or a notification
    // arrives about a bar that is still amber.
    //
    // So the pair is not decided here any more. The collector resolves it once
    // (usage_thresholds()), fires its notifications on it, and publishes it in
    // widget-data.json; this is where the widget reads it back. Whatever
    // painted the bar is therefore, by construction, the number that run would
    // have announced.
    //
    // Two fallbacks behind that, in order:
    //   * the pair from the config dialog, for a provider whose collector
    //     publishes none — the Codex one raises no usage notifications at all,
    //     so there is nothing for it to disagree with;
    //   * 75 / 90, which is what every installation had before this was
    //     configurable.
    readonly property var thresholds: resolveThresholds(
        usageData.thresholds, configuredThresholds)
    readonly property real warnAt: thresholds.warn
    readonly property real alertAt: thresholds.alert

    // Pure, so tests can lift it out of this file and run it against the
    // collector's own payload rather than against a copy of it.
    //
    // Both halves of a pair are rejected together. Falling back on one alone
    // is how you get warn above alert, which paints the amber zone on top of
    // the red one and warns about a quota already past the alert.
    function resolveThresholds(published, configured) {
        // Published first, always: it is the pair the collector actually
        // fired on, and anything preferred over it paints a boundary no
        // notification was raised at.
        var pair = thresholdPair(published);
        if (pair) return pair;
        // Then the dialog's pair, for a provider whose collector publishes
        // none — the Codex one raises no usage notifications at all, so there
        // is nothing there for it to contradict.
        pair = thresholdPair(configured);
        if (pair) return pair;
        // And last, what every installation had before this was configurable.
        return { "warn": 75, "alert": 90 };
    }

    function thresholdPair(raw) {
        if (!raw) return null;
        var w = cleanThreshold(raw.warn);
        var a = cleanThreshold(raw.alert);
        if (w === null || a === null || !(w < a)) return null;
        return { "warn": w, "alert": a };
    }

    // One number out of a file on disk. Everything refused here is something
    // that file can hold: a string, a null, a NaN, a number outside the range.
    // A threshold of "90" compares false against every percentage in
    // JavaScript too, which disables the zone in silence.
    function cleanThreshold(value) {
        if (typeof value !== "number" || !isFinite(value)) return null;
        if (value < 5 || value > 99) return null;
        return value;
    }

    // The dialog's pair, mirrored into a root property for one reason: there
    // is nowhere else to hang a change handler. Kept as `var` rather than two
    // ints because Plasmoid.configuration answers undefined until the applet's
    // configuration is readable, and coercing that into an int would silently
    // make it a zero.
    readonly property var configuredThresholds: ({
        "warn": Plasmoid.configuration.usageWarnAt,
        "alert": Plasmoid.configuration.usageAlertAt
    })
    onConfiguredThresholdsChanged: root.pushThresholds()

    // The last pair handed to the collector, so the refresh below can tell a
    // push that changed something from one that confirmed what was already
    // there.
    property real pushedWarnAt: -1
    property real pushedAlertAt: -1

    // The bridge between the dialog and the collector.
    //
    // The dialog writes KConfig; the collector reads
    // ~/.claude/widget-config.json and knows nothing about KConfig. This runs
    // the collector's own --set-thresholds rather than writing that file from
    // QML, because the merge, the lock and the atomic rename all live on that
    // side — and a second writer implemented here would be a second chance to
    // drop org_id, without which every remote read in the collector fails.
    //
    // Always the Claude collector, whatever provider this instance follows:
    // that file is the one it owns, and it is the only script that knows how
    // to write it without losing the keys it does not recognise.
    function pushThresholds() {
        // Numeric by construction. The string below is a shell command line
        // and these values arrive from a text file KConfig wrote, so they are
        // rounded and range-checked here instead of being interpolated as
        // they came. An unusable pair is not pushed at all: the collector then
        // keeps the last pair it was given, which is still a pair the widget
        // and the notifications agree on.
        var w = cleanThreshold(Math.round(Number(Plasmoid.configuration.usageWarnAt)));
        var a = cleanThreshold(Math.round(Number(Plasmoid.configuration.usageAlertAt)));
        if (w === null || a === null || !(w < a)) return;
        pushedWarnAt = w;
        pushedAlertAt = a;
        thresholdWriter.connectSource(
            "$HOME/.local/bin/usage-buddies-collector.py --set-thresholds="
            + w + "," + a);
    }

    P5Support.DataSource {
        id: thresholdWriter
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) {
            // Load-bearing. The executable engine keys a source by its command
            // string and ignores a connect for one already connected, so
            // without this the second push of the same pair never runs — and
            // the second push is precisely the one that repairs a first that
            // failed.
            disconnectSource(source);
            // The pair the widget paints with comes back inside
            // widget-data.json, so the colours only move once the collector
            // has run again. Asking for that read here is the difference
            // between the setting taking effect now and at the next tick.
            //
            // Only when it would change something, though. This handler also
            // runs at every panel start, and the collector reaches the
            // network — an unconditional read here would mean two round trips
            // a second apart every time the panel comes up.
            if (root.warnAt !== root.pushedWarnAt
                    || root.alertAt !== root.pushedAlertAt) {
                dataLoader.readData();
            }
        }
    }

    // The calm colour is a desaturated neutral, NOT Kirigami.Theme.highlightColor.
    //
    // Borrowing the theme accent looked like the right way to respect the user's
    // Plasma setup, until a theme whose accent *is* red made "you have plenty
    // left" and "you are about to hit the wall" render identically — measured at
    // rgb(243,83,83) on both, which is this theme's Colors:Selection. A state
    // channel cannot take its quiet end from an arbitrary palette. Quiet is now
    // quiet by construction, and follows the text colour so it still tracks
    // light and dark.
    readonly property color calmFill: Qt.rgba(Kirigami.Theme.textColor.r,
                                              Kirigami.Theme.textColor.g,
                                              Kirigami.Theme.textColor.b, 0.45)

    // Zone of a quota: "calm" | "warn" | "alert".
    // Absolute thresholds catch a quota that is simply nearly spent; the pace
    // comparison catches one that is still low but being spent faster than the
    // window refills, which is the failure you can still act on.
    function usageZone(pct, pace) {
        if (pct >= alertAt) return "alert";
        if (pct >= warnAt) return "warn";
        if (pace >= 0 && (pct - pace * 100) > paceTolerance) return "warn";
        if (pace < 0 && pct > 50) return "warn";
        return "calm";
    }

    function zoneColor(zone) {
        if (zone === "alert") return redAlert;
        if (zone === "warn") return claudeAmberLight;
        return calmFill;
    }

    // How many quotas are simultaneously in the alert zone. One is a problem;
    // two or more is a different kind of day, and the widget says so.
    readonly property int quotasInAlert: {
        var limits = usageData.rateLimits;
        if (!limits) return 0;
        var n = 0;
        var scopes = ["session", "weeklyAll", "weeklyOpus", "weeklySonnet",
                      "weeklyFable", "weeklyHaiku", "weeklyScoped"];
        for (var i = 0; i < scopes.length; i++) {
            var b = limits[scopes[i]];
            if (!b) continue;
            var hours = scopes[i] === "session" ? (b.windowHours ?? 5) : 168;
            if (usageZone(b.percentUsed ?? 0, windowPace(b.resetsAt ?? "", hours)) === "alert") n++;
        }
        return n;
    }

    // Worst zone across every quota on screen, so the widget has one answer to
    // "how am I doing" that the mascot and the gauges can both react to.
    readonly property string worstZone: worstZoneOf(usageData)

    // Taking a payload rather than reading usageData is not style.
    //
    // A property change handler runs before every binding that depends on the
    // same property has been re-evaluated, so a handler that read `worstZone`
    // would get the zone of the *previous* refresh — measured, not assumed:
    // the adaptive panel was written that way first and sat in "normal" with a
    // quota at 95%, one refresh behind for as long as it ran, with nothing in
    // the output to say so. The handler now passes the payload it was handed.
    function worstZoneOf(data) {
        var limits = (data || {}).rateLimits;
        if (!limits) return "calm";
        var worst = "calm";
        var scopes = ["session", "weeklyAll", "weeklyOpus", "weeklySonnet",
                      "weeklyFable", "weeklyHaiku", "weeklyScoped"];
        for (var i = 0; i < scopes.length; i++) {
            var b = limits[scopes[i]];
            if (!b) continue;
            var hours = scopes[i] === "session" ? (b.windowHours ?? 5) : 168;
            var z = usageZone(b.percentUsed ?? 0, windowPace(b.resetsAt ?? "", hours));
            if (z === "alert") return "alert";
            if (z === "warn") worst = "warn";
        }
        return worst;
    }

    // ── Adaptive panel mode ───────────────────────────────
    //
    // The panel is about forty pixels that stay on screen all day. The six
    // fixed modes each answer one question, chosen once and never revisited,
    // so the mode picked on a calm afternoon is still showing a weekly bar
    // during an outage. This one shows whichever of them matters now.
    //
    // Nothing new is measured for it: the order below is over predicates this
    // file already computes and the popup already draws — serviceStatus,
    // worstZone/usageZone, windowPace and limitEta.
    //
    // Priority, highest first, and why:
    //
    //   3  a major or critical service incident. It is the only state where
    //      slowing your own usage down is the wrong response, and it is the
    //      only one the user cannot infer from their own numbers.
    //   2  a quota in the alert zone. It is what stops work soonest, and it
    //      is the one the user can still act on.
    //  1.5 a minor incident — degraded, not down. Work continues, so it
    //      ranks under a spent quota and over a limit that is merely coming.
    //   1  the limit arriving: an ETA inside two hours, or a quota ahead of
    //      the pace its window refills at. Two hours because that is where
    //      the popup already starts marking the ETA (see limitIn, which goes
    //      DemiBold under 120 minutes) — the panel and the popup agreeing on
    //      one boundary is worth more than a second one invented here.
    //   0  normal, which is always available.
    //
    // Both failure modes of a mode that changes on its own are handled below:
    // flicker by adaptiveHolds() plus the dwell, and width by the delegate,
    // which is a fixed shape whatever state it is in.
    //
    // The functions are pure — plain values in, plain values out, the clock
    // passed as an argument — so tests/test_adaptive_panel.py can lift them
    // out of this file and drive a hundred refreshes through them. A binding
    // expression could only ever have been checked by reading it.

    // The release margin, in percentage points, for every entry condition
    // measured in them. Once a state is entered it is held until its own
    // condition has lapsed by this much.
    //
    // 3 points, from the geometry of the window rather than from taste: the
    // widget refreshes every 30 s (refreshInterval), and a 5 h window spent at
    // exactly the rate that would exhaust it moves percentUsed by
    // 100 / (5 * 3600 / 30) = 0.17 points per refresh. Three points is
    // eighteen refreshes of that, about nine minutes, so nothing a refresh can
    // do to the number crosses it — while the one thing that genuinely ends
    // the state, a window reset, drops it by tens of points at once and
    // crosses it immediately.
    readonly property real adaptiveDeadband: 3

    // And a floor in time for everything not measured in points — a service
    // incident appearing and clearing, an ETA that stops being computable.
    //
    // 120 s is four refreshes at the 30 s interval this widget polls on: a
    // reason that has gone has to stay gone across four consecutive refreshes
    // before the panel gives the state up. It bounds the way down only. The
    // way up is immediate, for the reason in pickAdaptive().
    readonly property int adaptiveDwellMs: 120000

    // Entry and release for the ETA, in minutes. The entry matches what the
    // popup already marks; the release is an hour beyond it, so a projection
    // has to move a full hour before the panel gives the state up. Unlike a
    // percentage, an ETA moves in both directions between refreshes: it is
    // recomputed from a burn rate that is re-averaged every run.
    readonly property int adaptiveEtaEnterMin: 120
    readonly property int adaptiveEtaHoldMin: 180

    property string adaptiveState: "normal"
    property string adaptiveScope: "session"
    // The last time the state being shown still had a reason to be — not the
    // time it was entered. Measuring the dwell from entry looks equivalent and
    // is not: a signal that flaps on and off, like an incident page that
    // answers "none" once in the middle of an outage, would then release the
    // state every two minutes and take it back on the next refresh. Measured
    // from the last time the reason held, a signal that keeps coming back
    // keeps the state, and only a reason that stays gone releases it.
    property real adaptiveHeldAt: 0

    readonly property real sessionPct: sessionPctOf(usageData)
    readonly property real worstWeeklyPct: worstWeeklyPctOf(usageData)

    function sessionPctOf(data) {
        return (data || {}).rateLimits?.session?.percentUsed ?? 0;
    }

    // The worst of the weekly quotas. Several are reported at once — the
    // all-models cap plus a per-model one — and the panel has room for one
    // number.
    function worstWeeklyPctOf(data) {
        var limits = (data || {}).rateLimits;
        if (!limits) return 0;
        var scopes = ["weeklyAll", "weeklyOpus", "weeklySonnet",
                      "weeklyFable", "weeklyHaiku", "weeklyScoped"];
        var worst = 0;
        for (var i = 0; i < scopes.length; i++) {
            var b = limits[scopes[i]];
            var pct = b ? (b.percentUsed ?? 0) : 0;
            if (pct > worst) worst = pct;
        }
        return worst;
    }

    // How far ahead of even burn the worst quota is, in points. The same
    // comparison usageZone() makes, kept as a number rather than a zone so
    // the release margin can be applied to it in the same units as everything
    // else.
    function worstPaceGapOf(data) {
        var limits = (data || {}).rateLimits;
        if (!limits) return -1;
        var scopes = ["session", "weeklyAll", "weeklyOpus", "weeklySonnet",
                      "weeklyFable", "weeklyHaiku", "weeklyScoped"];
        var gap = -1;
        for (var i = 0; i < scopes.length; i++) {
            var b = limits[scopes[i]];
            if (!b) continue;
            var hours = scopes[i] === "session" ? (b.windowHours ?? 5) : 168;
            var pace = windowPace(b.resetsAt ?? "", hours);
            if (pace < 0) continue;
            var g = (b.percentUsed ?? 0) - pace * 100;
            if (g > gap) gap = g;
        }
        return gap;
    }

    // Everything the decision needs, as plain values, computed from the
    // payload rather than from the bindings over it — see worstZoneOf().
    function adaptiveSignals(data) {
        var d = data || usageData || ({});
        var session = sessionPctOf(d);
        var weekly = worstWeeklyPctOf(d);
        return {
            "incident": d.serviceStatus?.indicator ?? "none",
            "worstZone": worstZoneOf(d),
            "pcts": { "session": session, "weekly": weekly },
            // Ties go to the session: it is the shorter window, so it is the
            // one that both stops work sooner and clears sooner.
            "worstScope": weekly > session ? "weekly" : "session",
            "worstPct": Math.max(session, weekly),
            "paceGap": worstPaceGapOf(d),
            "paceTolerance": paceTolerance,
            "etaMinutes": d.limitEta?.minutesToLimit ?? -1,
            "warnAt": warnAt,
            "alertAt": alertAt,
            "deadband": adaptiveDeadband,
            "dwellMs": adaptiveDwellMs,
            "etaEnterMin": adaptiveEtaEnterMin,
            "etaHoldMin": adaptiveEtaHoldMin
        };
    }

    // What each state is worth right now, or -1 when its condition is not met
    // at all. The numbers are the priority list at the top of this block.
    function adaptiveUrgency(state, s) {
        if (state === "incident") {
            if (s.incident === "major" || s.incident === "critical") return 3;
            return s.incident === "minor" ? 1.5 : -1;
        }
        if (state === "quota") return s.worstZone === "alert" ? 2 : -1;
        if (state === "eta") {
            var arriving = s.etaMinutes > 0 && s.etaMinutes <= s.etaEnterMin;
            return (arriving || s.worstZone === "warn") ? 1 : -1;
        }
        return 0;
    }

    // What a state outranks while it is the one being shown, whether or not
    // its condition still holds. Comparing against adaptiveUrgency() instead
    // would read a lapsed condition as -1 and let anything at all take the
    // panel over immediately, which is the flicker this exists to stop. The
    // incident case is not a constant because a degraded service and an
    // outage are not the same claim.
    function adaptiveRank(state, s) {
        if (state === "incident")
            return (s.incident === "major" || s.incident === "critical") ? 3 : 1.5;
        if (state === "quota") return 2;
        if (state === "eta") return 1;
        return 0;
    }

    function adaptiveDesired(s) {
        var best = "normal";
        var bestUrgency = 0;
        var order = ["incident", "quota", "eta"];
        for (var i = 0; i < order.length; i++) {
            var u = adaptiveUrgency(order[i], s);
            if (u > bestUrgency) { bestUrgency = u; best = order[i]; }
        }
        return best;
    }

    // Whether the state being shown still has a reason to be, with the
    // release margin applied. Every branch is the entry condition of the same
    // state, relaxed by the deadband.
    function adaptiveHolds(state, s) {
        if (state === "incident")
            return s.incident !== "none" && s.incident !== ""
                && s.incident !== "unknown";
        if (state === "quota")
            return s.worstPct >= s.alertAt - s.deadband;
        if (state === "eta")
            return s.worstPct >= s.warnAt - s.deadband
                || s.paceGap > s.paceTolerance - s.deadband
                || (s.etaMinutes > 0 && s.etaMinutes <= s.etaHoldMin);
        return true;
    }

    // The whole state machine, in one pure function. Takes the state being
    // shown and when its reason last held, returns both.
    function pickAdaptive(current, heldAt, nowMs, s) {
        // Rising is immediate, falling is held, and that asymmetry is the
        // design. Showing a problem late is the one failure this widget
        // cannot afford — it exists to warn while there is still something to
        // do about it — whereas staying serious for two minutes after the
        // problem has gone costs nothing.
        var holds = adaptiveHolds(current, s);
        if (holds) heldAt = nowMs;

        var desired = adaptiveDesired(s);
        var state = current;
        if (desired !== current) {
            if (adaptiveUrgency(desired, s) > adaptiveRank(current, s)) {
                state = desired;
            } else if (!holds && nowMs - heldAt >= s.dwellMs) {
                // Only here does the panel change its face on the way down,
                // and only after the reason has been gone for the whole
                // dwell without once coming back.
                state = desired;
            }
        }
        if (state !== current) heldAt = nowMs;
        return { "state": state, "heldAt": heldAt };
    }

    // Which quota the panel is describing. A challenger has to be ahead of the
    // incumbent by the same margin before it takes over, or two quotas a tenth
    // of a point apart trade the icon back and forth on every refresh — the
    // same defect as above, one level down.
    function pickAdaptiveScope(current, s) {
        if (!current || s.pcts[current] === undefined) return s.worstScope;
        if (s.worstScope === current) return current;
        return (s.worstPct - s.pcts[current] > s.deadband) ? s.worstScope
                                                           : current;
    }

    function updateAdaptive(data) {
        var s = adaptiveSignals(data);
        var picked = pickAdaptive(adaptiveState, adaptiveHeldAt, Date.now(), s);
        adaptiveState = picked.state;
        adaptiveHeldAt = picked.heldAt;
        adaptiveScope = pickAdaptiveScope(adaptiveScope, s);
    }

    // Two triggers. New data is the obvious one; nowMs is the timer that
    // already ticks once a minute for the forecasts, and without it a dwell
    // that expires while nothing else changes would never be noticed — the
    // panel would sit in a state whose reason went away until the next
    // refresh happened to arrive.
    onUsageDataChanged: root.updateAdaptive(usageData)
    onNowMsChanged: root.updateAdaptive(usageData)

    // What the delegate draws. Kept here so the delegate has no decisions left
    // in it, and so the state and its appearance cannot drift apart.
    readonly property string adaptiveIcon: {
        if (adaptiveState === "incident") return "network-disconnect";
        if (adaptiveState === "quota")
            return adaptiveScope === "weekly" ? "view-calendar-week" : "chronometer";
        if (adaptiveState === "eta") return "chronometer";
        return "";
    }

    readonly property color adaptiveColor: {
        if (adaptiveState === "incident")
            return statusColor(usageData.serviceStatus?.indicator ?? "none");
        if (adaptiveState === "quota") return redAlert;
        if (adaptiveState === "eta") return claudeAmberLight;
        return Kirigami.Theme.textColor;
    }

    readonly property real adaptivePct: adaptiveScope === "weekly" ? worstWeeklyPct
                                                                   : sessionPct

    readonly property string adaptiveReasonKey: {
        if (adaptiveState === "incident") return "adaptiveIncident";
        if (adaptiveState === "quota") return "adaptiveQuota";
        if (adaptiveState === "eta") return "adaptiveEta";
        return "adaptiveNormal";
    }

    function paceFill(pct, pace) {
        return zoneColor(usageZone(pct, pace));
    }

    function paceTextColor(pct, pace) {
        var z = usageZone(pct, pace);
        return z === "calm" ? Kirigami.Theme.textColor : zoneColor(z);
    }

    function limitColor(pct) {
        if (pct > 80) return redAlert;
        if (pct > 50) return claudeAmberLight;
        return Kirigami.Theme.textColor;
    }

    // ── Projections and baselines ─────────────────────────
    //
    // Everything in this block is plain JavaScript over plain values: no
    // `root.`, no Qt types, no theme lookups, and the clock arrives as an
    // argument instead of being read. That is not style. A binding expression
    // inside a delegate can only ever be checked by reading it, because the
    // widget does not load outside a Plasma session; a free function over
    // numbers can be lifted out of this file and run against real ones, which
    // is how the awkward cases below (a rate of zero, a projection past the
    // reset, a day that is three hours old, a series too short to mean
    // anything) are verified rather than merely asserted. The words and the
    // colours stay in the delegates; only the arithmetic lives here.

    // Fed to those functions by a timer rather than by Date.now() inside a
    // binding, which would never re-evaluate: the expression has no dependency
    // that changes, so the forecast would be frozen at the instant the popup
    // was built and look correct while going stale.
    property real nowMs: Date.now()
    Timer {
        // A minute is finer than anything this drives — the forecast resolves
        // to a quarter of a day and the comparison to the hour — and coarse
        // enough that it costs nothing while the popup is closed.
        interval: 60000
        running: true; repeat: true
        onTriggered: root.nowMs = Date.now()
    }

    // When the weekly ceiling is reached at the pace this week has kept.
    //
    // The 5h window already has limitEta. The week — the one that actually
    // stops the week — had a bar and a reset time, which say where you are and
    // never whether you arrive.
    //
    // The rate is percentUsed divided by the hours elapsed in the window, and
    // deliberately NOT burnRate.total_per_hour. The two are in different units,
    // percent of an undisclosed weekly allowance against tokens per hour, and
    // the payload carries no factor between them: the weekly cap is not
    // denominated in tokens and it weighs models differently, so a
    // tokens-to-percent conversion invented here would make the number look
    // more current while making it less true. burnRate is read for the one
    // question it can answer on its own — whether anything is being spent at
    // all — and that is what gates the forecast. It can serve as a gate
    // because the collector averages it over a rolling two hours
    // (calculate_burn_rate), so it reaches zero after an idle stretch rather
    // than flickering between refreshes.
    //
    // Damping, because a projection that walks from Thursday to Saturday
    // between two refreshes is noise wearing a date:
    //   - the pace is an average over the whole elapsed window, so a single
    //     idle hour moves it by at most 1/elapsed;
    //   - the caller renders a quarter of a day, not an instant, so a couple
    //     of hours of wobble does not change the label, and the label
    //     advertises the precision it actually has;
    //   - the far tail, where a small pace makes the projected instant wildly
    //     sensitive, is absorbed by the reset: past it the answer stops being
    //     a date at all and becomes "the window turns over first", which does
    //     not depend on where in the tail the projection landed.
    function weeklyForecast(weekly, burnPerHour, now) {
        var out = { state: "unknown", pctPerHour: 0, hoursToLimit: -1,
                    atMs: -1, resetMs: -1, elapsedHours: 0, percentUsed: 0 };
        if (!weekly) return out;
        // Loose on purpose: a scope the API reported with a null percentage
        // has an unknown position in the window, and Number(null) is 0, which
        // would quietly turn "we were not told" into "nothing spent".
        if (weekly.percentUsed == null) return out;
        var pct = Number(weekly.percentUsed);
        if (!isFinite(pct)) return out;
        out.percentUsed = pct;

        var reset = Date.parse(weekly.resetsAt || "");
        if (isNaN(reset)) return out;
        out.resetMs = reset;

        // The weekly window is 168h wide and resetsAt is its far edge, so how
        // far into it we are follows from the reset alone.
        var elapsed = 168 - (reset - now) / 3600000;
        // A reset already behind us, or further ahead than the window is long,
        // means the timestamp and the clock disagree. There is no position in
        // the window to divide by, and inventing one would silently scale
        // every number below it.
        if (!(elapsed > 0) || elapsed > 168) return out;
        out.elapsedHours = elapsed;

        if (pct >= 100) { out.state = "atLimit"; return out; }

        // No rate: nothing spent this week, or nothing being spent right now.
        // Dividing by it yields infinity, and "never" is a claim about the
        // future that this data cannot make. The honest statement is that
        // there is nothing to project from.
        if (!(pct > 0) || !(Number(burnPerHour) > 0)) { out.state = "noPace"; return out; }

        out.pctPerHour = pct / elapsed;
        var hours = (100 - pct) / out.pctPerHour;
        out.hoursToLimit = hours;
        out.atMs = now + hours * 3600000;
        // Landing after the reset is good news and a different statement, not
        // a quieter rendering of the same alarm.
        out.state = out.atMs >= reset ? "resetFirst" : "limitFirst";
        return out;
    }

    // How loud the forecast should be, in hours rather than percent: a ceiling
    // three days out is information, one twelve hours out is a decision.
    function forecastZone(f) {
        if (!f) return "calm";
        if (f.state === "atLimit") return "alert";
        if (f.state !== "limitFirst") return "calm";
        if (f.hoursToLimit < 24) return "alert";
        if (f.hoursToLimit < 72) return "warn";
        return "calm";
    }

    // Where an instant falls on the reader's calendar.
    //
    // Every getter here is a local-time getter, deliberately. resetsAt is UTC;
    // a reader three hours west told "Friday" about an instant that is Thursday
    // 23:00 where they are has been handed the wrong day, and the mistake is
    // invisible because the percentage beside it is right.
    //
    // The hour is bucketed into quarters of a day because the forecast is not
    // accurate to the hour and must not look as though it is.
    function calendarParts(ms, now) {
        var d = new Date(ms);
        var h = d.getHours();
        var part = h < 6 ? "night" : h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
        return { part: part, weekday: d.getDay(), hour: h };
    }

    // Cost per project, from the per-session rows.
    //
    // The key is the project string exactly as the collector emits it, and
    // that is not laziness. Those strings are Claude's project directory
    // names, in which a path separator and a literal dash in a directory name
    // have both become "/": "home/ti/claude/usage/widget" is one repository
    // called claude-usage-widget, not a widget inside a usage inside a claude.
    // Splitting on "/" to find "the repo" would invent a hierarchy that is not
    // in the data. Two sessions in the same checkout emit byte-identical
    // strings, which makes grouping on the whole string the correct general
    // answer as well as the safe one.
    //
    // Nothing here accumulates across days, and nothing should: sessionCosts
    // is today's list, and the payload carries no per-project series.
    function costsByProject(rows) {
        var list = rows || [];
        var index = {}, out = [], total = 0;
        for (var i = 0; i < list.length; i++) {
            var r = list[i] || {};
            var key = r.project ? String(r.project) : (r.id ? String(r.id) : "?");
            var g = index[key];
            if (!g) {
                g = { project: key, costUSD: 0, tokens: 0, messages: 0,
                      sessions: 0, share: 0 };
                index[key] = g;
                out.push(g);
            }
            var cost = Number(r.costUSD) || 0;
            g.costUSD += cost;
            g.tokens += Number(r.tokens) || 0;
            g.messages += Number(r.messages) || 0;
            g.sessions += 1;
            total += cost;
        }
        for (var j = 0; j < out.length; j++)
            out[j].share = total > 0 ? out[j].costUSD / total : 0;
        // Cost descending, then name, so rows with equal cost do not reshuffle
        // between refreshes.
        out.sort(function (a, b) {
            return (b.costUSD - a.costUSD)
                || (a.project < b.project ? -1 : a.project > b.project ? 1 : 0);
        });
        return out;
    }

    // How much of the reader's local day has gone by, 0..1.
    function dayFraction(now) {
        var midnight = new Date(now);
        midnight.setHours(0, 0, 0, 0);
        var f = (now - midnight.getTime()) / 86400000;
        return f < 0 ? 0 : f > 1 ? 1 : f;
    }

    // Today against this account's own recent days.
    //
    // A number with no baseline is decoration, and three separate things make
    // the naive version of this a lie. Each is handled rather than hidden.
    //
    //   Partial day. Today is a few hours old; the days it is measured against
    //   are whole. Compared with yesterday's total, 11:00 reads "below normal"
    //   every single day, which is a gauge that says the same thing whatever
    //   happens. The baseline is scaled by how much of today has elapsed —
    //   the same even-burn assumption the window gauges above already make,
    //   and just as much an assumption: it reads high for someone who works
    //   mornings and low for someone who works nights.
    //
    //   Too early. Before the day is a couple of hours old the scaled baseline
    //   is near zero and the ratio against it explodes; one request at 00:10
    //   would show as ten normal days. Below that the honest answer is that
    //   the day has not started yet.
    //
    //   Too little history. Seven prior days is a very small sample, and the
    //   idle ones say nothing about how much work a working day carries, so
    //   they are dropped — left in, they drag the centre down until every
    //   working day reads as a spike. The centre is a median, because one
    //   6.7-billion-token day out of five drags a mean somewhere no day has
    //   ever been. The verdict is a rank statement, inside or outside the
    //   range those days actually spanned, because a spread that wide supports
    //   no tighter claim. Under three active days there is no verdict at all.
    //
    // Deliberately NOT built: "high for a Wednesday morning". peakHours counts
    // by hour of day with no weekday in it, and eight days of trend give
    // exactly one sample per weekday. There is no day-of-week baseline in this
    // payload to compare against, and one sample is not a baseline.
    function baselineComparison(trend, field, now) {
        var out = { state: "insufficient", days: 0, value: 0, expected: 0,
                    ratio: 0, verdict: "typical", fraction: 0,
                    median: 0, lo: 0, hi: 0 };
        var rows = trend || [];
        if (rows.length < 2) return out;

        out.value = Number((rows[rows.length - 1] || {})[field]) || 0;

        var prior = [];
        for (var i = 0; i < rows.length - 1; i++) {
            var v = Number((rows[i] || {})[field]) || 0;
            if (v > 0) prior.push(v);
        }
        out.days = prior.length;
        if (prior.length < 3) return out;

        var frac = dayFraction(now);
        out.fraction = frac;
        if (frac < 1 / 12) { out.state = "tooEarly"; return out; }

        prior.sort(function (a, b) { return a - b; });
        var mid = Math.floor(prior.length / 2);
        out.median = prior.length % 2 ? prior[mid]
                                      : (prior[mid - 1] + prior[mid]) / 2;
        out.lo = prior[0] * frac;
        out.hi = prior[prior.length - 1] * frac;
        out.expected = out.median * frac;
        out.ratio = out.expected > 0 ? out.value / out.expected : 0;
        out.verdict = out.value > out.hi ? "above"
                    : out.value < out.lo ? "below" : "typical";
        out.state = "ok";
        return out;
    }

    // Words for a projected instant. A thin wrapper so the arithmetic above
    // stays free of tr() and the vocabulary stays in one place.
    //
    // The weekday is spelled out even when the instant is today: the window is
    // at most seven days wide, so an abbreviation is unambiguous, and "today"
    // followed by a part of the day does not survive translation into both
    // languages without a special case per language.
    function whenLabel(ms, now) {
        var p = calendarParts(ms, now);
        return tr("wd" + p.weekday) + " " + tr("part_" + p.part);
    }

    // A rate below 1%/h needs the second decimal to say anything at all.
    function formatPctPerHour(v) {
        return (v >= 1 ? v.toFixed(1) : v.toFixed(2)) + "%/h";
    }


    // Weekly rows, derived from whatever rateLimits actually carries.
    //
    // Order is fixed so the list does not reshuffle between refreshes; a scope
    // the API did not report is simply absent. `weeklyScoped` is the API's own
    // per-model entry: it is rendered under its own display_name only when no
    // named row already covers that model, so a scoped Fable cap shows up once,
    // not twice.
    // Three tiles: what today, this week and the whole history are worth at
    // public per-token prices. Built here so the card stays declarative.
    function _usd(v) {
        if (v >= 1000) return "$" + (v / 1000).toFixed(1) + "k";
        return "$" + v.toFixed(2);
    }

    // Three diagnostics, replacing a "value extracted" card that was 98% cache
    // reads — the same context re-read, billed at a tenth of input precisely
    // because it is cheap. Calling that extracted value inflated the number
    // with an implementation detail and answered nothing.
    readonly property var valueTiles: {
        var eff = usageData.efficiency ?? {};
        var mtd = usageData.monthToDate ?? {};
        var plan = Plasmoid.configuration.planMonthlyCost || 0;
        var rows = [];

        // What the cache is worth. Falls when something invalidates the prefix.
        rows.push({ label: tr("cacheSaved"),
                    value: _usd(eff.savedUSD ?? 0),
                    sub: Math.round((eff.cacheHitRate ?? 0) * 100) + "% " + tr("hit"),
                    accent: (eff.cacheHitRate ?? 0) >= 0.6 ? greenAccent
                          : (eff.cacheHitRate ?? 0) >= 0.3 ? Kirigami.Theme.textColor
                          : claudeAmberLight });

        // Read per produced. Climbs when context is carried without earning it.
        rows.push({ label: tr("readPerOutput"),
                    value: Math.round(eff.readPerOutput ?? 0) + ":1",
                    sub: formatTokens(eff.outputTokens ?? 0) + " " + tr("produced"),
                    accent: Kirigami.Theme.textColor });

        // Only with a plan price entered. Without one this would be a
        // fabricated denominator in a "is it worth it" answer.
        if (plan > 0 && (mtd.usd ?? 0) > 0) {
            rows.push({ label: tr("planPayback"),
                        value: (mtd.usd / plan).toFixed(1) + "×",
                        sub: _usd(mtd.usd) + " " + tr("thisMonth"),
                        accent: greenAccent });
        } else {
            rows.push({ label: tr("thisMonth"),
                        value: _usd(mtd.usd ?? 0),
                        sub: (mtd.days ?? 0) + tr("daysShort"),
                        accent: Kirigami.Theme.textColor });
        }
        return rows;
    }

    // Badges derived from data already collected. Nothing here triggers a
    // request or a new field — it is arithmetic over what the popup already
    // shows, surfaced because "1.7B tokens today" is a fact worth a reaction.
    readonly property var quirkBadges: {
        var out = [];
        var t = usageData.today ?? {};
        var tools = usageData.toolUse?.byTool ?? {};
        var hours = usageData.lifetime?.peakHours ?? {};

        var tok = t.totalTokens ?? 0;
        if (tok >= 1e9) out.push({ icon: "⚡", text: formatTokens(tok) + " today" });

        // Tool dominance: the share of the busiest tool. Above ~70% it says
        // something real about how the session is being driven.
        var total = 0, topName = "", topCount = 0;
        for (var k in tools) {
            total += tools[k];
            if (tools[k] > topCount) { topCount = tools[k]; topName = k; }
        }
        if (total > 200 && topCount / total > 0.7)
            out.push({ icon: "🔨", text: Math.round(100 * topCount / total) + "% " + topName });

        var streak = usageData.streak?.days ?? 0;
        if (streak >= 3) out.push({ icon: "🔥", text: streak + "-day streak" });

        // Night owl: meaningful share of lifetime activity between 00h and 05h.
        var night = 0, all = 0;
        for (var h = 0; h < 24; h++) {
            var v = hours[String(h)] || 0;
            all += v;
            if (h < 6) night += v;
        }
        if (all > 50 && night / all > 0.15)
            out.push({ icon: "🌙", text: Math.round(100 * night / all) + "% after midnight" });

        var comp = usageData.compaction?.count ?? 0;
        if (comp >= 5) out.push({ icon: "🧠", text: comp + " compactions" });

        return out;
    }

    readonly property var weeklyScopeOrder: [
        // The two generic scopes are named by the provider: "All models" reads
        // wrong for a single-model API, and Codex has no Sonnet. The rest are
        // Claude model families and simply never appear for another provider,
        // because that collector does not emit those keys.
        { key: "weeklyAll",       label: brand.weeklyAllLabel,       accent: blueAccent },
        { key: "weeklyOpus",      label: "Opus only",     accent: purpleAccent },
        { key: "weeklySonnet",    label: brand.weeklySecondaryLabel, accent: greenAccent },
        { key: "weeklyFable",     label: "Fable only",    accent: blueAccent },
        { key: "weeklyHaiku",     label: "Haiku only",    accent: cyanAccent },
        { key: "weeklyDesign",    label: "Claude Design", accent: pinkAccent },
        { key: "weeklyOauthApps", label: "OAuth apps",    accent: cyanAccent },
        { key: "weeklyCowork",    label: "Cowork",        accent: claudeAmberLight }
    ]

    readonly property var weeklyRows: {
        var limits = usageData.rateLimits;
        if (!limits) return [];

        var rows = [];
        var covered = {};
        for (var i = 0; i < weeklyScopeOrder.length; i++) {
            var spec = weeklyScopeOrder[i];
            var block = limits[spec.key];
            if (block === undefined || block === null) continue;
            if (block.modelName) covered[String(block.modelName).toLowerCase()] = true;
            rows.push({
                label: spec.label,
                accent: spec.accent,
                pct: block.percentUsed ?? 0,
                resetsLabel: block.resetsLabel ?? "",
                resetsAt: block.resetsAt ?? ""
            });
        }

        // A model the API scopes that has no row above — a new or renamed model
        // — would otherwise be invisible. Show it under the name the API gives.
        var scoped = limits.weeklyScoped;
        if (scoped && scoped.modelName
                && !covered[String(scoped.modelName).toLowerCase()]) {
            rows.push({
                label: scoped.modelName,
                accent: claudeAmberLight,
                pct: scoped.percentUsed ?? 0,
                resetsLabel: scoped.resetsLabel ?? "",
                resetsAt: scoped.resetsAt ?? ""
            });
        }
        return rows;
    }

    function barFill(pct, base) {
        if (pct > 80) return redAlert;
        if (pct > 50) return claudeAmberLight;
        return base;
    }

    function statusColor(indicator) {
        if (indicator === "none") return greenAccent;
        if (indicator === "minor") return claudeAmberLight;
        if (indicator === "major") return "#F97316";
        if (indicator === "critical") return redAlert;
        return Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.4);
    }

    function componentStatusColor(status) {
        if (status === "operational") return greenAccent;
        if (status === "degraded_performance") return claudeAmberLight;
        if (status === "partial_outage") return "#F97316";
        if (status === "major_outage") return redAlert;
        return Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.4);
    }

    // ─── Panel (Compact) ───
    compactRepresentation: MouseArea {
        id: compactArea
        Layout.minimumWidth: compactLoader.implicitWidth
        Layout.preferredWidth: compactLoader.implicitWidth
        hoverEnabled: true
        onClicked: root.expanded = !root.expanded

        // Loader selects the correct compact layout based on displayMode
        Loader {
            id: compactLoader
            anchors.fill: parent
            sourceComponent: {
                if (root.displayMode === "sparkline")        return compSparkline;
                if (root.displayMode === "weeklyBarOnly")     return compWeeklyBar;
                if (root.displayMode === "fableBarOnly")      return compFableBar;
                if (root.displayMode === "sessionCountdown")  return compSessionCountdown;
                if (root.displayMode === "weeklyCountdown")   return compWeeklyCountdown;
                if (root.displayMode === "adaptive")          return compAdaptive;
                return compFull;
            }
        }

        // ── Mode: full (default) ──────────────────────────────────
        Component {
            id: compFull
            RowLayout {
                spacing: Kirigami.Units.smallSpacing

                Image {
                    source: Qt.resolvedUrl("../icons/" + root.brand.logo)
                    Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                    Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                    sourceSize: Qt.size(Kirigami.Units.iconSizes.smallMedium, Kirigami.Units.iconSizes.smallMedium)
                    fillMode: Image.PreserveAspectFit
                }

                PlasmaComponents3.Label {
                    property real pct: root.usageData.rateLimits?.session?.percentUsed ?? 0
                    text: root.hasData ? Math.round(pct) + "%" : "--"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.15
                    font.weight: Font.Bold
                    color: limitColor(pct)
                }

                Rectangle {
                    Layout.preferredWidth: 34; Layout.preferredHeight: 5
                    Layout.alignment: Qt.AlignVCenter
                    radius: 3; color: root.subtleBorder
                    Rectangle {
                        property real pct: root.usageData.rateLimits?.session?.percentUsed ?? 0
                        width: parent.width * Math.min(1, pct / 100)
                        height: parent.height; radius: 3
                        color: barFill(pct, root.claudeAmber)
                        Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                    }
                }

                RowLayout {
                    id: statusCompact
                    property string indicator: root.usageData.serviceStatus?.indicator ?? "none"
                    visible: root.hasData && indicator !== "none" && indicator !== "" && indicator !== "unknown"
                    spacing: 3
                    Layout.alignment: Qt.AlignVCenter

                    Rectangle {
                        width: 8; height: 8; radius: 4
                        color: statusColor(statusCompact.indicator)
                        Layout.alignment: Qt.AlignVCenter
                        SequentialAnimation on opacity {
                            running: statusCompact.indicator === "major" || statusCompact.indicator === "critical"
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.2; duration: 650; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 1.0; duration: 650; easing.type: Easing.InOutSine }
                        }
                    }

                    PlasmaComponents3.Label {
                        text: {
                            var ind = statusCompact.indicator;
                            if (ind === "minor")    return "Degraded";
                            if (ind === "major")    return "Outage";
                            if (ind === "critical") return "Critical";
                            return "";
                        }
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.80
                        font.weight: Font.DemiBold
                        color: statusColor(statusCompact.indicator)
                    }
                }
            }
        }

        // ── Mode: sparkline ───────────────────────────────────────
        // Seven days of trend in the panel. The data was already collected and
        // only ever shown inside the popup, so the shape of the week cost a
        // click to see.
        Component {
            id: compSparkline
            RowLayout {
                spacing: Kirigami.Units.smallSpacing

                Image {
                    source: Qt.resolvedUrl("../icons/" + root.brand.logo)
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    sourceSize: Qt.size(Kirigami.Units.iconSizes.small, Kirigami.Units.iconSizes.small)
                    fillMode: Image.PreserveAspectFit
                    Layout.alignment: Qt.AlignVCenter
                }

                RowLayout {
                    id: spark
                    spacing: 2
                    Layout.alignment: Qt.AlignVCenter
                    // Scale to the busiest day, so the shape is readable even
                    // when the week is uniformly heavy or uniformly light.
                    property real peak: {
                        var t = root.usageData.trend7d ?? [];
                        var m = 0;
                        for (var i = 0; i < t.length; i++) m = Math.max(m, t[i].tokens ?? 0);
                        return m;
                    }

                    Repeater {
                        model: root.usageData.trend7d ?? []
                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            width: 4
                            height: 18
                            radius: 1
                            color: root.subtleBorder
                            Layout.alignment: Qt.AlignVCenter

                            Rectangle {
                                anchors.bottom: parent.bottom
                                width: parent.width
                                radius: 1
                                // Minimum 2px so a day with any activity is
                                // visibly different from a day with none.
                                height: {
                                    var v = modelData.tokens ?? 0;
                                    if (v <= 0 || spark.peak <= 0) return 0;
                                    return Math.max(2, parent.height * (v / spark.peak));
                                }
                                color: index === (root.usageData.trend7d ?? []).length - 1
                                       ? root.claudeAmberLight : root.calmFill
                                Behavior on height { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                            }
                        }
                    }
                }

                PlasmaComponents3.Label {
                    property real pct: root.usageData.rateLimits?.session?.percentUsed ?? 0
                    text: root.hasData ? Math.round(pct) + "%" : "--"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.95
                    font.weight: Font.Bold
                    font.features: ({ "tnum": 1 })
                    color: root.paceTextColor(pct, root.windowPace(
                        root.usageData.rateLimits?.session?.resetsAt ?? "",
                        root.usageData.rateLimits?.session?.windowHours ?? 5))
                    Layout.alignment: Qt.AlignVCenter
                }
            }
        }

        // ── Mode: weeklyBarOnly ───────────────────────────────────
        Component {
            id: compWeeklyBar
            RowLayout {
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents3.Label {
                    text: "W"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.75
                    font.weight: Font.Bold
                    opacity: 0.45
                    Layout.alignment: Qt.AlignVCenter
                }

                ColumnLayout {
                    spacing: 2
                    Layout.alignment: Qt.AlignVCenter

                    PlasmaComponents3.Label {
                        property real pct: root.usageData.rateLimits?.weeklyAll?.percentUsed ?? 0
                        text: root.hasData ? Math.round(pct) + "%" : "--"
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.90
                        font.weight: Font.Bold
                        color: limitColor(pct)
                    }

                    Rectangle {
                        Layout.preferredWidth: 48; height: 5; radius: 3
                        color: root.subtleBorder
                        Rectangle {
                            property real pct: root.usageData.rateLimits?.weeklyAll?.percentUsed ?? 0
                            width: parent.width * Math.min(1, pct / 100)
                            height: parent.height; radius: 3
                            color: barFill(pct, root.blueAccent)
                            Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                        }
                    }
                }
            }
        }

        // ── Mode: fableBarOnly ────────────────────────────────────
        Component {
            id: compFableBar
            RowLayout {
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents3.Label {
                    text: "F"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.75
                    font.weight: Font.Bold
                    opacity: 0.45
                    Layout.alignment: Qt.AlignVCenter
                }

                ColumnLayout {
                    spacing: 2
                    Layout.alignment: Qt.AlignVCenter

                    PlasmaComponents3.Label {
                        property var fable: root.usageData.rateLimits?.weeklyFable ?? null
                        property real pct: fable?.percentUsed ?? 0
                        text: (root.hasData && fable) ? Math.round(pct) + "%" : "--"
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.90
                        font.weight: Font.Bold
                        color: limitColor(pct)
                    }

                    Rectangle {
                        Layout.preferredWidth: 48; height: 5; radius: 3
                        color: root.subtleBorder
                        Rectangle {
                            property real pct: root.usageData.rateLimits?.weeklyFable?.percentUsed ?? 0
                            width: parent.width * Math.min(1, pct / 100)
                            height: parent.height; radius: 3
                            color: barFill(pct, root.blueAccent)
                            Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                        }
                    }
                }
            }
        }

        // ── Mode: sessionCountdown ────────────────────────────────
        Component {
            id: compSessionCountdown
            RowLayout {
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Icon {
                    source: "chronometer"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    opacity: 0.5
                    Layout.alignment: Qt.AlignVCenter
                }

                PlasmaComponents3.Label {
                    text: {
                        var totalSec = root.countdownMinutes * 60 + root.countdownSeconds;
                        return root.hasData ? root.formatCountdown(totalSec) : "--";
                    }
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.0
                    font.weight: Font.Bold
                    color: {
                        var m = root.countdownMinutes;
                        if (m < 30) return root.redAlert;
                        if (m < 60) return root.claudeAmberLight;
                        return Kirigami.Theme.textColor;
                    }
                    Layout.alignment: Qt.AlignVCenter
                }
            }
        }

        // ── Mode: adaptive ────────────────────────────────────────
        //
        // One shape, four states. The icon, the colour and which quota the
        // number belongs to change; the geometry does not, and that is the
        // point.
        //
        // Every other mode here is chosen by a person and then sits still. A
        // panel item that changes width shoves every icon to its right along
        // the panel, and this is the one mode that changes its own content
        // with nobody touching it — so it would do that shoving on its own,
        // repeatedly, while the user is looking somewhere else. Hence the
        // fixed slots: the icon column is one icon wide whichever icon it
        // holds, the bar is a constant 34 px, and the label is pinned to the
        // width of the widest string it can ever contain rather than to the
        // string it happens to hold. "7%" and "100%" are not the same width.
        //
        // Cost of that decision: the mode is always as wide as its widest
        // state, so it takes a few pixels more than it strictly needs most of
        // the time. That is the right trade — the alternative is paid by
        // every other applet in the panel.
        Component {
            id: compAdaptive
            RowLayout {
                spacing: Kirigami.Units.smallSpacing

                // A fixed slot holding both possible marks. The normal state
                // draws the brand logo and the others draw a themed icon;
                // swapping the item type inside a layout would resize the
                // column, which is the one thing this mode must not do.
                Item {
                    Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                    Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                    Layout.alignment: Qt.AlignVCenter

                    Image {
                        anchors.fill: parent
                        visible: root.adaptiveState === "normal"
                        source: Qt.resolvedUrl("../icons/" + root.brand.logo)
                        sourceSize: Qt.size(Kirigami.Units.iconSizes.smallMedium,
                                            Kirigami.Units.iconSizes.smallMedium)
                        fillMode: Image.PreserveAspectFit
                    }

                    Kirigami.Icon {
                        anchors.fill: parent
                        visible: root.adaptiveState !== "normal"
                        source: root.adaptiveIcon
                        color: root.adaptiveColor
                        isMask: true
                    }
                }

                PlasmaComponents3.Label {
                    Layout.preferredWidth: adaptiveWidest.width
                    horizontalAlignment: Text.AlignRight
                    text: root.hasData ? Math.round(root.adaptivePct) + "%" : "--"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.15
                    font.weight: Font.Bold
                    color: root.adaptiveColor
                    Layout.alignment: Qt.AlignVCenter
                }

                // The pin. Measured through Qt's own font engine rather than
                // guessed at in grid units, because the string is digits and
                // the font is the user's.
                TextMetrics {
                    id: adaptiveWidest
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.15
                    font.weight: Font.Bold
                    text: "100%"
                }

                Rectangle {
                    Layout.preferredWidth: 34; Layout.preferredHeight: 5
                    Layout.alignment: Qt.AlignVCenter
                    radius: 3; color: root.subtleBorder
                    Rectangle {
                        width: parent.width * Math.min(1, root.adaptivePct / 100)
                        height: parent.height; radius: 3
                        color: root.adaptiveColor
                        Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                    }
                }
            }
        }

        // ── Mode: weeklyCountdown ─────────────────────────────────
        Component {
            id: compWeeklyCountdown
            RowLayout {
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents3.Label {
                    text: "W"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.75
                    font.weight: Font.Bold
                    opacity: 0.45
                    Layout.alignment: Qt.AlignVCenter
                }

                Kirigami.Icon {
                    source: "chronometer"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    opacity: 0.5
                    Layout.alignment: Qt.AlignVCenter
                }

                PlasmaComponents3.Label {
                    text: root.hasData ? root.formatCountdown(root.weeklyCountdownLive) : "--"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.0
                    font.weight: Font.Bold
                    color: {
                        var h = Math.floor(root.weeklyCountdownLive / 3600);
                        if (h < 24)  return root.redAlert;
                        if (h < 72)  return root.claudeAmberLight;
                        return Kirigami.Theme.textColor;
                    }
                    Layout.alignment: Qt.AlignVCenter
                }
            }
        }
    }

    // ─── Popup (Full) ───
    // ─── Harness page ───
    //
    // Tollens' own thesis is INSTALLED != ENFORCED != ACTIVATED. Three states,
    // not one light: a policy can be deployed and not enforced, and enforced
    // while the installed tree has drifted from the manifest it enforces.
    Component {
        id: harnessPage

        ColumnLayout {
            spacing: Kirigami.Units.mediumSpacing

            readonly property var t: root.tollens
            readonly property var conf: t.conformance ?? ({})
            readonly property var uc: conf.userCounts ?? ({})
            readonly property var mc: conf.managedCounts ?? ({})
            readonly property bool conformant: (conf.state ?? "") === "conformant"

            // ── The three states, as a ladder ──
            // Each depends on the one above it, so they read top to bottom and
            // the first amber tells you where the chain breaks.
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: stateCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: stateCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: Kirigami.Units.smallSpacing

                    PlasmaComponents3.Label {
                        text: root.tr("harness")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                        font.weight: Font.DemiBold; opacity: 0.45
                    }

                    Repeater {
                        model: [
                            { key: "installed", ok: true,
                              note: (t.inventory?.total ?? 0) + " " + root.tr("componentsInManifest") },
                            { key: "enforced", ok: t.enforced === true,
                              note: t.enforced === true ? root.tr("policyWins") : root.tr("notEnforced") },
                            { key: "conformant", ok: conformant,
                              note: conf.state ? root.tr(conf.state === "conformant" ? "matchesManifest"
                                                       : conf.state === "user-drift" ? "userDrift"
                                                       : conf.state === "managed-missing" ? "managedMissing"
                                                       : conf.state === "managed-writable" ? "managedWritable"
                                                       : conf.state === "managed-drift" ? "managedDrift"
                                                       : "notCheckedYet")
                                                : root.tr("notCheckedYet") }
                        ]
                        delegate: ColumnLayout {
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            spacing: 1

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Kirigami.Units.smallSpacing

                                // Connector: the states are a chain, not a list.
                                Item {
                                    Layout.preferredWidth: 10
                                    Layout.preferredHeight: 18
                                    Rectangle {
                                        visible: index > 0
                                        x: 4.5; y: -3; width: 1; height: 9
                                        color: Kirigami.Theme.textColor; opacity: 0.18
                                    }
                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: 10; height: 10; radius: 5
                                        color: modelData.ok ? root.greenAccent : root.claudeAmberLight
                                        Rectangle {
                                            anchors.centerIn: parent
                                            width: 4; height: 4; radius: 2
                                            color: root.cardBg
                                            visible: !modelData.ok
                                        }
                                    }
                                }
                                PlasmaComponents3.Label {
                                    text: root.tr(modelData.key)
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.95
                                    font.weight: modelData.ok ? Font.Normal : Font.DemiBold
                                    color: modelData.ok ? Kirigami.Theme.textColor : root.claudeAmberLight
                                }
                                Item { Layout.fillWidth: true }
                            }
                            PlasmaComponents3.Label {
                                Layout.fillWidth: true
                                Layout.leftMargin: 10 + Kirigami.Units.smallSpacing
                                Layout.bottomMargin: 3
                                text: modelData.note
                                wrapMode: Text.WordWrap
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.75
                                opacity: 0.42
                            }
                        }
                    }
                }
            }

            // ── Conformance, as counters rather than prose ──
            // verify.sh emits a Portuguese sentence; rendering it raw wrapped
            // badly and pinned the widget to one language.
            Rectangle {
                Layout.fillWidth: true
                visible: (conf.available ?? false) === true && (uc.total ?? 0) > 0
                implicitHeight: confCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg
                // The ladder above already names the failing state, so this
                // border only needs to tie the two together, not shout.
                border.width: 1
                border.color: conformant ? "transparent"
                            : Qt.rgba(root.claudeAmberLight.r, root.claudeAmberLight.g,
                                      root.claudeAmberLight.b, 0.22)

                ColumnLayout {
                    id: confCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: Kirigami.Units.smallSpacing

                    RowLayout {
                        Layout.fillWidth: true
                        PlasmaComponents3.Label {
                            text: root.tr("conformance")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                            font.weight: Font.DemiBold; opacity: 0.45
                        }
                        Rectangle {
                            radius: height / 2
                            color: Qt.rgba(root.greenAccent.r, root.greenAccent.g, root.greenAccent.b, 0.14)
                            implicitWidth: liveLbl.implicitWidth + 10
                            implicitHeight: liveLbl.implicitHeight + 3
                            PlasmaComponents3.Label {
                                id: liveLbl; anchors.centerIn: parent
                                text: root.tr("live")
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.66
                                color: root.greenAccent
                            }
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            text: (conf.tookSeconds ?? 0).toFixed(2) + "s"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.7
                            font.features: ({ "tnum": 1 })
                            opacity: 0.28
                        }
                    }

                    // User scope: a proportion, so it reads at a glance.
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        RowLayout {
                            Layout.fillWidth: true
                            PlasmaComponents3.Label {
                                text: root.tr("userScope")
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.78
                                opacity: 0.6
                            }
                            Item { Layout.fillWidth: true }
                            PlasmaComponents3.Label {
                                text: (uc.ok ?? 0) + "/" + (uc.total ?? 0)
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.95
                                font.weight: Font.Bold
                                font.features: ({ "tnum": 1 })
                                color: (uc.ok ?? 0) === (uc.total ?? 0) ? root.greenAccent : root.claudeAmberLight
                            }
                        }
                        Rectangle {
                            Layout.fillWidth: true; height: 6; radius: 3
                            color: root.subtleBorder
                            Rectangle {
                                width: parent.width * ((uc.total ?? 0) > 0 ? (uc.ok ?? 0) / uc.total : 0)
                                height: parent.height; radius: 3
                                color: (uc.ok ?? 0) === (uc.total ?? 0) ? root.greenAccent : root.claudeAmberLight
                                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                            }
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            Repeater {
                                model: [
                                    { k: "divergent", v: uc.divergent ?? 0 },
                                    { k: "missing",   v: uc.missing ?? 0 },
                                    { k: "orphans",   v: uc.orphans ?? 0 }
                                ]
                                delegate: PlasmaComponents3.Label {
                                    required property var modelData
                                    text: modelData.v + " " + root.tr(modelData.k)
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.73
                                    font.features: ({ "tnum": 1 })
                                    color: modelData.v > 0 ? root.claudeAmberLight : Kirigami.Theme.textColor
                                    opacity: modelData.v > 0 ? 0.9 : 0.32
                                }
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: root.subtleBorder; opacity: 0.6 }

                    RowLayout {
                        Layout.fillWidth: true
                        visible: (mc.components ?? 0) > 0
                        PlasmaComponents3.Label {
                            text: root.tr("managedScope")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.78
                            opacity: 0.6
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            property int bad: (mc.divergent ?? 0) + (mc.wrongOwner ?? 0) + (mc.writable ?? 0)
                            text: bad === 0 ? (mc.components ?? 0) + " " + root.tr("components")
                                            : bad + " " + root.tr("divergent")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85
                            font.weight: Font.Bold
                            font.features: ({ "tnum": 1 })
                            color: bad === 0 ? root.greenAccent : root.claudeAmberLight
                        }
                    }
                }
            }

            // ── What diverged ──
            // "10 divergent" is a count; the ten names are a to-do list.
            Rectangle {
                Layout.fillWidth: true
                visible: (conf.details ?? []).length > 0
                implicitHeight: divCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: divCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 3

                    PlasmaComponents3.Label {
                        text: root.tr("divergentComponents")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                        font.weight: Font.DemiBold; opacity: 0.45
                    }

                    Repeater {
                        model: conf.details ?? []
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            Rectangle {
                                width: 6; height: 6; radius: 3
                                Layout.alignment: Qt.AlignVCenter
                                color: modelData.kind === "orphan" ? root.claudeAmberLight
                                     : modelData.kind === "missing" ? root.redAlert
                                     : root.calmFill
                            }
                            PlasmaComponents3.Label {
                                Layout.fillWidth: true
                                text: modelData.name
                                elide: Text.ElideMiddle
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.74
                                opacity: 0.75
                            }
                            PlasmaComponents3.Label {
                                text: modelData.kind
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.68
                                opacity: 0.35
                            }
                        }
                    }
                }
            }

            // ── Conformance trend ──
            // Tollens' heartbeat only records session starts, so the series is
            // ours: one sample per hour, collapsed to the worst reading of each
            // day, because a day that was ever broken was a broken day.
            Rectangle {
                Layout.fillWidth: true
                visible: (t.trend ?? []).length > 0
                implicitHeight: trendCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: trendCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 5

                    PlasmaComponents3.Label {
                        text: root.tr("conformanceTrend")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                        font.weight: Font.DemiBold; opacity: 0.45
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Repeater {
                            model: t.trend ?? []
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 2

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 22
                                    radius: 3
                                    // No sample is a different state from a bad
                                    // sample, and reads as such: hollow, not red.
                                    color: root.subtleBorder

                                    Rectangle {
                                        visible: modelData.share !== null
                                        anchors.bottom: parent.bottom
                                        width: parent.width
                                        height: Math.max(3, parent.height * (modelData.share ?? 0))
                                        radius: 3
                                        color: modelData.ok ? root.greenAccent : root.claudeAmberLight
                                    }
                                }
                                PlasmaComponents3.Label {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: (modelData.date ?? "").slice(8)
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.62
                                    font.features: ({ "tnum": 1 })
                                    opacity: 0.3
                                }
                            }
                        }
                    }
                }
            }

            // ── Hook map ──
            Rectangle {
                Layout.fillWidth: true
                visible: (t.hooks?.total ?? 0) > 0
                implicitHeight: hookCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: hookCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true
                        PlasmaComponents3.Label {
                            text: root.tr("hooks")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                            font.weight: Font.DemiBold; opacity: 0.45
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            text: (t.hooks?.total ?? 0) + " " + root.tr("acrossEvents") + " " +
                                  Object.keys(t.hooks?.byEvent ?? ({})).length + " " + root.tr("events")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.73
                            font.features: ({ "tnum": 1 })
                            opacity: 0.4
                        }
                    }

                    Repeater {
                        model: {
                            var by = t.hooks?.byEvent ?? ({});
                            var rows = [], peak = 1;
                            for (var k in by) { rows.push({ event: k, count: by[k] }); peak = Math.max(peak, by[k]); }
                            rows.sort(function (a, b) { return b.count - a.count || a.event.localeCompare(b.event); });
                            for (var i = 0; i < rows.length; i++) rows[i].share = rows[i].count / peak;
                            return rows;
                        }
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            PlasmaComponents3.Label {
                                // Fixed column so the bars share a baseline
                                // instead of starting wherever the name ends.
                                Layout.preferredWidth: Kirigami.Units.gridUnit * 7
                                text: modelData.event
                                elide: Text.ElideRight
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.75
                                opacity: 0.65
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignVCenter
                                height: 5; radius: 2.5
                                color: root.subtleBorder
                                Rectangle {
                                    width: parent.width * modelData.share
                                    height: parent.height; radius: 2.5
                                    color: root.calmFill
                                    Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                                }
                            }
                            PlasmaComponents3.Label {
                                Layout.preferredWidth: Kirigami.Units.gridUnit
                                horizontalAlignment: Text.AlignRight
                                text: modelData.count
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.75
                                font.features: ({ "tnum": 1 })
                                font.weight: Font.Bold
                                opacity: 0.55
                            }
                        }
                    }
                }
            }

            // ── Inventory ──
            Flow {
                Layout.fillWidth: true
                visible: (t.inventory?.total ?? 0) > 0
                spacing: Kirigami.Units.smallSpacing

                Repeater {
                    model: {
                        var by = t.inventory?.byType ?? ({});
                        var rows = [];
                        for (var k in by) rows.push({ kind: k, count: by[k] });
                        rows.sort(function (a, b) { return b.count - a.count || a.kind.localeCompare(b.kind); });
                        return rows;
                    }
                    delegate: Rectangle {
                        required property var modelData
                        radius: height / 2
                        color: root.subtleBorder
                        implicitWidth: invRow.implicitWidth + 14
                        implicitHeight: invRow.implicitHeight + 6
                        RowLayout {
                            id: invRow
                            anchors.centerIn: parent
                            spacing: 5
                            PlasmaComponents3.Label {
                                text: modelData.count
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                                font.weight: Font.Bold
                                font.features: ({ "tnum": 1 })
                            }
                            PlasmaComponents3.Label {
                                text: modelData.kind
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.76
                                opacity: 0.55
                            }
                        }
                    }
                }
            }

            // ── Activation: which layer actually supplied the instructions ──
            //
            // Tollens' three states are INSTALLED, ENFORCED and ACTIVATED, and
            // the third is the one its own README calls hard to establish.
            // This is the closest thing it records to evidence for it: a count
            // of where loaded instructions came from in the precedence chain.
            Rectangle {
                Layout.fillWidth: true
                visible: Object.keys(t.usage?.memoryScope ?? ({})).length > 0
                implicitHeight: actCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: actCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 5

                    readonly property var scopes: {
                        var m = t.usage?.memoryScope ?? ({});
                        var order = ["Managed", "Project", "User"];
                        var rows = [], total = 0;
                        for (var k in m) total += m[k];
                        for (var i = 0; i < order.length; i++) {
                            if (m[order[i]] === undefined) continue;
                            rows.push({ name: order[i], count: m[order[i]],
                                        share: total ? m[order[i]] / total : 0 });
                        }
                        return rows;
                    }

                    PlasmaComponents3.Label {
                        text: root.tr("activation")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                        font.weight: Font.DemiBold; opacity: 0.45
                    }

                    // One stacked bar: the split is the point, not the values.
                    Row {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 8
                        spacing: 2
                        Repeater {
                            model: actCol.scopes
                            delegate: Rectangle {
                                required property var modelData
                                required property int index
                                width: (actCol.width - 4) * modelData.share
                                height: 8
                                radius: 4
                                color: index === 0 ? root.greenAccent
                                     : index === 1 ? root.calmFill : root.subtleBorder
                                Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                            }
                        }
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        Repeater {
                            model: actCol.scopes
                            delegate: RowLayout {
                                required property var modelData
                                required property int index
                                spacing: 4
                                Rectangle {
                                    width: 7; height: 7; radius: 3.5
                                    Layout.alignment: Qt.AlignVCenter
                                    color: index === 0 ? root.greenAccent
                                         : index === 1 ? root.calmFill : root.subtleBorder
                                }
                                PlasmaComponents3.Label {
                                    text: modelData.name + " " + Math.round(modelData.share * 100) + "%"
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.73
                                    font.features: ({ "tnum": 1 })
                                    opacity: 0.6
                                }
                            }
                        }
                    }

                    PlasmaComponents3.Label {
                        Layout.fillWidth: true
                        text: root.tr("activationNote")
                        wrapMode: Text.WordWrap
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.7
                        opacity: 0.32
                    }
                }
            }

            // ── Activity: what actually gets invoked ──
            Rectangle {
                Layout.fillWidth: true
                visible: (t.usage?.records ?? 0) > 0
                implicitHeight: useCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: useCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: Kirigami.Units.smallSpacing

                    RowLayout {
                        Layout.fillWidth: true
                        PlasmaComponents3.Label {
                            text: root.tr("activity")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                            font.weight: Font.DemiBold; opacity: 0.45
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            text: (t.usage?.records ?? 0) + " " + root.tr("invocations") +
                                  " · " + (t.usage?.sessions ?? 0) + " " + root.tr("distinctSessions")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.72
                            font.features: ({ "tnum": 1 })
                            opacity: 0.4
                        }
                    }

                    // Agents, skills and tools share one delegate: same shape,
                    // different source, so they stay visually comparable.
                    Repeater {
                        model: [
                            { key: "agents", rows: t.usage?.agents ?? [] },
                            { key: "skills", rows: t.usage?.skills ?? [] },
                            { key: "tools",  rows: t.usage?.tools ?? [] }
                        ]
                        delegate: ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            visible: modelData.rows.length > 0
                            spacing: 2

                            PlasmaComponents3.Label {
                                Layout.topMargin: 3
                                text: root.tr(modelData.key)
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.72
                                opacity: 0.38
                            }
                            Repeater {
                                model: modelData.rows
                                delegate: RowLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: Kirigami.Units.smallSpacing

                                    PlasmaComponents3.Label {
                                        Layout.preferredWidth: Kirigami.Units.gridUnit * 7
                                        text: modelData.name
                                        elide: Text.ElideRight
                                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.75
                                        opacity: 0.7
                                    }
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.alignment: Qt.AlignVCenter
                                        height: 5; radius: 2.5
                                        color: root.subtleBorder
                                        Rectangle {
                                            width: parent.width * modelData.share
                                            height: parent.height; radius: 2.5
                                            color: root.calmFill
                                            Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                                        }
                                    }
                                    PlasmaComponents3.Label {
                                        Layout.preferredWidth: Kirigami.Units.gridUnit * 2.4
                                        horizontalAlignment: Text.AlignRight
                                        text: Math.round(modelData.share * 100) + "%"
                                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.73
                                        font.features: ({ "tnum": 1 })
                                        font.weight: Font.Bold
                                        opacity: 0.55
                                    }
                                }
                            }
                        }
                    }

                    PlasmaComponents3.Label {
                        Layout.fillWidth: true
                        Layout.topMargin: 2
                        text: root.tr("runningTotals")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.68
                        opacity: 0.28
                    }
                }
            }

            // ── Verify gate ──
            Rectangle {
                Layout.fillWidth: true
                visible: (t.gate?.total ?? 0) > 0
                implicitHeight: gateRow.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: gateRow
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true
                        PlasmaComponents3.Label {
                            text: root.tr("verifyGate")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                            font.weight: Font.DemiBold; opacity: 0.45
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            property real rate: t.gate?.passRate ?? 0
                            text: Math.round(rate * 100) + "% " + root.tr("passRate")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85
                            font.weight: Font.Bold
                            font.features: ({ "tnum": 1 })
                            color: rate >= 0.7 ? root.greenAccent
                                 : rate >= 0.4 ? Kirigami.Theme.textColor : root.claudeAmberLight
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true; height: 6; radius: 3
                        color: root.subtleBorder
                        Rectangle {
                            width: parent.width * (t.gate?.passRate ?? 0)
                            height: parent.height; radius: 3
                            color: (t.gate?.passRate ?? 0) >= 0.7 ? root.greenAccent : root.calmFill
                            Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                        }
                    }
                    PlasmaComponents3.Label {
                        text: {
                            var by = t.gate?.byVerdict ?? ({});
                            var parts = [];
                            for (var k in by) parts.push(by[k] + " " + k);
                            return parts.join(" · ") + "  (" + (t.gate?.total ?? 0) + ")";
                        }
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.7
                        font.features: ({ "tnum": 1 })
                        opacity: 0.35
                    }
                }
            }

            // ── History, explicitly dated and explicitly labelled ──
            // The heartbeat is written once per session start. Measured two
            // hours stale with a verdict inverted against a live run, so it
            // carries its own timestamp and a "history" tag, never presented
            // as current state.
            RowLayout {
                Layout.fillWidth: true
                visible: (t.heartbeat?.at ?? "") !== ""
                spacing: Kirigami.Units.smallSpacing

                Rectangle {
                    radius: height / 2
                    color: root.subtleBorder
                    implicitWidth: histLbl.implicitWidth + 10
                    implicitHeight: histLbl.implicitHeight + 3
                    PlasmaComponents3.Label {
                        id: histLbl; anchors.centerIn: parent
                        text: root.tr("history")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.66
                        opacity: 0.5
                    }
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    text: root.tr("lastSessionStart") + ": " + (t.heartbeat?.result ?? "?") +
                          " · " + root.relativeAge(t.heartbeat?.at ?? "")
                    elide: Text.ElideRight
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.7
                    opacity: 0.4

                    PlasmaComponents3.ToolTip { text: t.heartbeat?.at ?? "" }
                }
            }

            // Stated rather than drawn as an empty chart: Tollens records no
            // hook timings anywhere.
            PlasmaComponents3.Label {
                Layout.fillWidth: true
                Layout.bottomMargin: Kirigami.Units.smallSpacing
                text: root.tr("hookTimings") + ": " + root.tr("notMeasured")
                wrapMode: Text.WordWrap
                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.7
                opacity: 0.28
            }
        }
    }

    fullRepresentation: PlasmaExtras.Representation {
        // Widened by one unit when the header gained the focus control. The
        // shrinking title above is what makes the overflow impossible; this is
        // what keeps the title from having to elide on the common case.
        Layout.preferredWidth: Kirigami.Units.gridUnit * 25
        Layout.preferredHeight: Kirigami.Units.gridUnit * 40
        // Raised because the old value was a minimum the popup could not
        // actually draw. Rendering the header at the declared minimum put the
        // level badge and the Live/Offline word on top of the tool buttons —
        // not clipped, so it never looked like the overflow it is. Declaring a
        // width you cannot honour is the same defect as overflowing one; this
        // is the width the header measured as needing, plus a unit.
        Layout.minimumWidth: Kirigami.Units.gridUnit * 21
        Layout.maximumHeight: Kirigami.Units.gridUnit * 44

        header: PlasmaExtras.PlasmoidHeading { visible: false }

        Flickable {
            id: popupFlick
            anchors.fill: parent
            contentWidth: width
            contentHeight: mainCol.implicitHeight + Kirigami.Units.largeSpacing * 2
            clip: true

            ColumnLayout {
                id: mainCol
                x: Kirigami.Units.largeSpacing
                y: Kirigami.Units.largeSpacing
                width: popupFlick.width - Kirigami.Units.largeSpacing * 2
                spacing: Kirigami.Units.mediumSpacing

            // ══════════════════════════════════
            // ── Header with mascot ──
            // ══════════════════════════════════
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.mediumSpacing

                // Clawd mascot — 5 animated states + easter egg.
                // The sprites visualise the dumbness score, so a provider that
                // ships neither mascot art nor a score collapses the column.
                Item {
                    visible: root.brand.mascot !== ""
                    Layout.preferredWidth: Kirigami.Units.iconSizes.huge
                    Layout.preferredHeight: Kirigami.Units.iconSizes.huge

                    // Easter egg: tap Clawd 5x fast to cycle states
                    property int tapCount: 0
                    property var eggStates: ["genius", "smart", "slow", "dumb", "braindead", "live"]
                    property int eggIndex: 0
                    property bool eggActive: false

                    Timer {
                        id: tapReset; interval: 1500; onTriggered: parent.tapCount = 0
                    }
                    Timer {
                        id: eggTimeout; interval: 30000
                        onTriggered: { parent.eggActive = false; parent.eggIndex = 0; eggLabel.visible = false }
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            parent.tapCount++
                            tapReset.restart()
                            if (parent.tapCount >= 5) {
                                parent.tapCount = 0
                                parent.eggIndex = (parent.eggIndex + 1) % parent.eggStates.length
                                var state = parent.eggStates[parent.eggIndex]
                                if (state === "live") {
                                    parent.eggActive = false
                                    eggLabel.text = "🔴 Live"
                                } else {
                                    parent.eggActive = true
                                    root.dumbLevel = state
                                    root.dumbScore = state === "genius" ? 5 : state === "smart" ? 15 : state === "slow" ? 35 : state === "dumb" ? 60 : 85
                                    eggLabel.text = "🥚 " + state.charAt(0).toUpperCase() + state.slice(1)
                                }
                                eggLabel.visible = true; eggHide.restart()
                                eggTimeout.restart()
                            }
                        }
                    }
                    PlasmaComponents3.Label {
                        id: eggLabel; visible: false
                        anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottomMargin: -2
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.6
                        opacity: 0.7
                    }
                    Timer { id: eggHide; interval: 1500; onTriggered: eggLabel.visible = false }

                    // The buddy — hidden when braindead (ghost replaces him).
                    //
                    // It breathes all the time, and gets agitated when a quota
                    // enters the alert zone. The motion is the widget's one
                    // ambient animation, and it is tied to state rather than
                    // decorative: a still buddy means nothing is close to a
                    // limit, so glancing at it is already an answer.
                    Image {
                        id: mascotImage
                        visible: !root.isBraindead && root.quotasInAlert < 2
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: 6
                        width: parent.width * 0.7
                        height: parent.height * 0.7
                        source: Qt.resolvedUrl("../icons/" + root.brand.mascot)
                        sourceSize: Qt.size(parent.width, parent.height)
                        fillMode: Image.PreserveAspectFit

                        property bool agitated: root.worstZone === "alert"

                        transform: Translate {
                            id: mascotShift
                            y: mascotImage.bob
                            x: mascotImage.jitter
                        }
                        property real bob: 0
                        property real jitter: 0

                        SequentialAnimation on bob {
                            running: mascotImage.visible
                            loops: Animation.Infinite
                            NumberAnimation { to: -2.0; duration: mascotImage.agitated ? 260 : 1300
                                              easing.type: Easing.InOutSine }
                            NumberAnimation { to: 0;    duration: mascotImage.agitated ? 260 : 1300
                                              easing.type: Easing.InOutSine }
                        }
                        SequentialAnimation on jitter {
                            running: mascotImage.visible && mascotImage.agitated
                            loops: Animation.Infinite
                            NumberAnimation { to: -1.2; duration: 90 }
                            NumberAnimation { to:  1.2; duration: 90 }
                            NumberAnimation { to:  0;   duration: 90 }
                            PauseAnimation  { duration: 620 }
                        }
                        onAgitatedChanged: if (!agitated) jitter = 0
                    }
                    // Two or more quotas red at once. The asset shipped with the
                    // repo and was never wired to anything; this is the one
                    // state it was drawn for.
                    Image {
                        id: fineDog
                        visible: root.quotasInAlert >= 2
                        anchors.fill: parent
                        source: Qt.resolvedUrl("../icons/this-is-fine.png")
                        sourceSize: Qt.size(parent.width * 2, parent.height * 2)
                        fillMode: Image.PreserveAspectFit
                        opacity: 0

                        states: State {
                            when: fineDog.visible
                            PropertyChanges { target: fineDog; opacity: 1 }
                        }
                        transitions: Transition {
                            NumberAnimation { property: "opacity"; duration: 700
                                              easing.type: Easing.OutCubic }
                        }

                        PlasmaComponents3.ToolTip {
                            text: root.quotasInAlert + " quotas in the red at once"
                        }
                    }

                    // No speech bubble here. It was anchored to the buddy and
                    // overlapped the title and badge beside it — the header is
                    // 24 gridUnits wide and the bubble needs 13 of them. The
                    // talking belongs to the desktop companion, which has room.

                    // === ALL OVERLAYS ON TOP OF CLAWD ===
                    // DUMB: Fire
                    Image {
                        id: fireSprite; visible: root.isDumb
                        anchors.fill: parent; property int frame: 0
                        source: Qt.resolvedUrl("../icons/fire-" + frame + ".png")
                        sourceSize: Qt.size(parent.width, parent.height)
                        fillMode: Image.PreserveAspectFit; smooth: false
                        Timer { running: root.isDumb; interval: 120; repeat: true
                            onTriggered: fireSprite.frame = (fireSprite.frame + 1) % 6 }
                    }
                    // GENIUS: Crown sparkles
                    Image {
                        id: haloSprite; visible: root.isGenius
                        anchors.fill: parent; property int frame: 0
                        source: Qt.resolvedUrl("../icons/halo-" + frame + ".png")
                        sourceSize: Qt.size(parent.width, parent.height)
                        fillMode: Image.PreserveAspectFit; smooth: false
                        Timer { running: root.isGenius; interval: 250; repeat: true
                            onTriggered: haloSprite.frame = (haloSprite.frame + 1) % 6 }
                    }
                    // SLOW: Rain cloud full size over smaller Clawd
                    Image {
                        id: rainSprite; visible: root.isSlow
                        anchors.fill: parent; property int frame: 0
                        source: Qt.resolvedUrl("../icons/rain-" + frame + ".png")
                        sourceSize: Qt.size(parent.width, parent.height)
                        fillMode: Image.PreserveAspectFit; smooth: false
                        Timer { running: root.isSlow; interval: 100; repeat: true
                            onTriggered: rainSprite.frame = (rainSprite.frame + 1) % 6 }
                    }
                    // BRAINDEAD: Skull + smoke full size over smaller Clawd
                    Image {
                        id: skullSprite; visible: root.isBraindead
                        anchors.fill: parent; property int frame: 0
                        source: Qt.resolvedUrl("../icons/skull-" + frame + ".png")
                        sourceSize: Qt.size(parent.width, parent.height)
                        fillMode: Image.PreserveAspectFit; smooth: false
                        Timer { running: root.isBraindead; interval: 200; repeat: true
                            onTriggered: skullSprite.frame = (skullSprite.frame + 1) % 6 }
                    }
                    // SMART: Book + coffee overlay
                    Image {
                        id: smartSprite; visible: root.isSmart
                        anchors.fill: parent; property int frame: 0
                        source: Qt.resolvedUrl("../icons/smart-" + frame + ".png")
                        sourceSize: Qt.size(parent.width, parent.height)
                        fillMode: Image.PreserveAspectFit; smooth: false
                        Timer { running: root.isSmart; interval: 300; repeat: true
                            onTriggered: smartSprite.frame = (smartSprite.frame + 1) % 6 }
                    }
                    // GENIUS: Sun corner (removed sunglasses)
                    Image {
                        id: sunCorner; visible: false  // disabled — crown is enough
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.topMargin: -4
                        anchors.rightMargin: -4
                        width: parent.width * 0.45
                        height: parent.height * 0.45
                        property int frame: 0
                        source: Qt.resolvedUrl("../icons/sun-" + frame + ".png")
                        sourceSize: Qt.size(width, height)
                        fillMode: Image.PreserveAspectFit
                        smooth: false
                        Timer {
                            running: root.isGenius
                            interval: 200; repeat: true
                            onTriggered: sunCorner.frame = (sunCorner.frame + 1) % 6
                        }
                    }
                }

                // Allowed to give ground, and it is the only thing in this row
                // that can. A RowLayout never shrinks below the sum of its
                // children's minimum widths, so a block with no minimum of its
                // own sets the row's — and the row then overflows the column,
                // which the Flickable clips because it holds contentWidth at
                // its own width and does not scroll sideways. The symptom is
                // every row in the popup cut off at the same x, which reads as
                // the whole widget being broken rather than as one header that
                // no longer fits. It appeared the moment a sixth button joined
                // the row; the title yielding is what keeps the seventh from
                // doing it again.
                ColumnLayout {
                    spacing: 1
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        // The brand name is gone rather than elided. Letting it
                        // shrink is what stopped it cutting the popup off, but
                        // at the width the popup actually opens at there is not
                        // enough room for it, so what it bought was "Cla..." —
                        // three characters and an ellipsis where a word used to
                        // be, which is worse than the word being absent. The
                        // mascot beside it and the provider logo on the line
                        // below already say which one this is, and the width it
                        // was holding is what the header was short of.
                        Rectangle {
                            visible: root.hasData && root.usageData.dumbness !== undefined
                            radius: height / 2
                            color: {
                                var c = statusColor(root.usageData.serviceStatus?.indicator ?? "none");
                                return Qt.rgba(c.r, c.g, c.b, 0.18);
                            }
                            implicitWidth: _stateLbl.implicitWidth + 10
                            implicitHeight: _stateLbl.implicitHeight + 4
                            PlasmaComponents3.Label {
                                id: _stateLbl; anchors.centerIn: parent
                                text: {
                                    var l = root.dumbLevel;
                                    if (l === "genius") return "Genius";
                                    if (l === "slow") return "Slow";
                                    if (l === "dumb") return "Dumb";
                                    if (l === "braindead") return "Braindead";
                                    return "Smart";
                                }
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.0
                                font.weight: Font.Bold
                                color: {
                                    var l = root.dumbLevel;
                                    if (l === "genius") return "#FFD700";
                                    if (l === "slow") return root.claudeAmberLight;
                                    if (l === "dumb") return "#F97316";
                                    if (l === "braindead") return root.redAlert;
                                    return root.greenAccent;
                                }
                            }
                        }
                    }
                    // The other half of the same lesson. Giving the title label a
                    // zero minimum stopped the row cutting the whole popup off at
                    // the preferred width, and left this row still pinning the
                    // column at about 108 px — so dragged down to the width the
                    // popup itself declares as its minimum, this text is drawn
                    // over the tool buttons. Nothing is clipped, so it does not
                    // look like the first defect; it looks like the plan name
                    // printed on top of a button. Found by rendering the QML at
                    // the declared minimum, not by reading it.
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        spacing: Kirigami.Units.smallSpacing
                        // Provider logo small
                        Image {
                            source: Qt.resolvedUrl("../icons/" + root.brand.logo)
                            Layout.preferredWidth: 12
                            Layout.preferredHeight: 12
                            sourceSize: Qt.size(12, 12)
                            fillMode: Image.PreserveAspectFit
                        }
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            elide: Text.ElideRight
                            text: root.usageData.rateLimits?.plan ?? "Max (20x)"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                            color: root.claudeAmber
                            opacity: 0.8
                        }
                        Rectangle {
                            width: 4; height: 4; radius: 2
                            color: Kirigami.Theme.textColor; opacity: 0.2
                        }
                        PlasmaComponents3.Label {
                            Layout.minimumWidth: 0
                            elide: Text.ElideRight
                            text: {
                                var src = root.usageData.rateLimits?.source ?? "";
                                return src === "api" ? "Live" : "Offline";
                            }
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.825
                            color: root.usageData.rateLimits?.source === "api" ? root.greenAccent : Kirigami.Theme.textColor
                            opacity: 0.6
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                // Buddy chatter: off / alerts / chatty. Three states because
                // "alerts" — speak only when a session needs the human — is
                // the one worth leaving on, and it does not exist as a
                // checkbox.
                PlasmaComponents3.ToolButton {
                    id: buddyBtn
                    readonly property var modes: ["off", "alerts", "chatty"]
                    readonly property var icons: ({
                        "off":    "dialog-messages",
                        "alerts": "dialog-warning",
                        "chatty": "dialog-information"
                    })
                    icon.name: icons[root.buddyMode] ?? "dialog-messages"
                    opacity: root.buddyMode === "off" ? 0.4 : 1.0
                    onClicked: {
                        var i = modes.indexOf(root.buddyMode);
                        Plasmoid.configuration.buddyMode = modes[(i + 1) % modes.length];
                    }
                    PlasmaComponents3.ToolTip {
                        text: root.tr("buddy") + ": " + root.tr("buddy_" + root.buddyMode) +
                              "\n" + root.tr("clickToCycle")
                    }
                }

                // Focus session, started from the widget because the
                // companion has no window to click on. It is a separate
                // process, so this writes a command file it watches rather
                // than restarting it.
                //
                // Hidden with the companion switched off: the button would
                // write a command for a process that is not running, which is
                // a control that looks live and does nothing.
                PlasmaComponents3.ToolButton {
                    id: focusBtn
                    visible: root.buddyMode !== "off"
                    icon.name: root.focusRequested ? "process-stop" : "chronometer"
                    onClicked: root.toggleFocusSession()
                    PlasmaComponents3.ToolTip {
                        text: root.tr("focusSession") + ": " +
                              (root.focusRequested
                               ? root.tr("focusStop")
                               : root.tr("focusStart") + " " + root.buddyFocusMinutes + " min")
                    }
                }

                // Language, in the header rather than buried in the config
                // dialog. Two languages is a toggle, not a setting: making
                // someone open Configure to read the widget in their own
                // language is a worse trade than one small button.
                //
                // Clicking pins an explicit choice, so it stops following the
                // desktop locale; long-press returns to "auto".
                PlasmaComponents3.ToolButton {
                    id: langBtn
                    implicitWidth: Kirigami.Units.gridUnit * 1.9
                    onClicked: Plasmoid.configuration.language = root.lang === "pt" ? "en" : "pt"

                    contentItem: PlasmaComponents3.Label {
                        text: root.lang.toUpperCase()
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.72
                        font.weight: Font.Bold
                        // Dimmed while following the locale, solid once pinned,
                        // so the button also reports which of the two it is.
                        opacity: root.langSetting === "auto" ? 0.45 : 0.85
                    }

                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.NoButton
                        onPressAndHold: Plasmoid.configuration.language = "auto"
                    }

                    PlasmaComponents3.ToolTip {
                        text: root.tr("switchTo") + " " +
                              (root.lang === "pt" ? "English" : "Português") +
                              (root.langSetting === "auto"
                               ? "\n" + root.tr("followingLocale") : "")
                    }
                }

                // Only exists when Tollens does. A dead tab for an absent
                // integration is worse than no tab.
                PlasmaComponents3.ToolButton {
                    visible: root.hasTollens
                    icon.name: root.page === 0 ? "settings-configure" : "go-previous"
                    checked: root.page === 1
                    onClicked: root.page = root.page === 0 ? 1 : 0
                    PlasmaComponents3.ToolTip {
                        text: root.page === 0 ? root.tr("harness") + " (Tollens)"
                                              : root.tr("backToUsage")
                    }
                }

                PlasmaComponents3.ToolButton {
                    icon.name: "view-refresh"
                    // Force an immediate re-poll: disconnect then reconnect the
                    // source so the executable engine re-runs it right away.
                    onClicked: {
                        dataLoader.readData();
                    }
                    PlasmaComponents3.ToolTip { text: root.tr("refresh") }
                }

                // Display mode switcher — cycles through the panel modes
                PlasmaComponents3.ToolButton {
                    id: modeBtn
                    // "adaptive" is appended, never inserted: the order
                    // anyone has learned by clicking stays what it was, and
                    // the default in main.xml is still "full". Somebody who
                    // chose a mode chose it.
                    readonly property var modes: ["full", "weeklyBarOnly", "fableBarOnly", "sessionCountdown", "weeklyCountdown", "sparkline", "adaptive"]
                    readonly property var modeIcons: ({
                        "full":             "view-split-left-right",
                        "weeklyBarOnly":    "office-chart-bar",
                        "fableBarOnly":     "office-chart-bar-stacked",
                        "sessionCountdown": "chronometer",
                        "weeklyCountdown":  "view-calendar-week",
                        "sparkline":        "office-chart-bar",
                        "adaptive":         "view-filter"
                    })
                    readonly property var modeLabels: ({
                        "full":             "Full (default)",
                        "weeklyBarOnly":    "Weekly bar only",
                        "fableBarOnly":     "Fable bar only",
                        "sessionCountdown": "Session countdown",
                        "weeklyCountdown":  "Weekly countdown",
                        "sparkline":        "7-day sparkline",
                        "adaptive":         root.tr("panelAdaptive")
                    })
                    icon.name: modeIcons[root.displayMode] ?? "configure"
                    onClicked: {
                        var idx = modes.indexOf(root.displayMode);
                        var next = modes[(idx + 1) % modes.length];
                        Plasmoid.configuration.displayMode = next;
                    }
                    PlasmaComponents3.ToolTip {
                        text: root.tr("panelMode") + ": " + (modeBtn.modeLabels[root.displayMode] ?? root.displayMode) + "\n" + root.tr("clickToCycle")
                    }
                }
            }

                // ══════════════════════════════════
                // ── Harness page (Tollens) ──
                // ══════════════════════════════════
                Loader {
                    Layout.fillWidth: true
                    active: root.hasTollens && root.page === 1
                    visible: active
                    sourceComponent: harnessPage
                }


                // Provider cards. Hidden rather than unloaded on page 1, so
                // returning to page 0 does not re-run every binding.
                ColumnLayout {
                    id: providerPage
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.mediumSpacing
                    visible: root.page === 0


            // ══════════════════════════════════
            // ── Session Limit (HERO CARD) ──
            // ══════════════════════════════════
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: sessionInner.implicitHeight + Kirigami.Units.largeSpacing * 2
                radius: 12
                color: root.cardBg
                id: sessionCard
                border.width: 2

                // Same zones as every other gauge — the border used its own
                // 50/80 thresholds, so the card could read amber while the ring
                // inside it read calm.
                property string zone: root.usageZone(
                    root.usageData.rateLimits?.session?.percentUsed ?? 0,
                    progressRing.pace)
                property real alertPulse: 1.0

                border.color: {
                    var c = root.zoneColor(zone);
                    var a = zone === "alert" ? 0.75 * alertPulse
                          : zone === "warn" ? 0.5 : 0.28;
                    return Qt.rgba(c.r, c.g, c.b, a);
                }

                // Pulses only in the alert zone. Something that pulses always
                // stops meaning anything; here it means act now.
                SequentialAnimation on alertPulse {
                    running: sessionCard.zone === "alert"
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.35; duration: 700; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1.0;  duration: 700; easing.type: Easing.InOutSine }
                }
                onZoneChanged: if (zone !== "alert") alertPulse = 1.0

                ColumnLayout {
                    id: sessionInner
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.largeSpacing
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        PlasmaComponents3.Label {
                            text: root.tr("currentSession")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            font.weight: Font.DemiBold
                            opacity: 0.7
                        }
                        Item { Layout.fillWidth: true }
                        // The countdown now lives inside the ring, so this slot
                        // carries the reading the ring's tick makes possible:
                        // spending faster or slower than the window refills.
                        PlasmaComponents3.Label {
                            property real pct: root.usageData.rateLimits?.session?.percentUsed ?? 0
                            property real pace: progressRing.pace
                            visible: pace >= 0
                            text: {
                                var d = pct - pace * 100;
                                if (d > root.paceTolerance) return root.tr("aheadOfPace");
                                if (d < -root.paceTolerance) return root.tr("underPace");
                                return root.tr("onPace");
                            }
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                            color: root.paceTextColor(pct, pace)
                            opacity: 0.75
                        }
                    }

                    // Circular progress ring + percentage
                    Item {
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 6
                        Layout.preferredHeight: Kirigami.Units.gridUnit * 6
                        Layout.alignment: Qt.AlignHCenter

                        Canvas {
                            id: progressRing
                            anchors.fill: parent
                            // `drawn` is what gets painted. It sweeps from 0 on
                            // first data so the ring draws itself in, then trails
                            // pct on every update.
                            property real pct: root.usageData.rateLimits?.session?.percentUsed ?? 0
                            property real drawn: 0
                            // progressRing., not bare sweptIn: an unqualified
                            // name inside a nested object resolves against that
                            // object and the file's root, never against the
                            // object that encloses it. Bare, this logged
                            // "ReferenceError: sweptIn is not defined" twice on
                            // every popup and silently used undefined — which is
                            // falsy, so the ring always animated as if it had
                            // already swept in.
                            Behavior on drawn {
                                NumberAnimation {
                                    duration: progressRing.sweptIn ? 800 : 1100
                                    easing.type: progressRing.sweptIn ? Easing.OutCubic
                                                                      : Easing.OutQuart
                                }
                            }
                            property bool sweptIn: false
                            onPctChanged: {
                                drawn = pct;
                                if (!sweptIn && pct > 0) sweepDone.restart();
                            }
                            Timer { id: sweepDone; interval: 1200; onTriggered: progressRing.sweptIn = true }
                            onDrawnChanged: requestPaint()
                            onWidthChanged: requestPaint()

                            property real pace: root.windowPace(
                                root.usageData.rateLimits?.session?.resetsAt ?? "",
                                root.usageData.rateLimits?.session?.windowHours ?? 5)
                            onPaceChanged: requestPaint()

                            onPaint: {
                                var ctx = getContext("2d");
                                ctx.clearRect(0, 0, width, height);
                                var cx = width / 2, cy = height / 2;
                                var lw = 10;
                                var r = Math.min(cx, cy) - lw;
                                var start = -Math.PI / 2;

                                // Track
                                ctx.beginPath();
                                ctx.arc(cx, cy, r, 0, 2 * Math.PI);
                                ctx.strokeStyle = root.subtleBorder.toString();
                                ctx.lineWidth = lw;
                                ctx.stroke();

                                // Alert zones on the empty track, same
                                // boundaries as the weekly bars, so the danger
                                // is legible before the arc arrives in it.
                                function zone(fromPct, toPct, colour) {
                                    ctx.beginPath();
                                    ctx.arc(cx, cy, r,
                                            start + 2 * Math.PI * (fromPct / 100),
                                            start + 2 * Math.PI * (toPct / 100));
                                    ctx.strokeStyle = colour;
                                    ctx.lineWidth = lw;
                                    ctx.globalAlpha = 0.20;
                                    ctx.stroke();
                                    ctx.globalAlpha = 1;
                                }
                                zone(root.warnAt, root.alertAt, root.claudeAmberLight.toString());
                                zone(root.alertAt, 100, root.redAlert.toString());

                                // Usage arc
                                ctx.beginPath();
                                ctx.arc(cx, cy, r, start,
                                        start + 2 * Math.PI * Math.min(1, drawn / 100));
                                ctx.strokeStyle = root.paceFill(drawn, pace).toString();
                                ctx.lineWidth = lw;
                                ctx.lineCap = "round";
                                ctx.stroke();

                                // Pace tick: where even burn would have reached by now.
                                // Arc short of it means the window is refilling faster
                                // than it is being spent.
                                if (pace >= 0 && pace < 1) {
                                    var a = start + 2 * Math.PI * pace;
                                    ctx.beginPath();
                                    ctx.arc(cx, cy, r, a - 0.012, a + 0.012);
                                    ctx.strokeStyle = Kirigami.Theme.textColor.toString();
                                    ctx.lineWidth = lw + 5;
                                    ctx.lineCap = "butt";
                                    ctx.globalAlpha = 0.35;
                                    ctx.stroke();
                                    ctx.globalAlpha = 1;
                                }
                            }
                        }

                        // Percentage and time-left together: on their own, "3%"
                        // and "4h49m" each answer half the question the widget
                        // is opened to answer.
                        ColumnLayout {
                            anchors.centerIn: parent
                            spacing: 0
                            // Bound to the chord available inside the arc, not
                            // to the ring's bounding box. The countdown sits
                            // below centre, where the circle is already
                            // narrowing, and a long value ran over the stroke.
                            readonly property real innerChord: {
                                var r = Math.min(parent.width, parent.height) / 2 - 15;
                                var dy = 12;
                                return 2 * Math.sqrt(Math.max(1, r * r - dy * dy));
                            }
                            width: innerChord

                            PlasmaComponents3.Label {
                                Layout.alignment: Qt.AlignHCenter
                                // `shown` trails `pct`, so the number rolls to
                                // its new value instead of jumping. The ring arc
                                // already animated; the figure at its centre
                                // snapping made the two disagree mid-flight.
                                property real pct: root.usageData.rateLimits?.session?.percentUsed ?? 0
                                property real shown: 0
                                property real pace: progressRing.pace
                                Behavior on shown { NumberAnimation { duration: 800; easing.type: Easing.OutCubic } }
                                onPctChanged: shown = pct
                                Component.onCompleted: shown = pct
                                text: Math.round(shown) + "%"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 2.4
                                font.weight: Font.Bold
                                font.features: ({ "tnum": 1 })
                                color: root.paceTextColor(shown, pace)
                            }
                            PlasmaComponents3.Label {
                                Layout.alignment: Qt.AlignHCenter
                                Layout.maximumWidth: parent.innerChord
                                elide: Text.ElideRight
                                horizontalAlignment: Text.AlignHCenter
                                // Seconds only near the end, where they matter.
                                // "47m 12s left" is both longer and less useful
                                // than "47m left" three quarters of an hour out.
                                text: {
                                    var m = root.countdownMinutes, sec = root.countdownSeconds;
                                    if (m >= 60) return Math.floor(m / 60) + "h " + (m % 60) + "m";
                                    if (m > 5) return m + "m";
                                    if (m > 0) return m + "m " + sec + "s";
                                    if (sec > 0) return sec + "s";
                                    return root.tr("rolling5h");
                                }
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.78
                                font.features: ({ "tnum": 1 })
                                opacity: 0.55
                            }
                        }
                    }

                    // Burn rate and projected limit, always on.
                    //
                    // The projection used to appear only under two hours, which
                    // is the point where knowing it stops being useful — by
                    // then the decision to slow down has already been made for
                    // you. It is quiet at a distance and warms as it closes in.
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 2
                        spacing: Kirigami.Units.smallSpacing
                        visible: root.hasData

                        PlasmaComponents3.Label {
                            text: root.formatTokens(root.usageData.burnRate?.total_per_hour ?? 0) + "/h"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                            font.features: ({ "tnum": 1 })
                            opacity: 0.5
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            property int eta: root.usageData.limitEta?.minutesToLimit ?? -1
                            visible: eta > 0
                            text: root.tr("limitIn") + " " + (root.usageData.limitEta?.label ?? "?")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                            font.weight: eta < 120 ? Font.DemiBold : Font.Normal
                            font.features: ({ "tnum": 1 })
                            color: eta < 30 ? root.redAlert
                                 : eta < 120 ? root.claudeAmberLight
                                 : Kirigami.Theme.textColor
                            opacity: eta < 120 ? 0.95 : 0.5
                        }
                    }
                }
            }

            // ══════════════════════════════════
            // ── Weekly Limits Card ──
            // ══════════════════════════════════
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: weeklyCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: weeklyCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: Kirigami.Units.mediumSpacing

                    PlasmaComponents3.Label {
                        text: root.tr("weeklyLimits")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85
                        font.weight: Font.DemiBold
                        opacity: 0.5
                    }

                    // One row per weekly scope the API actually reported.
                    // These were seven near-identical 43-line blocks, hand
                    // written per model. That is how the Sonnet row ended up
                    // without the visibility guard the others had: the API
                    // deprecated seven_day_sonnet to null and the widget kept
                    // drawing a permanent "Sonnet only 0%" bar. Driving the
                    // rows from data removes the whole class of defect — a
                    // scope with no data has no row — and a model the API
                    // starts scoping shows up without touching this file.
                    Repeater {
                        model: root.weeklyRows

                        delegate: ColumnLayout {
                            id: weeklyRow
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 4

                            // 7-day window, so pace is measured against 168h.
                            property real pace: root.windowPace(modelData.resetsAt, 168)

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Kirigami.Units.smallSpacing
                                Rectangle {
                                    width: 8; height: 8; radius: 4
                                    color: modelData.accent
                                }
                                PlasmaComponents3.Label {
                                    text: modelData.label
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                                }
                                Item { Layout.fillWidth: true }
                                PlasmaComponents3.Label {
                                    visible: modelData.resetsLabel !== ""
                                    text: modelData.resetsLabel
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                                    font.features: ({ "tnum": 1 })
                                    opacity: 0.35
                                }
                                PlasmaComponents3.Label {
                                    text: Math.round(modelData.pct) + "%"
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.1
                                    font.weight: Font.Bold
                                    font.features: ({ "tnum": 1 })
                                    color: root.paceTextColor(modelData.pct, weeklyRow.pace)
                                }
                            }

                            Rectangle {
                                id: track
                                Layout.fillWidth: true; height: 8; radius: 4
                                color: root.subtleBorder
                                clip: true

                                // Alert zones, drawn on the empty track so the
                                // danger is visible before the bar reaches it.
                                // A gauge that only turns red on arrival tells
                                // you when it is already too late to slow down.
                                Rectangle {
                                    x: track.width * (root.warnAt / 100)
                                    width: track.width * ((root.alertAt - root.warnAt) / 100)
                                    height: parent.height
                                    color: root.claudeAmberLight
                                    opacity: 0.16
                                }
                                Rectangle {
                                    x: track.width * (root.alertAt / 100)
                                    width: track.width * (1 - root.alertAt / 100)
                                    height: parent.height
                                    color: root.redAlert
                                    opacity: 0.16
                                }

                                Rectangle {
                                    id: fill
                                    width: track.width * Math.min(1, modelData.pct / 100)
                                    height: parent.height; radius: 4
                                    color: root.paceFill(modelData.pct, weeklyRow.pace)
                                    Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                                    Behavior on color { ColorAnimation { duration: 400 } }

                                    property bool alerting: root.usageZone(modelData.pct, weeklyRow.pace) === "alert"
                                    SequentialAnimation on opacity {
                                        running: fill.alerting
                                        loops: Animation.Infinite
                                        NumberAnimation { to: 0.5; duration: 700; easing.type: Easing.InOutSine }
                                        NumberAnimation { to: 1.0; duration: 700; easing.type: Easing.InOutSine }
                                    }
                                    onAlertingChanged: if (!alerting) opacity = 1.0
                                }

                                // Same tick as the session ring: where even burn
                                // through the week would have reached by now.
                                Rectangle {
                                    visible: weeklyRow.pace >= 0 && weeklyRow.pace < 1
                                    x: Math.round(track.width * weeklyRow.pace) - width / 2
                                    width: 2; height: parent.height
                                    radius: 1
                                    color: Kirigami.Theme.textColor
                                    opacity: 0.5
                                }
                            }
                        }
                    }
                }
            }

            // ══════════════════════════════════
            // ── Weekly forecast ──
            // The rolling 5h window already has limitEta. The week — the limit
            // that actually ends a week — had a bar and a reset time, which
            // say where you are and never whether you arrive.
            //
            // The arithmetic, and the reasons for choosing that pace and that
            // resolution, are in weeklyForecast(). What lives here is the
            // vocabulary, and each state is a different sentence rather than a
            // louder version of one: "the reset comes first" is good news and
            // must not read like a countdown to a wall.
            // ══════════════════════════════════
            Rectangle {
                Layout.fillWidth: true
                visible: root.usageData.rateLimits?.weeklyAll != null
                implicitHeight: fcCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: fcCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 3

                    readonly property var fc: root.weeklyForecast(
                        root.usageData.rateLimits?.weeklyAll ?? null,
                        root.usageData.burnRate?.total_per_hour ?? 0,
                        root.nowMs)
                    readonly property string zone: root.forecastZone(fc)

                    PlasmaComponents3.Label {
                        text: root.tr("weeklyForecast")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                        font.weight: Font.DemiBold
                        opacity: 0.45
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        Rectangle {
                            Layout.preferredWidth: 8
                            Layout.preferredHeight: 8
                            Layout.alignment: Qt.AlignVCenter
                            radius: 4
                            color: root.zoneColor(fcCol.zone)
                        }

                        // fillWidth and elide: a weekday plus a part of the day
                        // is longer in Portuguese than in English, and the
                        // popup's Flickable clips horizontally instead of
                        // scrolling, so anything that overflows here does not
                        // wrap, it disappears — and takes the popup's width
                        // with it.
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            elide: Text.ElideRight
                            text: {
                                var f = fcCol.fc;
                                if (f.state === "atLimit") return root.tr("ceilingReached");
                                if (f.state === "noPace") return root.tr("noPaceToProject");
                                if (f.state === "resetFirst") return root.tr("resetComesFirst");
                                if (f.state === "limitFirst")
                                    return root.tr("ceilingAround") + " "
                                         + root.whenLabel(f.atMs, root.nowMs);
                                return root.tr("noWindow");
                            }
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.95
                            font.weight: fcCol.zone === "calm" ? Font.Normal : Font.DemiBold
                            color: fcCol.zone === "calm" ? Kirigami.Theme.textColor
                                                         : root.zoneColor(fcCol.zone)
                        }
                    }

                    // Which pace produced the line above. Without it a
                    // projection reads as a measurement.
                    PlasmaComponents3.Label {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        elide: Text.ElideRight
                        visible: fcCol.fc.pctPerHour > 0
                        text: root.tr("atWeekPace") + " · "
                            + root.formatPctPerHour(fcCol.fc.pctPerHour)
                            + (fcCol.fc.state === "resetFirst"
                               && (root.usageData.rateLimits?.weeklyAll?.resetsLabel ?? "") !== ""
                               ? " · " + root.usageData.rateLimits.weeklyAll.resetsLabel : "")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.78
                        font.features: ({ "tnum": 1 })
                        opacity: 0.4
                    }
                }
            }

            // ══════════════════════════════════
            // ── Credits & Spending Card ──
            // ══════════════════════════════════
            Rectangle {
                Layout.fillWidth: true
                visible: root.usageData.rateLimits?.credits != null
                implicitHeight: creditsCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: creditsCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 6

                    // Header: Balance big number
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        Kirigami.Icon {
                            source: "wallet-open"
                            Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                            Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                            color: root.claudeAmber; opacity: 0.6
                        }
                        PlasmaComponents3.Label {
                            text: root.tr("credits")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            font.weight: Font.DemiBold; opacity: 0.55
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            text: {
                                var c = root.usageData.rateLimits?.credits ?? {};
                                var amount = c.amount ?? 0;
                                var currency = c.currency ?? "USD";
                                if (currency === "BRL") return "R$ " + amount.toLocaleString(Qt.locale(), 'f', 2);
                                return "$ " + amount.toLocaleString(Qt.locale(), 'f', 2);
                            }
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.3
                            font.weight: Font.Bold
                            color: root.claudeAmber
                        }
                    }

                    // Auto-reload status
                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        Kirigami.Icon { source: "view-refresh"; Layout.preferredWidth: 12; Layout.preferredHeight: 12; opacity: 0.4 }
                        PlasmaComponents3.Label {
                            text: root.tr("autoReload")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82; opacity: 0.5
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            property bool on: root.usageData.rateLimits?.credits?.autoReload ?? false
                            text: on ? root.tr("on") : root.tr("off")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85
                            font.weight: Font.Bold
                            // Amber only when it would actually bite: auto-reload
                            // off with credit left is a preference, not a warning.
                            color: on ? root.greenAccent
                                 : (root.usageData.rateLimits?.credits?.amount ?? 0) < 1
                                   ? root.claudeAmberLight : Kirigami.Theme.textColor
                            opacity: on ? 1.0 : 0.55
                        }
                    }

                    // ── Extra Usage section ──
                    Rectangle {
                        Layout.fillWidth: true; height: 1
                        color: root.subtleBorder; opacity: 0.5
                        visible: root.usageData.rateLimits?.extraUsage != null
                    }

                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        visible: root.usageData.rateLimits?.extraUsage != null
                        Kirigami.Icon { source: "list-add"; Layout.preferredWidth: 14; Layout.preferredHeight: 14; opacity: 0.5 }
                        PlasmaComponents3.Label {
                            text: root.tr("extraUsage")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            font.weight: Font.DemiBold; opacity: 0.55
                        }
                        Item { Layout.fillWidth: true }
                        // Off is not an error. A red badge here competes for
                        // attention with the quotas that can actually run out.
                        Rectangle {
                            property bool on: root.usageData.rateLimits?.extraUsage?.enabled ?? false
                            radius: height / 2
                            color: on ? Qt.rgba(root.greenAccent.r, root.greenAccent.g,
                                                root.greenAccent.b, 0.18)
                                      : root.subtleBorder
                            implicitWidth: _extraLbl.implicitWidth + 12
                            implicitHeight: _extraLbl.implicitHeight + 4
                            PlasmaComponents3.Label {
                                id: _extraLbl; anchors.centerIn: parent
                                text: parent.on ? root.tr("active") : root.tr("off")
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                                font.weight: Font.Bold
                                color: parent.on ? root.greenAccent : Kirigami.Theme.textColor
                                opacity: parent.on ? 1.0 : 0.45
                            }
                        }
                    }

                    // Detail only when the feature is on: a spend limit and a
                    // 0/500 bar for something switched off is four rows of
                    // nothing, above the fold, next to quotas that matter.
                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        visible: root.usageData.rateLimits?.extraUsage?.enabled ?? false
                        PlasmaComponents3.Label {
                            text: root.tr("monthlyLimit")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82; opacity: 0.5
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            text: {
                                var e = root.usageData.rateLimits?.extraUsage ?? {};
                                var c = e.currency ?? "USD";
                                var amt = e.monthlyLimit ?? 0;
                                return (c === "BRL" ? "R$ " : "$ ") + amt.toLocaleString(Qt.locale(), 'f', 2);
                            }
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85
                            font.weight: Font.DemiBold
                        }
                    }

                    // Used / remaining bar
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 3
                        visible: root.usageData.rateLimits?.extraUsage?.enabled ?? false

                        RowLayout {
                            Layout.fillWidth: true
                            PlasmaComponents3.Label {
                                text: root.tr("used")
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82; opacity: 0.5
                            }
                            Item { Layout.fillWidth: true }
                            PlasmaComponents3.Label {
                                property real used: root.usageData.rateLimits?.extraUsage?.usedCredits ?? 0
                                property real limit: root.usageData.rateLimits?.extraUsage?.monthlyLimit ?? 1
                                text: {
                                    var c = root.usageData.rateLimits?.extraUsage?.currency ?? "USD";
                                    var prefix = c === "BRL" ? "R$ " : "$ ";
                                    return prefix + used.toLocaleString(Qt.locale(), 'f', 2) + " / " + prefix + limit.toLocaleString(Qt.locale(), 'f', 2);
                                }
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82; opacity: 0.6
                            }
                        }

                        // Usage bar
                        Rectangle {
                            Layout.fillWidth: true; height: 6; radius: 3
                            color: root.subtleBorder
                            Rectangle {
                                property real used: root.usageData.rateLimits?.extraUsage?.usedCredits ?? 0
                                property real limit: root.usageData.rateLimits?.extraUsage?.monthlyLimit ?? 1
                                width: parent.width * Math.min(1, limit > 0 ? used / limit : 0)
                                height: parent.height; radius: 3
                                color: (used / Math.max(1, limit)) > 0.8 ? root.redAlert : root.claudeAmber
                                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                            }
                        }
                    }
                }
            }

            // ══════════════════════════════════
            // ── Service Health Card ──
            // ══════════════════════════════════
            Rectangle {
                Layout.fillWidth: true
                visible: root.usageData.serviceStatus != null
                radius: 10
                color: {
                    var ind = root.usageData.serviceStatus?.indicator ?? "none";
                    if (ind === "none") return root.cardBg;
                    if (ind === "minor") return Qt.rgba(0.984, 0.620, 0.086, 0.10);
                    return Qt.rgba(0.937, 0.267, 0.267, 0.10);
                }
                border.width: 1
                border.color: {
                    var ind = root.usageData.serviceStatus?.indicator ?? "none";
                    if (ind === "none") return root.subtleBorder;
                    if (ind === "minor") return Qt.rgba(0.984, 0.620, 0.086, 0.40);
                    return Qt.rgba(0.937, 0.267, 0.267, 0.40);
                }
                implicitHeight: serviceHealthCol.implicitHeight + Kirigami.Units.mediumSpacing * 2

                ColumnLayout {
                    id: serviceHealthCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 6

                    // Overall status row
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        // Pulsing dot
                        Rectangle {
                            id: healthDot
                            property string ind: root.usageData.serviceStatus?.indicator ?? "none"
                            width: 10; height: 10; radius: 5
                            color: statusColor(ind)

                            SequentialAnimation on opacity {
                                running: healthDot.ind !== "none"
                                loops: Animation.Infinite
                                NumberAnimation { to: 0.3; duration: 900; easing.type: Easing.InOutSine }
                                NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
                            }
                        }

                        PlasmaComponents3.Label {
                            text: "Service Health"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.88
                            font.weight: Font.DemiBold
                            opacity: 0.65
                        }

                        Item { Layout.fillWidth: true }

                        // Status pill badge
                        Rectangle {
                            property string ind: root.usageData.serviceStatus?.indicator ?? "none"
                            radius: height / 2
                            color: {
                                var c = statusColor(ind);
                                return Qt.rgba(c.r, c.g, c.b, 0.20);
                            }
                            border.width: 1
                            border.color: {
                                var c = statusColor(ind);
                                return Qt.rgba(c.r, c.g, c.b, 0.55);
                            }
                            implicitWidth: _statusBadge.implicitWidth + 18
                            implicitHeight: _statusBadge.implicitHeight + 8

                            PlasmaComponents3.Label {
                                id: _statusBadge
                                anchors.centerIn: parent
                                text: {
                                    var ind = root.usageData.serviceStatus?.indicator ?? "none";
                                    if (ind === "none")     return "Healthy";
                                    if (ind === "minor")    return "Degraded";
                                    if (ind === "major")    return "Major Outage";
                                    if (ind === "critical") return "Critical Outage";
                                    return "Unknown";
                                }
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.88
                                font.weight: Font.Bold
                                color: statusColor(root.usageData.serviceStatus?.indicator ?? "none")
                            }
                        }
                    }

                    // Component dots row
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        Repeater {
                            model: root.usageData.serviceStatus?.components ?? []
                            RowLayout {
                                spacing: 3
                                Rectangle {
                                    width: 6; height: 6; radius: 3
                                    color: componentStatusColor(modelData.status ?? "")
                                }
                                PlasmaComponents3.Label {
                                    text: modelData.name ?? ""
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.822
                                    opacity: 0.55
                                }
                            }
                        }

                        Item { Layout.fillWidth: true }
                    }

                    // DownDetector link (crowd-sourced early warning)
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Kirigami.Icon {
                            source: "globe"
                            Layout.preferredWidth: 10; Layout.preferredHeight: 10
                            opacity: 0.35
                        }

                        PlasmaComponents3.Label {
                            text: "User reports:"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.822
                            opacity: 0.35
                        }

                        Item { Layout.fillWidth: true }

                        PlasmaComponents3.ToolButton {
                            text: "DownDetector ↗"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.822
                            opacity: 0.55
                            flat: true
                            padding: 0
                            onClicked: Qt.openUrlExternally(root.brand.downDetectorUrl)
                        }
                    }

                    // MCP re-auth pending — silent until something actually needs attention
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1  // lets fillWidth bind to parent instead of intrinsic content
                        spacing: 4
                        visible: (root.usageData.mcpAuthPending ?? []).length > 0

                        Rectangle {
                            Layout.preferredWidth: 6; Layout.preferredHeight: 6
                            radius: 3; color: root.claudeAmberLight
                        }

                        PlasmaComponents3.Label {
                            property var pending: root.usageData.mcpAuthPending ?? []
                            // Strip the 'claude.ai ' prefix from cache keys to save width
                            function stripPrefix(names) {
                                return names.map(function(n) { return n.replace(/^claude\.ai\s+/, ""); });
                            }
                            text: pending.length + " MCP" + (pending.length === 1 ? "" : "s") + " need re-auth: " + stripPrefix(pending.slice(0, 3)).join(", ") + (pending.length > 3 ? "…" : "")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.822
                            color: root.claudeAmberLight
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                    }

                    // Opus downgrade watch — suppressed unless the heuristic actually fires
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        visible: root.usageData.opusFallbacks?.suspicious === true

                        Rectangle { width: 6; height: 6; radius: 3; color: root.redAlert }

                        PlasmaComponents3.Label {
                            property real gap: root.usageData.opusFallbacks?.gap ?? 0
                            text: "Opus routing drop: " + Math.round(gap * 100) + " pp below weekly baseline"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.822
                            color: root.redAlert
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                    }

                    // Active incident details
                    Repeater {
                        model: root.activeIncidents
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2

                            PlasmaComponents3.Label {
                                Layout.fillWidth: true
                                text: modelData.name ?? ""
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.828
                                font.weight: Font.DemiBold
                                color: root.redAlert
                                wrapMode: Text.WordWrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                            }

                            PlasmaComponents3.Label {
                                Layout.fillWidth: true
                                visible: (modelData.latest_update ?? "") !== ""
                                text: modelData.latest_update ?? ""
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.823
                                opacity: 0.50
                                wrapMode: Text.WordWrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }

            // ══════════════════════════════════
            // ── Intelligence / Dumbness Card ──
            // ══════════════════════════════════
            Rectangle {
                Layout.fillWidth: true
                visible: root.dumbScore > 0
                radius: 10
                color: {
                    if (root.dumbScore >= 75) return Qt.rgba(0.937, 0.267, 0.267, 0.12);
                    if (root.dumbScore >= 50) return Qt.rgba(0.976, 0.451, 0.086, 0.10);
                    if (root.dumbScore >= 25) return Qt.rgba(0.961, 0.620, 0.043, 0.10);
                    return root.cardBg;
                }
                border.width: 1
                border.color: root.subtleBorder
                implicitHeight: dumbCol.implicitHeight + Kirigami.Units.mediumSpacing * 2

                ColumnLayout {
                    id: dumbCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        PlasmaComponents3.Label {
                            text: {
                                var lvl = root.dumbLevel;
                                if (lvl === "braindead") return "💀 Braindead";
                                if (lvl === "dumb") return "🔥 This is Fine";
                                if (lvl === "slow") return "🌧 Slow";
                                if (lvl === "genius") return "✨ Genius";
                                return "🤔 Hmm";
                            }
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            font.weight: Font.Bold
                        }

                        Item { Layout.fillWidth: true }

                        // Score badge
                        Rectangle {
                            radius: height / 2
                            color: {
                                if (root.dumbScore >= 75) return Qt.rgba(0.937, 0.267, 0.267, 0.25);
                                if (root.dumbScore >= 50) return Qt.rgba(0.976, 0.451, 0.086, 0.25);
                                return Qt.rgba(0.961, 0.620, 0.043, 0.25);
                            }
                            implicitWidth: _dumbLabel.implicitWidth + 14
                            implicitHeight: _dumbLabel.implicitHeight + 6

                            PlasmaComponents3.Label {
                                id: _dumbLabel
                                anchors.centerIn: parent
                                text: root.dumbScore + "/100"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.828
                                font.weight: Font.Bold
                                color: {
                                    if (root.dumbScore >= 75) return root.redAlert;
                                    if (root.dumbScore >= 50) return "#F97316";
                                    return root.claudeAmberLight;
                                }
                            }
                        }
                    }

                    // Reasons list
                    Repeater {
                        model: root.usageData.dumbness?.reasons ?? []
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            text: "  • " + modelData
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.822
                            opacity: 0.55
                        }
                    }

                    // Adaptive thinking workaround tip
                    PlasmaComponents3.Label {
                        Layout.fillWidth: true
                        visible: !(root.usageData.adaptiveThinking?.adaptive_thinking ?? true)
                        text: "Tip: Adaptive Thinking is OFF in settings.json"
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.822
                        font.italic: true
                        opacity: 0.45
                        wrapMode: Text.WordWrap
                    }
                }
            }

            // ══════════════════════════════════
            // ── Value Extracted Card ──
            // ══════════════════════════════════
            //
            // The collector computed all of this and the UI threw it away: the
            // only consumer of costProjection was a row gated on costUSD > 0,
            // which is always 0 on a subscription. So a plan running 1.7B
            // tokens a day showed nothing about what that is worth.
            //
            // These are notional API-equivalent figures — what the same traffic
            // would cost at public per-token prices — not money spent. The card
            // says so, because "$20,281" with no qualifier is a lie.
            Rectangle {
                Layout.fillWidth: true
                visible: (root.usageData.today?.totalTokens ?? 0) > 0
                implicitHeight: valueCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: valueCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        Kirigami.Icon {
                            source: "office-chart-area"
                            Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                            Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                            color: root.greenAccent; opacity: 0.6
                        }
                        PlasmaComponents3.Label {
                            text: root.tr("efficiency")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            font.weight: Font.DemiBold; opacity: 0.55
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            text: root.tr("apiEquivalent")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.72
                            opacity: 0.35
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 3
                        columnSpacing: Kirigami.Units.largeSpacing
                        rowSpacing: 2

                        Repeater {
                            model: root.valueTiles
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 0
                                PlasmaComponents3.Label {
                                    text: modelData.label
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.72
                                    opacity: 0.45
                                }
                                PlasmaComponents3.Label {
                                    text: modelData.value
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.15
                                    font.weight: Font.Bold
                                    font.features: ({ "tnum": 1 })
                                    color: modelData.accent
                                }
                                PlasmaComponents3.Label {
                                    text: modelData.sub
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.72
                                    font.features: ({ "tnum": 1 })
                                    opacity: 0.45
                                }
                            }
                        }
                    }
                }
            }

            // ── Live sessions ──
            // Several Claude sessions run at once across different repos and
            // nothing on the desktop says which finished, which is blocked on
            // an answer, and which has been idle for an hour. The repo name is
            // what identifies them to their owner, so it leads each row.
            Rectangle {
                Layout.fillWidth: true
                visible: (root.sessionsData.total ?? 0) > 0
                implicitHeight: liveCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg
                border.width: 2
                border.color: root.attentionSession
                            ? Qt.rgba(root.claudeAmberLight.r, root.claudeAmberLight.g,
                                      root.claudeAmberLight.b, 0.35)
                            : "transparent"

                ColumnLayout {
                    id: liveCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true
                        PlasmaComponents3.Label {
                            text: root.tr("liveSessions")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                            font.weight: Font.DemiBold; opacity: 0.45
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            text: root.sessionsData.total ?? 0
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                            font.weight: Font.Bold
                            font.features: ({ "tnum": 1 })
                            opacity: 0.5
                        }
                    }

                    Repeater {
                        model: root.sessionsData.sessions ?? []
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: rowLay.implicitHeight + 8
                            radius: 6
                            color: rowMouse.containsMouse
                                   ? Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g,
                                             Kirigami.Theme.textColor.b, 0.05)
                                   : "transparent"

                            MouseArea {
                                id: rowMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                // Clicking a session raises the terminal it is
                                // running in. Knowing which one is done is only
                                // half of it; getting there is the other half.
                                onClicked: focusHelper.connectSource(
                                    "$HOME/.local/bin/focus-session.sh " + modelData.pid)
                            }

                            RowLayout {
                                id: rowLay
                                anchors.fill: parent
                                anchors.leftMargin: 4
                                anchors.rightMargin: 4
                                spacing: Kirigami.Units.smallSpacing

                                Rectangle {
                                    width: 8; height: 8; radius: 4
                                    Layout.alignment: Qt.AlignVCenter
                                    color: modelData.state === "asking" ? root.redAlert
                                         : modelData.state === "waiting" ? root.claudeAmberLight
                                         : modelData.state === "idle" ? root.subtleBorder
                                         : root.greenAccent

                                    // Only the states that need a human pulse.
                                    SequentialAnimation on opacity {
                                        running: modelData.state === "asking"
                                        loops: Animation.Infinite
                                        NumberAnimation { to: 0.3; duration: 600 }
                                        NumberAnimation { to: 1.0; duration: 600 }
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    PlasmaComponents3.Label {
                                        Layout.fillWidth: true
                                        text: modelData.name
                                        elide: Text.ElideMiddle
                                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                                        font.weight: modelData.state === "asking" ? Font.Bold : Font.Normal
                                    }
                                    PlasmaComponents3.Label {
                                        Layout.fillWidth: true
                                        visible: (modelData.branch ?? "") !== ""
                                        text: modelData.branch
                                        elide: Text.ElideRight
                                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.68
                                        opacity: 0.35
                                    }
                                }

                                PlasmaComponents3.Label {
                                    text: root.tr("st_" + modelData.state)
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.72
                                    color: modelData.state === "asking" ? root.redAlert
                                         : modelData.state === "waiting" ? root.claudeAmberLight
                                         : Kirigami.Theme.textColor
                                    opacity: modelData.state === "working" ? 0.35 : 0.85
                                }
                                PlasmaComponents3.Label {
                                    Layout.preferredWidth: Kirigami.Units.gridUnit * 2.2
                                    horizontalAlignment: Text.AlignRight
                                    text: root._fmtIdle(modelData.idleSeconds ?? 0)
                                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.72
                                    font.features: ({ "tnum": 1 })
                                    opacity: 0.35
                                }
                            }
                        }
                    }
                }
            }

            // ── Costliest sessions ──
            // A daily total cannot be acted on; a session that cost four times
            // its neighbours can.
            Rectangle {
                Layout.fillWidth: true
                visible: (root.usageData.sessionCosts ?? []).length > 1
                implicitHeight: sessCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: sessCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 3

                    readonly property real peak: {
                        var rows = root.usageData.sessionCosts ?? [];
                        var m = 0;
                        for (var i = 0; i < rows.length; i++) m = Math.max(m, rows[i].costUSD ?? 0);
                        return m || 1;
                    }

                    PlasmaComponents3.Label {
                        text: root.tr("costliestSessions")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                        font.weight: Font.DemiBold; opacity: 0.45
                    }

                    Repeater {
                        model: root.usageData.sessionCosts ?? []
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            PlasmaComponents3.Label {
                                Layout.preferredWidth: Kirigami.Units.gridUnit * 7
                                text: modelData.project || modelData.id
                                elide: Text.ElideLeft
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.74
                                opacity: 0.7
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignVCenter
                                height: 5; radius: 2.5
                                color: root.subtleBorder
                                Rectangle {
                                    width: parent.width * ((modelData.costUSD ?? 0) / sessCol.peak)
                                    height: parent.height; radius: 2.5
                                    color: root.calmFill
                                    Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                                }
                            }
                            PlasmaComponents3.Label {
                                Layout.preferredWidth: Kirigami.Units.gridUnit * 3
                                horizontalAlignment: Text.AlignRight
                                text: root._usd(modelData.costUSD ?? 0)
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.74
                                font.features: ({ "tnum": 1 })
                                font.weight: Font.Bold
                                opacity: 0.6
                            }
                        }
                    }
                }
            }

            // ── Cost by project ──
            // sessionCosts is a flat list, and the card above shows several
            // sessions in the same checkout as unrelated rows. Grouping
            // answers what the list cannot: which piece of work the money went
            // to, rather than which individual session was expensive.
            //
            // On a day with one session per checkout this collapses into the
            // list above. The subtitle therefore counts the sessions, so an
            // identity is not dressed up as an aggregation.
            //
            // No history: sessionCosts is today, and the payload carries no
            // per-project series to accumulate over days.
            Rectangle {
                Layout.fillWidth: true
                visible: (root.usageData.sessionCosts ?? []).length > 0
                implicitHeight: projCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: projCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 3

                    readonly property var groups: root.costsByProject(
                        root.usageData.sessionCosts ?? [])

                    readonly property real peak: {
                        var m = 0;
                        for (var i = 0; i < groups.length; i++)
                            m = Math.max(m, groups[i].costUSD);
                        return m > 0 ? m : 1;
                    }

                    // True when every group holds exactly one session, which
                    // is to say when the grouping changed nothing today.
                    readonly property bool identity: {
                        for (var i = 0; i < groups.length; i++)
                            if (groups[i].sessions > 1) return false;
                        return true;
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        PlasmaComponents3.Label {
                            text: root.tr("costByProject")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                            font.weight: Font.DemiBold
                            opacity: 0.45
                        }
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            horizontalAlignment: Text.AlignRight
                            elide: Text.ElideRight
                            text: projCol.groups.length + " " + root.tr("projects")
                                + (projCol.identity ? ", " + root.tr("oneSessionEach") : "")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.72
                            opacity: 0.3
                        }
                    }

                    Repeater {
                        model: projCol.groups

                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            // fillWidth with minimumWidth 0, not a fixed
                            // preferredWidth: the popup's Flickable clips
                            // horizontally instead of scrolling, so a label
                            // that cannot shrink does not overflow, it takes
                            // the whole popup with it.
                            PlasmaComponents3.Label {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.preferredWidth: Kirigami.Units.gridUnit * 7
                                text: modelData.project
                                // The tail identifies the checkout; every one
                                // of these strings opens with the same home or
                                // var prefix.
                                elide: Text.ElideLeft
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.74
                                opacity: 0.7
                            }

                            PlasmaComponents3.Label {
                                visible: modelData.sessions > 1
                                text: modelData.sessions + "x"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.7
                                font.features: ({ "tnum": 1 })
                                opacity: 0.45
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.minimumWidth: Kirigami.Units.gridUnit * 2
                                Layout.preferredWidth: Kirigami.Units.gridUnit * 4
                                Layout.preferredHeight: 5
                                Layout.alignment: Qt.AlignVCenter
                                radius: 2.5
                                color: root.subtleBorder

                                Rectangle {
                                    width: parent.width * (modelData.costUSD / projCol.peak)
                                    height: parent.height
                                    radius: 2.5
                                    color: root.calmFill
                                    Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                                }
                            }

                            PlasmaComponents3.Label {
                                Layout.preferredWidth: Kirigami.Units.gridUnit * 3
                                horizontalAlignment: Text.AlignRight
                                text: root._usd(modelData.costUSD)
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.74
                                font.features: ({ "tnum": 1 })
                                font.weight: Font.Bold
                                opacity: 0.6
                            }

                            // Share of the day, which the bar cannot give: the
                            // bar is scaled to the biggest project, not to the
                            // total.
                            PlasmaComponents3.Label {
                                Layout.preferredWidth: Kirigami.Units.gridUnit * 1.8
                                horizontalAlignment: Text.AlignRight
                                text: Math.round(modelData.share * 100) + "%"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.7
                                font.features: ({ "tnum": 1 })
                                opacity: 0.35
                            }
                        }
                    }
                }
            }

            // ── Service health, against this account's own baseline ──
            // A fixed threshold cannot know that 10s is normal here. The
            // verdict is withheld until there is enough history to compare
            // against — "not enough history" is a real answer.
            RowLayout {
                Layout.fillWidth: true
                visible: (root.usageData.health?.state ?? "") !== ""
                spacing: Kirigami.Units.smallSpacing

                Rectangle {
                    width: 9; height: 9; radius: 4.5
                    Layout.alignment: Qt.AlignVCenter
                    property string st: root.usageData.health?.state ?? ""
                    color: st === "normal" ? root.greenAccent
                         : st === "degraded" ? root.claudeAmberLight : root.subtleBorder
                }
                PlasmaComponents3.Label {
                    text: root.tr("serviceHealth")
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.78
                    opacity: 0.5
                }
                Item { Layout.fillWidth: true }
                PlasmaComponents3.Label {
                    property string st: root.usageData.health?.state ?? ""
                    text: st === "normal" ? root.tr("normal")
                        : st === "degraded" ? root.tr("degraded") : root.tr("unknownHealth")
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.78
                    font.weight: st === "degraded" ? Font.Bold : Font.Normal
                    color: st === "degraded" ? root.claudeAmberLight : Kirigami.Theme.textColor
                    opacity: st === "degraded" ? 0.95 : 0.5
                }
            }

            // Quirks strip — the numbers that are fun rather than actionable.
            // Deliberately a single wrapping row, not a card: it must never
            // compete with a quota for attention.
            Flow {
                Layout.fillWidth: true
                visible: root.quirkBadges.length > 0
                spacing: Kirigami.Units.smallSpacing

                Repeater {
                    model: root.quirkBadges
                    delegate: Rectangle {
                        required property var modelData
                        radius: height / 2
                        color: root.subtleBorder
                        implicitWidth: badgeRow.implicitWidth + 14
                        implicitHeight: badgeRow.implicitHeight + 6

                        RowLayout {
                            id: badgeRow
                            anchors.centerIn: parent
                            spacing: 4
                            PlasmaComponents3.Label {
                                text: modelData.icon
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                            }
                            PlasmaComponents3.Label {
                                text: modelData.text
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.78
                                font.features: ({ "tnum": 1 })
                                opacity: 0.7
                            }
                        }
                    }
                }
            }

            // ══════════════════════════════════
            // ── Burn Rate & Errors Card ──
            // ══════════════════════════════════
            Rectangle {
                // Every row here comes from a local-log metric; a provider that
                // reports none of them hides the card instead of showing zeros.
                visible: root.usageData.burnRate !== undefined
                         || root.usageData.errorRate !== undefined
                         || root.usageData.adaptiveThinking !== undefined
                Layout.fillWidth: true
                radius: 10
                color: root.cardBg
                implicitHeight: burnCol.implicitHeight + Kirigami.Units.mediumSpacing * 2

                ColumnLayout {
                    id: burnCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 6

                    PlasmaComponents3.Label {
                        text: "Activity"
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                        font.weight: Font.DemiBold
                        opacity: 0.5
                    }

                    // Burn rate row
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Kirigami.Icon {
                            source: "speedometer"
                            Layout.preferredWidth: 14; Layout.preferredHeight: 14
                            opacity: 0.5
                        }

                        PlasmaComponents3.Label {
                            text: "Burn rate"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                            opacity: 0.6
                        }

                        Item { Layout.fillWidth: true }

                        PlasmaComponents3.Label {
                            property int rate: root.usageData.burnRate?.output_per_hour ?? 0
                            text: {
                                if (rate >= 1e6) return (rate / 1e6).toFixed(1) + "M/h";
                                if (rate >= 1e3) return (rate / 1e3).toFixed(0) + "K/h";
                                return rate + "/h";
                            }
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            font.weight: Font.Bold
                            color: rate > 500000 ? root.claudeAmberLight : Kirigami.Theme.textColor
                        }
                    }

                    // Error rate row
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Kirigami.Icon {
                            source: "dialog-warning-symbolic"
                            Layout.preferredWidth: 14; Layout.preferredHeight: 14
                            opacity: 0.5
                        }

                        PlasmaComponents3.Label {
                            text: "Errors (2h)"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                            opacity: 0.6
                        }

                        Item { Layout.fillWidth: true }

                        PlasmaComponents3.Label {
                            property int errs: root.usageData.errorRate?.total ?? 0
                            text: errs > 0 ? errs + " errors" : "None"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85
                            font.weight: Font.Bold
                            color: errs > 5 ? root.redAlert : errs > 0 ? root.claudeAmberLight : root.greenAccent
                        }
                    }

                    // Adaptive thinking status row
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Kirigami.Icon {
                            source: "preferences-system"
                            Layout.preferredWidth: 14; Layout.preferredHeight: 14
                            opacity: 0.5
                        }

                        PlasmaComponents3.Label {
                            text: "Adaptive Thinking"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                            opacity: 0.6
                        }

                        Item { Layout.fillWidth: true }

                        PlasmaComponents3.Label {
                            property bool on: root.usageData.adaptiveThinking?.adaptive_thinking ?? true
                            text: on ? "ON" : "OFF"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85
                            font.weight: Font.Bold
                            color: on ? root.greenAccent : root.redAlert
                        }
                    }

                    // Avg response quality
                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        visible: (root.usageData.responseQuality?.avgTokensPerResponse ?? 0) > 0
                        Kirigami.Icon { source: "document-edit"; Layout.preferredWidth: 14; Layout.preferredHeight: 14; opacity: 0.5 }
                        PlasmaComponents3.Label { text: "Avg response"; font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82; opacity: 0.6 }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            property int avg: root.usageData.responseQuality?.avgTokensPerResponse ?? 0
                            text: root.formatTokens(avg) + " tok"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85; font.weight: Font.Bold
                            color: avg > 500 ? root.greenAccent : avg > 200 ? root.claudeAmberLight : root.redAlert
                        }
                    }

                    // Latency
                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        visible: (root.usageData.latency?.avgSeconds ?? 0) > 0
                        Kirigami.Icon { source: "chronometer"; Layout.preferredWidth: 14; Layout.preferredHeight: 14; opacity: 0.5 }
                        PlasmaComponents3.Label { text: "Avg latency"; font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82; opacity: 0.6 }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            property real lat: root.usageData.latency?.avgSeconds ?? 0
                            text: lat.toFixed(1) + "s"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85; font.weight: Font.Bold
                            color: lat < 10 ? root.greenAccent : lat < 30 ? root.claudeAmberLight : root.redAlert
                        }
                    }

                    // Cache hit rate — the single most actionable efficiency signal
                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        visible: (root.usageData.today?.cacheHitRate ?? 0) > 0
                        Kirigami.Icon { source: "drive-harddisk"; Layout.preferredWidth: 14; Layout.preferredHeight: 14; opacity: 0.5 }
                        PlasmaComponents3.Label { text: "Cache hit"; font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82; opacity: 0.6 }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            property real hit: root.usageData.today?.cacheHitRate ?? 0
                            text: hit.toFixed(0) + "%"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85; font.weight: Font.Bold
                            // >60% = great (green), 15–60% = ok (neutral), <15% = leverage opportunity (amber)
                            color: hit >= 60 ? root.greenAccent : hit >= 15 ? Kirigami.Theme.textColor : root.claudeAmberLight
                        }
                    }

                    // Runway, only when there is credit actually draining. On a
                    // subscription runwayDays comes back 0.0 rather than null,
                    // and the old `!== null` test rendered a red "0.0d left" —
                    // an alarm about prepaid credit that is not being spent.
                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        property real runway: root.usageData.costProjection?.runwayDays ?? 0
                        visible: runway > 0
                        Kirigami.Icon { source: "office-chart-bar"; Layout.preferredWidth: 14; Layout.preferredHeight: 14; opacity: 0.5 }
                        PlasmaComponents3.Label { text: root.tr("creditRunway"); font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82; opacity: 0.6 }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            text: parent.runway.toFixed(1) + root.tr("daysLeft")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85
                            font.weight: Font.Bold
                            font.features: ({ "tnum": 1 })
                            color: parent.runway < 2 ? root.redAlert
                                 : parent.runway < 7 ? root.claudeAmberLight
                                 : Kirigami.Theme.textColor
                        }
                    }

                    // Context compactions — only visible when one or more happened
                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        visible: (root.usageData.compaction?.count ?? 0) > 0
                        Kirigami.Icon { source: "view-list-compact"; Layout.preferredWidth: 14; Layout.preferredHeight: 14; opacity: 0.5 }
                        PlasmaComponents3.Label { text: "Compactions (7d)"; font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82; opacity: 0.6 }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            property int c: root.usageData.compaction?.count ?? 0
                            text: c
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85; font.weight: Font.Bold
                            color: c >= 3 ? root.claudeAmberLight : Kirigami.Theme.textColor
                        }
                    }

                    // Top tools used (compact top-3)
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        spacing: 4
                        visible: (root.usageData.toolUse?.total ?? 0) > 0
                        Kirigami.Icon { source: "system-run"; Layout.preferredWidth: 14; Layout.preferredHeight: 14; opacity: 0.5 }
                        PlasmaComponents3.Label { text: "Top tools (7d)"; font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82; opacity: 0.6 }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            text: {
                                var by = root.usageData.toolUse?.byTool ?? {};
                                var entries = Object.keys(by).map(function(k) { return [k, by[k]]; });
                                entries.sort(function(a, b) { return b[1] - a[1]; });
                                return entries.slice(0, 3).map(function(e) { return e[0]; }).join(" · ");
                            }
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85
                            font.weight: Font.Bold
                            elide: Text.ElideRight
                            Layout.maximumWidth: 160
                            Layout.alignment: Qt.AlignRight
                        }
                    }

                    // Model distribution bar
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 4
                        visible: (root.usageData.modelBreakdown ?? []).length > 0
                        PlasmaComponents3.Label { text: "Model split"; font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.828; opacity: 0.4 }
                        Rectangle {
                            Layout.fillWidth: true; height: 8; radius: 4; color: root.subtleBorder; clip: true
                            Row {
                                anchors.fill: parent
                                Repeater {
                                    model: root.usageData.modelBreakdown ?? []
                                    Rectangle {
                                        width: parent.width * (modelData.percentage ?? 0) / 100
                                        height: parent.height; color: modelData.color ?? "#9CA3AF"
                                    }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: Kirigami.Units.smallSpacing
                            Repeater {
                                model: root.usageData.modelBreakdown ?? []
                                RowLayout {
                                    visible: (modelData.percentage ?? 0) > 0.5; spacing: 3
                                    Rectangle { width: 6; height: 6; radius: 3; color: modelData.color ?? "#9CA3AF" }
                                    PlasmaComponents3.Label {
                                        text: (modelData.model ?? "") + " " + Math.round(modelData.percentage ?? 0) + "%"
                                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8; opacity: 0.5
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ══════════════════════════════════
            // ── Quick Actions ──
            // ══════════════════════════════════
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents3.Button {
                    Layout.fillWidth: true
                    text: root.brand.siteLabel
                    icon.name: "internet-web-browser"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.828
                    onClicked: Qt.openUrlExternally(root.brand.siteUrl)
                }

                PlasmaComponents3.Button {
                    Layout.fillWidth: true
                    text: "Status"
                    icon.name: "network-connect"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.828
                    onClicked: Qt.openUrlExternally(root.brand.statusUrl)
                }

                PlasmaComponents3.Button {
                    Layout.fillWidth: true
                    text: "Copy Stats"
                    icon.name: "edit-copy"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.828
                    onClicked: {
                        var s = root.usageData;
                        var stats = root.brand.name + " " + new Date().toLocaleDateString()
                            + " | Session: " + Math.round(s.rateLimits?.session?.percentUsed ?? 0) + "%"
                            + " | Weekly: " + Math.round(s.rateLimits?.weeklyAll?.percentUsed ?? 0) + "%"
                            + " | $" + (s.today?.costUSD ?? 0).toFixed(2)
                            + " | " + root.formatTokens(s.today?.totalTokens ?? 0) + " tokens";
                        clipHelper.connectSource("echo " + JSON.stringify(stats) + " | wl-copy 2>/dev/null || echo " + JSON.stringify(stats) + " | xclip -selection clipboard 2>/dev/null");
                    }
                }
            }

            // ══════════════════════════════════
            // ── 7-Day Activity Chart ──
            // ══════════════════════════════════
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: chartCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: chartCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 4

                    PlasmaComponents3.Label {
                        text: "7-day activity"
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                        opacity: 0.4
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Kirigami.Units.gridUnit * 3.5

                        Canvas {
                            id: trendChart
                            anchors.fill: parent
                            property var chartData: root.usageData.trend7d ?? []
                            onChartDataChanged: requestPaint()
                            onWidthChanged: requestPaint()
                            onHeightChanged: requestPaint()

                            onPaint: {
                                var ctx = getContext("2d");
                                ctx.clearRect(0, 0, width, height);
                                var data = chartData;
                                if (!data || data.length === 0) return;

                                var maxT = 1;
                                for (var k = 0; k < data.length; k++)
                                    if ((data[k].tokens || 0) > maxT) maxT = data[k].tokens;

                                var bw = (width - 12) / data.length;
                                var pad = 3;
                                var ch = height - 14;

                                for (var i = 0; i < data.length; i++) {
                                    var x = 6 + i * bw + pad / 2;
                                    var barH = Math.max(2, (data[i].tokens / maxT) * ch);
                                    var y = ch - barH;
                                    var w = bw - pad;
                                    var isLast = (i === data.length - 1);

                                    // Gradient-like effect: brighter for today
                                    var alpha = isLast ? 0.85 : 0.2 + (i / data.length) * 0.2;
                                    ctx.fillStyle = Qt.rgba(0.851, 0.467, 0.024, alpha);

                                    var r = Math.min(4, w / 2);
                                    ctx.beginPath();
                                    ctx.moveTo(x + r, y);
                                    ctx.arcTo(x + w, y, x + w, y + barH, r);
                                    ctx.lineTo(x + w, ch);
                                    ctx.lineTo(x, ch);
                                    ctx.arcTo(x, y, x + r, y, r);
                                    ctx.closePath();
                                    ctx.fill();

                                    // Day label
                                    ctx.fillStyle = Kirigami.Theme.textColor.toString();
                                    ctx.globalAlpha = isLast ? 0.8 : 0.35;
                                    ctx.font = (isLast ? "bold " : "") + "8px sans-serif";
                                    ctx.textAlign = "center";
                                    ctx.fillText(data[i].label || "", x + w / 2, height - 1);
                                    ctx.globalAlpha = 1.0;
                                }
                            }
                        }
                    }
                }
            }

            // ══════════════════════════════════
            // ── Today against your own days ──
            // The chart above draws eight bars and leaves the reader to
            // eyeball whether the last one is unusual. A number with nothing
            // to compare it against is decoration, and the series to compare
            // it against was already on screen.
            //
            // The three things that would make this a lie are handled in
            // baselineComparison(), with the reasoning there: a partial day is
            // scaled before it is compared, a day that has barely started is
            // not compared at all, and under three active days there is no
            // verdict. What the band below adds to the ratio is width — the
            // same 1.4x means something different against days that ranged
            // 0.8B to 6.7B than against days that all landed near 3B.
            // ══════════════════════════════════
            Rectangle {
                Layout.fillWidth: true
                visible: (root.usageData.trend7d ?? []).length > 1
                implicitHeight: baseCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10
                color: root.cardBg

                ColumnLayout {
                    id: baseCol
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.mediumSpacing
                    spacing: 4

                    // Tokens rather than messages, to match the chart directly
                    // above it: two adjacent panels disagreeing about which
                    // quantity "activity" means is worse than either choice.
                    readonly property var cmp: root.baselineComparison(
                        root.usageData.trend7d ?? [], "tokens", root.nowMs)

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            elide: Text.ElideRight
                            text: root.tr("todayVsUsual")
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                            opacity: 0.4
                        }
                        PlasmaComponents3.Label {
                            visible: baseCol.cmp.state === "ok"
                            text: baseCol.cmp.ratio.toFixed(1) + "x"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.05
                            font.weight: Font.Bold
                            font.features: ({ "tnum": 1 })
                            color: baseCol.cmp.verdict === "above" ? root.claudeAmberLight
                                 : baseCol.cmp.verdict === "below" ? root.calmFill
                                 : Kirigami.Theme.textColor
                        }
                    }

                    // The band the prior active days actually spanned, scaled
                    // to the same fraction of the day today has reached, with
                    // today's mark on it.
                    Item {
                        id: band
                        Layout.fillWidth: true
                        Layout.preferredHeight: 8
                        visible: baseCol.cmp.state === "ok"

                        // Not named `scale`: Item already has one, and
                        // shadowing it silently resizes the row.
                        readonly property real span: {
                            var m = Math.max(baseCol.cmp.hi, baseCol.cmp.value);
                            return m > 0 ? m * 1.08 : 1;
                        }

                        Rectangle {
                            id: bandTrack
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.right: parent.right
                            height: 6
                            radius: 3
                            color: root.subtleBorder

                            Rectangle {
                                x: bandTrack.width * (baseCol.cmp.lo / band.span)
                                width: Math.max(2, bandTrack.width
                                       * ((baseCol.cmp.hi - baseCol.cmp.lo) / band.span))
                                height: parent.height
                                radius: 3
                                color: root.calmFill
                                opacity: 0.35
                            }

                            Rectangle {
                                x: Math.min(bandTrack.width - 2,
                                            Math.max(0, bandTrack.width
                                                     * (baseCol.cmp.value / band.span) - 1))
                                width: 2
                                height: parent.height
                                color: baseCol.cmp.verdict === "typical"
                                       ? Kirigami.Theme.textColor : root.claudeAmberLight
                                Behavior on x { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                            }
                        }
                    }

                    // The verdict is a rank statement, not a p-value: today is
                    // inside or outside the range those days spanned. Seven
                    // days, some of them idle, supports nothing tighter.
                    PlasmaComponents3.Label {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        elide: Text.ElideRight
                        text: {
                            var c = baseCol.cmp;
                            if (c.state === "tooEarly") return root.tr("tooEarlyToCompare");
                            if (c.state !== "ok") return root.tr("needMoreDays");
                            var v = c.verdict === "above" ? root.tr("aboveYourRange")
                                  : c.verdict === "below" ? root.tr("belowYourRange")
                                  : root.tr("withinYourRange");
                            return v + " · " + root.formatTokens(c.value)
                                 + " / " + root.formatTokens(c.expected);
                        }
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.78
                        opacity: 0.5
                    }

                    // The method, spelled out. Without it the ratio looks like
                    // a measurement instead of a projection of a partial day
                    // onto a median of five.
                    PlasmaComponents3.Label {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        elide: Text.ElideRight
                        visible: baseCol.cmp.state === "ok"
                        text: root.tr("medianOf") + " " + baseCol.cmp.days + " "
                            + root.tr("activeDays") + ", " + root.tr("adjustedForHour")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.72
                        opacity: 0.3
                    }
                }
            }

            // ══════════════════════════════════
            // ── Peak Hours ──
            // ══════════════════════════════════
            Rectangle {
                Layout.fillWidth: true
                visible: Object.keys(root.usageData.lifetime?.peakHours ?? {}).length > 0
                implicitHeight: peakCol.implicitHeight + Kirigami.Units.mediumSpacing * 2
                radius: 10; color: root.cardBg

                ColumnLayout {
                    id: peakCol
                    anchors.fill: parent; anchors.margins: Kirigami.Units.mediumSpacing; spacing: 4

                    PlasmaComponents3.Label {
                        text: "Peak hours"; font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8; opacity: 0.4
                    }

                    Item {
                        Layout.fillWidth: true; Layout.preferredHeight: Kirigami.Units.gridUnit * 2.5

                        Canvas {
                            id: peakChart; anchors.fill: parent
                            property var peakData: root.usageData.lifetime?.peakHours ?? {}
                            onPeakDataChanged: requestPaint()
                            onWidthChanged: requestPaint()
                            onPaint: {
                                var ctx = getContext("2d");
                                ctx.clearRect(0, 0, width, height);
                                var data = peakData;
                                if (!data || Object.keys(data).length === 0) return;
                                var vals = []; var maxV = 1;
                                for (var h = 0; h < 24; h++) { var v = data[h.toString()] || 0; vals.push(v); if (v > maxV) maxV = v; }
                                var bw = (width - 4) / 24; var ch = height - 12;
                                for (var i = 0; i < 24; i++) {
                                    var x = 2 + i * bw + 1; var barH = Math.max(1, (vals[i] / maxV) * ch); var y = ch - barH; var w = bw - 2;
                                    var alpha = vals[i] > 0 ? 0.3 + (vals[i] / maxV) * 0.5 : 0.08;
                                    ctx.fillStyle = (i >= 9 && i <= 18) ? Qt.rgba(0.851, 0.467, 0.024, alpha) : Qt.rgba(0.231, 0.510, 0.965, alpha);
                                    ctx.fillRect(x, y, w, barH);
                                    if (i % 6 === 0) {
                                        ctx.fillStyle = Kirigami.Theme.textColor.toString(); ctx.globalAlpha = 0.3;
                                        ctx.font = "7px sans-serif"; ctx.textAlign = "center";
                                        ctx.fillText(i + "h", x + w / 2, height - 1); ctx.globalAlpha = 1.0;
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ══════════════════════════════════
            // ── Footer ──
            // Split into two rows: (1) primary metadata + version/brand,
            // (2) overflow-capable badge row. Keeping them separate prevents
            // badges from growing the popup's implicit width past switchWidth.
            // ══════════════════════════════════
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    Image {
                        source: Qt.resolvedUrl("../icons/" + root.brand.logo)
                        Layout.preferredWidth: 10
                        Layout.preferredHeight: 10
                        sourceSize: Qt.size(10, 10)
                        fillMode: Image.PreserveAspectFit
                        opacity: 0.4
                    }

                    PlasmaComponents3.Label {
                        text: (root.usageData.lifetime?.totalSessions ?? 0) + " sessions"
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.825
                        opacity: 0.3
                    }

                    Rectangle { width: 3; height: 3; radius: 1.5; color: Kirigami.Theme.textColor; opacity: 0.15 }

                    PlasmaComponents3.Label {
                        text: {
                            var s = root.usageData.lifetime?.firstSession ?? "";
                            if (!s) return "";
                            return "since " + new Date(s).toLocaleDateString(Qt.locale(), "MMM yyyy");
                        }
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.825
                        opacity: 0.3
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }

                    // Version
                    PlasmaComponents3.Label {
                        visible: (root.usageData.claudeCodeVersion ?? "") !== ""
                        text: root.usageData.claudeCodeVersion ?? ""
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.828
                        opacity: 0.2
                    }

                    Rectangle {
                        visible: (root.usageData.claudeCodeVersion ?? "") !== ""
                        width: 3; height: 3; radius: 1.5
                        color: Kirigami.Theme.textColor; opacity: 0.15
                    }

                    PlasmaComponents3.Label {
                        text: root.brand.vendor
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                        font.weight: Font.DemiBold
                        opacity: 0.2
                    }
                }

                // Badges line — only rendered when at least one badge is visible,
                // keeps the first footer row clean on cold-start/empty accounts.
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    visible: (root.usageData.streak?.days ?? 0) > 1
                          || (root.usageData.lifetime?.longestSession?.duration ?? 0) > 60000
                          || (root.usageData.settings?.pluginCount ?? 0) > 0

                    // Streak badge
                    Rectangle {
                        visible: (root.usageData.streak?.days ?? 0) > 1
                        radius: height / 2
                        color: Qt.rgba(root.claudeAmber.r, root.claudeAmber.g, root.claudeAmber.b, 0.15)
                        implicitWidth: _streakLbl.implicitWidth + 10
                        implicitHeight: _streakLbl.implicitHeight + 4
                        PlasmaComponents3.Label {
                            id: _streakLbl; anchors.centerIn: parent
                            text: (root.usageData.streak?.days ?? 0) + "d streak"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                            font.weight: Font.Bold; color: root.claudeAmber
                        }
                    }

                    // Longest-session badge
                    Rectangle {
                        visible: (root.usageData.lifetime?.longestSession?.duration ?? 0) > 60000
                        radius: height / 2
                        color: Qt.rgba(root.blueAccent.r, root.blueAccent.g, root.blueAccent.b, 0.12)
                        implicitWidth: _longestLbl.implicitWidth + 10
                        implicitHeight: _longestLbl.implicitHeight + 4
                        PlasmaComponents3.Label {
                            id: _longestLbl; anchors.centerIn: parent
                            text: {
                                var ms = root.usageData.lifetime?.longestSession?.duration ?? 0;
                                var mins = Math.floor(ms / 60000);
                                if (mins >= 60) return "longest " + Math.floor(mins / 60) + "h" + (mins % 60) + "m";
                                return "longest " + mins + "m";
                            }
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                            font.weight: Font.Bold; color: root.blueAccent
                        }
                    }

                    // Plugin-count pill
                    Rectangle {
                        visible: (root.usageData.settings?.pluginCount ?? 0) > 0
                        radius: height / 2
                        color: Qt.rgba(root.greenAccent.r, root.greenAccent.g, root.greenAccent.b, 0.12)
                        implicitWidth: _pluginLbl.implicitWidth + 10
                        implicitHeight: _pluginLbl.implicitHeight + 4
                        PlasmaComponents3.Label {
                            id: _pluginLbl; anchors.centerIn: parent
                            text: (root.usageData.settings?.pluginCount ?? 0) + " plugins"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                            font.weight: Font.Bold; color: root.greenAccent
                        }
                    }

                    Item { Layout.fillWidth: true }
                }
            }

                }
        }
        } // Flickable
    }
}
