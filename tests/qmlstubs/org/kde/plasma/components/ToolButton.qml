import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import org.kde.kirigami as Kirigami

// PlasmaComponents3.ToolButton.
//
// This is the double whose width decides whether the harness can see a header
// row overflow at all, so it reproduces the real one's sizing rather than
// approximating it. From plasma-framework's ToolButton.qml and its private
// ButtonContent/ButtonBackground:
//
//   implicitWidth = max(background implicit + insets, content implicit + padding)
//   background implicit width = gridUnit + horizontal margins
//   content    = the icon at iconSizes.smallMedium for a flat button
//                (ButtonContent.defaultIconSize), beside the label if any
//
// The one number that cannot be read from those files is the padding: it comes
// from the margins of the Breeze SVG frame, which is theme data. smallSpacing
// per side is this harness's model of it, and it is the only fabricated
// quantity in the chain.
//
// The icon is never loaded — there is no icon theme offscreen — so the icon
// column is sized from the declared icon size instead of from a pixmap. A real
// IconImage that fails to load measures zero, and a zero-width button is
// precisely the failure that would make every layout in this repository appear
// to fit.
T.ToolButton {
    id: control

    flat: true

    readonly property int iconExtentHint: Kirigami.Units.iconSizes.smallMedium
    readonly property bool hasIconHint: icon.name !== "" || String(icon.source) !== ""
    readonly property bool hasTextHint: text !== ""

    leftPadding: Kirigami.Units.smallSpacing
    rightPadding: Kirigami.Units.smallSpacing
    topPadding: Kirigami.Units.smallSpacing
    bottomPadding: Kirigami.Units.smallSpacing

    spacing: Kirigami.Units.smallSpacing

    implicitWidth: Math.max(Kirigami.Units.gridUnit + leftPadding + rightPadding,
                            implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(Kirigami.Units.gridUnit + topPadding + bottomPadding,
                             implicitContentHeight + topPadding + bottomPadding)

    contentItem: RowLayout {
        spacing: control.hasIconHint && control.hasTextHint ? control.spacing : 0

        Item {
            visible: control.hasIconHint
            implicitWidth: control.icon.width > 0 ? control.icon.width : control.iconExtentHint
            implicitHeight: control.icon.height > 0 ? control.icon.height : control.iconExtentHint
            Layout.alignment: Qt.AlignCenter
        }

        Label {
            visible: control.hasTextHint
            text: control.text
            font: control.font
            verticalAlignment: Text.AlignVCenter
            Layout.alignment: Qt.AlignCenter
        }
    }

    background: Item {
        implicitWidth: Kirigami.Units.gridUnit + control.leftPadding + control.rightPadding
        implicitHeight: Kirigami.Units.gridUnit + control.topPadding + control.bottomPadding
    }
}
