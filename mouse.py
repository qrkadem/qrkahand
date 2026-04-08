import math
import platform
import time
from dataclasses import dataclass

import cv2
import numpy as np
import pyautogui
from cvzone.HandTrackingModule import HandDetector

# --- Camera / tracking setup ---
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


def classify_hand_pose(fingers):
    if fingers[1:] == [0, 0, 0, 0]:
        return "closed"
    if fingers[1:] == [1, 1, 1, 1]:
        return "open"
    return "neutral"


def draw_status(img, text, color, origin=TEXT_ORIGIN_MAIN, scale=1.0, thickness=3):
    cv2.putText(img, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)


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
            return cam
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
    pyautogui.PAUSE = 0

    cam = open_camera(CAMERA_INDEX)
    configure_camera(cam)

    screen_width, screen_height = pyautogui.size()
    detector = HandDetector(detectionCon=DETECTION_CONFIDENCE, maxHands=MAX_HANDS)

    state = ControllerState()
    mouse_x, mouse_y = pyautogui.position()
    state.ploc_x = mouse_x
    state.ploc_y = mouse_y

    print("Press 'q' in the camera window to quit.")

    try:
        while True:
            success, img = cam.read()
            if not success:
                continue

            img = cv2.flip(img, 1)
            hands, img = detector.findHands(img, flipType=False)

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
                    draw_status(img, "PAUSED (CLUTCH)", (0, 0, 255))
                    if state.is_clicking:
                        pyautogui.mouseUp()
                        state.is_clicking = False
                    state.is_scrolling = False
                    state.is_clutched = True

                elif dist_mid < SCROLL_DIST:
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
                    draw_status(img, "RIGHT CLICK", (0, 165, 255))
                    cv2.circle(img, (x_ring, y_ring), 15, (0, 165, 255), cv2.FILLED)

                    if not state.is_right_clicking:
                        pyautogui.click(button="right")
                        state.is_right_clicking = True
                        time.sleep(0.3)

                else:
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
                        cv2.circle(img, (x_index, y_index), 15, (0, 255, 0), cv2.FILLED)
                        if not state.is_clicking:
                            pyautogui.mouseDown()
                            state.is_clicking = True
                    else:
                        if state.is_clicking:
                            pyautogui.mouseUp()
                            state.is_clicking = False

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
