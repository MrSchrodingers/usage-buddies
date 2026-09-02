import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Scene the layout test renders into.
//
// It takes the already-created applet root and instantiates one of its
// representation Components at a width the test chooses, which is what a
// Plasma popup does with the full representation. The Loader is what makes the
// Component's own creation context survive: every binding inside it still
// resolves against main.qml's root, so the popup measured here is the popup
// the widget would show.
//
// The measuring is done here in QML rather than from Python because several of
// the properties that say whether something was cut off — elide, wrapMode,
// truncated — are QML enums that do not survive the trip through
// QObject::property().
Item {
    id: harness

    property Item widget: null
    property Component representation: null

    // The unit every size in the popup is a multiple of, reported so the test
    // can say what font the numbers below belong to.
    readonly property int gridUnit: Kirigami.Units.gridUnit

    readonly property Item content: repLoader.item
    readonly property int loaderStatus: repLoader.status

    // The sizes the representation asks the popup for. Read here rather than
    // in Python because they are attached properties, and this is the file
    // that imports QtQuick.Layouts.
    readonly property real declaredPreferredWidth: content ? content.Layout.preferredWidth : -1
    readonly property real declaredPreferredHeight: content ? content.Layout.preferredHeight : -1
    readonly property real declaredMinimumWidth: content ? content.Layout.minimumWidth : -1
    readonly property real declaredMaximumHeight: content ? content.Layout.maximumHeight : -1

    // Written by the runner once the scene has been rendered; reading treeJson
    // before that gives the geometry items were born with, which is nothing.
    property int dumpRequest: 0
    property string treeJson: "[]"
    onDumpRequestChanged: treeJson = JSON.stringify(harness.collectTree())

    // Types that place their own children. A child of one of these can never
    // legitimately stick out of it — that is the whole contract of a layout —
    // which is what makes them the frame of reference for the overflow check.
    // An item positioned by anchors can stick out, and main.qml does it on
    // purpose for decorations that overhang a corner.
    readonly property var layoutClasses: ["QQuickRowLayout", "QQuickColumnLayout",
                                          "QQuickGridLayout", "QQuickStackLayout"]

    function typeNameOf(item) {
        // QObject's toString is "ClassName(0xaddress)"; QML-defined types come
        // back as "Label_QMLTYPE_7(0x...)". The address is noise here.
        var s = String(item);
        var paren = s.indexOf("(");
        return paren > 0 ? s.substring(0, paren) : s;
    }

    function collectTree() {
        var root = harness.content;
        var out = [];

        function rec(item, parentIndex, parentIsLayout) {
            var index = out.length;
            var cls = harness.typeNameOf(item);
            var isLayout = harness.layoutClasses.indexOf(cls) >= 0;
            var topLeft = item.mapToItem(root, 0, 0);
            var node = {
                "i": index,
                "parent": parentIndex,
                "cls": cls,
                "x": item.x, "y": item.y,
                "w": item.width, "h": item.height,
                "iw": item.implicitWidth, "ih": item.implicitHeight,
                "visible": item.visible,
                "opacity": item.opacity,
                "clip": item.clip === true,
                "isLayout": isLayout,
                "parentIsLayout": parentIsLayout,
                "absL": topLeft.x, "absT": topLeft.y,
                "absR": topLeft.x + item.width, "absB": topLeft.y + item.height
            };
            if (item.truncated !== undefined && item.text !== undefined) {
                node["isText"] = true;
                node["text"] = String(item.text);
                node["truncated"] = item.truncated === true;
                node["elided"] = item.elide !== Text.ElideNone;
                node["wrapped"] = item.wrapMode !== Text.NoWrap;
                node["contentWidth"] = item.contentWidth;
            }
            if (item.contentWidth !== undefined && node["contentWidth"] === undefined) {
                node["contentWidth"] = item.contentWidth;
            }
            if (item.contentHeight !== undefined) {
                node["contentHeight"] = item.contentHeight;
            }
            out.push(node);

            var kids = item.children;
            for (var k = 0; k < kids.length; ++k) {
                rec(kids[k], index, isLayout);
            }
        }

        if (root) {
            rec(root, -1, false);
        }
        return out;
    }

    Loader {
        id: repLoader
        sourceComponent: harness.representation
        width: harness.width
        height: harness.height
    }
}
