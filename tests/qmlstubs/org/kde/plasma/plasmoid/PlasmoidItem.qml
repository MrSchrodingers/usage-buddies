import QtQuick

// PlasmoidItem: the root type of an applet.
//
// Only the surface main.qml assigns to is declared. That is on purpose — a
// missing property here is a hard load error rather than a silent no-op, so
// the day main.qml starts setting something this double does not know about,
// the harness says so instead of quietly laying out a different widget.
//
// The two representations stay Components and are never instantiated here; the
// harness loads the one it wants to measure. Instantiating both would run the
// compact representation's timers for no reason.
Item {
    property Component compactRepresentation: null
    property Component fullRepresentation: null
    property Component toolTipItem: null

    property string toolTipMainText: ""
    property string toolTipSubText: ""
    property string toolTipTextFormat: ""

    property real switchWidth: -1
    property real switchHeight: -1

    property bool expanded: false
    property bool activationTogglesExpanded: true
    property bool hideOnWindowDeactivate: false
    property int preferredRepresentation: 0
}
