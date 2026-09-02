pragma Singleton

import QtQuick

// Kirigami.Theme, reduced to what the widget reads from it.
//
// `defaultFont` matters more than it looks: main.qml sizes almost every label
// as `Kirigami.Theme.defaultFont.pixelSize * something`, so a font whose size
// is expressed in points would hand back pixelSize -1 and collapse every label
// in the popup to nothing. The harness sets an explicit pixel size on the
// application font for exactly that reason; this only passes it through.
QtObject {
    readonly property font defaultFont: Qt.application.font
    readonly property font smallFont: Qt.application.font
    readonly property color textColor: "#fcfcfc"
    readonly property color disabledTextColor: "#a0a0a0"
    readonly property color backgroundColor: "#31363b"
    readonly property color highlightColor: "#3daee9"
    readonly property color highlightedTextColor: "#fcfcfc"
    readonly property color linkColor: "#2980b9"
    readonly property color positiveTextColor: "#27ae60"
    readonly property color neutralTextColor: "#f67400"
    readonly property color negativeTextColor: "#da4453"
}
