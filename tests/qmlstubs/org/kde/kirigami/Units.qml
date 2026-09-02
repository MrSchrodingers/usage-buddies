pragma Singleton

import QtQuick

// Kirigami.Units. Everything here is derived from the font the way Kirigami
// derives it, rather than being written down as pixels: gridUnit is the height
// of one line of the default font, and the spacings are fractions of it. A
// widget laid out in grid units therefore scales with the test font the same
// way it scales with the user's.
//
// The iconSizes are the fixed ladder Kirigami documents (16/22/32/48/64/128);
// they are not derived from anything and are reproduced as constants.
QtObject {
    id: units

    readonly property FontMetrics fontMetrics: FontMetrics {
        font: Qt.application.font
    }

    readonly property int gridUnit: Math.round(fontMetrics.height)

    // Kirigami floors gridUnit/4 and keeps a floor of 2, so a tiny font still
    // leaves a gap between two adjacent controls.
    readonly property int smallSpacing: Math.max(2, Math.floor(gridUnit / 4))
    readonly property int mediumSpacing: Math.round(smallSpacing * 1.5)
    readonly property int largeSpacing: smallSpacing * 2
    readonly property int veryLongDuration: 400
    readonly property int longDuration: 200
    readonly property int shortDuration: 100
    readonly property int veryShortDuration: 50
    readonly property int humanMoment: 2000
    readonly property int toolTipDelay: 700

    readonly property QtObject iconSizes: QtObject {
        readonly property int sizeForLabels: units.gridUnit
        readonly property int small: 16
        readonly property int smallMedium: 22
        readonly property int medium: 32
        readonly property int large: 48
        readonly property int huge: 64
        readonly property int enormous: 128
    }
}
