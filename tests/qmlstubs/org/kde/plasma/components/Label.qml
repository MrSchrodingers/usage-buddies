import QtQuick
import QtQuick.Templates as T
import org.kde.kirigami as Kirigami

// PlasmaComponents3.Label. The real one is a QtQuick.Templates Label with the
// theme's colour on it, so this is the same type with the same two lines: the
// text is measured by Qt's font engine, not by anything invented here. That is
// what lets the harness see a label that no longer fits its column.
T.Label {
    horizontalAlignment: Text.AlignLeft
    activeFocusOnTab: false
    color: Kirigami.Theme.textColor
    linkColor: Kirigami.Theme.linkColor
    opacity: enabled ? 1 : 0.75
}
