import asyncio
import sys
import threading
import time
import math
import tkinter as tk
from tkinter import scrolledtext
import queue
import os
import csv
from datetime import datetime
import pytz
from collections import deque
from bleak import BleakClient

# ===== BLE MAC ADDRESSES =====
TAG_MACS = {
    "T0": "DC:B4:D9:22:3B:B9",
    "T1": "DC:B4:D9:22:3A:55",
    "T2": "DC:B4:D9:31:8F:59"
}

CHAR_UUID = "deadbeef-0000-0000-0000-000000000001"

# ===== GLOBAL DATA STRUCTURES =====
tag_data = {
    "T0": {"A0": -1, "A1": -1, "A2": -1, "A3": -1},
    "T1": {"A0": -1, "A1": -1, "A2": -1, "A3": -1},
    "T2": {"A0": -1, "A1": -1, "A2": -1, "A3": -1}
}

tag_status = {"T0": "Disconnected", "T1": "Disconnected", "T2": "Disconnected"}

log_queue = queue.Queue()

# ===== CSV / TIMEZONE SETUP =====
EST = pytz.timezone("America/New_York")
CSV_DIR = r"C:\RTLS"
CSV_PATH = None  # Assigned at startup


def init_csv():
    global CSV_PATH
    os.makedirs(CSV_DIR, exist_ok=True)
    start_ts = datetime.now(EST).strftime("%Y%m%d_%H%M%S")
    CSV_PATH = os.path.join(CSV_DIR, f"rtls_log_{start_ts}.csv")
    # Write header
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Tag1", "Tag2", "Distance_ft", "Delta_s"])


