# qrkahand Configuration Reference

This document explains every tunable constant in `mouse.py` and how each value affects behavior.

## Installation

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Linux prerequisites (recommended)

Some Linux setups need extra system packages for OpenCV and PyAutoGUI integrations:

```bash
sudo apt update
sudo apt install -y python3-tk scrot
```

### 4. Run the app

```bash
python3 mouse.py
```

Press `q` in the camera window to quit.

## Quick Start

1. Open `mouse.py`.
2. Edit the constants near the top of the file.
3. Re-run the script and test.

Tip: change one value at a time so you can feel what each constant does.

## Camera / Tracking Setup

| Constant | Default | What It Controls | Increase To... | Decrease To... |
|---|---:|---|---|---|
| `CAMERA_INDEX` | `0` | Which camera device to open. | Select another camera (`1`, `2`, etc.). | Use the primary camera. |
| `CAMERA_WIDTH` | `640` | Capture width in pixels. | Get more detail (may use more CPU). | Reduce CPU usage / latency. |
| `CAMERA_HEIGHT` | `480` | Capture height in pixels. | Get more detail (may use more CPU). | Reduce CPU usage / latency. |
| `DETECTION_CONFIDENCE` | `0.8` | Hand detector confidence threshold. | Reduce false positives. | Detect hands more aggressively. |
| `MAX_HANDS` | `1` | Max hands tracked. | Track both hands if needed. | Keep single-hand behavior stable. |

## Cursor Mapping / Smoothing

| Constant | Default | What It Controls | Increase To... | Decrease To... |
|---|---:|---|---|---|
| `FRAME_REDUCTION` | `120` | Dead border around camera frame used for mapping to screen. | Add margin and reduce edge jitter. | Use more of camera frame area. |
| `CURSOR_SMOOTHING` | `4` | Cursor interpolation smoothing factor. | Make movement smoother/slower. | Make movement quicker/snappier. |

## Scroll Tuning

| Constant | Default | What It Controls | Increase To... | Decrease To... |
|---|---:|---|---|---|
| `SCROLL_GAIN` | `0.35` | Base multiplier from finger motion to scroll velocity. | Scroll faster per hand motion. | Scroll slower / finer control. |
| `SCROLL_DEADZONE_PX` | `2` | Small motion ignored while scrolling. | Filter more tiny jitter. | React to very small movement. |
| `MAX_SCROLL_STEP` | `18` | Max per-frame scroll step (speed cap). | Allow faster peak scrolling. | Prevent big scroll bursts. |
| `SCROLL_MOMENTUM` | `0.22` | How fast velocity follows target velocity. | More responsive / punchy. | More gradual acceleration. |
| `SCROLL_DECAY` | `0.92` | Per-frame damping of scroll velocity. | Keep momentum longer (more glide). | Stop momentum quicker. |

## Gesture Thresholds (Pixels)

| Constant | Default | What It Controls | Increase To... | Decrease To... |
|---|---:|---|---|---|
| `CLICK_DIST` | `15` | Thumb-index pinch distance for left click/drag. | Make click easier to trigger. | Require tighter pinch. |
| `SCROLL_DIST` | `15` | Thumb-middle pinch distance to enter scroll mode. | Make scrolling easier to trigger. | Require tighter pinch. |
| `RCLICK_DIST` | `15` | Thumb-ring pinch distance to right click. | Make right click easier to trigger. | Require tighter pinch. |

## Program Toggle Gesture

The app toggles active/pause when it sees fast open/close transitions twice in quick succession.

| Constant | Default | What It Controls | Increase To... | Decrease To... |
|---|---:|---|---|---|
| `TOGGLE_WINDOW_SEC` | `1.2` | Time window to complete toggle transitions. | Make toggle easier/slower paced. | Require faster toggle gesture. |
| `TOGGLE_DEBOUNCE_SEC` | `0.10` | Minimum time between accepted transitions. | Reduce accidental toggles from noisy flips. | Accept very fast transitions. |

## UI Labels

| Constant | Default | What It Controls |
|---|---|---|
| `WINDOW_NAME` | `"Gesture"` | OpenCV display window title. |
| `TEXT_ORIGIN_MAIN` | `(50, 50)` | Main status text position. |
| `TEXT_ORIGIN_HINT` | `(50, 90)` | Secondary hint text position. |

## Runtime Setting (Not a constant)

- `pyautogui.PAUSE = 0`
  - Disables PyAutoGUI’s automatic pause between actions for lower latency.

## Suggested Presets

### Smoother / Safer

- `CURSOR_SMOOTHING = 5`
- `SCROLL_GAIN = 0.28`
- `SCROLL_MOMENTUM = 0.18`
- `SCROLL_DECAY = 0.90`
- `CLICK_DIST = 14`
- `SCROLL_DIST = 14`
- `RCLICK_DIST = 14`

### Faster / More Responsive

- `CURSOR_SMOOTHING = 3`
- `SCROLL_GAIN = 0.45`
- `SCROLL_MOMENTUM = 0.28`
- `SCROLL_DECAY = 0.94`
- `CLICK_DIST = 16`
- `SCROLL_DIST = 16`
- `RCLICK_DIST = 16`

## Troubleshooting

- Cursor feels jumpy:
  - Increase `CURSOR_SMOOTHING`.
  - Increase `FRAME_REDUCTION` slightly.
- Scroll starts too suddenly:
  - Lower `SCROLL_GAIN`.
  - Lower `SCROLL_MOMENTUM`.
  - Lower `SCROLL_DECAY`.
- Gestures trigger too easily:
  - Lower pinch thresholds (`CLICK_DIST`, `SCROLL_DIST`, `RCLICK_DIST`).
  - Increase `TOGGLE_DEBOUNCE_SEC` if pause toggle false-triggers.
- Toggle is hard to trigger:
  - Increase `TOGGLE_WINDOW_SEC`.
  - Reduce `TOGGLE_DEBOUNCE_SEC` slightly.
