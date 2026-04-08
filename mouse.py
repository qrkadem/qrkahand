import math
import os
import platform
import time
import importlib
from dataclasses import dataclass

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = importlib.import_module("tomli")

import cv2
import numpy as np
import pyautogui
from cvzone.HandTrackingModule import HandDetector

# --- Camera / tracking setup ---
CONFIG_FILE = "config.toml"

CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 60
DETECTION_CONFIDENCE = 0.8
MAX_HANDS = 1

# --- Cursor mapping / smoothing ---
FRAME_REDUCTION = 120
CURSOR_SMOOTHING = 4
MOUSE_SPEED = 1.0

# --- Scroll tuning ---
SCROLL_GAIN = 0.35
SCROLL_DEADZONE_PX = 2
MAX_SCROLL_STEP = 18
SCROLL_MOMENTUM = 0.22
SCROLL_DECAY = 0.92

# --- Action thresholds (pixels) ---
CLICK_DIST = 15
SCROLL_DIST = 15
RCLICK_DIST = 15

# --- Program toggle gesture ---
# Toggle active/pause by rapidly alternating OPEN <-> CLOSED twice.
TOGGLE_WINDOW_SEC = 1.2
TOGGLE_DEBOUNCE_SEC = 0.10

# --- UI labels ---
WINDOW_NAME = "Gesture"
TEXT_ORIGIN_MAIN = (50, 50)
TEXT_ORIGIN_HINT = (50, 90)
TEXT_ORIGIN_DIAG = (10, 20)
SHOW_DIAGNOSTICS = True


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


def validate_settings():
    errors = []

    if CAMERA_INDEX < 0:
        errors.append("CAMERA_INDEX must be >= 0")
    if CAMERA_WIDTH <= 0:
        errors.append("CAMERA_WIDTH must be > 0")
    if CAMERA_HEIGHT <= 0:
        errors.append("CAMERA_HEIGHT must be > 0")
    if CAMERA_FPS <= 0:
        errors.append("CAMERA_FPS must be > 0")
    if not (0.0 < DETECTION_CONFIDENCE <= 1.0):
        errors.append("DETECTION_CONFIDENCE must be in (0, 1]")
    if MAX_HANDS < 1:
        errors.append("MAX_HANDS must be >= 1")

    if FRAME_REDUCTION < 0:
        errors.append("FRAME_REDUCTION must be >= 0")
    if CURSOR_SMOOTHING <= 0:
        errors.append("CURSOR_SMOOTHING must be > 0")
    if MOUSE_SPEED <= 0:
        errors.append("MOUSE_SPEED must be > 0")

    if SCROLL_GAIN < 0:
        errors.append("SCROLL_GAIN must be >= 0")
    if SCROLL_DEADZONE_PX < 0:
        errors.append("SCROLL_DEADZONE_PX must be >= 0")
    if MAX_SCROLL_STEP <= 0:
        errors.append("MAX_SCROLL_STEP must be > 0")
    if not (0.0 <= SCROLL_MOMENTUM <= 1.0):
        errors.append("SCROLL_MOMENTUM must be in [0, 1]")
    if not (0.0 <= SCROLL_DECAY <= 1.0):
        errors.append("SCROLL_DECAY must be in [0, 1]")

    if CLICK_DIST <= 0:
        errors.append("CLICK_DIST must be > 0")
    if SCROLL_DIST <= 0:
        errors.append("SCROLL_DIST must be > 0")
    if RCLICK_DIST <= 0:
        errors.append("RCLICK_DIST must be > 0")

    if TOGGLE_WINDOW_SEC <= 0:
        errors.append("TOGGLE_WINDOW_SEC must be > 0")
    if TOGGLE_DEBOUNCE_SEC < 0:
        errors.append("TOGGLE_DEBOUNCE_SEC must be >= 0")
    if TOGGLE_DEBOUNCE_SEC >= TOGGLE_WINDOW_SEC:
        errors.append("TOGGLE_DEBOUNCE_SEC must be less than TOGGLE_WINDOW_SEC")

    if errors:
        raise ValueError("Invalid configuration:\n- " + "\n- ".join(errors))


