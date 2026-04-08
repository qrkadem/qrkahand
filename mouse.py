import math
import os
import platform
import time
import importlib
from dataclasses import dataclass, field

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = importlib.import_module("tomli")

import cv2
import numpy as np
import pyautogui
from cvzone.HandTrackingModule import HandDetector

CONFIG_FILE = "config.toml"


@dataclass
class CameraConfig:
    index: int = 0
    width: int = 640
    height: int = 480
    fps: int = 60
    detection_confidence: float = 0.8
    max_hands: int = 1


@dataclass
class CursorConfig:
    frame_reduction: int = 120
    smoothing: float = 4.0
    mouse_speed: float = 1.0


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
    toggle_window_sec: float = 1.2
    toggle_debounce_sec: float = 0.10


@dataclass
class UiConfig:
    window_name: str = "Gesture"
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
    is_right_clicking: bool = False
    is_scrolling: bool = False
    is_clutched: bool = False
    offset_x: float = 0.0
    offset_y: float = 0.0
    scroll_anchor_y: float = 0.0
    scroll_velocity: float = 0.0
    program_active: bool = True
    last_hand_pose: str = "unknown"
    toggle_transition_count: int = 0
    toggle_window_start: float = 0.0
    last_toggle_transition_ts: float = 0.0
    ploc_x: float = 0.0
    ploc_y: float = 0.0
    fps: float = 0.0
    fps_frame_count: int = 0
    fps_last_ts: float = 0.0
    backend_name: str = "unknown"
    capture_label: str = "unknown"
    mode_label: str = "NO_HAND"


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
    if camera.max_hands < 1:
        errors.append("MAX_HANDS must be >= 1")

    if cursor.frame_reduction < 0:
        errors.append("FRAME_REDUCTION must be >= 0")
    if cursor.smoothing <= 0:
        errors.append("CURSOR_SMOOTHING must be > 0")
    if cursor.mouse_speed <= 0:
        errors.append("MOUSE_SPEED must be > 0")

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
    cfg.camera.max_hands = int(camera.get("max_hands", cfg.camera.max_hands))

    cursor = data.get("cursor", {})
    cfg.cursor.frame_reduction = int(cursor.get("frame_reduction", cfg.cursor.frame_reduction))
    cfg.cursor.smoothing = float(cursor.get("smoothing", cfg.cursor.smoothing))
    cfg.cursor.mouse_speed = float(cursor.get("mouse_speed", cfg.cursor.mouse_speed))

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


def classify_hand_pose(fingers):
    if fingers[1:] == [0, 0, 0, 0]:
        return "closed"
    if fingers[1:] == [1, 1, 1, 1]:
        return "open"
    return "neutral"


def draw_status(img, text, color, origin, scale=1.0, thickness=3):
    cv2.putText(img, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)


def draw_diagnostics(img, state, cfg):
    if not cfg.ui.show_diagnostics:
        return

    lines = [
        f"FPS: {state.fps:.1f}",
        f"Backend: {state.backend_name}",
        f"Capture: {state.capture_label}",
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
                if state.is_clicking:
                    pyautogui.mouseUp()
                    state.is_clicking = False
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
    system = platform.system()
    if system == "Windows":
        # Prefer low-latency backends first on Windows.
        backends = [cv2.CAP_DSHOW, cv2.CAP_ANY, cv2.CAP_MSMF]
    elif system == "Linux":
        backends = [cv2.CAP_V4L2, cv2.CAP_ANY]
    elif system == "Darwin":
        backends = [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]
    else:
        backends = [cv2.CAP_ANY]

    for backend in backends:
        cam = cv2.VideoCapture(camera_index, backend)
        if cam.isOpened():
            return cam, backend
        cam.release()

    raise RuntimeError("Could not open camera with available backends.")


def configure_camera(cam, cfg):
    system = platform.system()

    # Common capture settings.
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.camera.width)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.camera.height)
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cam.set(cv2.CAP_PROP_FPS, cfg.camera.fps)

    if system == "Windows":
        # MJPG often improves FPS and latency on USB webcams in Windows.
        cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))