def write_csv_row(ts, t1, t2, dist, dt):
    try:
        with open(CSV_PATH, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([ts, t1, t2, f"{dist:.1f}ft", f"{dt:.2f}s"])
    except Exception as e:
        print(f"[CSV ERROR] {e}")


def get_est_timestamp():
    """Returns EST military time formatted as M.D.YYYY HH:MM:SS"""
    now = datetime.now(EST)
    return now.strftime(f"{now.month}.{now.day}.{now.year} %H:%M:%S")


def custom_print(msg):
    log_queue.put(msg)
    print(msg)


# ===== RTLS ROOM SETTINGS =====
ROOM_W = 30.0
ROOM_H = 26.0

ANCHORS = {
    "A0": (0.0, 0.0),
    "A1": (0.0, ROOM_H),
    "A2": (ROOM_W, ROOM_H),
    "A3": (ROOM_W, 0.0)
}

BG_COLOR = "white"
AXIS_COLOR = "black"
GRID_COLOR = "#e0e0e0"
ANCHOR_COLOR = "blue"
TAG_COLORS = {"T0": "red", "T1": "green", "T2": "purple"}
LINE_COLOR = "orange"


# ==========================================
# BLE BACKGROUND THREAD
# ==========================================
def parse_and_store(data_str):
    try:
        parts = [p.strip() for p in data_str.split('|')]
        if len(parts) >= 5:
            t_id = parts[0]
            if t_id in tag_data:
                for i in range(1, 5):
                    val = parts[i].split(':')[1].strip()
                    tag_data[t_id][f"A{i - 1}"] = -1.0 if val == "---" else float(val)
    except Exception:
        pass


def notification_handler(sender, data):
    clean_text = data.decode('utf-8').strip()
    parse_and_store(clean_text)


async def connect_and_listen(tag_name, mac):
    while True:
        try:
            custom_print(f"[*] Connecting to {tag_name} [{mac}]...")
            tag_status[tag_name] = "Connecting..."
            async with BleakClient(mac) as client:
                custom_print(f"[+] {tag_name} Connected!")
                tag_status[tag_name] = "Connected"
                await client.start_notify(CHAR_UUID, notification_handler)
                while client.is_connected:
                    await asyncio.sleep(1)
        except Exception as e:
            tag_status[tag_name] = "Disconnected"
            # Wipe stale distances so this tag is excluded from all calculations
            tag_data[tag_name] = {"A0": -1, "A1": -1, "A2": -1, "A3": -1}
            custom_print(f"[-] {tag_name} dropped. Reconnecting...")
            await asyncio.sleep(3.0)


async def ble_main_loop():
    custom_print("Initializing BLE Background Service...")
    tasks = []
    for name, mac in TAG_MACS.items():
        tasks.append(asyncio.create_task(connect_and_listen(name, mac)))
        await asyncio.sleep(3.0)
    await asyncio.gather(*tasks)


def run_ble_thread():
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(ble_main_loop())


# ==========================================
# MATH: MULTI-LATERATION
# ==========================================
def calc_pos_multi(distances_dict):
    valid = []
    for a_id, r in distances_dict.items():
        if r > 0:
            valid.append((ANCHORS[a_id][0], ANCHORS[a_id][1], r))

    if len(valid) < 2:
        return None, None

    if len(valid) == 2:
        x1, y1, r1 = valid[0]
        x2, y2, r2 = valid[1]
        d = math.hypot(x2 - x1, y2 - y1)
        if d == 0 or d > r1 + r2 or d < abs(r1 - r2):
            return None, None

        a = (r1 ** 2 - r2 ** 2 + d ** 2) / (2 * d)
        h = math.sqrt(abs(r1 ** 2 - a ** 2))
        x3 = x1 + a * (x2 - x1) / d
        y3 = y1 + a * (y2 - y1) / d
        ix1 = x3 + h * (y2 - y1) / d
        iy1 = y3 - h * (x2 - x1) / d
        ix2 = x3 - h * (y2 - y1) / d
        iy2 = y3 + h * (x2 - x1) / d

        def dist_to_center(px, py):
            return (px - ROOM_W / 2) ** 2 + (py - ROOM_H / 2) ** 2

        if dist_to_center(ix1, iy1) < dist_to_center(ix2, iy2):
            return round(ix1, 3), round(iy1, 3)
        return round(ix2, 3), round(iy2, 3)

    else:
        x0, y0, r0 = valid[0]
        A, B = [], []
        for i in range(1, len(valid)):
            xi, yi, ri = valid[i]
            A.append([2 * (xi - x0), 2 * (yi - y0)])
            B.append(r0 ** 2 - ri ** 2 - x0 ** 2 - y0 ** 2 + xi ** 2 + yi ** 2)

        a11 = sum(row[0] * row[0] for row in A)
        a12 = sum(row[0] * row[1] for row in A)
        a21 = a12
        a22 = sum(row[1] * row[1] for row in A)
        b1 = sum(A[i][0] * B[i] for i in range(len(B)))
        b2 = sum(A[i][1] * B[i] for i in range(len(B)))

        det = a11 * a22 - a12 * a21
        if abs(det) < 1e-5:
            return None, None
        px = (a22 * b1 - a12 * b2) / det
        py = (-a21 * b1 + a11 * b2) / det
        return round(px, 3), round(py, 3)


# ==========================================
# RTLS APP
# ==========================================
class RTLSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("UWB RTLS Multi-Tag Map Control Center")
        self.root.geometry("1200x750")

        self.scale = 20.0
        self.pan_x = 100.0
        self.pan_y = 650.0
        self.drag_start_x = 0
        self.drag_start_y = 0

        # Right panel fixed at 300px; map expands to fill the rest
        self.right_frame = tk.Frame(self.root, bg="#f0f0f0", width=300)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_frame.pack_propagate(False)

        self.left_frame = tk.Frame(self.root, bg="white")
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # --- SMOOTHING STATE ---
        self.ema_pos      = {"T0": None, "T1": None, "T2": None}
        self.roll_buf     = {"T0": deque(maxlen=20), "T1": deque(maxlen=20), "T2": deque(maxlen=20)}
        self.kalman_state = {"T0": None, "T1": None, "T2": None}
        self.kalman_P     = {"T0": None, "T1": None, "T2": None}

        # Filter control tkinter vars (populated before setup_right_panel reads them)
        self.filter_mode = tk.StringVar(value="EMA")
        self.ema_alpha   = tk.DoubleVar(value=0.2)
        self.roll_n      = tk.IntVar(value=8)
        self.kalman_q    = tk.DoubleVar(value=0.1)
        self.kalman_r    = tk.DoubleVar(value=2.0)

        self.setup_left_panel()
        self.setup_right_panel()

        self.tag_positions = {"T0": None, "T1": None, "T2": None}
        self.last_log_time = {"T0-T1": time.time(), "T1-T2": time.time(), "T0-T2": time.time()}


        self.root.after(100, self.reset_view)
        self.process_log_queue()
        self.loop()

    # --- CANVAS TRANSFORMS ---
    def to_cx(self, x_ft):
        return self.pan_x + (x_ft * self.scale)

    def to_cy(self, y_ft):
        return self.pan_y - (y_ft * self.scale)

    def to_rx(self, cx):
        return (cx - self.pan_x) / self.scale

    def to_ry(self, cy):
        return (self.pan_y - cy) / self.scale

    # --- MOUSE EVENTS ---
    def on_mouse_press(self, event):
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_mouse_drag(self, event):
        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y
        self.pan_x += dx
        self.pan_y += dy
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        self.draw_canvas()

    def on_mouse_wheel(self, event):
        if event.num == 4 or getattr(event, 'delta', 0) > 0:
            zoom_factor = 1.1
        else:
            zoom_factor = 0.9

        mouse_rx = self.to_rx(event.x)
        mouse_ry = self.to_ry(event.y)
        self.scale *= zoom_factor
        self.pan_x = event.x - (mouse_rx * self.scale)
        self.pan_y = event.y + (mouse_ry * self.scale)
        self.draw_canvas()

    def reset_view(self):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        padding = 100
        scale_x = (cw - padding) / ROOM_W
        scale_y = (ch - padding) / ROOM_H
        self.scale = min(scale_x, scale_y)
        self.pan_x = (cw - (ROOM_W * self.scale)) / 2
        self.pan_y = ch - (ch - (ROOM_H * self.scale)) / 2
        self.draw_canvas()

    # --- GUI SETUP ---
    def setup_left_panel(self):
        self.canvas = tk.Canvas(self.left_frame, bg=BG_COLOR, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)
        self.canvas.bind("<Configure>", lambda e: self.draw_canvas())

    def setup_right_panel(self):
        title_font = ("Arial", 10, "bold")
        value_font = ("Arial", 9)
        BG = "#f0f0f0"

        # ── Scrollable right panel ──
        # Outer frame holds the canvas+scrollbar
        scroll_canvas = tk.Canvas(self.right_frame, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(self.right_frame, orient=tk.VERTICAL, command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Inner frame lives inside the canvas
        inner = tk.Frame(scroll_canvas, bg=BG)
        inner_window = scroll_canvas.create_window((0, 0), window=inner, anchor="nw")

        # Resize inner frame to canvas width, update scroll region when content changes
        def on_inner_configure(e):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        def on_canvas_resize(e):
            scroll_canvas.itemconfig(inner_window, width=e.width)
        inner.bind("<Configure>", on_inner_configure)
        scroll_canvas.bind("<Configure>", on_canvas_resize)

        # Mouse wheel scrolling
        def on_mousewheel(e):
            scroll_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        scroll_canvas.bind_all("<MouseWheel>", on_mousewheel)

        # All widgets now pack into `inner` instead of self.right_frame
        tk.Button(inner, text="🎯 Reset Map View", command=self.reset_view,
                  font=title_font, bg="#d0d0d0").pack(fill=tk.X, padx=5, pady=5)

        # Connectivity
        sf = tk.LabelFrame(inner, text="Connectivity", font=title_font, bg=BG)
        sf.pack(fill=tk.X, padx=5, pady=2)
        self.status_labels = {}
        for tag in TAG_MACS:
            lbl = tk.Label(sf, text=f"{tag}: Disconnected", font=value_font, fg="red", bg="#f0f0f0")
            lbl.pack(anchor="w", padx=2, pady=1)
            self.status_labels[tag] = lbl

        # Coordinates
        pf = tk.LabelFrame(inner, text="Coordinates (ft)", font=title_font, bg=BG)
        pf.pack(fill=tk.X, padx=5, pady=2)
        self.pos_labels = {}
        for tag in TAG_MACS:
            lbl = tk.Label(pf, text=f"{tag}: (---, ---)", font=value_font, bg="#f0f0f0")
            lbl.pack(anchor="w", padx=2, pady=1)
            self.pos_labels[tag] = lbl

        # Inter-Tag Distances
        df = tk.LabelFrame(inner, text="Inter-Tag Distances", font=title_font, bg=BG)
        df.pack(fill=tk.X, padx=5, pady=2)
        self.dist_labels = {}
        for p1, p2 in [("T0", "T1"), ("T1", "T2"), ("T0", "T2")]:
            lbl = tk.Label(df, text=f"{p1} to {p2}: --- ft", font=value_font, bg="#f0f0f0")
            lbl.pack(anchor="w", padx=2, pady=1)
            self.dist_labels[f"{p1}-{p2}"] = lbl

        # CSV path display
        cf = tk.LabelFrame(inner, text="CSV Log", font=title_font, bg=BG)
        cf.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(cf, text=CSV_PATH, font=("Consolas", 7), bg=BG, fg="#444",
                 wraplength=285, justify="left").pack(anchor="w", padx=2, pady=2)

        # Terminal
        tf = tk.LabelFrame(inner, text="Terminal Output", font=title_font, bg=BG)
        tf.pack(fill=tk.X, padx=5, pady=5)
        self.terminal = scrolledtext.ScrolledText(tf, wrap=tk.WORD, font=("Consolas", 8),
                                                  bg="black", fg="lime", height=10)
        self.terminal.pack(fill=tk.X, padx=2, pady=2)

        # ── Smoothing Filter Panel ──
        filt_frame = tk.LabelFrame(inner, text="Smoothing Filter", font=title_font, bg=BG)
        filt_frame.pack(fill=tk.X, padx=5, pady=(0, 6))

        # Mode selector row
        mode_row = tk.Frame(filt_frame, bg=BG)
        mode_row.pack(fill=tk.X, padx=4, pady=(4, 2))
        for mode in ("EMA", "Rolling", "Kalman"):
            tk.Radiobutton(mode_row, text=mode, variable=self.filter_mode, value=mode,
                           font=value_font, bg="#f0f0f0", activebackground="#f0f0f0").pack(side=tk.LEFT, padx=4)

        # EMA alpha
        ema_row = tk.Frame(filt_frame, bg=BG)
        ema_row.pack(fill=tk.X, padx=4, pady=1)
        tk.Label(ema_row, text="EMA α (0=smooth, 1=raw):", font=("Arial", 8), bg=BG, width=22, anchor="w").pack(side=tk.LEFT)
        self.ema_val_lbl = tk.Label(ema_row, text="0.20", font=("Arial", 8, "bold"), bg=BG, width=4)
        self.ema_val_lbl.pack(side=tk.RIGHT)
        tk.Scale(filt_frame, variable=self.ema_alpha, from_=0.01, to=1.0, resolution=0.01,
                 orient=tk.HORIZONTAL, bg=BG, highlightthickness=0, showvalue=False,
                 command=lambda v: self.ema_val_lbl.config(text=f"{float(v):.2f}")
                 ).pack(fill=tk.X, padx=4)

        # Rolling window N
        roll_row = tk.Frame(filt_frame, bg=BG)
        roll_row.pack(fill=tk.X, padx=4, pady=1)
        tk.Label(roll_row, text="Rolling window (frames):", font=("Arial", 8), bg=BG, width=22, anchor="w").pack(side=tk.LEFT)
        self.roll_val_lbl = tk.Label(roll_row, text="8", font=("Arial", 8, "bold"), bg=BG, width=4)
        self.roll_val_lbl.pack(side=tk.RIGHT)
        tk.Scale(filt_frame, variable=self.roll_n, from_=2, to=30, resolution=1,
                 orient=tk.HORIZONTAL, bg=BG, highlightthickness=0, showvalue=False,
                 command=lambda v: self.roll_val_lbl.config(text=str(int(float(v))))
                 ).pack(fill=tk.X, padx=4)

        # Kalman Q (process noise)
        kq_row = tk.Frame(filt_frame, bg=BG)
        kq_row.pack(fill=tk.X, padx=4, pady=1)
        tk.Label(kq_row, text="Kalman Q (process noise):", font=("Arial", 8), bg=BG, width=22, anchor="w").pack(side=tk.LEFT)
        self.kq_val_lbl = tk.Label(kq_row, text="0.10", font=("Arial", 8, "bold"), bg=BG, width=4)
        self.kq_val_lbl.pack(side=tk.RIGHT)
        tk.Scale(filt_frame, variable=self.kalman_q, from_=0.01, to=2.0, resolution=0.01,
                 orient=tk.HORIZONTAL, bg=BG, highlightthickness=0, showvalue=False,
                 command=lambda v: self.kq_val_lbl.config(text=f"{float(v):.2f}")
                 ).pack(fill=tk.X, padx=4)

        # Kalman R (measurement noise)
        kr_row = tk.Frame(filt_frame, bg=BG)
        kr_row.pack(fill=tk.X, padx=4, pady=1)
        tk.Label(kr_row, text="Kalman R (meas. noise):", font=("Arial", 8), bg=BG, width=22, anchor="w").pack(side=tk.LEFT)
        self.kr_val_lbl = tk.Label(kr_row, text="2.00", font=("Arial", 8, "bold"), bg=BG, width=4)
        self.kr_val_lbl.pack(side=tk.RIGHT)
        tk.Scale(filt_frame, variable=self.kalman_r, from_=0.1, to=10.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=BG, highlightthickness=0, showvalue=False,
                 command=lambda v: self.kr_val_lbl.config(text=f"{float(v):.1f}")
                 ).pack(fill=tk.X, padx=4)

    def process_log_queue(self):
        while not log_queue.empty():
            msg = log_queue.get()
            self.terminal.insert(tk.END, msg + "\n")
            self.terminal.see(tk.END)
        self.root.after(100, self.process_log_queue)

    def update_ui_tables(self):
        for tag, lbl in self.status_labels.items():
            status = tag_status[tag]
            lbl.config(text=f"{tag}: {status}", fg="green" if status == "Connected" else "red")

        for tag, lbl in self.pos_labels.items():
            pos = self.tag_positions[tag]
            if pos:
                lbl.config(text=f"{tag}: ({pos[0]:.2f}, {pos[1]:.2f})")
            else:
                lbl.config(text=f"{tag}: (---, ---)")

    # --- CANVAS DRAWING ---
    def draw_canvas(self):
        self.canvas.delete("all")

        # Grid
        for x in range(0, int(ROOM_W) + 1, 2):
            self.canvas.create_line(self.to_cx(x), self.to_cy(0), self.to_cx(x), self.to_cy(ROOM_H), fill=GRID_COLOR)
        for y in range(0, int(ROOM_H) + 1, 2):
            self.canvas.create_line(self.to_cx(0), self.to_cy(y), self.to_cx(ROOM_W), self.to_cy(y), fill=GRID_COLOR)

        # Room bounds
        self.canvas.create_line(
            self.to_cx(0), self.to_cy(0), self.to_cx(ROOM_W), self.to_cy(0),
            self.to_cx(ROOM_W), self.to_cy(ROOM_H), self.to_cx(0), self.to_cy(ROOM_H),
            self.to_cx(0), self.to_cy(0), fill=AXIS_COLOR, width=2
        )

        # Dimension labels
        self.canvas.create_text(self.to_cx(ROOM_W / 2), self.to_cy(0) + 20,
                                text=f"{ROOM_W} ft", fill=AXIS_COLOR, font=("Arial", 12, "bold"))
        self.canvas.create_text(self.to_cx(0) - 30, self.to_cy(ROOM_H / 2),
                                text=f"{ROOM_H} ft", fill=AXIS_COLOR, font=("Arial", 12, "bold"), angle=90)

        # Anchors
        for a_id, (ax, ay) in ANCHORS.items():
            cx, cy = self.to_cx(ax), self.to_cy(ay)
            r = 8
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=ANCHOR_COLOR)
            label = f"{a_id} (0,0)" if a_id == "A0" else a_id
            self.canvas.create_text(cx, cy - 15, text=label, fill=AXIS_COLOR, font=("Arial", 10, "bold"))

        # Inter-tag lines + logging
        pos = self.tag_positions
        now = time.time()
        pairs = [("T0", "T1"), ("T1", "T2"), ("T0", "T2")]

        for t1, t2 in pairs:
            p1, p2 = pos[t1], pos[t2]
            pair_key = f"{t1}-{t2}"

            if p1 and p2:
                dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])

                # Draw dashed line
                c1x, c1y = self.to_cx(p1[0]), self.to_cy(p1[1])
                c2x, c2y = self.to_cx(p2[0]), self.to_cy(p2[1])
                self.canvas.create_line(c1x, c1y, c2x, c2y, fill=LINE_COLOR, width=1.5, dash=(4, 4))
                mid_cx = (c1x + c2x) / 2
                mid_cy = (c1y + c2y) / 2
                self.canvas.create_text(mid_cx, mid_cy - 10, text=f"{dist:.2f}ft",
                                        fill=LINE_COLOR, font=("Arial", 9, "bold"))

                # Update sidebar label
                self.dist_labels[pair_key].config(text=f"{t1} to {t2}: {dist:.2f} ft")

                # Calculate delta and log immediately — no throttle
                dt = now - self.last_log_time[pair_key]
                ts = get_est_timestamp()
                line = f"[{ts}][{t1}][{t2}][{dist:.1f}ft][{dt:.2f}s]"
                custom_print(line)
                write_csv_row(ts, t1, t2, dist, dt)
                self.last_log_time[pair_key] = now

            else:
                self.dist_labels[pair_key].config(text=f"{t1} to {t2}: --- ft")

        # Tags
        for t_id, t_pos in self.tag_positions.items():
            if t_pos:
                cx, cy = self.to_cx(t_pos[0]), self.to_cy(t_pos[1])
                r = 8
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=TAG_COLORS[t_id])
                self.canvas.create_text(cx + 15, cy - 10, text=t_id, fill=TAG_COLORS[t_id],
                                        font=("Arial", 10, "bold"), anchor="w")


    # ==========================================
    # SMOOTHING FILTERS
    # ==========================================
    def apply_ema(self, t_id, rx, ry):
        alpha = self.ema_alpha.get()
        prev = self.ema_pos[t_id]
        if prev is None:
            self.ema_pos[t_id] = (rx, ry)
        else:
            self.ema_pos[t_id] = (
                alpha * rx + (1 - alpha) * prev[0],
                alpha * ry + (1 - alpha) * prev[1]
            )
        return self.ema_pos[t_id]

    def apply_rolling(self, t_id, rx, ry):
        n = self.roll_n.get()
        buf = self.roll_buf[t_id]
        buf.maxlen  # deque — update maxlen dynamically
        # Rebuild deque with new maxlen if needed
        if buf.maxlen != n:
            self.roll_buf[t_id] = deque(list(buf)[-n:], maxlen=n)
            buf = self.roll_buf[t_id]
        buf.append((rx, ry))
        xs = [p[0] for p in buf]
        ys = [p[1] for p in buf]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    def apply_kalman(self, t_id, rx, ry):
        """Simple 2D constant-velocity Kalman filter."""
        q = self.kalman_q.get()   # process noise (lower = trust model more)
        r = self.kalman_r.get()   # measurement noise (higher = smooth more)
        dt = 0.05                  # matches loop interval (50ms)

        # State: [x, y, vx, vy]
        # Transition matrix F
        F = [[1, 0, dt, 0],
             [0, 1, 0, dt],
             [0, 0, 1,  0],
             [0, 0, 0,  1]]
        # Observation matrix H (we measure x, y only)
        H = [[1, 0, 0, 0],
             [0, 1, 0, 0]]
        # Process noise Q
        Q = [[q*dt**3/3, 0, q*dt**2/2, 0],
             [0, q*dt**3/3, 0, q*dt**2/2],
             [q*dt**2/2, 0, q*dt,  0],
             [0, q*dt**2/2, 0, q*dt]]
        # Measurement noise R
        R = [[r, 0], [0, r]]

        def mat_mul(A, B):
            rows_A, cols_A = len(A), len(A[0])
            cols_B = len(B[0])
            return [[sum(A[i][k]*B[k][j] for k in range(cols_A))
                     for j in range(cols_B)] for i in range(rows_A)]

        def mat_add(A, B):
            return [[A[i][j]+B[i][j] for j in range(len(A[0]))] for i in range(len(A))]

        def mat_sub(A, B):
            return [[A[i][j]-B[i][j] for j in range(len(A[0]))] for i in range(len(A))]

        def mat_T(A):
            return [[A[j][i] for j in range(len(A))] for i in range(len(A[0]))]

        def mat_inv2(A):
            """2x2 matrix inverse."""
            det = A[0][0]*A[1][1] - A[0][1]*A[1][0]
            if abs(det) < 1e-9: det = 1e-9
            return [[ A[1][1]/det, -A[0][1]/det],
                    [-A[1][0]/det,  A[0][0]/det]]

        def eye(n):
            return [[1 if i==j else 0 for j in range(n)] for i in range(n)]

        # Init state on first reading
        if self.kalman_state[t_id] is None:
            self.kalman_state[t_id] = [[rx], [ry], [0.0], [0.0]]
            self.kalman_P[t_id] = [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]

        x = self.kalman_state[t_id]
        P = self.kalman_P[t_id]

        # --- Predict ---
        x_pred = mat_mul(F, x)
        P_pred = mat_add(mat_mul(mat_mul(F, P), mat_T(F)), Q)

        # --- Update ---
        z = [[rx], [ry]]
        y_k = mat_sub(z, mat_mul(H, x_pred))
        S   = mat_add(mat_mul(mat_mul(H, P_pred), mat_T(H)), R)
        K   = mat_mul(mat_mul(P_pred, mat_T(H)), mat_inv2(S))
        x_new = mat_add(x_pred, mat_mul(K, y_k))
        P_new = mat_mul(mat_sub(eye(4), mat_mul(K, H)), P_pred)

        self.kalman_state[t_id] = x_new
        self.kalman_P[t_id]     = P_new
        return (x_new[0][0], x_new[1][0])

    def smooth(self, t_id, rx, ry):
        """Route to the selected filter."""
        mode = self.filter_mode.get()
        if mode == "EMA":
            return self.apply_ema(t_id, rx, ry)
        elif mode == "Rolling":
            return self.apply_rolling(t_id, rx, ry)
        elif mode == "Kalman":
            return self.apply_kalman(t_id, rx, ry)
        return (rx, ry)

    def reset_filter_state(self, t_id):
        """Called when a tag reconnects so old state doesn't corrupt new data."""
        self.ema_pos[t_id]      = None
        self.roll_buf[t_id]     = deque(maxlen=20)
        self.kalman_state[t_id] = None
        self.kalman_P[t_id]     = None

    def loop(self):
        for t_id in TAG_MACS:
            if tag_status[t_id] != "Connected":
                if self.tag_positions[t_id] is not None:
                    # Tag just dropped — wipe filter state so reconnect starts fresh
                    self.reset_filter_state(t_id)
                self.tag_positions[t_id] = None
                continue

            x, y = calc_pos_multi(tag_data[t_id])
            if x is not None and y is not None:
                sx, sy = self.smooth(t_id, x, y)
                self.tag_positions[t_id] = (round(sx, 3), round(sy, 3))
            else:
                self.tag_positions[t_id] = None

        self.update_ui_tables()
        self.draw_canvas()
        self.root.after(50, self.loop)


if __name__ == "__main__":
    init_csv()
    custom_print(f"[CSV] Logging to: {CSV_PATH}")

    ble_thread = threading.Thread(target=run_ble_thread, daemon=True)
    ble_thread.start()

    root = tk.Tk()
    app = RTLSApp(root)
    root.mainloop()