#!/usr/bin/env python3
"""
Drone Training Controller
=========================
Connects to the XIAO ESP32-S3 MJPEG stream, detects AprilTags with OpenCV,
and overlays large directional arrows telling the human operator what to do.

Requirements (pip install):
    opencv-python
    opencv-contrib-python   ← needed for AprilTag detector
    numpy
    requests

Usage:
    python3 drone_controller.py --ip 192.168.1.42

Replace the IP with the one printed to Serial Monitor on the XIAO.
"""

import argparse
import time
import urllib.request
import cv2
import numpy as np

# ── AprilTag family used on your landing pad ───────────────────────────────────
APRILTAG_DICT = cv2.aruco.DICT_APRILTAG_36h11

# ── Mission states ─────────────────────────────────────────────────────────────
STATE_FIND_TAG   = "FIND_TAG"     # scan until we see the tag
STATE_TAKEOFF    = "TAKEOFF"      # command: fly up
STATE_TRICK      = "TRICK"        # command: spin / flip
STATE_LAND       = "LAND"         # command: descend back onto tag
STATE_DONE       = "DONE"         # mission complete

# How long (seconds) the operator must hold each manoeuvre before we advance
HOLD_TIMES = {
    STATE_TAKEOFF: 3.0,
    STATE_TRICK:   4.0,
    STATE_LAND:    4.0,
}

# Tag must be this fraction of frame width to count as "close enough to land"
LAND_SIZE_THRESH = 0.25

# ── Colours (BGR) ─────────────────────────────────────────────────────────────
C_YELLOW  = (0,   220, 255)
C_GREEN   = (0,   200,  60)
C_RED     = (40,   40, 230)
C_WHITE   = (255, 255, 255)
C_BLACK   = (0,     0,   0)
C_CYAN    = (220, 200,   0)
C_MAGENTA = (200,   0, 200)

# ── Arrow drawing helper ───────────────────────────────────────────────────────
def draw_arrow(img, direction, colour):
    """
    Draws a large filled arrow in the centre of the frame.
    direction: "UP" | "DOWN" | "CW" (clockwise spin) | "HOLD"
    """
    h, w = img.shape[:2]
    cx, cy = w // 2, h // 2

    overlay = img.copy()

    if direction == "UP":
        pts = np.array([
            [cx,          cy - 140],   # tip
            [cx - 80,     cy -  20],
            [cx - 35,     cy -  20],
            [cx - 35,     cy +  90],
            [cx + 35,     cy +  90],
            [cx + 35,     cy -  20],
            [cx + 80,     cy -  20],
        ], np.int32)
        cv2.fillPoly(overlay, [pts], colour)

    elif direction == "DOWN":
        pts = np.array([
            [cx,          cy + 140],
            [cx - 80,     cy +  20],
            [cx - 35,     cy +  20],
            [cx - 35,     cy -  90],
            [cx + 35,     cy -  90],
            [cx + 35,     cy +  20],
            [cx + 80,     cy +  20],
        ], np.int32)
        cv2.fillPoly(overlay, [pts], colour)

    elif direction == "CW":
        # Draw a circular arrow (arc + arrowhead) for the spin trick
        axes = (90, 90)
        cv2.ellipse(overlay, (cx, cy), axes, 0, 20, 340, colour, 22)
        # Arrowhead at bottom of arc
        ah = np.array([
            [cx + 90,  cy + 15],
            [cx + 60,  cy - 30],
            [cx + 120, cy - 30],
        ], np.int32)
        cv2.fillPoly(overlay, [ah], colour)

    elif direction == "HOLD":
        # Pulsing stop-hand / hold symbol — just an outlined rectangle
        cv2.rectangle(overlay, (cx-80, cy-80), (cx+80, cy+80), colour, -1)
        cv2.rectangle(overlay, (cx-80, cy-80), (cx+80, cy+80), C_BLACK, 5)
        cv2.putText(overlay, "HOLD", (cx-52, cy+18),
                    cv2.FONT_HERSHEY_DUPLEX, 1.6, C_BLACK, 3, cv2.LINE_AA)

    cv2.addWeighted(overlay, 0.72, img, 0.28, 0, img)


