import QtQuick
import org.kde.kirigami as Kirigami

// Kirigami.Icon. It paints nothing — there is no icon theme under the
// offscreen platform — but it keeps the implicit size of a real one, because
// the callers that do not set an explicit Layout size rely on the icon to
// occupy a column of its own.
Item {
    id: icon

    property var source: ""
    property color color: "transparent"
    property bool selected: false
    property bool isMask: false
    property bool active: false
    property bool valid: String(source) !== ""
    property int status: Image.Ready
    property int placeholder: 0

    implicitWidth: Kirigami.Units.iconSizes.smallMedium
    implicitHeight: Kirigami.Units.iconSizes.smallMedium
}
