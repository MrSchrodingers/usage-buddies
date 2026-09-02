import QtQuick
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents3

// Control scene for the doubles themselves.
//
// The failure this exists to catch is the quiet one: a double that reports
// zero width makes every layout in the popup fit, and the whole geometry suite
// goes green while measuring nothing. So the test asserts these numbers before
// it trusts any of the others — a label has to get wider when its text gets
// longer, and a button has to be as wide as the icon it is drawn around.
Item {
    id: probe

    readonly property real shortLabelWidth: shortLabel.implicitWidth
    readonly property real longLabelWidth: longLabel.implicitWidth
    readonly property real labelHeight: shortLabel.implicitHeight
    readonly property real emptyLabelWidth: emptyLabel.implicitWidth

    readonly property real iconButtonWidth: iconButton.implicitWidth
    readonly property real iconButtonHeight: iconButton.implicitHeight
    readonly property real textButtonWidth: textButton.implicitWidth
    readonly property real bareButtonWidth: bareButton.implicitWidth

    readonly property real iconWidth: someIcon.implicitWidth
    readonly property real iconHeight: someIcon.implicitHeight

    readonly property int gridUnit: Kirigami.Units.gridUnit
    readonly property int smallSpacing: Kirigami.Units.smallSpacing
    readonly property int mediumSpacing: Kirigami.Units.mediumSpacing
    readonly property int largeSpacing: Kirigami.Units.largeSpacing
    readonly property int smallMediumIcon: Kirigami.Units.iconSizes.smallMedium
    readonly property int hugeIcon: Kirigami.Units.iconSizes.huge
    readonly property real defaultFontPixelSize: Kirigami.Theme.defaultFont.pixelSize

    PlasmaComponents3.Label { id: shortLabel; text: "Hi" }
    PlasmaComponents3.Label { id: longLabel; text: "Hi, and a good deal more text than that" }
    PlasmaComponents3.Label { id: emptyLabel; text: "" }

    PlasmaComponents3.ToolButton { id: iconButton; icon.name: "view-refresh" }
    PlasmaComponents3.ToolButton { id: textButton; icon.name: "view-refresh"; text: "Refresh" }
    PlasmaComponents3.ToolButton { id: bareButton }

    Kirigami.Icon { id: someIcon; source: "chronometer" }
}