def draw_label(img, text, sub="", colour=C_WHITE):
    """Large centred text label at the top."""
    h, w = img.shape[:2]
    # shadow
    cv2.putText(img, text, (w//2 - len(text)*18 + 3, 70),
                cv2.FONT_HERSHEY_DUPLEX, 2.0, C_BLACK, 8, cv2.LINE_AA)
    cv2.putText(img, text, (w//2 - len(text)*18, 70),
                cv2.FONT_HERSHEY_DUPLEX, 2.0, colour, 4, cv2.LINE_AA)
    if sub:
        cv2.putText(img, sub, (w//2 - len(sub)*8, 110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, colour, 2, cv2.LINE_AA)


def draw_state_hud(img, state, hold_progress=0.0, tag_visible=False):
    """Bottom-left HUD: current state + hold progress bar."""
    h, w = img.shape[:2]
    bar_w = int(hold_progress * 200)
    if bar_w > 0:
        cv2.rectangle(img, (10, h-30), (10+bar_w, h-10), C_GREEN, -1)
    cv2.rectangle(img, (10, h-30), (210, h-10), C_WHITE, 2)

    tag_txt = "TAG: VISIBLE" if tag_visible else "TAG: searching..."
    tag_col = C_GREEN if tag_visible else C_RED
    cv2.putText(img, tag_txt, (10, h-40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, tag_col, 2)
    cv2.putText(img, f"State: {state}", (10, h-60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, C_CYAN, 2)


# ── Main ───────────────────────────────────────────────────────────────────────
def main(stream_ip: str, port: int = 80):
    stream_url = f"http://{stream_ip}:{port}/stream"
    print(f"Connecting to {stream_url} …")

    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        # Fallback: use urllib for the MJPEG boundary parsing
        print("VideoCapture failed, trying urllib fallback …")
        cap = None

    # AprilTag detector
    aruco_dict   = cv2.aruco.getPredefinedDictionary(APRILTAG_DICT)
    aruco_params = cv2.aruco.DetectorParameters()
    detector     = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    state       = STATE_FIND_TAG
    hold_start  = None   # when the current hold phase began
    mission_log = []

    print("Press  Q  to quit at any time.")
    cv2.namedWindow("Drone Controller", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Drone Controller", 960, 720)

    # ── urllib MJPEG reader (fallback) ────────────────────────────────────────
    stream_bytes = b""
    urllib_stream = None
    if cap is None:
        urllib_stream = urllib.request.urlopen(stream_url, timeout=5)

    while True:
        # ── grab frame ────────────────────────────────────────────────────────
        frame = None
        if cap is not None:
            ret, frame = cap.read()
            if not ret:
                print("Stream lost, retrying…"); time.sleep(1); continue
        else:
            stream_bytes += urllib_stream.read(4096)
            a = stream_bytes.find(b'\xff\xd8')  # JPEG start
            b_ = stream_bytes.find(b'\xff\xd9')  # JPEG end
            if a != -1 and b_ != -1:
                jpg = stream_bytes[a:b_+2]
                stream_bytes = stream_bytes[b_+2:]
                frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)

        if frame is None:
            continue

        h, w = frame.shape[:2]

        # ── AprilTag detection ─────────────────────────────────────────────────
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = detector.detectMarkers(gray)

        tag_visible  = ids is not None and len(ids) > 0
        tag_size_rel = 0.0  # relative width of the detected tag

        if tag_visible:
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
            # Compute tag apparent size (diagonal of bounding box / frame width)
            for corn in corners:
                pts = corn[0]
                tw = np.linalg.norm(pts[0] - pts[1])
                tag_size_rel = max(tag_size_rel, tw / w)

        now = time.time()

        # ── State machine ──────────────────────────────────────────────────────
        if state == STATE_FIND_TAG:
            draw_label(frame, "FIND THE TAG", "Point camera at landing pad", C_YELLOW)
            draw_arrow(frame, "HOLD", C_YELLOW)
            if tag_visible:
                print("Tag found — starting mission!")
                mission_log.append(f"{now:.1f}  Tag acquired")
                state = STATE_TAKEOFF
                hold_start = now

        elif state == STATE_TAKEOFF:
            elapsed = now - hold_start
            progress = min(elapsed / HOLD_TIMES[STATE_TAKEOFF], 1.0)
            draw_label(frame, "TAKE OFF", "Lift the drone straight UP", C_GREEN)
            draw_arrow(frame, "UP", C_GREEN)
            draw_state_hud(frame, state, progress, tag_visible)
            if elapsed >= HOLD_TIMES[STATE_TAKEOFF]:
                mission_log.append(f"{now:.1f}  Takeoff complete")
                state = STATE_TRICK
                hold_start = now

        elif state == STATE_TRICK:
            elapsed = now - hold_start
            progress = min(elapsed / HOLD_TIMES[STATE_TRICK], 1.0)
            draw_label(frame, "DO A SPIN!", "Rotate the drone clockwise", C_MAGENTA)
            draw_arrow(frame, "CW", C_MAGENTA)
            draw_state_hud(frame, state, progress, tag_visible)
            if elapsed >= HOLD_TIMES[STATE_TRICK]:
                mission_log.append(f"{now:.1f}  Trick complete")
                state = STATE_LAND
                hold_start = now

        elif state == STATE_LAND:
            elapsed = now - hold_start
            progress = min(elapsed / HOLD_TIMES[STATE_LAND], 1.0)
            draw_label(frame, "LAND ON TAG", "Lower drone onto the pad", C_CYAN)
            draw_arrow(frame, "DOWN", C_CYAN)
            draw_state_hud(frame, state, progress, tag_visible)
            # Advance when tag fills enough of the frame AND hold time elapsed
            if tag_size_rel >= LAND_SIZE_THRESH and elapsed >= HOLD_TIMES[STATE_LAND]:
                mission_log.append(f"{now:.1f}  Landed — mission complete!")
                state = STATE_DONE

        elif state == STATE_DONE:
            draw_label(frame, "MISSION COMPLETE", "Great flying!", C_GREEN)
            cv2.putText(frame, "Press Q to quit", (w//2-110, h//2+60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, C_WHITE, 2)

        # Always show tag status in find / done states
        if state in (STATE_FIND_TAG, STATE_DONE):
            draw_state_hud(frame, state, 0.0, tag_visible)

        cv2.imshow("Drone Controller", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap and cap.release()
    cv2.destroyAllWindows()

    print("\n── Mission Log ──────────────────────────────")
    for entry in mission_log:
        print(" ", entry)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drone training controller")
    parser.add_argument("--ip",   required=True, help="XIAO ESP32-S3 IP address")
    parser.add_argument("--port", default=80, type=int)
    args = parser.parse_args()
    main(args.ip, args.port)
