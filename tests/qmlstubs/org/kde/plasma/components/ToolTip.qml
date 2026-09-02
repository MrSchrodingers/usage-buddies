import QtQuick
import QtQuick.Templates as T

// PlasmaComponents3.ToolTip. Declared inside buttons all over main.qml and
// never shown by the harness — a Popup is not a visual child, so it
// contributes nothing to the layout. It exists so those declarations resolve.
T.ToolTip {
    visible: false
}
