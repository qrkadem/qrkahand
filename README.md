# qrkahand: Hand Gesture Mouse Controller

Control your mouse with hand gestures using a webcam.

The app uses MediaPipe hand landmarks (via cvzone), maps your palm position to cursor movement, and supports gesture-based click, right-click, scroll, clutch, and pause toggle.

## What This Project Does

- Moves cursor from palm motion
- Left-clicks and drags with thumb-index pinch
- Scrolls with thumb-middle pinch and vertical movement
- Right-clicks with thumb-ring pinch
- Supports clutch mode for hand repositioning
- Toggles full controller active/paused with quick open-close transitions

## Requirements

- Python 3.12! **REQUIRED**
- Webcam
- Linux note: some systems need `python3-tk` and `scrot`
  - **qrkahand** does *not* work on Wayland, I am very sorry.
- Windows note: no extra system packages are typically required

## Setup

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Optional Linux packages

```bash
sudo apt update
sudo apt install -y python3-tk scrot
```

### 4. Windows notes

- Camera backend selection is automatic on Windows (DirectShow/MSMF fallback).
- If the wrong camera opens, change `CAMERA_INDEX` in `mouse.py`.

## Run

```bash
python3 mouse.py
```

Press `q` in the camera window to quit.

The app reads settings from `config.toml` in the project root. If the file is missing, built-in defaults are used.

## Gestures

The app evaluates gestures in this priority order: clutch, scroll, right click, then movement/left click.

| Gesture | How to do it | Result |
| --- | --- | --- |
| Move cursor | Keep hand open/neutral and move hand | Moves cursor from palm position with smoothing and speed scaling |
| Left click / drag | Pinch thumb + index (`dist_index < CLICK_DIST`) | Holds left mouse button while pinched. Cursor stays still inside a margin box around pinch start, then starts dragging after hand exits the box. |
| Scroll | Pinch thumb + middle (`dist_mid < SCROLL_DIST`), move hand up/down | Enters scroll mode; vertical motion controls direction and speed |
| Right click | Pinch thumb + ring (`dist_ring < RCLICK_DIST`) | Triggers right click (rate-limited briefly) |
| Clutch | Close hand (fingers down) | Pauses movement/scroll and releases active left drag so hand can reposition |
| Toggle app active/paused | Alternate `open -> closed -> open -> closed` quickly | Enables or pauses all mouse actions |

## Tuning Guide

Edit values in `config.toml`, then rerun the app.

### Configuration Validation

At startup, configuration values are validated (for example: positive dimensions, smoothing > 0, decay in [0, 1], debounce < toggle window).

If values are invalid, the app exits with a clear configuration error.

### Diagnostics Overlay

The preview window includes a live diagnostics overlay with:

- FPS
- Camera backend
- Capture target (resolution/FPS)
- Current mode (for example `MOVE`, `SCROLL`, `LEFT_DRAG`, `PROGRAM_PAUSED`)
- Active/paused state

You can disable this via `ui.show_diagnostics = false` in `config.toml`.

### Camera and Detection

| Constant | Default | Purpose | Raise it to... | Lower it to... |
| --- | ---: | --- | --- | --- |
| `CAMERA_INDEX` | `0` | Camera device ID | Use another camera (`1`, `2`, ...) | Use primary camera |
| `CAMERA_WIDTH` | `640` | Capture width | Improve detail (higher CPU) | Reduce CPU and latency |
| `CAMERA_HEIGHT` | `480` | Capture height | Improve detail (higher CPU) | Reduce CPU and latency |
| `CAMERA_FPS` | `60` | Target camera FPS hint | Request faster updates (if camera supports it) | Reduce CPU use |
| `DETECTION_CONFIDENCE` | `0.8` | Hand detection threshold | Reduce false positives | Detect more aggressively |
| `MAX_HANDS` | `1` | Hands tracked | Track both hands | Keep behavior stable/simple |

### Cursor Movement

| Constant | Default | Purpose | Raise it to... | Lower it to... |
| --- | ---: | --- | --- | --- |
| `FRAME_REDUCTION` | `120` | Mapping margin around frame edges | Reduce edge jitter | Use more frame area |
| `CURSOR_SMOOTHING` | `4` | Cursor interpolation smoothing | Smooth/slower movement | Faster/snappier movement |
| `MOUSE_SPEED` | `1.0` | Speed multiplier after smoothing | Increase overall cursor speed | Decrease overall cursor speed |

### Scroll Behavior

