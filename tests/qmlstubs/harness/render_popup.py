"""Render one representation of the plasmoid and dump the geometry it got.

Run as a subprocess by tests/test_qml_layout.py, never imported by it. Two
reasons for the separate process:

  * The rest of the suite builds the companion, which is a QWidget, so it
    creates a QApplication on the xcb platform. A QGuiApplication made here
    first would be handed to it by QApplication.instance() and it would fail to
    make a widget out of it. There is one application object per process and
    these two tests want different ones.
  * It takes a QML file path as an argument, so the same harness can be pointed
    at a version of main.qml checked out of git — which is how the test proves
    it can still fail.

Writes JSON to stdout: the sizes the representation asked for, and one flat
record per item in the scene with its geometry. All judgement lives in the
test; this only measures.
"""
import argparse
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QFont, QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlComponent, QQmlEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402

HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "PopupHarness.qml")
STUBS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def die(message, errors=()):
    json.dump({"ok": False, "error": message,
               "errors": [str(e) for e in errors]}, sys.stdout)
    sys.stdout.write("\n")
    raise SystemExit(2)


def create(engine, path):
    component = QQmlComponent(engine, QUrl.fromLocalFile(path))
    if component.errors():
        die("%s did not load" % path,
            [e.toString() for e in component.errors()])
    obj = component.create()
    if obj is None:
        die("%s produced no object" % path)
    # The component owns nothing; keep it alive alongside the object or the
    # compilation unit goes away under the running scene.
    return component, obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qml", required=True)
    ap.add_argument("--stubs", default=STUBS)
    ap.add_argument("--font-px", type=int, required=True)
    ap.add_argument("--scenario", default=None,
                    help="JSON file: {config: {...}, properties: {...}}")
    ap.add_argument("--width", required=True,
                    help="'preferred', 'minimum' or a number of pixels")
    ap.add_argument("--representation", default="fullRepresentation")
    args = ap.parse_args()

    app = QGuiApplication(sys.argv[:1])

    # Pinned rather than inherited. Every size in the popup is a multiple of
    # Kirigami.Units.gridUnit, which is the height of one line of this font, so
    # the machine's font settings would otherwise decide whether the widget
    # fits. A font whose size is given in points also reports pixelSize -1,
    # which would collapse every label in main.qml to nothing, since they are
    # all sized as defaultFont.pixelSize * something.
    font = QFont(app.font())
    font.setPixelSize(args.font_px)
    app.setFont(font)

    engine = QQmlEngine()
    engine.addImportPath(args.stubs)

    scenario = {}
    if args.scenario:
        with open(args.scenario, encoding="utf-8") as fh:
            scenario = json.load(fh)

    configuration = engine.singletonInstance(
        "org.kde.plasma.plasmoid", "Plasmoid").property("configuration")
    for key, value in (scenario.get("config") or {}).items():
        if configuration.metaObject().indexOfProperty(key) < 0:
            die("no such configuration key in the Plasmoid double: %s" % key)
        configuration.setProperty(key, value)

    _widget_component, widget = create(engine, args.qml)

    for key, value in (scenario.get("properties") or {}).items():
        if widget.metaObject().indexOfProperty(key) < 0:
            die("main.qml has no property %s" % key)
        widget.setProperty(key, value)

    representation = widget.property(args.representation)
    if representation is None:
        die("main.qml declares no %s" % args.representation)

    _harness_component, harness = create(engine, HARNESS)
    harness.setProperty("widget", widget)
    harness.setProperty("representation", representation)

    window = QQuickWindow()
    harness.setParentItem(window.contentItem())
    window.show()
    app.processEvents()

    declared = {
        "preferredWidth": harness.property("declaredPreferredWidth"),
        "preferredHeight": harness.property("declaredPreferredHeight"),
        "minimumWidth": harness.property("declaredMinimumWidth"),
        "maximumHeight": harness.property("declaredMaximumHeight"),
    }
    if harness.property("content") is None:
        die("the representation did not instantiate (Loader status %s)"
            % harness.property("loaderStatus"))

    if args.width == "preferred":
        width = declared["preferredWidth"]
    elif args.width == "minimum":
        width = declared["minimumWidth"]
    else:
        width = float(args.width)
    height = declared["preferredHeight"]
    if not width or width <= 0 or not height or height <= 0:
        die("the representation declared no usable size: %r" % declared)

    harness.setWidth(width)
    harness.setHeight(height)
    window.resize(int(round(width)), int(round(height)))
    # Kept as insurance, not because it was needed here: on this Qt the
    # layouts arrange as soon as the sizes are set, and the tree comes out
    # identical with these three lines removed. A Qt that defers arranging to
    # updatePolish would need a render pass, and grabWindow is the synchronous
    # one. It costs a few milliseconds. The guard against measuring an
    # unarranged scene is not this — it is
    # test_every_visible_label_and_button_has_a_size, which fails when the
    # geometry is all zeroes.
    for _ in range(3):
        app.processEvents()
    window.grabWindow()
    app.processEvents()

    harness.setProperty("dumpRequest", harness.property("dumpRequest") + 1)
    nodes = json.loads(harness.property("treeJson"))
    content = harness.property("content")
    json.dump({
        "ok": True,
        "qml": args.qml,
        "fontPx": args.font_px,
        "gridUnit": harness.property("gridUnit"),
        "renderedWidth": content.width(),
        "renderedHeight": content.height(),
        "declared": declared,
        "nodes": nodes,
    }, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
