import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: page

    property string cfg_provider
    property string cfg_language
    property string cfg_buddyVoice
    property double cfg_planMonthlyCost

    Kirigami.FormLayout {
        anchors.left: parent.left
        anchors.right: parent.right

        QQC2.ComboBox {
            id: providerBox
            Kirigami.FormData.label: "Usage source:"
            textRole: "text"
            valueRole: "value"
            model: [
                { value: "claude", text: "Claude — Claude Code / claude.ai" },
                { value: "codex",  text: "Codex — Codex CLI / chatgpt.com" }
            ]
            currentIndex: Math.max(0, indexOfValue(page.cfg_provider))
            onActivated: page.cfg_provider = currentValue
        }

        QQC2.ComboBox {
            id: languageBox
            Kirigami.FormData.label: "Language:"
            textRole: "text"
            valueRole: "value"
            model: [
                { value: "auto", text: "Automatic (follow desktop)" },
                { value: "en",   text: "English" },
                { value: "pt",   text: "Português" }
            ]
            currentIndex: Math.max(0, indexOfValue(page.cfg_language))
            onActivated: page.cfg_language = currentValue
        }

        // The written table costs nothing and never waits. Claude writes lines
        // about the actual state of the machine, in batches of twelve —
        // measured at about $0.0026 a line, against a subscription this widget
        // is already watching. Off by default: it is real spending.
        QQC2.ComboBox {
            id: voiceBox
            Kirigami.FormData.label: "Companion voice:"
            textRole: "text"
            valueRole: "value"
            model: [
                { value: "table",  text: "Written lines — free, instant" },
                { value: "claude", text: "Claude — about $0.003 per line" }
            ]
            currentIndex: Math.max(0, indexOfValue(page.cfg_buddyVoice))
            onActivated: page.cfg_buddyVoice = currentValue
        }

        QQC2.SpinBox {
            Kirigami.FormData.label: "Plan cost per month:"
            from: 0
            to: 100000
            stepSize: 10
            editable: true
            value: page.cfg_planMonthlyCost
            onValueModified: page.cfg_planMonthlyCost = value
            textFromValue: function (v) { return v === 0 ? "not set" : String(v) }
        }

        QQC2.Label {
            Kirigami.FormData.label: ""
            text: "Leave at zero to hide the payback figure."
            opacity: 0.6
            font.italic: true
        }

        QQC2.Label {
            Kirigami.FormData.label: ""
            text: providerBox.currentValue === "codex"
                  ? "Reads ~/.codex/sessions plus the ChatGPT usage endpoints."
                  : "Reads ~/.claude plus the claude.ai usage endpoints."
            opacity: 0.7
            wrapMode: Text.WordWrap
        }
    }
}
