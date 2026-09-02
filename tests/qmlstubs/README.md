QML doubles for the modules `plasmoid/contents/ui/*.qml` imports.

`org.kde.plasma.*`, `org.kde.kirigami` and the `Plasmoid` singleton only resolve
inside a running Plasma session, so nothing here can load the real ones. These
doubles exist to answer one question the text-reading tests cannot: does the QML
still *fit* when it is laid out.

That makes their measurements the load-bearing part. A double that reports zero
width makes every layout fit and turns the whole harness permanently green, so
each one below either measures for real (text through Qt's own font metrics) or
reproduces the geometry of the type it stands in for, taken from the installed
Plasma sources and named in a comment where it was taken from.
`test_qml_layout.py::test_doubles_measure_*` is the guard: it fails if a double
starts reporting zero.

They are deliberately not faithful in anything but geometry — no painting, no
icon loading, and `DataSource` runs nothing at all.

What is modelled rather than measured
-------------------------------------

One quantity: the padding of a Plasma tool button. The real one takes it from
the margins of the Breeze SVG frame it is drawn with, which is theme data, not
source. `ToolButton.qml` uses one `smallSpacing` per side instead, and says so.
Everything else in the chain — the icon size the flat button uses, the
`gridUnit + margins` floor, the max() that combines them — is what
plasma-framework's own `ToolButton.qml`, `ButtonContent.qml` and
`ButtonBackground.qml` do, as installed under
`/usr/lib64/qt6/qml/org/kde/plasma/components/`.

What these doubles cannot cover
-------------------------------

`configGeneral.qml` does not load through them. It uses `Kirigami.FormData`,
an *attached* property, and attached properties cannot be declared in QML — the
type has to come from C++ or from a registered Python type. The loader stops at

    configGeneral.qml:26:22: Non-existent attached object

A `FormLayout` double that accepted the attached property but ignored it would
be worse than no test: `Kirigami.FormLayout` sizes its label column from those
labels, so a double without them would lay the page out at a width the real
dialog never has, and report that it fits.
