import math
import os
import time
import importlib
from dataclasses import dataclass, field

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = importlib.import_module("tomli")

import cv2
import hyprpointer as pointer
from cvzone.HandTrackingModule import HandDetector

CONFIG_FILE = "config.toml"

@dataclass
class CameraConfig:
    index: int = 0
    width: int = 640
    height: int = 480
    fps: int = 60
    detection_confidence: float = 0.8


@dataclass
class CursorConfig:
    speed_mm: float = 1100.0
    jitter_cutoff_hz: float = 1.0
    jitter_beta: float = 0.03
    pointer_hz: float = 0.0
    accel_min: float = 0.5
    accel_max: float = 1.6
    accel_speed: float = 1.5
    accel_curve: tuple[float, float, float, float] = (0.6, 0.0, 0.4, 1.0)


@dataclass
class ScrollConfig:
    gain: float = 0.35
    deadzone_px: float = 2.0
    max_step: float = 18.0
    momentum: float = 0.22
    decay: float = 0.92


@dataclass
class GestureConfig:
    click_dist: float = 15.0
    scroll_dist: float = 15.0
    rclick_dist: float = 15.0
    super_drag_dist: float = 15.0
    super_release_dist: float = 40.0
    super_release_grace_sec: float = 0.15
    drag_unlock_margin_px: float = 22.0
    toggle_window_sec: float = 1.2
    toggle_debounce_sec: float = 0.10


@dataclass
class UiConfig:
    window_name: str = "qrkahand"
    text_origin_main: tuple[int, int] = (50, 50)
    text_origin_hint: tuple[int, int] = (50, 90)
    text_origin_diag: tuple[int, int] = (10, 20)
    show_diagnostics: bool = True


@dataclass
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    cursor: CursorConfig = field(default_factory=CursorConfig)
    scroll: ScrollConfig = field(default_factory=ScrollConfig)
    gesture: GestureConfig = field(default_factory=GestureConfig)
    ui: UiConfig = field(default_factory=UiConfig)


@dataclass
class ControllerState:
    is_clicking: bool = False
    is_super_held: bool = False
    super_release_since: float | None = None
    is_right_clicking: bool = False
    is_scrolling: bool = False
    is_clutched: bool = False
    target_x: float = 0.0
    target_y: float = 0.0
    prev_palm: tuple[float, float] | None = None
    palm_filter: "OneEuroFilter | None" = None
    accel_ease: object = None
    scroll_anchor_y: float = 0.0
    scroll_visual_anchor_y: float = 0.0
    scroll_velocity: float = 0.0
    program_active: bool = True
    last_hand_pose: str = "unknown"
    toggle_transition_count: int = 0
    toggle_window_start: float = 0.0
    last_toggle_transition_ts: float = 0.0
    fps: float = 0.0
    fps_frame_count: int = 0
    fps_last_ts: float = 0.0
    backend_name: str = "unknown"
    capture_label: str = "unknown"
    pointer_label: str = "unknown"
    mode_label: str = "NO_HAND"
    drag_anchor_x: float = 0.0
    drag_anchor_y: float = 0.0
    drag_unlocked: bool = True