def main():
    cfg = load_config()
    pyautogui.PAUSE = 0

    cam, backend = open_camera(cfg.camera.index)
    configure_camera(cam, cfg)

    screen_width, screen_height = pyautogui.size()
    detector = HandDetector(
        detectionCon=cfg.camera.detection_confidence,
        maxHands=cfg.camera.max_hands,
    )

    state = ControllerState()
    mouse_x, mouse_y = pyautogui.position()
    state.ploc_x = mouse_x
    state.ploc_y = mouse_y
    state.fps_last_ts = time.time()
    state.backend_name = {
        getattr(cv2, "CAP_DSHOW", -1): "DSHOW",
        getattr(cv2, "CAP_MSMF", -2): "MSMF",
        getattr(cv2, "CAP_V4L2", -3): "V4L2",
        getattr(cv2, "CAP_AVFOUNDATION", -4): "AVFOUNDATION",
        getattr(cv2, "CAP_ANY", -5): "ANY",
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
                x_palm, y_palm = lm_list[9][0], lm_list[9][1]

                dist_index = math.hypot(x_index - x_thumb, y_index - y_thumb)
                dist_mid = math.hypot(x_mid - x_thumb, y_mid - y_thumb)
                dist_ring = math.hypot(x_ring - x_thumb, y_ring - y_thumb)

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

                if current_pose == "closed":
                    state.mode_label = "CLUTCH"
                    draw_status(img, "PAUSED (CLUTCH)", (0, 0, 255), cfg.ui.text_origin_main)
                    if state.is_clicking:
                        pyautogui.mouseUp()
                        state.is_clicking = False
                    state.is_scrolling = False
                    state.is_clutched = True

                elif dist_mid < cfg.gesture.scroll_dist:
                    state.mode_label = "SCROLL"
                    draw_status(img, "SCROLLING", (255, 255, 0), cfg.ui.text_origin_main)
                    cv2.circle(img, (x_mid, y_mid), 15, (255, 255, 0), cv2.FILLED)

                    if not state.is_scrolling:
                        state.is_scrolling = True
                        state.scroll_anchor_y = y_mid
                        state.scroll_velocity = 0.0
                    else:
                        delta_y = state.scroll_anchor_y - y_mid
                        state.scroll_anchor_y = y_mid

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
                            pyautogui.scroll(int(round(state.scroll_velocity)))

                elif dist_ring < cfg.gesture.rclick_dist:
                    state.mode_label = "RIGHT_CLICK"
                    draw_status(img, "RIGHT CLICK", (0, 165, 255), cfg.ui.text_origin_main)
                    cv2.circle(img, (x_ring, y_ring), 15, (0, 165, 255), cv2.FILLED)

                    if not state.is_right_clicking:
                        pyautogui.click(button="right")
                        state.is_right_clicking = True
                        time.sleep(0.3)

                else:
                    state.mode_label = "MOVE"
                    state.is_scrolling = False
                    state.scroll_velocity = 0.0
                    state.is_right_clicking = False

                    mapped_x = np.interp(
                        x_palm,
                        (cfg.cursor.frame_reduction, cfg.camera.width - cfg.cursor.frame_reduction),
                        (0, screen_width),
                    )
                    mapped_y = np.interp(
                        y_palm,
                        (cfg.cursor.frame_reduction, cfg.camera.height - cfg.cursor.frame_reduction),
                        (0, screen_height),
                    )

                    if state.is_clutched:
                        state.offset_x = state.ploc_x - mapped_x
                        state.offset_y = state.ploc_y - mapped_y
                        state.is_clutched = False

                    target_x = mapped_x + state.offset_x
                    target_y = mapped_y + state.offset_y

                    cloc_x = state.ploc_x + (
                        (target_x - state.ploc_x) / cfg.cursor.smoothing
                    ) * cfg.cursor.mouse_speed
                    cloc_y = state.ploc_y + (
                        (target_y - state.ploc_y) / cfg.cursor.smoothing
                    ) * cfg.cursor.mouse_speed

                    pyautogui.moveTo(cloc_x, cloc_y)
                    state.ploc_x, state.ploc_y = cloc_x, cloc_y

                    if dist_index < cfg.gesture.click_dist:
                        state.mode_label = "LEFT_DRAG"
                        cv2.circle(img, (x_index, y_index), 15, (0, 255, 0), cv2.FILLED)
                        if not state.is_clicking:
                            pyautogui.mouseDown()
                            state.is_clicking = True
                    else:
                        if state.is_clicking:
                            pyautogui.mouseUp()
                            state.is_clicking = False

            draw_diagnostics(img, state, cfg)

            cv2.imshow(cfg.ui.window_name, img)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        if state.is_clicking:
            pyautogui.mouseUp()
        cam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