def load_config(config_path=CONFIG_FILE):
    global CAMERA_INDEX
    global CAMERA_WIDTH
    global CAMERA_HEIGHT
    global CAMERA_FPS
    global DETECTION_CONFIDENCE
    global MAX_HANDS
    global FRAME_REDUCTION
    global CURSOR_SMOOTHING
    global MOUSE_SPEED
    global SCROLL_GAIN
    global SCROLL_DEADZONE_PX
    global MAX_SCROLL_STEP
    global SCROLL_MOMENTUM
    global SCROLL_DECAY
    global CLICK_DIST
    global SCROLL_DIST
    global RCLICK_DIST
    global TOGGLE_WINDOW_SEC
    global TOGGLE_DEBOUNCE_SEC
    global WINDOW_NAME
    global TEXT_ORIGIN_MAIN
    global TEXT_ORIGIN_HINT
    global TEXT_ORIGIN_DIAG
    global SHOW_DIAGNOSTICS

    if not os.path.exists(config_path):
        validate_settings()
        return

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    camera = data.get("camera", {})
    CAMERA_INDEX = int(camera.get("index", CAMERA_INDEX))
    CAMERA_WIDTH = int(camera.get("width", CAMERA_WIDTH))
    CAMERA_HEIGHT = int(camera.get("height", CAMERA_HEIGHT))
    CAMERA_FPS = int(camera.get("fps", CAMERA_FPS))
    DETECTION_CONFIDENCE = float(camera.get("detection_confidence", DETECTION_CONFIDENCE))
    MAX_HANDS = int(camera.get("max_hands", MAX_HANDS))

    cursor = data.get("cursor", {})
    FRAME_REDUCTION = int(cursor.get("frame_reduction", FRAME_REDUCTION))
    CURSOR_SMOOTHING = float(cursor.get("smoothing", CURSOR_SMOOTHING))
    MOUSE_SPEED = float(cursor.get("mouse_speed", MOUSE_SPEED))

    scroll = data.get("scroll", {})
    SCROLL_GAIN = float(scroll.get("gain", SCROLL_GAIN))
    SCROLL_DEADZONE_PX = float(scroll.get("deadzone_px", SCROLL_DEADZONE_PX))
    MAX_SCROLL_STEP = float(scroll.get("max_step", MAX_SCROLL_STEP))
    SCROLL_MOMENTUM = float(scroll.get("momentum", SCROLL_MOMENTUM))
    SCROLL_DECAY = float(scroll.get("decay", SCROLL_DECAY))

    gesture = data.get("gesture", {})
    CLICK_DIST = float(gesture.get("click_dist", CLICK_DIST))
    SCROLL_DIST = float(gesture.get("scroll_dist", SCROLL_DIST))
    RCLICK_DIST = float(gesture.get("rclick_dist", RCLICK_DIST))
    TOGGLE_WINDOW_SEC = float(gesture.get("toggle_window_sec", TOGGLE_WINDOW_SEC))
    TOGGLE_DEBOUNCE_SEC = float(gesture.get("toggle_debounce_sec", TOGGLE_DEBOUNCE_SEC))

    ui = data.get("ui", {})
    WINDOW_NAME = str(ui.get("window_name", WINDOW_NAME))
    if "text_origin_main" in ui:
        TEXT_ORIGIN_MAIN = _parse_origin(ui["text_origin_main"], "ui.text_origin_main")
    if "text_origin_hint" in ui:
        TEXT_ORIGIN_HINT = _parse_origin(ui["text_origin_hint"], "ui.text_origin_hint")
    if "text_origin_diag" in ui:
        TEXT_ORIGIN_DIAG = _parse_origin(ui["text_origin_diag"], "ui.text_origin_diag")
    SHOW_DIAGNOSTICS = bool(ui.get("show_diagnostics", SHOW_DIAGNOSTICS))

    validate_settings()


def classify_hand_pose(fingers):
    if fingers[1:] == [0, 0, 0, 0]:
        return "closed"
    if fingers[1:] == [1, 1, 1, 1]:
        return "open"
    return "neutral"


def draw_status(img, text, color, origin=TEXT_ORIGIN_MAIN, scale=1.0, thickness=3):
    cv2.putText(img, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)


def draw_diagnostics(img, state):
    if not SHOW_DIAGNOSTICS:
        return

    lines = [
        f"FPS: {state.fps:.1f}",
        f"Backend: {state.backend_name}",
        f"Capture: {state.capture_label}",
        f"Mode: {state.mode_label}",
        f"Active: {'yes' if state.program_active else 'no'}",
    ]
    x, y = TEXT_ORIGIN_DIAG
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


def handle_program_toggle(current_pose, state):
    now = time.time()
    if current_pose not in ("open", "closed"):
        return

    if (
        state.last_hand_pose in ("open", "closed")
        and current_pose != state.last_hand_pose
        and (now - state.last_toggle_transition_ts) > TOGGLE_DEBOUNCE_SEC
    ):
        if state.toggle_transition_count == 0 or (now - state.toggle_window_start) > TOGGLE_WINDOW_SEC:
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