def _parse_origin(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must be a 2-item list/tuple")
    return (int(value[0]), int(value[1]))


def validate_settings(cfg):
    errors = []

    camera = cfg.camera
    cursor = cfg.cursor
    scroll = cfg.scroll
    gesture = cfg.gesture

    if camera.index < 0:
        errors.append("CAMERA_INDEX must be >= 0")
    if camera.width <= 0:
        errors.append("CAMERA_WIDTH must be > 0")
    if camera.height <= 0:
        errors.append("CAMERA_HEIGHT must be > 0")
    if camera.fps <= 0:
        errors.append("CAMERA_FPS must be > 0")
    if not (0.0 < camera.detection_confidence <= 1.0):
        errors.append("DETECTION_CONFIDENCE must be in (0, 1]")

    if cursor.speed_mm <= 0:
        errors.append("SPEED_MM must be > 0")
    if cursor.jitter_cutoff_hz <= 0:
        errors.append("JITTER_CUTOFF_HZ must be > 0")
    if cursor.jitter_beta < 0:
        errors.append("JITTER_BETA must be >= 0")
    if cursor.pointer_hz < 0:
        errors.append("POINTER_HZ must be >= 0")
    if not (0 < cursor.accel_min <= cursor.accel_max):
        errors.append("ACCEL_MIN must be > 0 and <= ACCEL_MAX")
    if cursor.accel_speed <= 0:
        errors.append("ACCEL_SPEED must be > 0")
    if not (0.0 <= cursor.accel_curve[0] <= 1.0 and 0.0 <= cursor.accel_curve[2] <= 1.0):
        errors.append("ACCEL_CURVE x values (1st and 3rd) must be in [0, 1]")

    if scroll.gain < 0:
        errors.append("SCROLL_GAIN must be >= 0")
    if scroll.deadzone_px < 0:
        errors.append("SCROLL_DEADZONE_PX must be >= 0")
    if scroll.max_step <= 0:
        errors.append("MAX_SCROLL_STEP must be > 0")
    if not (0.0 <= scroll.momentum <= 1.0):
        errors.append("SCROLL_MOMENTUM must be in [0, 1]")
    if not (0.0 <= scroll.decay <= 1.0):
        errors.append("SCROLL_DECAY must be in [0, 1]")

    if gesture.click_dist <= 0:
        errors.append("CLICK_DIST must be > 0")
    if gesture.scroll_dist <= 0:
        errors.append("SCROLL_DIST must be > 0")
    if gesture.rclick_dist <= 0:
        errors.append("RCLICK_DIST must be > 0")
    if gesture.super_drag_dist <= 0:
        errors.append("SUPER_DRAG_DIST must be > 0")
    if gesture.super_release_dist < gesture.super_drag_dist:
        errors.append("SUPER_RELEASE_DIST must be >= SUPER_DRAG_DIST")
    if gesture.super_release_grace_sec < 0:
        errors.append("SUPER_RELEASE_GRACE_SEC must be >= 0")
    if gesture.drag_unlock_margin_px < 0:
        errors.append("DRAG_UNLOCK_MARGIN_PX must be >= 0")

    if gesture.toggle_window_sec <= 0:
        errors.append("TOGGLE_WINDOW_SEC must be > 0")
    if gesture.toggle_debounce_sec < 0:
        errors.append("TOGGLE_DEBOUNCE_SEC must be >= 0")
    if gesture.toggle_debounce_sec >= gesture.toggle_window_sec:
        errors.append("TOGGLE_DEBOUNCE_SEC must be less than TOGGLE_WINDOW_SEC")

    if errors:
        raise ValueError("Invalid configuration:\n- " + "\n- ".join(errors))


def load_config(config_path=CONFIG_FILE):
    cfg = AppConfig()

    if not os.path.exists(config_path):
        validate_settings(cfg)
        return cfg

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    camera = data.get("camera", {})
    cfg.camera.index = int(camera.get("index", cfg.camera.index))
    cfg.camera.width = int(camera.get("width", cfg.camera.width))
    cfg.camera.height = int(camera.get("height", cfg.camera.height))
    cfg.camera.fps = int(camera.get("fps", cfg.camera.fps))
    cfg.camera.detection_confidence = float(
        camera.get("detection_confidence", cfg.camera.detection_confidence)
    )

    cursor = data.get("cursor", {})
    cfg.cursor.speed_mm = float(cursor.get("speed_mm", cfg.cursor.speed_mm))
    cfg.cursor.jitter_cutoff_hz = float(
        cursor.get("jitter_cutoff_hz", cfg.cursor.jitter_cutoff_hz)
    )
    cfg.cursor.jitter_beta = float(cursor.get("jitter_beta", cfg.cursor.jitter_beta))
    cfg.cursor.pointer_hz = float(cursor.get("pointer_hz", cfg.cursor.pointer_hz))
    cfg.cursor.accel_min = float(cursor.get("accel_min", cfg.cursor.accel_min))
    cfg.cursor.accel_max = float(cursor.get("accel_max", cfg.cursor.accel_max))
    cfg.cursor.accel_speed = float(cursor.get("accel_speed", cfg.cursor.accel_speed))
    if "accel_curve" in cursor:
        curve = cursor["accel_curve"]
        if not isinstance(curve, (list, tuple)) or len(curve) != 4:
            raise ValueError("cursor.accel_curve must be a 4-item list")
        cfg.cursor.accel_curve = tuple(float(v) for v in curve)

    scroll = data.get("scroll", {})
    cfg.scroll.gain = float(scroll.get("gain", cfg.scroll.gain))
    cfg.scroll.deadzone_px = float(scroll.get("deadzone_px", cfg.scroll.deadzone_px))
    cfg.scroll.max_step = float(scroll.get("max_step", cfg.scroll.max_step))
    cfg.scroll.momentum = float(scroll.get("momentum", cfg.scroll.momentum))
    cfg.scroll.decay = float(scroll.get("decay", cfg.scroll.decay))

    gesture = data.get("gesture", {})
    cfg.gesture.click_dist = float(gesture.get("click_dist", cfg.gesture.click_dist))
    cfg.gesture.scroll_dist = float(gesture.get("scroll_dist", cfg.gesture.scroll_dist))
    cfg.gesture.rclick_dist = float(gesture.get("rclick_dist", cfg.gesture.rclick_dist))
    cfg.gesture.super_drag_dist = float(
        gesture.get("super_drag_dist", cfg.gesture.super_drag_dist)
    )
    cfg.gesture.super_release_dist = float(
        gesture.get("super_release_dist", cfg.gesture.super_release_dist)
    )
    cfg.gesture.super_release_grace_sec = float(
        gesture.get("super_release_grace_sec", cfg.gesture.super_release_grace_sec)
    )
    cfg.gesture.drag_unlock_margin_px = float(
        gesture.get("drag_unlock_margin_px", cfg.gesture.drag_unlock_margin_px)
    )
    cfg.gesture.toggle_window_sec = float(
        gesture.get("toggle_window_sec", cfg.gesture.toggle_window_sec)
    )
    cfg.gesture.toggle_debounce_sec = float(
        gesture.get("toggle_debounce_sec", cfg.gesture.toggle_debounce_sec)
    )

    ui = data.get("ui", {})
    cfg.ui.window_name = str(ui.get("window_name", cfg.ui.window_name))
    if "text_origin_main" in ui:
        cfg.ui.text_origin_main = _parse_origin(ui["text_origin_main"], "ui.text_origin_main")
    if "text_origin_hint" in ui:
        cfg.ui.text_origin_hint = _parse_origin(ui["text_origin_hint"], "ui.text_origin_hint")
    if "text_origin_diag" in ui:
        cfg.ui.text_origin_diag = _parse_origin(ui["text_origin_diag"], "ui.text_origin_diag")
    cfg.ui.show_diagnostics = bool(ui.get("show_diagnostics", cfg.ui.show_diagnostics))

    validate_settings(cfg)
    return cfg


class OneEuroFilter:
    """One Euro filter (Casiez et al., 2012) for a 2D point.

    Smooths heavily while the hand is nearly still, where jitter shows, and
    backs off as it speeds up, where lag would show.
    """

    def __init__(self, min_cutoff, beta, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self):
        self._x = None
        self._dx = (0.0, 0.0)
        self._t = None

    @property
    def speed(self):
        """Smoothed speed of the point, in input units per second."""
        return math.hypot(*self._dx)

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, y, t):
        if self._x is None or t <= self._t:
            self._x, self._t = (float(x), float(y)), t
            return self._x

        dt = t - self._t
        self._t = t
        a_d = self._alpha(self.d_cutoff, dt)
        dx = ((x - self._x[0]) / dt, (y - self._x[1]) / dt)
        self._dx = tuple(a_d * d + (1 - a_d) * p for d, p in zip(dx, self._dx))

        a = self._alpha(self.min_cutoff + self.beta * self.speed, dt)
        self._x = (a * x + (1 - a) * self._x[0], a * y + (1 - a) * self._x[1])
        return self._x


