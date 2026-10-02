"""Hyprland pointer backend: a small pyautogui-style API over wlr-virtual-pointer.

wayland_automation provides the Wayland connection and the virtual pointer
object; its high-level helpers only do click-at-coordinates (and shell out to
wayland-info on every call), so press/release, motion and scroll are sent as
raw zwlr_virtual_pointer_v1 requests here. Cursor position and the monitor
layout come from hyprctl. SUPER is held with a long-lived wtype process.
"""

import json
import struct
import subprocess
import time

from wayland_automation.mouse_controller import Mouse

# zwlr_virtual_pointer_v1 request opcodes
_MOTION_ABSOLUTE = 1
_BUTTON = 2
_FRAME = 4
_AXIS_SOURCE = 5
_AXIS_DISCRETE = 7

_AXIS_VERTICAL = 0
_AXIS_SOURCE_WHEEL = 0
_SCROLL_UNITS_PER_CLICK = 15  # libinput convention for one wheel detent

_BUTTONS = {"left": 0x110, "right": 0x111, "middle": 0x112}

_mouse = None
_layout = None  # (origin_x, origin_y, extent_w, extent_h) in logical px
_super_proc = None


def _hyprctl_json(*args):
    out = subprocess.run(
        ["hyprctl", "-j", *args], capture_output=True, text=True, check=True
    ).stdout
    return json.loads(out)


def _logical_size(mon):
    w, h = mon["width"] / mon["scale"], mon["height"] / mon["scale"]
    # Odd transforms are 90/270 degree rotations.
    if mon.get("transform", 0) % 2:
        w, h = h, w
    return w, h


def _get_layout():
    global _layout
    if _layout is None:
        monitors = _hyprctl_json("monitors")
        left = min(m["x"] for m in monitors)
        top = min(m["y"] for m in monitors)
        right = max(m["x"] + _logical_size(m)[0] for m in monitors)
        bottom = max(m["y"] + _logical_size(m)[1] for m in monitors)
        _layout = (left, top, int(right - left), int(bottom - top))
    return _layout


def _get_mouse():
    global _mouse
    if _mouse is None:
        _mouse = Mouse()
    return _mouse


def _send(opcode, fmt="", *args):
    m = _get_mouse()
    payload = struct.pack(m.endianness + fmt, *args) if fmt else b""
    m.send_message(m.current_virtual_pointer_id, opcode, payload)


def _now_ms():
    return int(time.monotonic() * 1000) & 0xFFFFFFFF


def size():
    """Logical size of the focused monitor, used to scale hand motion."""
    for mon in _hyprctl_json("monitors"):
        if mon.get("focused"):
            w, h = _logical_size(mon)
            return int(w), int(h)
    _, _, w, h = _get_layout()
    return w, h


def position():
    """Current cursor position in global layout coordinates."""
    pos = _hyprctl_json("cursorpos")
    return pos["x"], pos["y"]


def moveTo(x, y):
    left, top, width, height = _get_layout()
    rel_x = int(min(max(x - left, 0), width - 1))
    rel_y = int(min(max(y - top, 0), height - 1))
    _send(_MOTION_ABSOLUTE, "IIIII", _now_ms(), rel_x, rel_y, width, height)
    _send(_FRAME)


def _button(button, pressed):
    _send(_BUTTON, "III", _now_ms(), _BUTTONS[button], 1 if pressed else 0)
    _send(_FRAME)


def mouseDown(button="left"):
    _button(button, True)


def mouseUp(button="left"):
    _button(button, False)


def click(button="left"):
    mouseDown(button)
    mouseUp(button)


def scroll(clicks):
    """Scroll by wheel clicks; positive scrolls up, like pyautogui."""
    if not clicks:
        return
    # Wayland's vertical axis is positive-down; values are 24.8 fixed point.
    discrete = -int(clicks)
    value = int(discrete * _SCROLL_UNITS_PER_CLICK * 256)
    _send(_AXIS_SOURCE, "I", _AXIS_SOURCE_WHEEL)
    _send(_AXIS_DISCRETE, "IIii", _now_ms(), _AXIS_VERTICAL, value, discrete)
    _send(_FRAME)


def superDown():
    """Hold SUPER until superUp().

    wtype presses the modifier, then blocks reading stdin; closing stdin makes
    it exit, and wtype releases held modifiers on exit. If this process dies,
    the pipe closes too, so SUPER can't get stuck.
    """
    global _super_proc
    if _super_proc is None:
        _super_proc = subprocess.Popen(["wtype", "-M", "logo", "-"], stdin=subprocess.PIPE)
        # Let the modifier reach the compositor before any button press.
        time.sleep(0.15)


def superUp():
    global _super_proc
    if _super_proc is not None:
        _super_proc.stdin.close()
        _super_proc.wait(timeout=1)
        _super_proc = None
