import QtQuick

// P5Support.DataSource, inert by construction.
//
// The real one with `engine: "executable"` runs shell commands. main.qml uses
// it to run the collector, the sessions probe, the Tollens probe and the
// companion control script, and it calls readData() from Component.onCompleted
// and from repeating timers — so a double that forwarded anywhere would have
// the test suite starting and stopping the companion that is running on the
// machine.
//
// connectSource therefore does nothing and newData is never emitted. Tests
// that need the popup populated assign root.usageData directly, which is the
// same thing the real onNewData handler ends up doing.
QtObject {
    property string engine: ""
    property var connectedSources: []
    property var sources: []
    property int interval: 0
    property int intervalAlignment: 0
    readonly property var data: ({})
    readonly property bool valid: true

    signal newData(string sourceName, var payload)
    signal sourceAdded(string source)
    signal sourceRemoved(string source)

    function connectSource(source) { }
    function disconnectSource(source) { }
    function serviceForSource(source) { return null; }
    function keysForSource(source) { return []; }
}
