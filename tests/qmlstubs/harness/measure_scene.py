"""Instantiate one QML scene and print the properties asked for, as JSON.

Used by tests/test_qml_layout.py for the control scene that checks the doubles
report real sizes. Separate process for the same reason as render_popup.py: the
suite's other Qt tests want a QApplication on xcb, and there is one application
object per process.
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

STUBS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qml", required=True)
    ap.add_argument("--stubs", default=STUBS)
    ap.add_argument("--font-px", type=int, required=True)
    args = ap.parse_args()

    app = QGuiApplication(sys.argv[:1])
    font = QFont(app.font())
    font.setPixelSize(args.font_px)
    app.setFont(font)

    engine = QQmlEngine()
    engine.addImportPath(args.stubs)
    component = QQmlComponent(engine, QUrl.fromLocalFile(args.qml))
    if component.errors():
        json.dump({"ok": False, "error": "%s did not load" % args.qml,
                   "errors": [e.toString() for e in component.errors()]},
                  sys.stdout)
        sys.stdout.write("\n")
        raise SystemExit(2)
    item = component.create()

    # A window and one render pass, for the same reason as in
    # render_popup.py: not needed on this Qt, kept for one that defers
    # arranging a control's content until it is polished.
    window = QQuickWindow()
    item.setParentItem(window.contentItem())
    window.resize(600, 400)
    window.show()
    for _ in range(3):
        app.processEvents()
    window.grabWindow()
    app.processEvents()

    meta = item.metaObject()
    values = {}
    for i in range(meta.propertyOffset(), meta.propertyCount()):
        name = meta.property(i).name()
        values[name] = item.property(name)
    values["fontFamily"] = app.font().family()
    values["fontPixelSize"] = app.font().pixelSize()
    json.dump({"ok": True, "values": values}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
