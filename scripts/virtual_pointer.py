"""Move the pointer for real, by being an input device.

QCursor.setPos does not work here and looks like it does. Under Wayland the
compositor owns the pointer; XWayland keeps a shadow of it that a client is
allowed to warp, so the call succeeds, QCursor.pos() reads back the new value,
and every test passes — while on screen the cursor flicks to the new spot and
is immediately corrected back. Measuring the shadow and calling it the pointer
is the mistake this module exists to undo.

What does work is not asking the compositor to move the pointer but giving it
a mouse that moved. /dev/uinput creates a kernel input device; relative motion
written to it arrives as ordinary hardware input, indistinguishable from the
real mouse, and the compositor moves the cursor because that is what mice do.

Needs write access to /dev/uinput — on this machine an ACL grants it to the
logged-in user. Where it is not writable this returns None and the caller
falls back to doing nothing, which is the correct behaviour for a joke.
"""
from __future__ import annotations

import ctypes
import fcntl
import os
import struct

UINPUT = "/dev/uinput"
IFACE = "org.kde.KWin.InputDevice"

EV_SYN, EV_KEY, EV_REL = 0x00, 0x01, 0x02
REL_X, REL_Y = 0x00, 0x01
SYN_REPORT = 0x00
BTN_LEFT = 0x110

# _IOW('U', n, int) and friends. Spelled out rather than computed so the
# numbers can be checked against linux/uinput.h by eye.
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_RELBIT = 0x40045566
UI_DEV_SETUP = 0x405C5503
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502

_EVENT = struct.Struct("llHHi")          # timeval, type, code, value


class VirtualPointer:
    """A mouse that only ever moves. Context manager; safe to fail."""

    def __init__(self, name=b"usage-buddies companion"):
        self.fd = None
        self.name = name
        self.device_path = None
        # Whole pixels are all the protocol carries, so the fraction left over
        # is kept and spent on the next call. Dropping it loses a few percent
        # of every movement, which over a run across the desktop is the
        # pointer arriving somewhere the character is not.
        self._rest_x = 0.0
        self._rest_y = 0.0
        self._flatten_tries = 0

    def open(self):
        try:
            fd = os.open(UINPUT, os.O_WRONLY | os.O_NONBLOCK)
        except OSError:
            return None
        try:
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_REL)
            fcntl.ioctl(fd, UI_SET_RELBIT, REL_X)
            fcntl.ioctl(fd, UI_SET_RELBIT, REL_Y)
            # A pointer with no buttons is not treated as a pointer by every
            # stack that looks at one, so it claims a left button it never
            # presses.
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(fd, UI_SET_KEYBIT, BTN_LEFT)

            setup = struct.pack("HHHH80sI", 0x03, 0x1209, 0x0001, 0x0001,
                                self.name.ljust(80, b"\0")[:80], 0)
            fcntl.ioctl(fd, UI_DEV_SETUP, setup)
            fcntl.ioctl(fd, UI_DEV_CREATE)
        except OSError:
            os.close(fd)
            return None
        self.fd = fd
        return self

    def _flatten(self):
        """Turn off pointer acceleration for this device.

        libinput accelerates by default, so a delta of ten pixels moves the
        cursor rather more than ten pixels, and the further it travels the
        further ahead of the character it gets. The point here is to carry the
        pointer, which means one pixel of movement has to be one pixel.

        KWin exposes the setting per device over D-Bus, but not until it has
        noticed the device — which takes a second or two. Calling this from
        open() found nothing every time and left acceleration on: measured, a
        900 pixel request moved the cursor 1220. So it is tried on the first
        movement instead, by which point the device is registered, and given
        up on after a few attempts.

        Best effort throughout: without it the pointer still moves, just less
        precisely, and that is not worth refusing to run over.
        """
        if self.device_path or self._flatten_tries > 4:
            return
        self._flatten_tries += 1
        import subprocess
        try:
            listing = subprocess.run(
                ["qdbus-qt6", "org.kde.KWin"], capture_output=True, text=True, timeout=4)
        except (OSError, subprocess.SubprocessError):
            return
        wanted = self.name.decode("utf-8", "replace").strip("\0")
        for path in listing.stdout.split():
            if "/InputDevice/event" not in path:
                continue
            try:
                # Properties.Get, not the dotted property name: qdbus answers
                # the latter with UnknownInterface, which reads like the
                # interface is missing rather than like the call is wrong, and
                # cost an hour of looking in the wrong place.
                name = subprocess.run(
                    ["qdbus-qt6", "org.kde.KWin", path,
                     "org.freedesktop.DBus.Properties.Get",
                     IFACE, "name"],
                    capture_output=True, text=True, timeout=4).stdout.strip()
                if name != wanted:
                    continue
                for prop, value in (("pointerAccelerationProfileFlat", "true"),
                                    ("pointerAcceleration", "0")):
                    subprocess.run(
                        ["qdbus-qt6", "org.kde.KWin", path,
                         "org.freedesktop.DBus.Properties.Set",
                         IFACE, prop, value],
                        capture_output=True, text=True, timeout=4)
                self.device_path = path
                return
            except (OSError, subprocess.SubprocessError):
                return

    def move(self, dx, dy):
        """Relative motion, in pixels. Returns False once the device is gone."""
        if self.fd is None:
            return False
        self._flatten()
        dx += self._rest_x
        dy += self._rest_y
        # round, not int: truncating loses a pixel every time the carried
        # fraction lands on 0.9999999999999999 instead of 1.0, and ten moves
        # of 0.6 arrive as 5 pixels rather than 6. Rounding can overshoot by
        # half a pixel, and the remainder it leaves is negative, which the
        # next call spends — so it corrects itself either way.
        whole_x, whole_y = round(dx), round(dy)
        self._rest_x, self._rest_y = dx - whole_x, dy - whole_y
        dx, dy = whole_x, whole_y
        if dx == 0 and dy == 0:
            return True
        payload = b""
        if dx:
            payload += _EVENT.pack(0, 0, EV_REL, REL_X, dx)
        if dy:
            payload += _EVENT.pack(0, 0, EV_REL, REL_Y, dy)
        payload += _EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0)
        try:
            os.write(self.fd, payload)
        except OSError:
            self.close()
            return False
        return True

    def close(self):
        if self.fd is None:
            return
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.fd = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *_exc):
        self.close()


def available():
    """Whether a pointer can be created at all, without leaving one behind."""
    device = VirtualPointer().open()
    if device is None:
        return False
    device.close()
    return True
