# qrkahand: Hand Gesture Mouse Controller

Control your mouse with hand gestures using a webcam.

> **This is the `hyprland` branch.** It drives the cursor on Hyprland (Wayland) through the `zwlr_virtual_pointer_v1` protocol via [`wayland-automation`](https://pypi.org/project/wayland-automation/), and reads cursor/monitor info from `hyprctl`. For X11 or Windows use `main`.

The app uses MediaPipe hand landmarks (via cvzone), maps your palm position to cursor movement, and supports gesture-based click, right-click, scroll, clutch, and pause toggle.

## What This Project Does

- Moves cursor from palm motion
- Left-clicks and drags with thumb-index pinch
- Scrolls with thumb-middle pinch and vertical movement
- Right-clicks with thumb-ring pinch
- Moves windows with thumb-pinky pinch (SUPER + drag)
- Supports clutch mode for hand repositioning
- Toggles full controller active/paused with quick open-close transitions

## Requirements

- Python 3.12! **REQUIRED**
- Webcam
- Hyprland (Wayland) with `hyprctl` on `PATH`
- `wtype` (holds SUPER for window dragging)
  - Other wlroots compositors provide the virtual pointer protocol, but cursor position and monitor layout are read from `hyprctl`, so only Hyprland is supported.

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

## Run

```bash
python3 mouse.py
```

Press `q` in the camera window to quit.

The app reads settings from `config.toml` in the project root. If the file is missing, built-in defaults are used.

## Gestures

The app evaluates gestures in this priority order: clutch, scroll, right click, then movement/left click/window drag.

| Gesture | How to do it | Result |
| --- | --- | --- |
| Move cursor | Keep hand open/neutral and move hand | Moves the cursor by how far the palm moves, at the same physical speed on every monitor |
| Left click / drag | Pinch thumb + index (`dist_index < CLICK_DIST`) | Holds left mouse button while pinched. Cursor stays still inside a margin box around pinch start, then starts dragging after hand exits the box. |
| Scroll | Pinch thumb + middle (`dist_mid < SCROLL_DIST`), move hand up/down | Enters scroll mode; vertical motion controls direction and speed |
| Right click | Pinch thumb + ring (`dist_ring < RCLICK_DIST`) | Triggers right click (rate-limited briefly) |
| Move window | Pinch thumb + pinky (`dist_pinky < SUPER_DRAG_DIST`) | Holds SUPER + left button, Hyprland's default window-move bind. Same margin box as left drag. Ends only when the pinky is clearly apart (`SUPER_RELEASE_DIST`) for `SUPER_RELEASE_GRACE_SEC`; other gestures are ignored meanwhile. |
| Clutch | Close hand (fingers down) | Pauses movement/scroll and releases active left drag so hand can reposition |
| Toggle app active/paused | Alternate `open -> closed -> open -> closed` quickly | Enables or pauses all mouse actions |

## Tuning Guide

Edit values in `config.toml`, then rerun the app.

### Configuration Validation

At startup, configuration values are validated (for example: positive dimensions, speed > 0, decay in [0, 1], debounce < toggle window).

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
| `SPEED_MM` | `1100` | Cursor travel in millimetres when the palm crosses the whole camera frame. Same on every monitor regardless of resolution. | Faster cursor | Slower, finer cursor |
| `JITTER_CUTOFF_HZ` | `1.0` | Smoothing when the hand is nearly still (One Euro filter) | Less lag at slow speeds | Steadier cursor when holding still |
| `JITTER_BETA` | `0.03` | How quickly smoothing backs off as the hand speeds up | Less lag on fast moves | Smoother fast moves |
| `POINTER_HZ` | `0` (auto) | Cursor update rate; `0` uses your fastest monitor's refresh rate | Smoother on high-refresh monitors | Less CPU |
| `ACCEL_MIN` | `0.5` | Speed multiplier for slow, precise hand movement | Faster fine movement | Finer control |
| `ACCEL_MAX` | `1.6` | Speed multiplier for fast flicks | Cover more ground on flicks | Calmer flicks |
| `ACCEL_SPEED` | `1.5` | Hand speed (camera-frame widths per second) where `ACCEL_MAX` is reached | Reach full speed later | Reach full speed sooner |
| `ACCEL_CURVE` | `[0.6, 0.0, 0.4, 1.0]` | Shape of the ramp from min to max, as CSS `cubic-bezier(x1, y1, x2, y2)`; x values must be in [0, 1] | — | — |

Set `ACCEL_MIN` and `ACCEL_MAX` both to `1.0` to turn acceleration off.

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
| `SUPER_DRAG_DIST` | `15` | Thumb-pinky pinch threshold | Make window drag easier to trigger | Require tighter pinch |
| `SUPER_RELEASE_DIST` | `40` | Thumb-pinky distance that counts as letting go of a window drag | Harder to drop by accident | Drop with a smaller release |
| `SUPER_RELEASE_GRACE_SEC` | `0.15` | How long the pinky must stay apart before the window drops | Ignore longer tracking glitches | Drop sooner after letting go |
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

### Cursor Backend (`hyprpointer.py`)

- Cursor speed is measured in millimetres using each monitor's reported physical size, so mixed resolutions and pixel densities move at the same speed.
- The camera delivers roughly 30 frames per second, so a separate thread moves the cursor at monitor refresh rate and glides between tracked positions along cubic Bezier curves that carry the cursor's velocity from one frame to the next, so curves stay round instead of turning a corner every frame. This adds about one camera frame of latency.
- The cursor stays on real monitors and never strays into gaps in the layout.

## Suggested Presets

### Smooth and Stable

- `SPEED_MM = 950`
- `JITTER_CUTOFF_HZ = 0.6`
- `SCROLL_GAIN = 0.28`
- `SCROLL_MOMENTUM = 0.18`
- `SCROLL_DECAY = 0.90`
- `CLICK_DIST = 14`
- `SCROLL_DIST = 14`
- `RCLICK_DIST = 14`

### Fast and Responsive

- `SPEED_MM = 1300`
- `JITTER_BETA = 0.06`
- `SCROLL_GAIN = 0.45`
- `SCROLL_MOMENTUM = 0.28`
- `SCROLL_DECAY = 0.94`
- `CLICK_DIST = 16`
- `SCROLL_DIST = 16`
- `RCLICK_DIST = 16`

## Troubleshooting

- Cursor is jumpy:
  - Lower `JITTER_CUTOFF_HZ` (steadier when still).
  - Lower `JITTER_BETA` (smoother when moving).
- Cursor lags behind the hand:
  - Raise `JITTER_BETA`, then `JITTER_CUTOFF_HZ`.
- Cursor is too fast or too slow:
  - Raise `SPEED_MM` to speed up.
  - Lower `SPEED_MM` to slow down.
- Scroll starts too aggressively:
  - Lower `SCROLL_GAIN`.
  - Lower `SCROLL_MOMENTUM`.
  - Lower `SCROLL_DECAY`.
- Update rate feels slow:
  - Lower `CAMERA_WIDTH`/`CAMERA_HEIGHT`.
  - Keep `CAMERA_FPS` at `60` (or try `30` if your camera is unstable).
  - Try a different `CAMERA_INDEX`.
- Gestures trigger too easily:
  - Lower `CLICK_DIST`, `SCROLL_DIST`, and `RCLICK_DIST`.
  - Raise `TOGGLE_DEBOUNCE_SEC` if toggle false-triggers.
- Toggle gesture is hard to trigger:
  - Raise `TOGGLE_WINDOW_SEC`.
  - Lower `TOGGLE_DEBOUNCE_SEC` slightly.