| Constant | Default | Purpose | Raise it to... | Lower it to... |
| --- | ---: | --- | --- | --- |
| `SCROLL_GAIN` | `0.35` | Base scroll sensitivity | Scroll faster | Scroll slower/finer |
| `SCROLL_DEADZONE_PX` | `2` | Ignore tiny vertical movement | Filter more jitter | React to tiny movement |
| `MAX_SCROLL_STEP` | `18` | Per-frame scroll cap | Allow faster peak scroll | Prevent large bursts |
| `SCROLL_MOMENTUM` | `0.22` | How fast velocity follows target | Make scroll more responsive | Make acceleration gentler |
| `SCROLL_DECAY` | `0.92` | Per-frame velocity damping | Keep glide longer | Stop scrolling sooner |

### Gesture Thresholds

| Constant | Default | Purpose | Raise it to... | Lower it to... |
| --- | ---: | --- | --- | --- |
| `CLICK_DIST` | `15` | Thumb-index pinch threshold | Make click easier to trigger | Require tighter pinch |
| `SCROLL_DIST` | `15` | Thumb-middle pinch threshold | Make scroll easier to trigger | Require tighter pinch |
| `RCLICK_DIST` | `15` | Thumb-ring pinch threshold | Make right click easier to trigger | Require tighter pinch |
| `DRAG_UNLOCK_MARGIN_PX` | `22` | Half-size of the drag unlock box in camera pixels | Require larger motion before drag starts | Start dragging sooner after pinch |

### Toggle Timing

| Constant | Default | Purpose | Raise it to... | Lower it to... |
| --- | ---: | --- | --- | --- |
| `TOGGLE_WINDOW_SEC` | `1.2` | Time allowed for toggle transitions | Make toggle easier/slower | Require faster toggles |
| `TOGGLE_DEBOUNCE_SEC` | `0.10` | Minimum time between transitions | Prevent accidental toggles | Accept faster transitions |

### UI Constants

| Constant | Default | Purpose |
| --- | --- | --- |
| `WINDOW_NAME` | `"Gesture"` | Camera preview window title |
| `TEXT_ORIGIN_MAIN` | `(50, 50)` | Main status text location |
| `TEXT_ORIGIN_HINT` | `(50, 90)` | Hint/status text location |
| `TEXT_ORIGIN_DIAG` | `(10, 20)` | Diagnostics overlay origin |
| `SHOW_DIAGNOSTICS` | `true` | Toggle on-screen diagnostics overlay |

### Runtime Setting

- `pyautogui.PAUSE = 0`
  - Removes automatic delay between PyAutoGUI actions for lower latency.

## Suggested Presets

### Smooth and Stable

- `CURSOR_SMOOTHING = 5`
- `MOUSE_SPEED = 0.9`
- `SCROLL_GAIN = 0.28`
- `SCROLL_MOMENTUM = 0.18`
- `SCROLL_DECAY = 0.90`
- `CLICK_DIST = 14`
- `SCROLL_DIST = 14`
- `RCLICK_DIST = 14`

### Fast and Responsive

- `CURSOR_SMOOTHING = 3`
- `MOUSE_SPEED = 1.15`
- `SCROLL_GAIN = 0.45`
- `SCROLL_MOMENTUM = 0.28`
- `SCROLL_DECAY = 0.94`
- `CLICK_DIST = 16`
- `SCROLL_DIST = 16`
- `RCLICK_DIST = 16`

## Troubleshooting

- Cursor is jumpy:
  - Increase `CURSOR_SMOOTHING`.
  - Increase `FRAME_REDUCTION` slightly.
- Cursor is too fast or too slow:
  - Raise `MOUSE_SPEED` to speed up.
  - Lower `MOUSE_SPEED` to slow down.
- Scroll starts too aggressively:
  - Lower `SCROLL_GAIN`.
  - Lower `SCROLL_MOMENTUM`.
  - Lower `SCROLL_DECAY`.
- Windows update rate feels slow:
  - Lower `CAMERA_WIDTH`/`CAMERA_HEIGHT`.
  - Keep `CAMERA_FPS` at `60` (or try `30` if your camera is unstable).
  - Try a different `CAMERA_INDEX`.
- Gestures trigger too easily:
  - Lower `CLICK_DIST`, `SCROLL_DIST`, and `RCLICK_DIST`.
  - Raise `TOGGLE_DEBOUNCE_SEC` if toggle false-triggers.
- Toggle gesture is hard to trigger:
  - Raise `TOGGLE_WINDOW_SEC`.
  - Lower `TOGGLE_DEBOUNCE_SEC` slightly.
