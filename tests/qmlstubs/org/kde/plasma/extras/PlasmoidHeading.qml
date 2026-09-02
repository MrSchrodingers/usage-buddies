import QtQuick
import QtQuick.Templates as T
import org.kde.kirigami as Kirigami

// PlasmaExtras.PlasmoidHeading: the toolbar strip a popup can put above its
// content. main.qml declares one only to hide it, so all that is needed is a
// type that a Page will accept as its header and that reports no height when
// invisible.
T.ToolBar {
    padding: Kirigami.Units.smallSpacing
    implicitHeight: visible ? Kirigami.Units.gridUnit + padding * 2 : 0
}