def cubic_bezier(x1, y1, x2, y2):
    """CSS-style cubic-bezier easing from (0, 0) to (1, 1); returns y for x."""

    def axis(a1, a2, t):
        u = 1.0 - t
        return 3 * a1 * u * u * t + 3 * a2 * u * t * t + t * t * t

    def ease(x):
        # x(t) is monotonic when x1, x2 are in [0, 1], so bisect for t.
        lo, hi = 0.0, 1.0
        for _ in range(24):
            mid = (lo + hi) / 2
            if axis(x1, x2, mid) < x:
                lo = mid
            else:
                hi = mid
        return axis(y1, y2, (lo + hi) / 2)

    return ease


def accel_gain(cfg, ease, palm_speed):
    """Speed multiplier for a palm speed in camera px/s.

    Rises along the bezier from ACCEL_MIN when the hand is still to ACCEL_MAX
    at ACCEL_SPEED frame widths per second, and stays there above it.
    """
    x = min(palm_speed / (cfg.cursor.accel_speed * cfg.camera.width), 1.0)
    return cfg.cursor.accel_min + (cfg.cursor.accel_max - cfg.cursor.accel_min) * ease(x)


def move_cursor(state, glide, cfg, palm_x, palm_y):
    """Move the cursor by the palm's motion since the last frame.

    Speed is in millimetres, so it is the same on monitors of any pixel density,
    and scaled by the acceleration curve.
    """
    if state.prev_palm is not None:
        px_per_cam_px = (
            (cfg.cursor.speed_mm / cfg.camera.width)
            * pointer.px_per_mm_at(state.target_x, state.target_y)
            * accel_gain(cfg, state.accel_ease, state.palm_filter.speed)
        )
        x = state.target_x + (palm_x - state.prev_palm[0]) * px_per_cam_px
        y = state.target_y + (palm_y - state.prev_palm[1]) * px_per_cam_px
        state.target_x, state.target_y = pointer.clamp_to_monitors(x, y)
        glide.set_target(state.target_x, state.target_y)
    state.prev_palm = (palm_x, palm_y)