def configure_camera(cam):
    system = platform.system()

    # Common capture settings.
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cam.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

    if system == "Windows":
        # MJPG often improves FPS and latency on USB webcams in Windows.
        cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))


def main():
    load_config()
    pyautogui.PAUSE = 0

    cam, backend = open_camera(CAMERA_INDEX)
    configure_camera(cam)

    screen_width, screen_height = pyautogui.size()
    detector = HandDetector(detectionCon=DETECTION_CONFIDENCE, maxHands=MAX_HANDS)

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
    state.capture_label = f"{CAMERA_WIDTH}x{CAMERA_HEIGHT}@{CAMERA_FPS}"

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
                handle_program_toggle(current_pose, state)

                if not state.program_active:
                    state.mode_label = "PROGRAM_PAUSED"
                    draw_status(img, "PROGRAM PAUSED", (0, 0, 255))
                    draw_status(
                        img,
                        "Toggle: open/close x2 quickly",
                        (0, 200, 255),
                        origin=TEXT_ORIGIN_HINT,
                        scale=0.7,
                        thickness=2,
                    )
                    cv2.imshow(WINDOW_NAME, img)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                    continue

                if current_pose == "closed":
                    state.mode_label = "CLUTCH"
                    draw_status(img, "PAUSED (CLUTCH)", (0, 0, 255))
                    if state.is_clicking:
                        pyautogui.mouseUp()
                        state.is_clicking = False
                    state.is_scrolling = False
                    state.is_clutched = True

                elif dist_mid < SCROLL_DIST:
                    state.mode_label = "SCROLL"
                    draw_status(img, "SCROLLING", (255, 255, 0))
                    cv2.circle(img, (x_mid, y_mid), 15, (255, 255, 0), cv2.FILLED)

                    if not state.is_scrolling:
                        state.is_scrolling = True
                        state.scroll_anchor_y = y_mid
                        state.scroll_velocity = 0.0
                    else:
                        delta_y = state.scroll_anchor_y - y_mid
                        state.scroll_anchor_y = y_mid

                        if abs(delta_y) < SCROLL_DEADZONE_PX:
                            target_velocity = 0.0
                        else:
                            target_velocity = delta_y * SCROLL_GAIN

                        state.scroll_velocity = (
                            (1.0 - SCROLL_MOMENTUM) * state.scroll_velocity
                            + SCROLL_MOMENTUM * target_velocity
                        )
                        state.scroll_velocity *= SCROLL_DECAY
                        state.scroll_velocity = max(
                            -MAX_SCROLL_STEP,
                            min(MAX_SCROLL_STEP, state.scroll_velocity),
                        )

                        if abs(state.scroll_velocity) >= 1.0:
                            pyautogui.scroll(int(round(state.scroll_velocity)))

                elif dist_ring < RCLICK_DIST:
                    state.mode_label = "RIGHT_CLICK"
                    draw_status(img, "RIGHT CLICK", (0, 165, 255))
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
                        (FRAME_REDUCTION, CAMERA_WIDTH - FRAME_REDUCTION),
                        (0, screen_width),
                    )
                    mapped_y = np.interp(
                        y_palm,
                        (FRAME_REDUCTION, CAMERA_HEIGHT - FRAME_REDUCTION),
                        (0, screen_height),
                    )

                    if state.is_clutched:
                        state.offset_x = state.ploc_x - mapped_x
                        state.offset_y = state.ploc_y - mapped_y
                        state.is_clutched = False

                    target_x = mapped_x + state.offset_x
                    target_y = mapped_y + state.offset_y

                    cloc_x = state.ploc_x + ((target_x - state.ploc_x) / CURSOR_SMOOTHING) * MOUSE_SPEED
                    cloc_y = state.ploc_y + ((target_y - state.ploc_y) / CURSOR_SMOOTHING) * MOUSE_SPEED

                    pyautogui.moveTo(cloc_x, cloc_y)
                    state.ploc_x, state.ploc_y = cloc_x, cloc_y

                    if dist_index < CLICK_DIST:
                        state.mode_label = "LEFT_DRAG"
                        cv2.circle(img, (x_index, y_index), 15, (0, 255, 0), cv2.FILLED)
                        if not state.is_clicking:
                            pyautogui.mouseDown()
                            state.is_clicking = True
                    else:
                        if state.is_clicking:
                            pyautogui.mouseUp()
                            state.is_clicking = False

            draw_diagnostics(img, state)

            cv2.imshow(WINDOW_NAME, img)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        if state.is_clicking:
            pyautogui.mouseUp()
        cam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
