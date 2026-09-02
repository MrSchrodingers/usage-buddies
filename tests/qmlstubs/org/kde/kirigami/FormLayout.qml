import QtQuick
import QtQuick.Layouts

// Kirigami.FormLayout, as far as a QML-only double can go.
//
// The real one lays out label/field pairs read from a `Kirigami.FormData`
// attached property, and attached properties cannot be declared in QML — they
// need a C++ (or Python-registered) type. So this stands in for the container
// only. Anything importing it still fails to load if it uses
// `Kirigami.FormData`, which is the honest outcome: a file this harness cannot
// lay out must not appear to pass.
ColumnLayout {
    property bool wideMode: true
    property int twinFormLayouts: 0
}
