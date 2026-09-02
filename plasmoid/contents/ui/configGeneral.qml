import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: page

    property string cfg_provider
    property string cfg_language
    property string cfg_buddyVoice
    property int cfg_buddyFocusMinutes
    property string cfg_buddyInsistence
    property bool cfg_buddyQuietHours
    property string cfg_buddyMemes
    property bool cfg_buddyShadow
    property bool cfg_buddyEscort
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

        Kirigami.Separator {
            Kirigami.FormData.label: "Companion"
            Kirigami.FormData.isSection: true
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
            Kirigami.FormData.label: "Focus session:"
            from: 5
            to: 240
            stepSize: 5
            editable: true
            value: page.cfg_buddyFocusMinutes
            onValueModified: page.cfg_buddyFocusMinutes = value
            textFromValue: function (v) { return v + " min" }
        }

        QQC2.Label {
            Kirigami.FormData.label: ""
            text: "How long a session started from the popup runs. It stays quiet for that long."
            opacity: 0.6
            font.italic: true
            wrapMode: Text.WordWrap
        }

        // The ladder is ordered by how much of the user's attention each step
        // takes. Only the last one takes input away from them, which is why it
        // is spelled out here and is not the default.
        QQC2.ComboBox {
            id: insistenceBox
            Kirigami.FormData.label: "Insistence:"
            textRole: "text"
            valueRole: "value"
            model: [
                { value: "off",     text: "Off — it never chases a waiting session" },
                { value: "speak",   text: "Speak — a line in its bubble, nothing more" },
                { value: "walk",    text: "Walk — it goes and stands by the window that is waiting" },
                { value: "wave",    text: "Wave — it walks over, then waves at you" },
                { value: "pointer", text: "Pointer — it moves your mouse cursor to that window" }
            ]
            currentIndex: Math.max(0, indexOfValue(page.cfg_buddyInsistence))
            onActivated: page.cfg_buddyInsistence = currentValue
        }

        QQC2.Label {
            Kirigami.FormData.label: ""
            text: insistenceBox.currentValue === "pointer"
                  ? "Warning: this step moves your mouse cursor. The companion takes the pointer out of whatever you are doing and drags it to the window that is waiting."
                  : insistenceBox.currentValue === "off"
                  ? "It never escalates, and never touches the pointer — off is the one setting that also stops it running off with your mouse when you drag it around."
                  : "How far it escalates while a session waits on you. The ladder stops at the step chosen here; drag it around for long enough and it still takes the pointer and runs, which is a reply to being handled rather than a step of the ladder."
            opacity: 0.7
            font.italic: true
            wrapMode: Text.WordWrap
        }

        QQC2.CheckBox {
            Kirigami.FormData.label: "Quiet hours:"
            text: "Speak less outside your usual working hours"
            checked: page.cfg_buddyQuietHours
            onToggled: page.cfg_buddyQuietHours = checked
        }

        QQC2.Label {
            Kirigami.FormData.label: ""
            text: "Read from the hours this account has actually worked, not from a schedule someone has to keep up to date."
            opacity: 0.6
            font.italic: true
            wrapMode: Text.WordWrap
        }

        QQC2.ComboBox {
            id: memesBox
            Kirigami.FormData.label: "Visual jokes:"
            textRole: "text"
            valueRole: "value"
            model: [
                { value: "off",   text: "Off — plain sprite, no props" },
                { value: "light", text: "Light — a prop now and then" },
                { value: "full",  text: "Full — a prop on most lines" }
            ]
            currentIndex: Math.max(0, indexOfValue(page.cfg_buddyMemes))
            onActivated: page.cfg_buddyMemes = currentValue
        }

        QQC2.Label {
            Kirigami.FormData.label: ""
            text: "Free to run, paid for in attention: a joke that arrives every time stops registering."
            opacity: 0.6
            font.italic: true
            wrapMode: Text.WordWrap
        }

        QQC2.CheckBox {
            Kirigami.FormData.label: "Shadow:"
            text: "Contact shadow under the character"
            checked: page.cfg_buddyShadow
            onToggled: page.cfg_buddyShadow = checked
        }

        QQC2.Label {
            Kirigami.FormData.label: ""
            text: "Without it the sprite reads as pasted on top of the screen. Costs a little compositing on every frame."
            opacity: 0.6
            font.italic: true
            wrapMode: Text.WordWrap
        }

        QQC2.CheckBox {
            Kirigami.FormData.label: "Escort:"
            text: "Stay with one session until it is resolved"
            checked: page.cfg_buddyEscort
            onToggled: page.cfg_buddyEscort = checked
        }

        QQC2.Label {
            Kirigami.FormData.label: ""
            text: "Off, it rotates over every session that needs you. On, the others wait their turn — quieter, and easier to miss one."
            opacity: 0.6
            font.italic: true
            wrapMode: Text.WordWrap
        }

        Kirigami.Separator {
            Kirigami.FormData.label: "Usage"
            Kirigami.FormData.isSection: true
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
