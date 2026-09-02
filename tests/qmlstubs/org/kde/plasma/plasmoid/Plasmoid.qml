pragma Singleton

import QtQuick

// The `Plasmoid` singleton, reduced to `configuration`.
//
// The keys and their defaults are the ones declared in
// plasmoid/contents/config/main.xml, so a popup laid out through this double
// is laid out with the values a fresh installation actually has. They are
// writable, because main.qml writes them from the header buttons and because a
// test that wants the header at its widest sets buddyMode here.
QtObject {
    readonly property QtObject configuration: QtObject {
        property string provider: "claude"
        property string language: "auto"
        property string displayMode: "full"
        property real planMonthlyCost: 0
        property string buddyMode: "off"
        property string buddyVoice: "table"
        property int buddyFocusMinutes: 25
        property string buddyInsistence: "walk"
        property bool buddyQuietHours: true
        property string buddyMemes: "light"
        property bool buddyShadow: true
        property bool buddyEscort: false
    }

    function setConfiguration(key, value) { configuration[key] = value; }
}