def classify_hand_pose(fingers):
    if fingers[1:] == [0, 0, 0, 0]:
        return "closed"
    if fingers[1:] == [1, 1, 1, 1]:
        return "open"
    return "neutral"


def release_drag(state):
    if state.is_clicking:
        pointer.mouseUp()
        state.is_clicking = False
    if state.is_super_held:
        pointer.superUp()
        state.is_super_held = False
    state.super_release_since = None


def draw_status(img, text, color, origin, scale=1.0, thickness=3):
    cv2.putText(img, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)


def draw_diagnostics(img, state, cfg):
    if not cfg.ui.show_diagnostics:
        return

    lines = [
        f"FPS: {state.fps:.1f}",
        f"Backend: {state.backend_name}",
        f"Capture: {state.capture_label}",
        f"Pointer: {state.pointer_label}",
        f"Mode: {state.mode_label}",
        f"Active: {'yes' if state.program_active else 'no'}",
    ]
    x, y = cfg.ui.text_origin_diag
    for i, line in enumerate(lines):
        cv2.putText(
            img,
            line,
            (x, y + i * 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )


def handle_program_toggle(current_pose, state, cfg):
    now = time.time()
    if current_pose not in ("open", "closed"):
        return

    if (
        state.last_hand_pose in ("open", "closed")
        and current_pose != state.last_hand_pose
        and (now - state.last_toggle_transition_ts) > cfg.gesture.toggle_debounce_sec
    ):
        if state.toggle_transition_count == 0 or (
            (now - state.toggle_window_start) > cfg.gesture.toggle_window_sec
        ):
            state.toggle_window_start = now
            state.toggle_transition_count = 1
        else:
            state.toggle_transition_count += 1

        state.last_toggle_transition_ts = now

        if state.toggle_transition_count >= 4:
            state.program_active = not state.program_active
            state.toggle_transition_count = 0
            state.toggle_window_start = 0.0

            if not state.program_active:
                release_drag(state)
                state.is_scrolling = False
                state.is_right_clicking = False
                state.scroll_velocity = 0.0
            else:
                # Re-engage movement without cursor snap.
                state.is_clutched = True
                state.is_scrolling = False
                state.scroll_velocity = 0.0

    state.last_hand_pose = current_pose


def open_camera(camera_index):
    backends = [cv2.CAP_V4L2, cv2.CAP_ANY]

    for backend in backends:
        cam = cv2.VideoCapture(camera_index, backend)
        if cam.isOpened():
            return cam, backend
        cam.release()

    raise RuntimeError("Could not open camera with available backends.")


def configure_camera(cam, cfg):
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.camera.width)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.camera.height)
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cam.set(cv2.CAP_PROP_FPS, cfg.camera.fps)


