import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: page

    property string cfg_provider
    property string cfg_language
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
