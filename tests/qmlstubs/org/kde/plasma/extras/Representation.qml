import QtQuick
import QtQuick.Templates as T

// PlasmaExtras.Representation. The real one is a Plasma Page — header,
// contentItem, footer — whose paddings are zero unless it asks to collapse
// over the popup's borders, which this widget does not. Keeping it a Page
// matters: `anchors.fill: parent` inside it fills the contentItem, so the
// Flickable in main.qml gets the area left over by the header, exactly as it
// does in a real popup.
T.Page {
    padding: 0

    property bool collapseMarginsHint: false

    contentItem: Item {}
}