def main():
    cfg = load_config()

    cam, backend = open_camera(cfg.camera.index)
    configure_camera(cam, cfg)

    detector = HandDetector(
        detectionCon=cfg.camera.detection_confidence,
        maxHands=1,
    )

    pointer_hz = cfg.cursor.pointer_hz or pointer.max_refresh_hz()
    glide = pointer.Glide(pointer_hz)

    state = ControllerState()
    state.target_x, state.target_y = glide.snap()
    state.palm_filter = OneEuroFilter(cfg.cursor.jitter_cutoff_hz, cfg.cursor.jitter_beta)
    state.accel_ease = cubic_bezier(*cfg.cursor.accel_curve)
    state.pointer_label = f"{pointer_hz:.0f} Hz"
    state.fps_last_ts = time.time()
    state.backend_name = {
        cv2.CAP_V4L2: "V4L2",
        cv2.CAP_ANY: "ANY",
    }.get(backend, str(backend))
    state.capture_label = f"{cfg.camera.width}x{cfg.camera.height}@{cfg.camera.fps}"

    print("Press 'q' in the camera window to quit.")

    try:
        while True:
            success, img = cam.read()
            if not success:
                continue

            state.fps_frame_count += 1
            now = time.time()
            elapsed = now - state.fps_last_ts
            if elapsed >= 1.0:
                state.fps = state.fps_frame_count / elapsed
                state.fps_frame_count = 0
                state.fps_last_ts = now

            img = cv2.flip(img, 1)
            hands, img = detector.findHands(img, flipType=False)

            state.mode_label = "NO_HAND"

            if hands:
                hand = hands[0]
                lm_list = hand["lmList"]
                fingers = detector.fingersUp(hand)

                x_thumb, y_thumb = lm_list[4][0], lm_list[4][1]
                x_index, y_index = lm_list[8][0], lm_list[8][1]
                x_mid, y_mid = lm_list[12][0], lm_list[12][1]
                x_ring, y_ring = lm_list[16][0], lm_list[16][1]
                x_pinky, y_pinky = lm_list[20][0], lm_list[20][1]
                x_palm, y_palm = lm_list[9][0], lm_list[9][1]
                palm_fx, palm_fy = state.palm_filter(x_palm, y_palm, time.monotonic())

                dist_index = math.hypot(x_index - x_thumb, y_index - y_thumb)
                dist_mid = math.hypot(x_mid - x_thumb, y_mid - y_thumb)
                dist_ring = math.hypot(x_ring - x_thumb, y_ring - y_thumb)
                dist_pinky = math.hypot(x_pinky - x_thumb, y_pinky - y_thumb)

                cv2.circle(img, (x_palm, y_palm), 8, (255, 255, 255), 2)

                current_pose = classify_hand_pose(fingers)
                handle_program_toggle(current_pose, state, cfg)

                if not state.program_active:
                    state.mode_label = "PROGRAM_PAUSED"
                    draw_status(img, "PROGRAM PAUSED", (0, 0, 255), cfg.ui.text_origin_main)
                    draw_status(
                        img,
                        "Toggle: open/close x2 quickly",
                        (0, 200, 255),
                        origin=cfg.ui.text_origin_hint,
                        scale=0.7,
                        thickness=2,
                    )
                    draw_diagnostics(img, state, cfg)
                    cv2.imshow(cfg.ui.window_name, img)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                    continue

                # A window drag ends only on a clear release of the pinky, so
                # other gesture readings can't interrupt it (the ring finger
                # sits close to the thumb during a pinky pinch, and curling the
                # free fingers can read as a closed hand).
                window_dragging = state.is_clicking and state.is_super_held

                if not window_dragging and current_pose == "closed":
                    state.mode_label = "CLUTCH"
                    draw_status(img, "PAUSED (CLUTCH)", (0, 0, 255), cfg.ui.text_origin_main)
                    release_drag(state)
                    state.is_scrolling = False
                    state.is_clutched = True

                elif not window_dragging and dist_mid < cfg.gesture.scroll_dist:
                    state.mode_label = "SCROLL"
                    state.prev_palm = None
                    draw_status(img, "SCROLLING", (255, 255, 0), cfg.ui.text_origin_main)
                    cv2.circle(img, (x_mid, y_mid), 15, (255, 255, 0), cv2.FILLED)

                    if not state.is_scrolling:
                        state.is_scrolling = True
                        state.scroll_anchor_y = y_mid
                        state.scroll_visual_anchor_y = y_mid
                        state.scroll_velocity = 0.0
                    else:
                        # Use displacement from fixed scroll-start anchor so the
                        # guide lines match the actual scroll control logic.
                        delta_y = state.scroll_visual_anchor_y - y_mid

                        if abs(delta_y) < cfg.scroll.deadzone_px:
                            target_velocity = 0.0
                        else:
                            target_velocity = delta_y * cfg.scroll.gain

                        state.scroll_velocity = (
                            (1.0 - cfg.scroll.momentum) * state.scroll_velocity
                            + cfg.scroll.momentum * target_velocity
                        )
                        state.scroll_velocity *= cfg.scroll.decay
                        state.scroll_velocity = max(
                            -cfg.scroll.max_step,
                            min(cfg.scroll.max_step, state.scroll_velocity),
                        )

                        if abs(state.scroll_velocity) >= 1.0:
                            pointer.scroll(int(round(state.scroll_velocity)))

                    # Draw deadzone bounds around a fixed anchor captured at scroll start.
                    deadzone_vis = max(6.0, cfg.scroll.deadzone_px)
                    anchor_y = state.scroll_visual_anchor_y
                    upper_y = int(max(0, anchor_y - deadzone_vis))
                    lower_y = int(min(cfg.camera.height - 1, anchor_y + deadzone_vis))
                    center_y = int(y_mid)
                    cv2.line(img, (0, upper_y), (cfg.camera.width - 1, upper_y), (0, 200, 255), 1)
                    cv2.line(img, (0, center_y), (cfg.camera.width - 1, center_y), (255, 255, 255), 1)
                    cv2.line(img, (0, lower_y), (cfg.camera.width - 1, lower_y), (0, 200, 255), 1)

                elif not window_dragging and dist_ring < cfg.gesture.rclick_dist:
                    state.mode_label = "RIGHT_CLICK"
                    state.prev_palm = None
                    draw_status(img, "RIGHT CLICK", (0, 165, 255), cfg.ui.text_origin_main)
                    cv2.circle(img, (x_ring, y_ring), 15, (0, 165, 255), cv2.FILLED)

                    if not state.is_right_clicking:
                        pointer.click(button="right")
                        state.is_right_clicking = True
                        time.sleep(0.3)

                else:
                    state.mode_label = "MOVE"
                    state.is_scrolling = False
                    state.scroll_velocity = 0.0
                    state.is_right_clicking = False

                    is_left_pinched = dist_index < cfg.gesture.click_dist
                    is_super_pinched = dist_pinky < cfg.gesture.super_drag_dist
                    super_releasing = False

                    if window_dragging:
                        # Hysteresis plus a grace period: the pinky has to be
                        # clearly apart, for a moment, before the window drops.
                        is_left_pinched = False
                        if dist_pinky < cfg.gesture.super_release_dist:
                            state.super_release_since = None
                        elif state.super_release_since is None:
                            state.super_release_since = time.monotonic()
                        super_releasing = state.super_release_since is not None
                        is_super_pinched = (
                            not super_releasing
                            or time.monotonic() - state.super_release_since
                            < cfg.gesture.super_release_grace_sec
                        )

                    if state.is_clutched:
                        # Resume from wherever the hand is now, without a jump.
                        state.prev_palm = None
                        state.is_clutched = False

                    if is_left_pinched or is_super_pinched:
                        if not state.is_clicking:
                            # SUPER + drag moves windows in Hyprland. The drag
                            # kind is latched until release.
                            if is_super_pinched:
                                pointer.superDown()
                                state.is_super_held = True
                            # Press where the cursor is, not where it's gliding to.
                            state.target_x, state.target_y = glide.snap()
                            pointer.mouseDown()
                            state.is_clicking = True
                            state.drag_anchor_x = x_palm
                            state.drag_anchor_y = y_palm
                            state.drag_unlocked = False

                        if state.is_super_held:
                            state.mode_label = "SUPER_RELEASING" if super_releasing else "SUPER_DRAG"
                            cv2.circle(img, (x_pinky, y_pinky), 15, (255, 0, 255), cv2.FILLED)
                        else:
                            state.mode_label = "LEFT_DRAG"
                            cv2.circle(img, (x_index, y_index), 15, (0, 255, 0), cv2.FILLED)

                        margin = cfg.gesture.drag_unlock_margin_px
                        in_margin = (
                            abs(x_palm - state.drag_anchor_x) <= margin
                            and abs(y_palm - state.drag_anchor_y) <= margin
                        )

                        if state.drag_unlocked or not in_margin:
                            # prev_palm is frozen while locked, so the first move
                            # covers everything since the pinch started.
                            state.drag_unlocked = True
                            move_cursor(state, glide, cfg, palm_fx, palm_fy)
                        else:
                            if not state.is_super_held:
                                state.mode_label = "LEFT_HOLD"
                            elif not super_releasing:
                                state.mode_label = "SUPER_HOLD"

                        left = int(max(0, state.drag_anchor_x - margin))
                        top = int(max(0, state.drag_anchor_y - margin))
                        right = int(min(cfg.camera.width - 1, state.drag_anchor_x + margin))
                        bottom = int(min(cfg.camera.height - 1, state.drag_anchor_y + margin))
                        box_color = (0, 255, 255) if not state.drag_unlocked else (0, 200, 0)
                        cv2.rectangle(img, (left, top), (right, bottom), box_color, 2)
                        cv2.circle(
                            img,
                            (int(state.drag_anchor_x), int(state.drag_anchor_y)),
                            3,
                            box_color,
                            cv2.FILLED,
                        )
                    else:
                        if state.is_clicking:
                            release_drag(state)
                            # Opening the pinch shifts the palm; don't move on it.
                            state.prev_palm = None
                        state.drag_unlocked = True
                        move_cursor(state, glide, cfg, palm_fx, palm_fy)

            else:
                state.prev_palm = None
                state.palm_filter.reset()
                glide.pause()

            draw_diagnostics(img, state, cfg)

            cv2.imshow(cfg.ui.window_name, img)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        glide.stop()
        release_drag(state)
        cam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
