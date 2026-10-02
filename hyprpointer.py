"""Hyprland pointer backend: a small pyautogui-style API over wlr-virtual-pointer.

wayland_automation provides the Wayland connection and the virtual pointer
object; its high-level helpers only do click-at-coordinates (and shell out to
wayland-info on every call), so press/release, motion and scroll are sent as
raw zwlr_virtual_pointer_v1 requests here. Cursor position and the monitor
layout come from hyprctl. SUPER is held with a long-lived wtype process.

Glide runs on its own thread at monitor refresh rate and interpolates between
the positions hand tracking produces, so the cursor moves smoothly even though
the camera only delivers ~30 frames per second.
"""

import json
import struct
import subprocess
import threading
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
# motion_absolute takes integer coordinates; scaling coordinates and extent
# together gives the compositor sub-pixel positions.
_SUBPIXEL = 16
_FALLBACK_PX_PER_MM = 96 / 25.4  # when a monitor reports no physical size

_BUTTONS = {"left": 0x110, "right": 0x111, "middle": 0x112}

_mouse = None
_layout = None  # (origin_x, origin_y, extent_w, extent_h) in logical px
_monitors = None  # [(x, y, w, h, px_per_mm, refresh_hz)] in logical px
_super_proc = None
# Glide's thread and the main thread both write to the Wayland socket.
_io_lock = threading.Lock()


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


def _get_monitors():
    global _monitors
    if _monitors is None:
        _monitors = []
        for m in _hyprctl_json("monitors"):
            w, h = _logical_size(m)
            # Physical size is of the unrotated panel.
            phys_w = m.get("physicalHeight" if m.get("transform", 0) % 2 else "physicalWidth", 0)
            px_per_mm = w / phys_w if phys_w else _FALLBACK_PX_PER_MM
            _monitors.append((m["x"], m["y"], w, h, px_per_mm, m.get("refreshRate", 60.0)))
    return _monitors


def _get_layout():
    global _layout
    if _layout is None:
        monitors = _get_monitors()
        left = min(m[0] for m in monitors)
        top = min(m[1] for m in monitors)
        right = max(m[0] + m[2] for m in monitors)
        bottom = max(m[1] + m[3] for m in monitors)
        _layout = (left, top, int(right - left), int(bottom - top))
    return _layout


def _nearest_monitor(x, y):
    """Return (monitor, clamped_x, clamped_y) for the monitor closest to (x, y)."""
    best = None
    for mon in _get_monitors():
        mx, my, mw, mh = mon[:4]
        cx = min(max(x, mx), mx + mw - 1)
        cy = min(max(y, my), my + mh - 1)
        dist = (cx - x) ** 2 + (cy - y) ** 2
        if best is None or dist < best[0]:
            best = (dist, mon, cx, cy)
    return best[1], best[2], best[3]


def clamp_to_monitors(x, y):
    """Clamp (x, y) onto the nearest monitor, skipping gaps in the layout."""
    _, cx, cy = _nearest_monitor(x, y)
    return cx, cy


def px_per_mm_at(x, y):
    """Logical pixels per millimetre of the monitor at (x, y)."""
    return _nearest_monitor(x, y)[0][4]


def max_refresh_hz():
    return max(m[5] for m in _get_monitors())


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


def position():
    """Current cursor position in global layout coordinates."""
    pos = _hyprctl_json("cursorpos")
    return pos["x"], pos["y"]


def moveTo(x, y):
    left, top, width, height = _get_layout()
    ext_w, ext_h = width * _SUBPIXEL, height * _SUBPIXEL
    rel_x = int(min(max((x - left) * _SUBPIXEL, 0), ext_w - 1))
    rel_y = int(min(max((y - top) * _SUBPIXEL, 0), ext_h - 1))
    with _io_lock:
        _send(_MOTION_ABSOLUTE, "IIIII", _now_ms(), rel_x, rel_y, ext_w, ext_h)
        _send(_FRAME)


def _button(button, pressed):
    with _io_lock:
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
    with _io_lock:
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


def _bezier(p0, p1, p2, p3, t):
    u = 1.0 - t
    return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3


def _bezier_slope(p0, p1, p2, p3, t):
    u = 1.0 - t
    return 3 * u * u * (p1 - p0) + 6 * u * t * (p2 - p1) + 3 * t * t * (p3 - p2)


class Glide:
    """Moves the cursor at a steady rate toward the latest target.

    Each new target starts a cubic Bezier segment from where the cursor is now,
    timed to last one input frame interval. The segment leaves at the cursor's
    current velocity and arrives at the targets' velocity, so motion stays
    continuous in speed and direction across camera frames. 30 fps input looks
    like refresh-rate motion, at the cost of one input frame of latency.
    """

    def __init__(self, rate_hz):
        self._period = 1.0 / rate_hz
        self._lock = threading.Lock()
        x, y = position()
        self._pos = (float(x), float(y))
        self._hold(self._pos)
        self._t0 = time.monotonic()
        self._interval = 1.0 / 30
        self._last_target_ts = None
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _hold(self, pos):
        # A segment whose control points all sit at pos: stay still.
        self._ctrl = ((pos[0],) * 4, (pos[1],) * 4)

    def _progress(self, now):
        return min(1.0, (now - self._t0) / self._interval)

    def _velocity(self, now):
        # A target arriving a little late, after the segment has ended, should
        # continue at the segment's end velocity rather than restart from rest.
        # Only a real gap in input (clutch, lost hand) counts as stopped.
        if now - self._t0 > 2 * self._interval:
            return 0.0, 0.0
        k = self._progress(now)
        return tuple(_bezier_slope(*axis, k) / self._interval for axis in self._ctrl)

    def set_target(self, x, y):
        with self._lock:
            now = time.monotonic()
            v_start = self._velocity(now)
            if self._last_target_ts is not None:
                # Track the input frame interval; cap it so a stall doesn't
                # turn the next segment into a slow crawl.
                gap = min(now - self._last_target_ts, 0.1)
                self._interval += 0.2 * (gap - self._interval)
                prev_to = (self._ctrl[0][3], self._ctrl[1][3])
                v_end = ((x - prev_to[0]) / self._interval, (y - prev_to[1]) / self._interval)
            else:
                v_end = (0.0, 0.0)
            self._last_target_ts = now

            third = self._interval / 3
            self._ctrl = tuple(
                (p0, p0 + vs * third, p3 - ve * third, p3)
                for p0, p3, vs, ve in zip(self._pos, (float(x), float(y)), v_start, v_end)
            )
            self._t0 = now

    def snap(self):
        """Stop where the cursor is now and return that position."""
        with self._lock:
            self._hold(self._pos)
            return self._pos

    def pause(self):
        """Forget input timing, e.g. while the hand is out of view."""
        with self._lock:
            self._last_target_ts = None

    def stop(self):
        self._running = False
        self._thread.join(timeout=1)

    def _run(self):
        next_tick = time.monotonic()
        last_sent = None
        while self._running:
            with self._lock:
                k = self._progress(time.monotonic())
                self._pos = tuple(_bezier(*axis, k) for axis in self._ctrl)
                pos = self._pos
            if pos != last_sent:
                moveTo(*pos)
                last_sent = pos
            next_tick += self._period
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.monotonic()
