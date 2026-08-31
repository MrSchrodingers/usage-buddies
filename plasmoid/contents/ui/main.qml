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

    // Claude palette
    // Global font scale — multiplier applied to every `pixelSize` binding.
    // Default 1.20 bumps the UI one step up from Plasma's system font size
    // without needing user intervention. Safe to tweak live.
    readonly property real fontScale: 1.20

    readonly property color claudeAmber: "#D97706"
    readonly property color claudeAmberLight: "#F59E0B"
    readonly property color claudeAmberDim: "#92400E"
    readonly property color blueAccent: "#3B82F6"
    readonly property color greenAccent: "#10B981"
    readonly property color redAlert: "#EF4444"
    readonly property color purpleAccent: "#A855F7"    // Opus
    readonly property color pinkAccent: "#EC4899"      // Claude Design
    readonly property color cyanAccent: "#06B6D4"      // Cowork / OAuth apps
    readonly property color cardBg: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.05)
    readonly property color subtleBorder: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.08)

    switchWidth: Kirigami.Units.gridUnit * 24
    switchHeight: Kirigami.Units.gridUnit * 32

    toolTipMainText: "Usage Buddies"
    toolTipSubText: {
        if (!hasData) return "Loading...";
        var p = usageData.rateLimits?.session?.percentUsed ?? 0;
        var base = "Session: " + Math.round(p) + "% | Weekly: " +
                   Math.round(usageData.rateLimits?.weeklyAll?.percentUsed ?? 0) + "%";
        var status = usageData.serviceStatus?.description ?? "";
        return (status && status !== "All Systems Operational") ? base + "\n⚠ " + status : base;
    }

    // ─── Data ───
    // Declarative polling: the executable engine re-runs `source` every
    // `interval` ms on its own. This avoids the connectSource/disconnectSource
    // race where re-connecting an identical source string fails to re-emit
    // onNewData. The systemd timer refreshes widget-data.json independently, so
    // the widget only needs to `cat` it (fast, atomic via os.replace) and also
    // runs the collector itself as a fallback when the timer is disabled.
    property string dataCmd: "$HOME/.local/bin/usage-buddies-collector.py 1>/dev/null 2>/dev/null; cat $HOME/.claude/widget-data.json"

    P5Support.DataSource {
        id: dataLoader
        engine: "executable"
        connectedSources: [root.dataCmd]
        interval: root.refreshInterval
        onNewData: function(source, data) {
            if (data["exit code"] === 0 && data.stdout) {
                try {
                    var parsed = JSON.parse(data.stdout.trim());
                    root.usageData = parsed;
                    root.countdownMinutes = parsed.rateLimits?.session?.resetsInMinutes ?? 0;
                    root.countdownSeconds = 0;
                } catch(e) {
                    console.warn("usage-buddies: failed to parse widget-data.json:", e);
                }
            }
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

    function limitColor(pct) {
        if (pct > 80) return redAlert;
        if (pct > 50) return claudeAmberLight;
        return Kirigami.Theme.textColor;
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
                if (root.displayMode === "weeklyBarOnly")     return compWeeklyBar;
                if (root.displayMode === "fableBarOnly")      return compFableBar;
                if (root.displayMode === "sessionCountdown")  return compSessionCountdown;
                if (root.displayMode === "weeklyCountdown")   return compWeeklyCountdown;
                return compFull;
            }
        }

        // ── Mode: full (default) ──────────────────────────────────
        Component {
            id: compFull
            RowLayout {
                spacing: Kirigami.Units.smallSpacing

                Image {
                    source: Qt.resolvedUrl("../icons/claude-logo.svg")
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
    fullRepresentation: PlasmaExtras.Representation {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 24
        Layout.preferredHeight: Kirigami.Units.gridUnit * 40
        Layout.minimumWidth: Kirigami.Units.gridUnit * 20
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

                // Clawd mascot — 5 animated states + easter egg
                Item {
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

                    // Clawd — hidden when braindead (ghost replaces him)
                    Image {
                        visible: !root.isBraindead
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: 6
                        width: parent.width * 0.7
                        height: parent.height * 0.7
                        source: Qt.resolvedUrl("../icons/clawd.svg")
                        sourceSize: Qt.size(parent.width, parent.height)
                        fillMode: Image.PreserveAspectFit
                    }
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

                ColumnLayout {
                    spacing: 1
                    RowLayout {
                        spacing: 6
                        PlasmaComponents3.Label {
                            text: "Claude"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.5
                            font.weight: Font.Bold
                        }
                        Rectangle {
                            visible: root.hasData
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
                    RowLayout {
                        spacing: Kirigami.Units.smallSpacing
                        // Claude logo small
                        Image {
                            source: Qt.resolvedUrl("../icons/claude-logo.svg")
                            Layout.preferredWidth: 12
                            Layout.preferredHeight: 12
                            sourceSize: Qt.size(12, 12)
                            fillMode: Image.PreserveAspectFit
                        }
                        PlasmaComponents3.Label {
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

                PlasmaComponents3.ToolButton {
                    icon.name: "view-refresh"
                    // Force an immediate re-poll: disconnect then reconnect the
                    // source so the executable engine re-runs it right away.
                    onClicked: {
                        dataLoader.disconnectSource(root.dataCmd);
                        dataLoader.connectSource(root.dataCmd);
                    }
                    PlasmaComponents3.ToolTip { text: "Refresh" }
                }

                // Display mode switcher — cycles through the 4 panel modes
                PlasmaComponents3.ToolButton {
                    id: modeBtn
                    readonly property var modes: ["full", "weeklyBarOnly", "fableBarOnly", "sessionCountdown", "weeklyCountdown"]
                    readonly property var modeIcons: ({
                        "full":             "view-split-left-right",
                        "weeklyBarOnly":    "office-chart-bar",
                        "fableBarOnly":     "office-chart-bar-stacked",
                        "sessionCountdown": "chronometer",
                        "weeklyCountdown":  "view-calendar-week"
                    })
                    readonly property var modeLabels: ({
                        "full":             "Full (default)",
                        "weeklyBarOnly":    "Weekly bar only",
                        "fableBarOnly":     "Fable bar only",
                        "sessionCountdown": "Session countdown",
                        "weeklyCountdown":  "Weekly countdown"
                    })
                    icon.name: modeIcons[root.displayMode] ?? "configure"
                    onClicked: {
                        var idx = modes.indexOf(root.displayMode);
                        var next = modes[(idx + 1) % modes.length];
                        Plasmoid.configuration.displayMode = next;
                    }
                    PlasmaComponents3.ToolTip {
                        text: "Panel mode: " + (modeBtn.modeLabels[root.displayMode] ?? root.displayMode) + "\nClick to cycle"
                    }
                }
            }

            // ══════════════════════════════════
            // ── Session Limit (HERO CARD) ──
            // ══════════════════════════════════
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: sessionInner.implicitHeight + Kirigami.Units.largeSpacing * 2
                radius: 12
                color: root.cardBg
                border.width: 2
                border.color: {
                    var p = root.usageData.rateLimits?.session?.percentUsed ?? 0;
                    if (p > 80) return Qt.rgba(redAlert.r, redAlert.g, redAlert.b, 0.6);
                    if (p > 50) return Qt.rgba(claudeAmberLight.r, claudeAmberLight.g, claudeAmberLight.b, 0.5);
                    return Qt.rgba(claudeAmber.r, claudeAmber.g, claudeAmber.b, 0.35);
                }

                ColumnLayout {
                    id: sessionInner
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.largeSpacing
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        PlasmaComponents3.Label {
                            text: "Current session"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            font.weight: Font.DemiBold
                            opacity: 0.7
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            text: {
                                var m = root.countdownMinutes;
                                var s = root.countdownSeconds;
                                if (m > 60) return "Resets in " + Math.floor(m/60) + "h " + (m%60) + "m";
                                if (m > 0) return "Resets in " + m + "m " + s + "s";
                                if (s > 0) return "Resets in " + s + "s";
                                return "Rolling 5h";
                            }
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.8
                            opacity: 0.4
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
                            property real pct: root.usageData.rateLimits?.session?.percentUsed ?? 0
                            Behavior on pct { NumberAnimation { duration: 800; easing.type: Easing.OutCubic } }
                            onPctChanged: requestPaint()
                            onWidthChanged: requestPaint()

                            onPaint: {
                                var ctx = getContext("2d");
                                ctx.clearRect(0, 0, width, height);
                                var cx = width / 2, cy = height / 2;
                                var r = Math.min(cx, cy) - 6;
                                // Background ring
                                ctx.beginPath();
                                ctx.arc(cx, cy, r, 0, 2 * Math.PI);
                                ctx.strokeStyle = root.subtleBorder.toString();
                                ctx.lineWidth = 8;
                                ctx.stroke();
                                // Progress arc
                                var startAngle = -Math.PI / 2;
                                var endAngle = startAngle + (2 * Math.PI * Math.min(1, pct / 100));
                                ctx.beginPath();
                                ctx.arc(cx, cy, r, startAngle, endAngle);
                                ctx.strokeStyle = barFill(pct, root.claudeAmber).toString();
                                ctx.lineWidth = 8;
                                ctx.lineCap = "round";
                                ctx.stroke();
                            }
                        }

                        PlasmaComponents3.Label {
                            anchors.centerIn: parent
                            property real pct: root.usageData.rateLimits?.session?.percentUsed ?? 0
                            Behavior on pct { NumberAnimation { duration: 800; easing.type: Easing.OutCubic } }
                            text: Math.round(pct) + "%"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 2.5
                            font.weight: Font.Bold
                            color: limitColor(pct)
                        }
                    }

                    // Predictive limit alert
                    PlasmaComponents3.Label {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignHCenter
                        visible: {
                            var eta = root.usageData.limitEta?.minutesToLimit;
                            return eta != null && eta < 120 && eta > 0;
                        }
                        text: "At current rate, limit in " + (root.usageData.limitEta?.label ?? "?")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.828
                        font.italic: true
                        horizontalAlignment: Text.AlignHCenter
                        color: root.claudeAmberLight
                        opacity: 0.7
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
                        text: "Weekly limits"
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85
                        font.weight: Font.DemiBold
                        opacity: 0.5
                    }

                    // All models row
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true
                            Rectangle { width: 8; height: 8; radius: 4; color: root.blueAccent }
                            PlasmaComponents3.Label {
                                text: "All models"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            }
                            Item { Layout.fillWidth: true }
                            PlasmaComponents3.Label {
                                visible: (root.usageData.rateLimits?.weeklyAll?.resetsLabel ?? "") !== ""
                                text: "Resets " + (root.usageData.rateLimits?.weeklyAll?.resetsLabel ?? "")
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                                opacity: 0.35
                            }
                            PlasmaComponents3.Label {
                                property real pct: root.usageData.rateLimits?.weeklyAll?.percentUsed ?? 0
                                text: Math.round(pct) + "%"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.1
                                font.weight: Font.Bold
                                color: limitColor(pct)
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 6; radius: 3
                            color: root.subtleBorder
                            Rectangle {
                                property real pct: root.usageData.rateLimits?.weeklyAll?.percentUsed ?? 0
                                width: parent.width * Math.min(1, pct / 100)
                                height: parent.height; radius: 3
                                color: barFill(pct, root.blueAccent)
                                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                            }
                        }
                    }

                    // Sonnet only row
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true
                            Rectangle { width: 8; height: 8; radius: 4; color: root.greenAccent }
                            PlasmaComponents3.Label {
                                text: "Sonnet only"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            }
                            Item { Layout.fillWidth: true }
                            PlasmaComponents3.Label {
                                visible: (root.usageData.rateLimits?.weeklySonnet?.resetsLabel ?? "") !== ""
                                text: "Resets " + (root.usageData.rateLimits?.weeklySonnet?.resetsLabel ?? "")
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                                opacity: 0.35
                            }
                            PlasmaComponents3.Label {
                                property real pct: root.usageData.rateLimits?.weeklySonnet?.percentUsed ?? 0
                                text: Math.round(pct) + "%"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.1
                                font.weight: Font.Bold
                                color: limitColor(pct)
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 6; radius: 3
                            color: root.subtleBorder
                            Rectangle {
                                property real pct: root.usageData.rateLimits?.weeklySonnet?.percentUsed ?? 0
                                width: parent.width * Math.min(1, pct / 100)
                                height: parent.height; radius: 3
                                color: barFill(pct, root.greenAccent)
                                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                            }
                        }
                    }

                    // Opus only row (visible only when API populated the field)
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        visible: root.usageData.rateLimits?.weeklyOpus !== undefined &&
                                 root.usageData.rateLimits?.weeklyOpus !== null

                        RowLayout {
                            Layout.fillWidth: true
                            Rectangle { width: 8; height: 8; radius: 4; color: root.purpleAccent }
                            PlasmaComponents3.Label {
                                text: "Opus only"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            }
                            Item { Layout.fillWidth: true }
                            PlasmaComponents3.Label {
                                visible: (root.usageData.rateLimits?.weeklyOpus?.resetsLabel ?? "") !== ""
                                text: "Resets " + (root.usageData.rateLimits?.weeklyOpus?.resetsLabel ?? "")
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                                opacity: 0.35
                            }
                            PlasmaComponents3.Label {
                                property real pct: root.usageData.rateLimits?.weeklyOpus?.percentUsed ?? 0
                                text: Math.round(pct) + "%"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.1
                                font.weight: Font.Bold
                                color: limitColor(pct)
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 6; radius: 3
                            color: root.subtleBorder
                            Rectangle {
                                property real pct: root.usageData.rateLimits?.weeklyOpus?.percentUsed ?? 0
                                width: parent.width * Math.min(1, pct / 100)
                                height: parent.height; radius: 3
                                color: barFill(pct, root.purpleAccent)
                                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                            }
                        }
                    }

                    // Fable only row (visible only when the field is populated)
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        visible: root.usageData.rateLimits?.weeklyFable !== undefined &&
                                 root.usageData.rateLimits?.weeklyFable !== null

                        RowLayout {
                            Layout.fillWidth: true
                            Rectangle { width: 8; height: 8; radius: 4; color: root.blueAccent }
                            PlasmaComponents3.Label {
                                text: "Fable only"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            }
                            Item { Layout.fillWidth: true }
                            PlasmaComponents3.Label {
                                visible: (root.usageData.rateLimits?.weeklyFable?.resetsLabel ?? "") !== ""
                                text: "Resets " + (root.usageData.rateLimits?.weeklyFable?.resetsLabel ?? "")
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                                opacity: 0.35
                            }
                            PlasmaComponents3.Label {
                                property real pct: root.usageData.rateLimits?.weeklyFable?.percentUsed ?? 0
                                text: Math.round(pct) + "%"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.1
                                font.weight: Font.Bold
                                color: limitColor(pct)
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 6; radius: 3
                            color: root.subtleBorder
                            Rectangle {
                                property real pct: root.usageData.rateLimits?.weeklyFable?.percentUsed ?? 0
                                width: parent.width * Math.min(1, pct / 100)
                                height: parent.height; radius: 3
                                color: barFill(pct, root.blueAccent)
                                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                            }
                        }
                    }

                    // Claude Design row (API codename: omelette)
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        visible: root.usageData.rateLimits?.weeklyDesign !== undefined &&
                                 root.usageData.rateLimits?.weeklyDesign !== null

                        RowLayout {
                            Layout.fillWidth: true
                            Rectangle { width: 8; height: 8; radius: 4; color: root.pinkAccent }
                            PlasmaComponents3.Label {
                                text: "Claude Design"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            }
                            Item { Layout.fillWidth: true }
                            PlasmaComponents3.Label {
                                visible: (root.usageData.rateLimits?.weeklyDesign?.resetsLabel ?? "") !== ""
                                text: "Resets " + (root.usageData.rateLimits?.weeklyDesign?.resetsLabel ?? "")
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                                opacity: 0.35
                            }
                            PlasmaComponents3.Label {
                                property real pct: root.usageData.rateLimits?.weeklyDesign?.percentUsed ?? 0
                                text: Math.round(pct) + "%"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.1
                                font.weight: Font.Bold
                                color: limitColor(pct)
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 6; radius: 3
                            color: root.subtleBorder
                            Rectangle {
                                property real pct: root.usageData.rateLimits?.weeklyDesign?.percentUsed ?? 0
                                width: parent.width * Math.min(1, pct / 100)
                                height: parent.height; radius: 3
                                color: barFill(pct, root.pinkAccent)
                                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                            }
                        }
                    }

                    // OAuth apps row
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        visible: root.usageData.rateLimits?.weeklyOauthApps !== undefined &&
                                 root.usageData.rateLimits?.weeklyOauthApps !== null

                        RowLayout {
                            Layout.fillWidth: true
                            Rectangle { width: 8; height: 8; radius: 4; color: root.cyanAccent }
                            PlasmaComponents3.Label {
                                text: "OAuth apps"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            }
                            Item { Layout.fillWidth: true }
                            PlasmaComponents3.Label {
                                visible: (root.usageData.rateLimits?.weeklyOauthApps?.resetsLabel ?? "") !== ""
                                text: "Resets " + (root.usageData.rateLimits?.weeklyOauthApps?.resetsLabel ?? "")
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                                opacity: 0.35
                            }
                            PlasmaComponents3.Label {
                                property real pct: root.usageData.rateLimits?.weeklyOauthApps?.percentUsed ?? 0
                                text: Math.round(pct) + "%"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.1
                                font.weight: Font.Bold
                                color: limitColor(pct)
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 6; radius: 3
                            color: root.subtleBorder
                            Rectangle {
                                property real pct: root.usageData.rateLimits?.weeklyOauthApps?.percentUsed ?? 0
                                width: parent.width * Math.min(1, pct / 100)
                                height: parent.height; radius: 3
                                color: barFill(pct, root.cyanAccent)
                                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                            }
                        }
                    }

                    // Cowork (Claude Code teams) row
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        visible: root.usageData.rateLimits?.weeklyCowork !== undefined &&
                                 root.usageData.rateLimits?.weeklyCowork !== null

                        RowLayout {
                            Layout.fillWidth: true
                            Rectangle { width: 8; height: 8; radius: 4; color: root.claudeAmberLight }
                            PlasmaComponents3.Label {
                                text: "Cowork"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            }
                            Item { Layout.fillWidth: true }
                            PlasmaComponents3.Label {
                                visible: (root.usageData.rateLimits?.weeklyCowork?.resetsLabel ?? "") !== ""
                                text: "Resets " + (root.usageData.rateLimits?.weeklyCowork?.resetsLabel ?? "")
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                                opacity: 0.35
                            }
                            PlasmaComponents3.Label {
                                property real pct: root.usageData.rateLimits?.weeklyCowork?.percentUsed ?? 0
                                text: Math.round(pct) + "%"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 1.1
                                font.weight: Font.Bold
                                color: limitColor(pct)
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 6; radius: 3
                            color: root.subtleBorder
                            Rectangle {
                                property real pct: root.usageData.rateLimits?.weeklyCowork?.percentUsed ?? 0
                                width: parent.width * Math.min(1, pct / 100)
                                height: parent.height; radius: 3
                                color: barFill(pct, root.claudeAmberLight)
                                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                            }
                        }
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
                            text: "Credits"
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
                            text: "Auto-reload"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82; opacity: 0.5
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            property bool on: root.usageData.rateLimits?.credits?.autoReload ?? false
                            text: on ? "ON" : "OFF"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85
                            font.weight: Font.Bold
                            color: on ? root.greenAccent : root.claudeAmberLight
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
                            text: "Extra Usage"
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.9
                            font.weight: Font.DemiBold; opacity: 0.55
                        }
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            property bool on: root.usageData.rateLimits?.extraUsage?.enabled ?? false
                            radius: height / 2
                            color: Qt.rgba(on ? root.greenAccent.r : root.redAlert.r,
                                           on ? root.greenAccent.g : root.redAlert.g,
                                           on ? root.greenAccent.b : root.redAlert.b, 0.18)
                            implicitWidth: _extraLbl.implicitWidth + 12
                            implicitHeight: _extraLbl.implicitHeight + 4
                            PlasmaComponents3.Label {
                                id: _extraLbl; anchors.centerIn: parent
                                text: parent.on ? "Active" : "Disabled"
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82
                                font.weight: Font.Bold
                                color: parent.on ? root.greenAccent : root.redAlert
                            }
                        }
                    }

                    // Extra usage: monthly limit + used
                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        visible: root.usageData.rateLimits?.extraUsage != null
                        PlasmaComponents3.Label {
                            text: "Monthly limit"
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
                        visible: root.usageData.rateLimits?.extraUsage != null

                        RowLayout {
                            Layout.fillWidth: true
                            PlasmaComponents3.Label {
                                text: "Used"
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
                            onClicked: Qt.openUrlExternally("https://downdetector.com/status/claude-ai/")
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
            // ── Burn Rate & Errors Card ──
            // ══════════════════════════════════
            Rectangle {
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

                    // Today's cost + runway — only when we have credits info to project against
                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        visible: (root.usageData.today?.costUSD ?? 0) > 0 || (root.usageData.costProjection?.runwayDays ?? null) !== null
                        Kirigami.Icon { source: "office-chart-bar"; Layout.preferredWidth: 14; Layout.preferredHeight: 14; opacity: 0.5 }
                        PlasmaComponents3.Label { text: "Cost today"; font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.82; opacity: 0.6 }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents3.Label {
                            property real usd: root.usageData.today?.costUSD ?? 0
                            property var runway: root.usageData.costProjection?.runwayDays ?? null
                            text: {
                                var base = "$" + usd.toFixed(2);
                                if (runway !== null && runway < 14) base += " · " + runway.toFixed(1) + "d left";
                                return base;
                            }
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.85; font.weight: Font.Bold
                            color: (runway !== null && runway < 2) ? root.redAlert
                                 : (runway !== null && runway < 7) ? root.claudeAmberLight
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
                    text: "claude.ai"
                    icon.name: "internet-web-browser"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.828
                    onClicked: Qt.openUrlExternally("https://claude.ai")
                }

                PlasmaComponents3.Button {
                    Layout.fillWidth: true
                    text: "Status"
                    icon.name: "network-connect"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.828
                    onClicked: Qt.openUrlExternally("https://status.claude.com")
                }

                PlasmaComponents3.Button {
                    Layout.fillWidth: true
                    text: "Copy Stats"
                    icon.name: "edit-copy"
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * root.fontScale * 0.828
                    onClicked: {
                        var s = root.usageData;
                        var stats = "Claude " + new Date().toLocaleDateString()
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
                        source: Qt.resolvedUrl("../icons/claude-logo.svg")
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
                        text: "Anthropic"
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
        } // Flickable
    }
}
