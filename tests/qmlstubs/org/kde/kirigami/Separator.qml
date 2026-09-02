import QtQuick
import org.kde.kirigami as Kirigami

// Kirigami.Separator: a hairline. One logical pixel thick, no implicit length,
// so it takes whatever the layout gives it along its long axis.
Rectangle {
    color: Qt.rgba(Kirigami.Theme.textColor.r,
                   Kirigami.Theme.textColor.g,
                   Kirigami.Theme.textColor.b, 0.15)
    implicitWidth: 1
    implicitHeight: 1
}
