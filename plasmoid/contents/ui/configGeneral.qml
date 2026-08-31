import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: page

    property string cfg_provider
    property string cfg_language

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
