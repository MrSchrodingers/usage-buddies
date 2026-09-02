import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import org.kde.kirigami as Kirigami

// PlasmaComponents3.Button. Same shape as the ToolButton double, minus flat:
// a raised button uses the smaller icon (ButtonContent.defaultIconSize picks
// iconSizes.small when the button is not flat) and gets the same modelled
// padding.
T.Button {
    id: control

    readonly property int iconExtentHint: Kirigami.Units.iconSizes.small
    readonly property bool hasIconHint: icon.name !== "" || String(icon.source) !== ""
    readonly property bool hasTextHint: text !== ""

    leftPadding: Kirigami.Units.smallSpacing * 2
    rightPadding: Kirigami.Units.smallSpacing * 2
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
