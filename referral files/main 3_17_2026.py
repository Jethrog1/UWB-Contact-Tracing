# concept code
import asyncio
import sys
import threading
import time
import math
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import json
from datetime import datetime
from collections import deque
import pytz
import numpy as np
import warnings
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from bleak import BleakClient

try:
    from numpy.exceptions import RankWarning
except ImportError:
    from numpy import RankWarning
warnings.simplefilter('ignore', RankWarning)

# ==========================================
# CONFIG
# ==========================================
TAG_MACS = {
    "T0": "dc:b4:d9:22:3b:b9",
    "T1": "dc:b4:d9:22:3a:55",
    "T2": "dc:b4:d9:31:8f:59"
}
MAC_TO_TAG = {v: k for k, v in TAG_MACS.items()}

tag_data = {
    "T0": {"A0": -1, "A1": -1, "A2": -1, "A3": -1},
    "T1": {"A0": -1, "A1": -1, "A2": -1, "A3": -1},
    "T2": {"A0": -1, "A1": -1, "A2": -1, "A3": -1}
}
tag_status = {"T0": "Disconnected", "T1": "Disconnected", "T2": "Disconnected"}

EST      = pytz.timezone("America/New_York")

ANCHOR_COLORS = {"A0": "#e74c3c", "A1": "#27ae60", "A2": "#8e44ad", "A3": "#f39c12"}
TAG_COLORS    = {"T0": "red",     "T1": "#00aa00", "T2": "purple"}
GRID_COLOR    = "#d0d0d0"

UPDATE_MS = 50

CHAR_UUID = "deadbeef-0000-0000-0000-000000000001"

def custom_print(msg):
    print(msg)

# ==========================================
# BLE
# ==========================================
def parse_and_store(data_str):
    try:
        parts = [p.strip() for p in data_str.split('|')]
        if len(parts) >= 5:
            t_id = parts[0]
            if t_id in tag_data:
                for i in range(1, 5):
                    val = parts[i].split(':')[1].strip()
                    tag_data[t_id][f"A{i-1}"] = -1.0 if val == "---" else float(val)
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
# MULTILATERATION
# ==========================================
def calc_pos(anchor_positions, distances_dict):
    valid = [(anchor_positions[a][0], anchor_positions[a][1], r)
             for a, r in distances_dict.items()
             if r > 0 and a in anchor_positions]
    if len(valid) < 2:
        return None, None

    if len(valid) == 2:
        x1,y1,r1 = valid[0]; x2,y2,r2 = valid[1]
        d = math.hypot(x2-x1, y2-y1)
        if d == 0 or d > r1+r2 or d < abs(r1-r2):
            return None, None
        a = (r1**2 - r2**2 + d**2) / (2*d)
        h = math.sqrt(max(0, r1**2 - a**2))
        x3 = x1 + a*(x2-x1)/d; y3 = y1 + a*(y2-y1)/d
        ix1 = x3 + h*(y2-y1)/d; iy1 = y3 - h*(x2-x1)/d
        ix2 = x3 - h*(y2-y1)/d; iy2 = y3 + h*(x2-x1)/d
        cx = sum(p[0] for p in valid)/len(valid)
        cy = sum(p[1] for p in valid)/len(valid)
        if (ix1-cx)**2+(iy1-cy)**2 < (ix2-cx)**2+(iy2-cy)**2:
            return round(ix1,3), round(iy1,3)
        return round(ix2,3), round(iy2,3)

    # 3+ anchors — least squares
    x0,y0,r0 = valid[0]
    A, B = [], []
    for xi,yi,ri in valid[1:]:
        A.append([2*(xi-x0), 2*(yi-y0)])
        B.append(r0**2 - ri**2 - x0**2 - y0**2 + xi**2 + yi**2)
    a11=sum(r[0]**2 for r in A); a12=sum(r[0]*r[1] for r in A)
    a22=sum(r[1]**2 for r in A)
    b1 =sum(A[i][0]*B[i] for i in range(len(B)))
    b2 =sum(A[i][1]*B[i] for i in range(len(B)))
    det = a11*a22 - a12**2
    if abs(det) < 1e-6: return None, None
    return round((a22*b1 - a12*b2)/det, 3), round((-a12*b1 + a11*b2)/det, 3)

# ==========================================
# CALIBRATION CURVE FITTING
# ==========================================
def build_eval_func(mode, X, Y, poly_deg=4, ma_period=4, ma_type="Trailing"):
    n = len(X)
    if n == 0: return lambda x: x, "Raw (no data)"
    try:
        if mode == "Linear":
            m,b = np.polyfit(X,Y,1)
            return (lambda x,m=m,b=b: m*x+b), f"({m:.5f}*Raw)+{b:.5f}"
        elif mode == "Exponential":
            v = Y>0
            if v.sum()>1:
                b,la = np.polyfit(X[v], np.log(Y[v]),1); a=np.exp(la)
                return (lambda x,a=a,b=b: a*np.exp(b*x)), f"{a:.5f}*e^({b:.5f}*Raw)"
        elif mode == "Polynomial":
            d = min(poly_deg, n-1); d = max(d,1)
            c = np.polyfit(X,Y,d)
            def pf(c,d): return lambda x: sum(c[i]*(x**(d-i)) for i in range(d+1))
            terms=[]
            for i,cv in enumerate(c):
                p=d-i
                if p>1: terms.append(f"{cv:.4f}*Raw^{p}")
                elif p==1: terms.append(f"{cv:.4f}*Raw")
                else: terms.append(f"{cv:.4f}")
            return pf(c,d), " + ".join(terms)
        elif mode == "Logarithmic":
            v = X>0
            if v.sum()>1:
                a,b = np.polyfit(np.log(X[v]),Y[v],1)
                return (lambda x,a=a,b=b: a*np.log(x)+b if x>0 else 0), f"{a:.5f}*ln(Raw)+{b:.5f}"
        elif mode == "Power Series":
            v = (X>0)&(Y>0)
            if v.sum()>1:
                b,la = np.polyfit(np.log(X[v]),np.log(Y[v]),1); a=np.exp(la)
                return (lambda x,a=a,b=b: a*(x**b) if x>0 else 0), f"{a:.5f}*Raw^{b:.5f}"
        elif mode == "Moving Average":
            w = min(ma_period, n)
            pts = sorted(zip(X,Y))
            sX = np.array([p[0] for p in pts]); sY = np.array([p[1] for p in pts])
            mX,mY = [],[]
            for i in range(len(sX)):
                if ma_type=="Trailing": s,e = max(0,i-w+1),i+1
                else:
                    h=w//2; s,e=max(0,i-h),min(len(sX),i+h+1)
                seg=sY[s:e]; mX.append(sX[i]); mY.append(seg.mean())
            if len(mX)>1:
                return (lambda x,mx=mX,my=mY: float(np.interp(x,mx,my))), f"{ma_type} MA(period={w})"
    except Exception:
        pass
    if n>=2:
        m,b=np.polyfit(X,Y,1)
        return (lambda x,m=m,b=b: m*x+b), f"({m:.5f}*Raw)+{b:.5f}"
    return lambda x: x, "Raw"


# ==========================================
# MAIN APP
# ==========================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("UWB RTLS Multi-Tag Map Control Center")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # larger default window
        self.root.geometry("1400x900")
        self.root.minsize(1100, 700)

        # anchor positions (ft)
        self.anchor_pos = {
            "A0": [0.0,  0.0],
            "A1": [0.0,  26.0],
            "A2": [30.0, 26.0],
            "A3": [30.0, 0.0]
        }
        # connection order for the border lines (user can rearrange)
        self.anchor_order = ["A0","A1","A2","A3"]

        # blue crosshair for floor-distance measurement (None = not placed)
        self.crosshair_pos   = None
        self._crosshair_mode = False  # True while "place crosshair" is armed

        # map transform
        self.scale  = 18.0
        self.pan_x  = 60.0
        self.pan_y  = 560.0
        self._drag_anchor = None

        # smoothing
        self.ema_pos      = {t: None for t in TAG_MACS}
        self.roll_buf     = {t: deque(maxlen=20) for t in TAG_MACS}
        self.kal_state    = {t: None for t in TAG_MACS}
        self.kal_P        = {t: None for t in TAG_MACS}
        self.filter_mode  = tk.StringVar(value="EMA")
        self.ema_alpha    = tk.DoubleVar(value=0.2)
        self.roll_n       = tk.IntVar(value=8)
        self.kal_q        = tk.DoubleVar(value=0.1)
        self.kal_r        = tk.DoubleVar(value=2.0)

        # tag positions
        self.tag_pos = {t: None for t in TAG_MACS}

        # calibration state (per tag, per anchor)
        self.cal_pts  = {t: {a: [] for a in ["A0","A1","A2","A3"]} for t in TAG_MACS}
        self.cal_func = {t: {a: (lambda x: x) for a in ["A0","A1","A2","A3"]} for t in TAG_MACS}
        self.cal_tag_var    = tk.StringVar(value="T0")
        # per-anchor curve type and options
        self.fit_mode_vars   = {a: tk.StringVar(value="Polynomial") for a in ["A0","A1","A2","A3"]}
        self.poly_deg_vars   = {a: tk.StringVar(value="4")          for a in ["A0","A1","A2","A3"]}
        self.ma_period_vars  = {a: tk.StringVar(value="4")          for a in ["A0","A1","A2","A3"]}
        self.ma_type_vars    = {a: tk.StringVar(value="Trailing")   for a in ["A0","A1","A2","A3"]}

        self.auto_rec_var   = tk.BooleanVar(value=True)
        self.preset_var     = tk.BooleanVar(value=False)
        # per-anchor preset toggle (independent)
        self.preset_vars    = {a: tk.BooleanVar(value=False) for a in ["A0","A1","A2","A3"]}
        self.num_samples_var= tk.StringVar(value="20")
        self.true_dist_vars = {a: tk.StringVar() for a in ["A0","A1","A2","A3"]}
        self.is_capturing   = False
        self.cur_raws       = {a: 0.0 for a in ["A0","A1","A2","A3"]}

        self._build_ui()

        self.root.after(UPDATE_MS, self._cal_live_update)
        self._rtls_loop()

    # ──────────────────────────────────────
    # BUILD UI
    # ──────────────────────────────────────
    def _build_ui(self):
        self.left_frame = tk.Frame(self.root, bg="white")
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.right_frame = tk.Frame(self.root, bg="#f0f0f0", width=360)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_frame.pack_propagate(False)

        self._build_map_canvas()
        self._build_cal_graph()
        self._build_right_panel()

    # ── MAP CANVAS ──
    def _build_map_canvas(self):
        self.canvas = tk.Canvas(self.left_frame, bg="white", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>",   self._map_press)
        self.canvas.bind("<B1-Motion>",       self._map_drag)
        self.canvas.bind("<ButtonRelease-1>", self._map_release)
        self.canvas.bind("<Double-Button-1>", self._map_dblclick)
        self.canvas.bind("<MouseWheel>",      self._map_wheel)
        self.canvas.bind("<Button-4>",        self._map_wheel)
        self.canvas.bind("<Button-5>",        self._map_wheel)
        self.canvas.bind("<Configure>",       lambda e: self._reset_view())

    # ── CALIBRATION GRAPH (resizable) ──
    def _build_cal_graph(self):
        self._cal_graph_height = 320

        # thick black drag bar between map and graph
        self._sash = tk.Frame(self.left_frame, bg="#222222", height=10, cursor="sb_v_double_arrow")
        self._sash.pack(fill=tk.X, side=tk.BOTTOM)
        self._sash.bind("<ButtonPress-1>",   self._sash_press)
        self._sash.bind("<B1-Motion>",       self._sash_drag)

        self.cal_frame = tk.Frame(self.left_frame, bg="#f0f0f0", relief=tk.RAISED, bd=2)
        self.cal_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.cal_frame.config(height=self._cal_graph_height)
        self.cal_frame.pack_propagate(False)

        hdr = tk.Frame(self.cal_frame, bg="#f0f0f0")
        hdr.pack(fill=tk.X, padx=4, pady=2)
        tk.Label(hdr, text="Calibration Graph", font=("Arial",9,"bold"), bg="#f0f0f0").pack(side=tk.LEFT)
        self._cal_graph_shown = True
        self._btn_toggle_cal = tk.Button(hdr, text="▼ Hide", font=("Arial",8), bg="#d0d0d0",
                                          command=self._toggle_cal_graph)
        self._btn_toggle_cal.pack(side=tk.RIGHT)

        self.cal_graph_inner = tk.Frame(self.cal_frame, bg="#f0f0f0")
        self.cal_graph_inner.pack(fill=tk.BOTH, expand=True)

        self.cal_fig, self.cal_ax = plt.subplots(figsize=(9, 3.2), dpi=90)
        self.cal_fig.patch.set_facecolor('#f0f0f0')
        self.cal_ax.set_facecolor('#fafafa')
        self.cal_ax.set_title("Calibration: Raw vs True (ft) — all anchors", fontsize=9, fontweight='bold')
        self.cal_ax.set_xlabel("Raw UWB (ft)", fontsize=8)
        self.cal_ax.set_ylabel("True (ft)", fontsize=8)
        self.cal_ax.set_xlim(0,35); self.cal_ax.set_ylim(0,35)
        self.cal_ax.grid(True, linestyle='--', alpha=0.5)
        self.cal_ax.tick_params(labelsize=7)

        self._cal_sc  = {}; self._cal_fl = {}
        self._cal_ld  = {}; self._cal_cap = {}
        for a in ["A0","A1","A2","A3"]:
            c = ANCHOR_COLORS[a]
            sc, = self.cal_ax.plot([],[], 'o', color=c, markersize=5, label=f"{a} pts", zorder=5)
            fl, = self.cal_ax.plot([],[], '-', color=c, linewidth=1.5, zorder=4)
            ld, = self.cal_ax.plot([],[], 'D', color=c, markersize=7,
                                    markeredgecolor='green', markeredgewidth=2, zorder=6)
            cp, = self.cal_ax.plot([],[], 'o', color=c, markersize=3, alpha=0.4, zorder=3)
            self._cal_sc[a]=sc; self._cal_fl[a]=fl
            self._cal_ld[a]=ld; self._cal_cap[a]=cp
        self.cal_ax.legend(loc='upper left', fontsize=7, ncol=4)
        self.cal_fig.tight_layout()

        self._cal_mpl = FigureCanvasTkAgg(self.cal_fig, master=self.cal_graph_inner)
        self._cal_mpl.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _sash_press(self, e):
        self._sash_y0 = e.y_root
        self._sash_h0 = self._cal_graph_height

    def _sash_drag(self, e):
        delta = self._sash_y0 - e.y_root   # drag up = increase height
        new_h = max(80, self._sash_h0 + delta)
        self._cal_graph_height = new_h
        if self._cal_graph_shown:
            self.cal_frame.config(height=new_h)

    def _toggle_cal_graph(self):
        if self._cal_graph_shown:
            self.cal_graph_inner.pack_forget()
            self.cal_frame.config(height=28)
            self._btn_toggle_cal.config(text="▲ Show")
        else:
            self.cal_graph_inner.pack(fill=tk.BOTH, expand=True)
            self.cal_frame.config(height=self._cal_graph_height)
            self._btn_toggle_cal.config(text="▼ Hide")
        self._cal_graph_shown = not self._cal_graph_shown

    # ── RIGHT PANEL ──
    def _build_right_panel(self):
        BG  = "#f0f0f0"
        tf  = ("Arial", 10, "bold")
        vf  = ("Arial", 9)

        sc = tk.Canvas(self.right_frame, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(self.right_frame, orient=tk.VERTICAL, command=sc.yview)
        sc.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        sc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner = tk.Frame(sc, bg=BG)
        iw = sc.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: sc.configure(scrollregion=sc.bbox("all")))
        sc.bind("<Configure>",    lambda e: sc.itemconfig(iw, width=e.width))
        sc.bind_all("<MouseWheel>", lambda e: sc.yview_scroll(int(-1*(e.delta/120)),"units"))

        def section(parent, title):
            f = tk.LabelFrame(parent, text=title, font=tf, bg=BG)
            f.pack(fill=tk.X, padx=5, pady=3)
            return f

        # reset view
        tk.Button(inner, text="🎯 Reset Map View", command=self._reset_view,
                  font=tf, bg="#d0d0d0").pack(fill=tk.X, padx=5, pady=5)

        # ── Anchor Connection Order ──
        ord_f = section(inner, "Anchor Connection Order")
        tk.Label(ord_f, text="Drag to reorder — sets how border lines connect:",
                 font=("Arial",7), bg=BG, fg="#555", wraplength=320).pack(anchor="w", padx=4, pady=(2,4))

        self._order_listbox = tk.Listbox(ord_f, height=4, font=("Consolas",9),
                                          selectmode=tk.SINGLE, activestyle="dotbox")
        self._order_listbox.pack(fill=tk.X, padx=6, pady=2)
        for a in self.anchor_order:
            self._order_listbox.insert(tk.END, a)
        # color each entry
        for i, a in enumerate(self.anchor_order):
            self._order_listbox.itemconfig(i, fg=ANCHOR_COLORS[a])

        btn_row = tk.Frame(ord_f, bg=BG); btn_row.pack(fill=tk.X, padx=6, pady=(0,4))
        tk.Button(btn_row, text="▲ Up", font=vf, bg="#d0d0d0",
                  command=self._order_move_up).pack(side=tk.LEFT, padx=(0,4))
        tk.Button(btn_row, text="▼ Down", font=vf, bg="#d0d0d0",
                  command=self._order_move_down).pack(side=tk.LEFT)

        # ── Connectivity ──
        conn_f = section(inner, "Connectivity")
        self.conn_labels = {}
        for t in TAG_MACS:
            l = tk.Label(conn_f, text=f"{t}: Disconnected", font=vf, fg="red", bg=BG)
            l.pack(anchor="w", padx=4, pady=1)
            self.conn_labels[t] = l

        # ── Calibration ──
        cal_f = section(inner, "Calibration")

        # tag selector
        tr = tk.Frame(cal_f, bg=BG); tr.pack(fill=tk.X, padx=4, pady=3)
        tk.Label(tr, text="Calibrate Tag:", font=vf, bg=BG).pack(side=tk.LEFT)
        for t in ["T0","T1","T2"]:
            tk.Radiobutton(tr, text=t, variable=self.cal_tag_var, value=t,
                           font=vf, bg=BG, activebackground=BG,
                           command=self._cal_tag_changed).pack(side=tk.LEFT, padx=5)

        # live readings
        tk.Label(cal_f, text="Live Readings:", font=("Arial",8,"bold"), bg=BG).pack(anchor="w", padx=4, pady=(4,0))
        self._live_raw_lbl  = {}
        self._live_cal_lbl  = {}
        for a in ["A0","A1","A2","A3"]:
            row = tk.Frame(cal_f, bg=BG); row.pack(fill=tk.X, padx=6, pady=1)
            c = ANCHOR_COLORS[a]
            tk.Label(row, text=f"{a}:", font=(vf[0],vf[1],"bold"), fg=c, bg=BG, width=3).pack(side=tk.LEFT)
            tk.Label(row, text="Raw:", font=vf, bg=BG).pack(side=tk.LEFT)
            r = tk.Label(row, text="---", font=("Consolas",9), fg="gray", bg=BG, width=7); r.pack(side=tk.LEFT)
            tk.Label(row, text="Cal:", font=vf, bg=BG).pack(side=tk.LEFT, padx=(8,0))
            cl= tk.Label(row, text="---", font=("Consolas",9,"bold"), fg=c, bg=BG, width=7); cl.pack(side=tk.LEFT)
            self._live_raw_lbl[a] = r
            self._live_cal_lbl[a] = cl

        # true distance calculator (hypotenuse from floor distance + tag height)
        calc_f = tk.LabelFrame(cal_f, text="True Distance Calculator  (h = √(x²+y²))",
                               font=("Arial",8,"bold"), bg=BG)
        calc_f.pack(fill=tk.X, padx=4, pady=(8,2))

        # tag height (y) — shared across all anchors
        hy = tk.Frame(calc_f, bg=BG); hy.pack(fill=tk.X, padx=6, pady=(4,2))
        tk.Label(hy, text="Tag height y (ft):", font=vf, bg=BG).pack(side=tk.LEFT)
        self._height_var = tk.StringVar()
        tk.Entry(hy, textvariable=self._height_var, width=6, font=("Consolas",9)).pack(side=tk.LEFT, padx=4)
        self._crosshair_btn = tk.Button(hy, text="+ Place on Map", font=("Arial",8,"bold"),
                                         bg="#1abc9c", fg="white",
                                         command=self._toggle_crosshair_mode)
        self._crosshair_btn.pack(side=tk.LEFT, padx=(4,0))

        # floor distances (x) per anchor — auto-filled when crosshair is placed
        tk.Label(calc_f, text="Floor distance x (ft) per anchor  [or use map ✛ above]:",
                 font=("Arial",8), bg=BG).pack(anchor="w", padx=6)
        xrow = tk.Frame(calc_f, bg=BG); xrow.pack(fill=tk.X, padx=6, pady=2)
        self._floor_vars = {a: tk.StringVar() for a in ["A0","A1","A2","A3"]}
        for i, a in enumerate(["A0","A1","A2","A3"]):
            c = ANCHOR_COLORS[a]
            tk.Label(xrow, text=f"{a}:", font=(vf[0],vf[1],"bold"), fg=c, bg=BG).grid(row=0, column=i*2, sticky="e", padx=(4,1))
            tk.Entry(xrow, textvariable=self._floor_vars[a], width=5, font=("Consolas",9)).grid(row=0, column=i*2+1, padx=(0,4))

        # solved hypotenuse results display
        hrow = tk.Frame(calc_f, bg=BG); hrow.pack(fill=tk.X, padx=6, pady=(2,2))
        self._hyp_labels = {}
        for i, a in enumerate(["A0","A1","A2","A3"]):
            c = ANCHOR_COLORS[a]
            tk.Label(hrow, text=f"{a}:", font=(vf[0],vf[1],"bold"), fg=c, bg=BG).grid(row=0, column=i*2, sticky="e", padx=(4,1))
            lbl = tk.Label(hrow, text="---", font=("Consolas",9,"bold"), fg=c, bg=BG, width=6)
            lbl.grid(row=0, column=i*2+1, padx=(0,4))
            self._hyp_labels[a] = lbl

        tk.Button(calc_f, text="⬆ Calculate & Upload to True Distances",
                  bg="#2196F3", fg="white", font=("Arial",9,"bold"),
                  command=self._calc_and_upload).pack(fill=tk.X, padx=6, pady=(2,6))

        # true distance inputs (filled by calculator or manually)
        tk.Label(cal_f, text="True Distances (ft):", font=("Arial",8,"bold"), bg=BG).pack(anchor="w", padx=4, pady=(4,0))
        tdr = tk.Frame(cal_f, bg=BG); tdr.pack(fill=tk.X, padx=6, pady=3)
        self._true_entries = {}
        for i, a in enumerate(["A0","A1","A2","A3"]):
            c = ANCHOR_COLORS[a]
            tk.Label(tdr, text=f"{a}:", font=(vf[0],vf[1],"bold"), fg=c, bg=BG).grid(row=0, column=i*2, sticky="e", padx=(4,1))
            e = tk.Entry(tdr, textvariable=self.true_dist_vars[a], width=5, font=("Consolas",9))
            e.grid(row=0, column=i*2+1, padx=(0,4))
            self._true_entries[a] = e

        # ── per-anchor curve type (anchor selector above dropdown) ──
        tk.Label(cal_f, text="Calibration Curve Type:", font=("Arial",8,"bold"), bg=BG).pack(anchor="w", padx=4, pady=(10,0))

        # anchor selector for which anchor's curve we're editing
        an_row = tk.Frame(cal_f, bg=BG); an_row.pack(fill=tk.X, padx=6, pady=(2,0))
        tk.Label(an_row, text="For anchor:", font=vf, bg=BG).pack(side=tk.LEFT)
        self.curve_anchor_var = tk.StringVar(value="A0")
        for a in ["A0","A1","A2","A3"]:
            tk.Radiobutton(an_row, text=a, variable=self.curve_anchor_var, value=a,
                           font=(vf[0],vf[1],"bold"), fg=ANCHOR_COLORS[a],
                           bg=BG, activebackground=BG,
                           command=self._on_curve_anchor_change).pack(side=tk.LEFT, padx=3)

        # auto-recommend checkbox
        tk.Checkbutton(cal_f, text="Auto-Recommend", variable=self.auto_rec_var,
                       font=("Arial",8), bg=BG).pack(anchor="e", padx=6)

        # curve type dropdown for selected anchor
        self._fit_combo_frame = tk.Frame(cal_f, bg=BG)
        self._fit_combo_frame.pack(fill=tk.X, padx=6, pady=(2,0))
        self._fit_combo = ttk.Combobox(self._fit_combo_frame, state="readonly", font=vf)
        self._fit_combo['values'] = ("Linear","Exponential","Polynomial","Logarithmic","Power Series","Moving Average")
        self._fit_combo.pack(fill=tk.X)
        self._fit_combo.bind("<<ComboboxSelected>>", self._on_fit_mode_change)
        # init combo to current anchor
        self._fit_combo.set(self.fit_mode_vars["A0"].get())

        # poly degree options (shown inline when Polynomial selected)
        self._poly_frame = tk.Frame(cal_f, bg=BG)
        tk.Label(self._poly_frame, text="Degree:", font=vf, bg=BG).pack(side=tk.LEFT)
        self._poly_spin = tk.Spinbox(self._poly_frame, from_=1, to=20, width=4,
                                      command=self._recalc_for_anchor)
        self._poly_spin.pack(side=tk.LEFT, padx=4)
        self._poly_spin.bind("<KeyRelease>", lambda e: self._recalc_for_anchor())

        # moving average options
        self._ma_frame = tk.Frame(cal_f, bg=BG)
        self._ma_type_cb = ttk.Combobox(self._ma_frame, values=["Trailing","Centered"],
                                         state="readonly", width=8)
        self._ma_type_cb.pack(side=tk.LEFT, padx=2)
        self._ma_type_cb.bind("<<ComboboxSelected>>", lambda e: self._recalc_for_anchor())
        self._ma_per_cb = ttk.Combobox(self._ma_frame, values=["2","3","4","5","6","8","10"],
                                        state="readonly", width=3)
        self._ma_per_cb.pack(side=tk.LEFT, padx=2)
        self._ma_per_cb.bind("<<ComboboxSelected>>", lambda e: self._recalc_for_anchor())
        self._refresh_curve_options()

        # ── Multi-Sample Capture ──
        cap_f = tk.LabelFrame(cal_f, text="Multi-Sample Capture", font=("Arial",8,"bold"), bg=BG)
        cap_f.pack(fill=tk.X, padx=4, pady=6)

        caprow = tk.Frame(cap_f, bg=BG); caprow.pack(fill=tk.X, padx=4, pady=4)
        tk.Label(caprow, text="Samples:", font=vf, bg=BG).pack(side=tk.LEFT)
        ttk.Combobox(caprow, textvariable=self.num_samples_var,
                     values=["1","5","10","20","50","100"], state="readonly", width=4
                     ).pack(side=tk.LEFT, padx=4)
        self._btn_cap = tk.Button(caprow, text="Add Point", bg="#4CAF50", fg="white",
                                   font=("Arial",9,"bold"), command=self._start_capture)
        self._btn_cap.pack(side=tk.LEFT, padx=6)

        # scrollable inner area (listbox + progress bars live here)
        cap_scroll_outer = tk.Frame(cap_f, bg=BG, height=180)
        cap_scroll_outer.pack(fill=tk.X, padx=4, pady=2)
        cap_scroll_outer.pack_propagate(False)

        cap_canvas = tk.Canvas(cap_scroll_outer, bg=BG, highlightthickness=0)
        cap_sb = tk.Scrollbar(cap_scroll_outer, orient=tk.VERTICAL, command=cap_canvas.yview)
        cap_canvas.configure(yscrollcommand=cap_sb.set)
        cap_sb.pack(side=tk.RIGHT, fill=tk.Y)
        cap_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cap_inner = tk.Frame(cap_canvas, bg=BG)
        cap_iw = cap_canvas.create_window((0,0), window=cap_inner, anchor="nw")
        cap_inner.bind("<Configure>", lambda e: cap_canvas.configure(scrollregion=cap_canvas.bbox("all")))
        cap_canvas.bind("<Configure>", lambda e: cap_canvas.itemconfig(cap_iw, width=e.width))

        # progress bars (hidden until capture starts)
        self._prog_frame = tk.Frame(cap_inner, bg=BG)
        self._prog_frame.pack(fill=tk.X, pady=(2,4))
        self._prog_bars  = {}
        self._prog_labels = {}
        for a in ["A0","A1","A2","A3"]:
            row = tk.Frame(self._prog_frame, bg=BG); row.pack(fill=tk.X, padx=2, pady=1)
            c_col = ANCHOR_COLORS[a]
            tk.Label(row, text=f"{a}:", font=("Arial",8,"bold"), fg=c_col, bg=BG, width=3).pack(side=tk.LEFT)
            bar = ttk.Progressbar(row, orient=tk.HORIZONTAL, mode="determinate", length=160)
            bar.pack(side=tk.LEFT, padx=(2,4))
            lbl = tk.Label(row, text="0/0", font=("Arial",8), bg=BG, width=7)
            lbl.pack(side=tk.LEFT)
            self._prog_bars[a]   = bar
            self._prog_labels[a] = lbl
        self._prog_frame.pack_forget()  # hidden until capture

        # listbox of saved points
        self._listbox = tk.Listbox(cap_inner, height=5, font=("Consolas",8))
        self._listbox.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        tk.Button(cap_f, text="Clear Data", fg="red", bg=BG, command=self._clear_cal).pack(pady=2)

        # ── Calibration Equations (all 4 anchors at once) ──
        eq_section = section(inner, "Calibration Equations")

        eq_top = tk.Frame(eq_section, bg=BG); eq_top.pack(fill=tk.X, padx=4, pady=(2,0))
        tk.Button(eq_top, text="⟲ Reset All Auto", font=("Arial",8), bg=BG,
                  command=lambda: [self.preset_vars[a].set(False) for a in ["A0","A1","A2","A3"]] or self._recalc_all()
                  ).pack(side=tk.RIGHT, padx=2)

        # one equation row per anchor with its own preset toggle
        self._eq_texts = {}
        for a in ["A0","A1","A2","A3"]:
            anchor_f = tk.Frame(eq_section, bg=BG, relief=tk.GROOVE, bd=1)
            anchor_f.pack(fill=tk.X, padx=4, pady=3)
            col = ANCHOR_COLORS[a]
            # header row: label + preset checkbox
            hrow = tk.Frame(anchor_f, bg=BG); hrow.pack(fill=tk.X, padx=2, pady=(2,0))
            tk.Label(hrow, text=f"{a}  True =", font=("Arial",8,"bold"), fg=col, bg=BG).pack(side=tk.LEFT)
            tk.Checkbutton(hrow, text="Preset", variable=self.preset_vars[a],
                           font=("Arial",7), fg="purple", bg=BG, activebackground=BG,
                           command=self._recalc_all).pack(side=tk.RIGHT)
            et = tk.Text(anchor_f, font=("Consolas",8,"bold"), fg="blue",
                         height=2, wrap=tk.WORD, bg="white")
            et.pack(fill=tk.X, padx=2, pady=(0,2))
            et.bind("<KeyRelease>", lambda event, anchor=a: self._on_eq_edit(event, anchor))
            self._eq_texts[a] = et

        tk.Button(eq_section, text="💾  Save Calibration Equations", bg="#27ae60", fg="white",
                  font=("Arial",9,"bold"), command=self._save_cal).pack(fill=tk.X, padx=6, pady=(4,8))

        # ── Smoothing Filter ──
        filt_f = section(inner, "Smoothing Filter")
        mr = tk.Frame(filt_f, bg=BG); mr.pack(fill=tk.X, padx=4, pady=(4,2))
        for m in ("EMA","Rolling","Kalman"):
            tk.Radiobutton(mr, text=m, variable=self.filter_mode, value=m,
                           font=vf, bg=BG, activebackground=BG).pack(side=tk.LEFT, padx=4)

        def _slider(parent, lbl, var, lo, hi, res, fmt, init):
            row = tk.Frame(parent, bg=BG); row.pack(fill=tk.X, padx=4, pady=1)
            tk.Label(row, text=lbl, font=("Arial",8), bg=BG, width=22, anchor="w").pack(side=tk.LEFT)
            vl = tk.Label(row, text=init, font=("Arial",8,"bold"), bg=BG, width=5); vl.pack(side=tk.RIGHT)
            tk.Scale(parent, variable=var, from_=lo, to=hi, resolution=res,
                     orient=tk.HORIZONTAL, bg=BG, highlightthickness=0, showvalue=False,
                     command=lambda v, l=vl, f=fmt: l.config(text=f.format(float(v)))
                     ).pack(fill=tk.X, padx=4)
        _slider(filt_f,"EMA α (0=smooth,1=raw):", self.ema_alpha, 0.01,1.0, 0.01,"{:.2f}","0.20")
        _slider(filt_f,"Rolling window (frames):",self.roll_n,    2,   30,  1,   "{:.0f}","8")
        _slider(filt_f,"Kalman Q (process noise):",self.kal_q,   0.01, 2.0, 0.01,"{:.2f}","0.10")
        _slider(filt_f,"Kalman R (meas. noise):",  self.kal_r,   0.1,  10.0,0.1, "{:.1f}","2.00")

        # ── Save / Load Settings ──
        sl_f = section(inner, "Save / Load Settings")
        tk.Label(sl_f, text="Saves anchors, calibration points, equations & curve types.",
                 font=("Arial",7), bg=BG, fg="#555", wraplength=320).pack(anchor="w", padx=4, pady=(2,4))
        sl_row = tk.Frame(sl_f, bg=BG); sl_row.pack(fill=tk.X, padx=6, pady=(0,6))
        tk.Button(sl_row, text="💾  Save Settings", bg="#2196F3", fg="white",
                  font=("Arial",10,"bold"), command=self._save_settings).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,4))
        tk.Button(sl_row, text="📂  Load Settings", bg="#555", fg="white",
                  font=("Arial",10,"bold"), command=self._load_settings).pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ──────────────────────────────────────
    # HYPOTENUSE CALCULATOR
    # ──────────────────────────────────────
    def _toggle_crosshair_mode(self):
        if self.crosshair_pos is not None:
            # already placed — remove it and reset
            self.crosshair_pos   = None
            self._crosshair_mode = False
            self._crosshair_btn.config(text="+ Place on Map", bg="#1abc9c")
            for a in ["A0","A1","A2","A3"]:
                self._floor_vars[a].set("")
            self._draw()
        else:
            # arm placement mode
            self._crosshair_mode = not self._crosshair_mode
            if self._crosshair_mode:
                self._crosshair_btn.config(text="✕ Cancel", bg="#e74c3c")
            else:
                self._crosshair_btn.config(text="+ Place on Map", bg="#1abc9c")

    def _update_crosshair_floors(self):
        if self.crosshair_pos is None: return
        cx, cy = self.crosshair_pos
        for a, (ax, ay) in self.anchor_pos.items():
            floor_d = math.hypot(cx - ax, cy - ay)
            self._floor_vars[a].set(f"{floor_d:.3f}")
    def _calc_and_upload(self):
        try:
            y = float(self._height_var.get())
        except ValueError:
            messagebox.showerror("Input Error", "Enter a valid tag height (y).")
            return

        any_set = False
        for a in ["A0","A1","A2","A3"]:
            xs = self._floor_vars[a].get().strip()
            if xs == "":
                self._hyp_labels[a].config(text="---")
                continue
            try:
                x = float(xs)
            except ValueError:
                messagebox.showerror("Input Error", f"Invalid floor distance for {a}.")
                return
            h = math.sqrt(x**2 + y**2)
            self._hyp_labels[a].config(text=f"{h:.3f}")
            self.true_dist_vars[a].set(f"{h:.3f}")
            any_set = True

        if not any_set:
            messagebox.showerror("Input Error", "Enter at least one floor distance (x).")

    # ──────────────────────────────────────
    # ANCHOR CONNECTION ORDER
    # ──────────────────────────────────────
    def _order_move_up(self):
        sel = self._order_listbox.curselection()
        if not sel or sel[0] == 0: return
        i = sel[0]
        self.anchor_order[i], self.anchor_order[i-1] = self.anchor_order[i-1], self.anchor_order[i]
        self._refresh_order_listbox(i-1)
        self._draw()

    def _order_move_down(self):
        sel = self._order_listbox.curselection()
        if not sel or sel[0] == len(self.anchor_order)-1: return
        i = sel[0]
        self.anchor_order[i], self.anchor_order[i+1] = self.anchor_order[i+1], self.anchor_order[i]
        self._refresh_order_listbox(i+1)
        self._draw()

    def _refresh_order_listbox(self, select_idx=None):
        self._order_listbox.delete(0, tk.END)
        for a in self.anchor_order:
            self._order_listbox.insert(tk.END, a)
            self._order_listbox.itemconfig(tk.END, fg=ANCHOR_COLORS[a])
        if select_idx is not None:
            self._order_listbox.selection_set(select_idx)
            self._order_listbox.activate(select_idx)

    # ──────────────────────────────────────
    # CURVE TYPE UI HELPERS
    # ──────────────────────────────────────
    def _on_curve_anchor_change(self):
        a = self.curve_anchor_var.get()
        self._fit_combo.set(self.fit_mode_vars[a].get())
        self._poly_spin.delete(0, tk.END)
        self._poly_spin.insert(0, self.poly_deg_vars[a].get())
        self._ma_type_cb.set(self.ma_type_vars[a].get())
        self._ma_per_cb.set(self.ma_period_vars[a].get())
        self._refresh_curve_options()

    def _on_fit_mode_change(self, event=None):
        a = self.curve_anchor_var.get()
        self.fit_mode_vars[a].set(self._fit_combo.get())
        self._refresh_curve_options()
        self._recalc_for_anchor()

    def _refresh_curve_options(self):
        # show/hide poly/MA sub-options directly below the dropdown
        a    = self.curve_anchor_var.get()
        mode = self.fit_mode_vars[a].get()
        self._poly_frame.pack_forget()
        self._ma_frame.pack_forget()
        if mode == "Polynomial":
            self._poly_frame.pack(in_=self._fit_combo_frame.master,
                                   fill=tk.X, padx=6, pady=(2,0))
        elif mode == "Moving Average":
            self._ma_frame.pack(in_=self._fit_combo_frame.master,
                                 fill=tk.X, padx=6, pady=(2,0))

    def _recalc_for_anchor(self):
        a = self.curve_anchor_var.get()
        self.poly_deg_vars[a].set(self._poly_spin.get())
        self.ma_period_vars[a].set(self._ma_per_cb.get())
        self.ma_type_vars[a].set(self._ma_type_cb.get())
        self._recalc_all()

    # ──────────────────────────────────────
    # MAP DRAWING
    # ──────────────────────────────────────
    def _cx(self, x): return self.pan_x + x * self.scale
    def _cy(self, y): return self.pan_y - y * self.scale
    def _fx(self, cx): return (cx - self.pan_x) / self.scale
    def _fy(self, cy): return (self.pan_y - cy) / self.scale

    def _reset_view(self):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10: return
        all_x = [p[0] for p in self.anchor_pos.values()]
        all_y = [p[1] for p in self.anchor_pos.values()]
        span_x = max(all_x) - min(all_x) or 1
        span_y = max(all_y) - min(all_y) or 1
        pad = 80
        self.scale = min((cw-pad)/span_x, (ch-pad)/span_y)
        cx_mid = (min(all_x) + max(all_x)) / 2
        cy_mid = (min(all_y) + max(all_y)) / 2
        self.pan_x = cw/2 - cx_mid * self.scale
        self.pan_y = ch/2 + cy_mid * self.scale
        self._draw()

    def _draw(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width(); h = c.winfo_height()

        all_x = [p[0] for p in self.anchor_pos.values()]
        all_y = [p[1] for p in self.anchor_pos.values()]
        if not all_x: return

        gx_min = math.floor(min(all_x)/5)*5 - 5
        gx_max = math.ceil( max(all_x)/5)*5 + 5
        gy_min = math.floor(min(all_y)/5)*5 - 5
        gy_max = math.ceil( max(all_y)/5)*5 + 5

        for gx in range(int(gx_min), int(gx_max)+1, 2):
            c.create_line(self._cx(gx), self._cy(gy_min),
                          self._cx(gx), self._cy(gy_max), fill=GRID_COLOR, width=1)
        for gy in range(int(gy_min), int(gy_max)+1, 2):
            c.create_line(self._cx(gx_min), self._cy(gy),
                          self._cx(gx_max), self._cy(gy), fill=GRID_COLOR, width=1)

        c.create_line(self._cx(gx_min), self._cy(0), self._cx(gx_max), self._cy(0),
                      fill="#999", width=1, dash=(4,4))
        c.create_line(self._cx(0), self._cy(gy_min), self._cx(0), self._cy(gy_max),
                      fill="#999", width=1, dash=(4,4))

        order = self.anchor_order
        pts_line = []
        for a in order:
            pts_line += [self._cx(self.anchor_pos[a][0]), self._cy(self.anchor_pos[a][1])]
        pts_line += [self._cx(self.anchor_pos[order[0]][0]), self._cy(self.anchor_pos[order[0]][1])]
        c.create_line(*pts_line, fill="#555", width=2)

        for i in range(len(order)):
            a1 = order[i]; a2 = order[(i+1) % len(order)]
            x1,y1 = self.anchor_pos[a1]; x2,y2 = self.anchor_pos[a2]
            dist = math.hypot(x2-x1, y2-y1)
            mx = (self._cx(x1)+self._cx(x2))/2
            my = (self._cy(y1)+self._cy(y2))/2
            c.create_text(mx, my-10, text=f"{dist:.1f} ft", font=("Arial",7), fill="#777")

        for a_id, (ax, ay) in self.anchor_pos.items():
            cx_a, cy_a = self._cx(ax), self._cy(ay)
            col = ANCHOR_COLORS[a_id]
            r = 9
            c.create_oval(cx_a-r, cy_a-r, cx_a+r, cy_a+r, fill=col, outline="white", width=2,
                          tags=(f"anchor_{a_id}","anchor"))
            c.create_text(cx_a, cy_a-r-8, text=a_id, font=("Arial",9,"bold"), fill=col)
            c.create_text(cx_a, cy_a+r+9, text=f"({ax:.1f}, {ay:.1f})", font=("Arial",8), fill=col)

        now = time.time()
        for t1,t2 in [("T0","T1"),("T1","T2"),("T0","T2")]:
            p1,p2 = self.tag_pos[t1], self.tag_pos[t2]
            if p1 and p2:
                dist = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
                c.create_line(self._cx(p1[0]),self._cy(p1[1]),
                              self._cx(p2[0]),self._cy(p2[1]),
                              fill="orange", width=1.5, dash=(4,4))
                mc = ((self._cx(p1[0])+self._cx(p2[0]))/2,
                      (self._cy(p1[1])+self._cy(p2[1]))/2)
                c.create_text(mc[0], mc[1]-10, text=f"{dist:.2f}ft",
                               fill="orange", font=("Arial",9,"bold"))

        for t_id, tp in self.tag_pos.items():
            if tp:
                cx_t, cy_t = self._cx(tp[0]), self._cy(tp[1])
                r = 9
                c.create_oval(cx_t-r, cy_t-r, cx_t+r, cy_t+r,
                               fill=TAG_COLORS[t_id], outline="white", width=2)
                c.create_text(cx_t+14, cy_t-8, text=t_id, fill=TAG_COLORS[t_id],
                               font=("Arial",10,"bold"), anchor="w")

        # blue crosshair for floor distance measurement
        if self.crosshair_pos is not None:
            px, py = self._cx(self.crosshair_pos[0]), self._cy(self.crosshair_pos[1])
            arm = 14
            c.create_line(px-arm, py, px+arm, py, fill="#0055ff", width=2, tags="crosshair")
            c.create_line(px, py-arm, px, py+arm, fill="#0055ff", width=2, tags="crosshair")
            c.create_oval(px-5, py-5, px+5, py+5, outline="#0055ff", width=2, tags="crosshair")
            c.create_text(px, py+arm+10,
                          text=f"✛ ({self.crosshair_pos[0]:.1f}, {self.crosshair_pos[1]:.1f})",
                          font=("Arial",8,"bold"), fill="#0055ff", tags="crosshair")
            # dashed lines to each anchor showing floor distance
            for a_id, (ax, ay) in self.anchor_pos.items():
                acx, acy = self._cx(ax), self._cy(ay)
                floor_d = math.hypot(self.crosshair_pos[0]-ax, self.crosshair_pos[1]-ay)
                c.create_line(px, py, acx, acy, fill="#0055ff", width=1, dash=(3,5), tags="crosshair")
                mdx = (px+acx)/2; mdy = (py+acy)/2
                c.create_text(mdx, mdy-8, text=f"{floor_d:.2f}ft",
                               font=("Arial",7), fill="#0055ff", tags="crosshair")

    # ── map interactions ──
    def _crosshair_hit(self, cx, cy, radius=14):
        if self.crosshair_pos is None: return False
        px, py = self._cx(self.crosshair_pos[0]), self._cy(self.crosshair_pos[1])
        return math.hypot(cx-px, cy-py) <= radius

    def _anchor_hit(self, cx, cy, radius=14):
        for a_id, (ax, ay) in self.anchor_pos.items():
            if math.hypot(cx-self._cx(ax), cy-self._cy(ay)) <= radius:
                return a_id
        return None

    def _map_press(self, e):
        # if crosshair placement mode is armed, drop the crosshair here
        if self._crosshair_mode:
            self.crosshair_pos = [round(self._fx(e.x),2), round(self._fy(e.y),2)]
            self._crosshair_mode = False
            self._crosshair_btn.config(text="+ Place on Map", bg="#1abc9c")
            self._update_crosshair_floors()
            self._draw()
            return

        if self._crosshair_hit(e.x, e.y):
            self._drag_anchor = "__crosshair__"
            self._drag_ox = e.x - self._cx(self.crosshair_pos[0])
            self._drag_oy = e.y - self._cy(self.crosshair_pos[1])
            return

        hit = self._anchor_hit(e.x, e.y)
        if hit:
            self._drag_anchor = hit
            self._drag_ox = e.x - self._cx(self.anchor_pos[hit][0])
            self._drag_oy = e.y - self._cy(self.anchor_pos[hit][1])
        else:
            self._drag_anchor = None
            self._map_pan_start = (e.x, e.y, self.pan_x, self.pan_y)

    def _map_drag(self, e):
        if self._drag_anchor == "__crosshair__":
            self.crosshair_pos = [round(self._fx(e.x - self._drag_ox),2),
                                   round(self._fy(e.y - self._drag_oy),2)]
            self._update_crosshair_floors()
            self._draw()
        elif self._drag_anchor:
            self.anchor_pos[self._drag_anchor] = [round(self._fx(e.x - self._drag_ox),2),
                                                   round(self._fy(e.y - self._drag_oy),2)]
            if self.crosshair_pos is not None:
                self._update_crosshair_floors()
            self._draw()
        else:
            if hasattr(self, '_map_pan_start'):
                sx,sy,px,py = self._map_pan_start
                self.pan_x = px + (e.x - sx)
                self.pan_y = py + (e.y - sy)
                self._draw()

    def _map_release(self, e):
        self._drag_anchor = None

    def _map_wheel(self, e):
        zoom = 1.1 if (e.num==4 or getattr(e,'delta',0)>0) else 0.9
        mx = self._fx(e.x); my = self._fy(e.y)
        self.scale *= zoom
        self.pan_x = e.x - mx*self.scale
        self.pan_y = e.y + my*self.scale
        self._draw()

    def _map_dblclick(self, e):
        # crosshair coordinate edit
        if self._crosshair_hit(e.x, e.y, radius=22):
            self._open_coord_editor(e.x_root, e.y_root,
                                    self.crosshair_pos[0], self.crosshair_pos[1],
                                    self._commit_crosshair)
            return
        hit = self._anchor_hit(e.x, e.y, radius=22)
        if not hit: return
        ax, ay = self.anchor_pos[hit]
        self._open_coord_editor(e.x_root, e.y_root, ax, ay,
                                lambda nx, ny: self._commit_anchor(hit, nx, ny))

    def _open_coord_editor(self, x_root, y_root, init_x, init_y, commit_cb):
        entry_win = tk.Toplevel(self.root)
        entry_win.overrideredirect(True)
        entry_win.geometry(f"+{x_root-30}+{y_root+10}")
        entry_win.lift()
        var = tk.StringVar(value=f"{init_x:.1f},{init_y:.1f}")
        ent = tk.Entry(entry_win, textvariable=var, width=12, font=("Consolas",10), justify="center")
        ent.pack(padx=2, pady=2)
        ent.select_range(0, tk.END)
        ent.focus_set()
        def commit(ev=None):
            try:
                parts = var.get().replace(" ","").split(",")
                commit_cb(round(float(parts[0]),2), round(float(parts[1]),2))
            except: pass
            entry_win.destroy()
        ent.bind("<Return>", commit)
        ent.bind("<Escape>", lambda ev: entry_win.destroy())
        ent.bind("<FocusOut>", commit)

    def _commit_anchor(self, a_id, nx, ny):
        self.anchor_pos[a_id] = [nx, ny]
        if self.crosshair_pos is not None:
            self._update_crosshair_floors()
        self._draw()

    def _commit_crosshair(self, nx, ny):
        self.crosshair_pos = [nx, ny]
        self._update_crosshair_floors()
        self._draw()

    # ──────────────────────────────────────
    # RTLS LOOP
    # ──────────────────────────────────────
    def _rtls_loop(self):
        for t_id in TAG_MACS:
            if tag_status[t_id] != "Connected":
                if self.tag_pos[t_id] is not None:
                    self._reset_filter(t_id)
                self.tag_pos[t_id] = None
                continue
            cal_d = {}
            for a in ["A0","A1","A2","A3"]:
                raw = tag_data[t_id][a]
                if raw > 0:
                    try: cal_d[a] = self.cal_func[t_id][a](raw)
                    except: cal_d[a] = raw
            x, y = calc_pos(self.anchor_pos, cal_d)
            if x is not None:
                sx, sy = self._smooth(t_id, x, y)
                self.tag_pos[t_id] = (round(sx,3), round(sy,3))
            else:
                self.tag_pos[t_id] = None

        self._update_tables()
        self._draw()
        self.root.after(50, self._rtls_loop)

    def _update_tables(self):
        for t, l in self.conn_labels.items():
            s = tag_status[t]
            l.config(text=f"{t}: {s}",
                     fg="green" if s=="Connected" else ("orange" if "Connect" in s else "red"))

    # ──────────────────────────────────────
    # SMOOTHING
    # ──────────────────────────────────────
    def _smooth(self, t, rx, ry):
        m = self.filter_mode.get()
        if m=="EMA":     return self._ema(t,rx,ry)
        if m=="Rolling": return self._rolling(t,rx,ry)
        if m=="Kalman":  return self._kalman(t,rx,ry)
        return rx, ry

    def _ema(self, t, rx, ry):
        a = self.ema_alpha.get(); p = self.ema_pos[t]
        if p is None: self.ema_pos[t]=(rx,ry)
        else: self.ema_pos[t]=(a*rx+(1-a)*p[0], a*ry+(1-a)*p[1])
        return self.ema_pos[t]

    def _rolling(self, t, rx, ry):
        n = self.roll_n.get(); buf = self.roll_buf[t]
        if buf.maxlen != n: self.roll_buf[t] = deque(list(buf)[-n:], maxlen=n); buf=self.roll_buf[t]
        buf.append((rx,ry))
        return sum(p[0] for p in buf)/len(buf), sum(p[1] for p in buf)/len(buf)

    def _kalman(self, t, rx, ry):
        q=self.kal_q.get(); r=self.kal_r.get(); dt=0.05
        F=[[1,0,dt,0],[0,1,0,dt],[0,0,1,0],[0,0,0,1]]
        H=[[1,0,0,0],[0,1,0,0]]
        Q=[[q*dt**3/3,0,q*dt**2/2,0],[0,q*dt**3/3,0,q*dt**2/2],
           [q*dt**2/2,0,q*dt,0],[0,q*dt**2/2,0,q*dt]]
        R=[[r,0],[0,r]]
        def mm(A,B): return [[sum(A[i][k]*B[k][j] for k in range(len(B))) for j in range(len(B[0]))] for i in range(len(A))]
        def ma(A,B): return [[A[i][j]+B[i][j] for j in range(len(A[0]))] for i in range(len(A))]
        def ms(A,B): return [[A[i][j]-B[i][j] for j in range(len(A[0]))] for i in range(len(A))]
        def mt(A): return [[A[j][i] for j in range(len(A))] for i in range(len(A[0]))]
        def mi2(A):
            d=A[0][0]*A[1][1]-A[0][1]*A[1][0]
            if abs(d)<1e-9: d=1e-9
            return [[A[1][1]/d,-A[0][1]/d],[-A[1][0]/d,A[0][0]/d]]
        def eye(n): return [[1 if i==j else 0 for j in range(n)] for i in range(n)]
        if self.kal_state[t] is None:
            self.kal_state[t]=[[rx],[ry],[0.0],[0.0]]; self.kal_P[t]=eye(4)
        x=self.kal_state[t]; P=self.kal_P[t]
        xp=mm(F,x); Pp=ma(mm(mm(F,P),mt(F)),Q)
        z=[[rx],[ry]]; yk=ms(z,mm(H,xp))
        S=ma(mm(mm(H,Pp),mt(H)),R); K=mm(mm(Pp,mt(H)),mi2(S))
        xn=ma(xp,mm(K,yk)); Pn=mm(ms(eye(4),mm(K,H)),Pp)
        self.kal_state[t]=xn; self.kal_P[t]=Pn
        return xn[0][0], xn[1][0]

    def _reset_filter(self, t):
        self.ema_pos[t]=None
        self.roll_buf[t]=deque(maxlen=20)
        self.kal_state[t]=None; self.kal_P[t]=None

    # ──────────────────────────────────────
    # CALIBRATION
    # ──────────────────────────────────────
    def _cal_tag_changed(self):
        self._refresh_listbox()
        self._recalc_all()

    def _refresh_listbox(self):
        tag    = self.cal_tag_var.get()
        anchor = self.curve_anchor_var.get()
        self._listbox.delete(0, tk.END)
        for raw, true in self.cal_pts[tag][anchor]:
            self._listbox.insert(tk.END, f"Raw: {raw:.2f} ft → True: {true:.2f} ft")

    def _recalc_all(self, *_):
        tag = self.cal_tag_var.get()
        for a in ["A0","A1","A2","A3"]:
            mode = self.fit_mode_vars[a].get()
            try: pd = int(self.poly_deg_vars[a].get())
            except: pd = 4
            try: mp = int(self.ma_period_vars[a].get())
            except: mp = 4
            mt = self.ma_type_vars[a].get()
            pts = self.cal_pts[tag][a]
            if self.preset_vars[a].get():
                self.cal_func[tag][a] = lambda x: (0.7514969*x)+0.0295246
            elif len(pts)>=2:
                X=np.array([p[0] for p in pts]); Y=np.array([p[1] for p in pts])
                f,_ = build_eval_func(mode,X,Y,pd,mp,mt)
                self.cal_func[tag][a] = f
            elif len(pts)==1:
                off=pts[0][1]-pts[0][0]
                self.cal_func[tag][a] = lambda x,o=off: x+o
            else:
                self.cal_func[tag][a] = lambda x: x
            self._update_cal_graph(a)
        self._refresh_all_eq_displays()

    def _refresh_all_eq_displays(self):
        tag = self.cal_tag_var.get()
        for a in ["A0","A1","A2","A3"]:
            pts = self.cal_pts[tag][a]
            mode = self.fit_mode_vars[a].get()
            if self.preset_vars[a].get():
                eq  = "True = (0.7514969*Raw)+0.0295246  [preset]"
                col = "purple"
            elif len(pts)>=2:
                X=np.array([p[0] for p in pts]); Y=np.array([p[1] for p in pts])
                try: pd=int(self.poly_deg_vars[a].get())
                except: pd=4
                try: mp=int(self.ma_period_vars[a].get())
                except: mp=4
                _,eq_str = build_eval_func(mode,X,Y,pd,mp,self.ma_type_vars[a].get())
                eq  = eq_str
                col = "blue"
            elif len(pts)==1:
                off=pts[0][1]-pts[0][0]
                eq  = f"Raw + {off:.5f}  (1 point)"
                col = "blue"
            else:
                eq  = "Raw (not enough data)"
                col = "gray"
            et = self._eq_texts[a]
            et.config(fg=col)
            et.delete("1.0", tk.END)
            et.insert("1.0", eq)
        self._refresh_listbox()

    def _on_eq_edit(self, event=None, anchor="A0"):
        if self.preset_var.get(): return
        tag     = self.cal_tag_var.get()
        eq_str  = self._eq_texts[anchor].get("1.0", tk.END).strip()
        safe    = eq_str.replace("^","**")
        math_env= {"ln":np.log,"log":np.log10,"e":np.e,"pi":np.pi,
                   "sin":np.sin,"cos":np.cos,"sqrt":np.sqrt,"abs":abs}
        try:
            code = compile(safe,'<string>','eval')
            eval(code,{"__builtins__":{}}, dict(math_env, Raw=1.0))
            self._eq_texts[anchor].config(fg="black")
            def mfunc(raw, c=code, me=math_env):
                try: return float(eval(c,{"__builtins__":{}}, dict(me, Raw=float(raw))))
                except: return 0.0
            self.cal_func[tag][anchor] = mfunc
        except:
            self._eq_texts[anchor].config(fg="red")

    def _update_cal_graph(self, anchor):
        tag = self.cal_tag_var.get()
        pts = self.cal_pts[tag][anchor]
        if pts:
            self._cal_sc[anchor].set_data([p[0] for p in pts],[p[1] for p in pts])
            lx=np.linspace(0.01,35,120)
            try: ly=[self.cal_func[tag][anchor](x) for x in lx]
            except: ly=[0]*120
            self._cal_fl[anchor].set_data(lx,ly)
        else:
            self._cal_sc[anchor].set_data([],[])
            self._cal_fl[anchor].set_data([],[])
        self._cal_mpl.draw_idle()

    def _cal_live_update(self):
        tag = self.cal_tag_var.get()
        for a in ["A0","A1","A2","A3"]:
            raw = tag_data[tag][a]
            if raw > 0:
                self.cur_raws[a] = raw
                try: cal = self.cal_func[tag][a](raw)
                except: cal = raw
                self._live_raw_lbl[a].config(text=f"{raw:.2f} ft", fg="#333")
                self._live_cal_lbl[a].config(text=f"{cal:.2f} ft", fg=ANCHOR_COLORS[a])
                self._cal_ld[a].set_data([raw],[cal])
            else:
                self._live_raw_lbl[a].config(text="---", fg="gray")
                self._live_cal_lbl[a].config(text="---", fg="gray")
                self._cal_ld[a].set_data([],[])
        self._cal_mpl.draw_idle()
        self.root.after(UPDATE_MS, self._cal_live_update)

    def _start_capture(self):
        if self.is_capturing: return
        try: n = int(self.num_samples_var.get())
        except: return
        true_dists={}
        for a in ["A0","A1","A2","A3"]:
            s=self.true_dist_vars[a].get().strip()
            if s=="": continue
            try: true_dists[a]=float(s)
            except:
                messagebox.showerror("Input Error",f"Bad true dist for {a}"); return
        if not true_dists:
            messagebox.showerror("Input Error","Enter at least one true distance."); return
        self.is_capturing=True
        self._btn_cap.config(state=tk.DISABLED, text="Capturing...")

        # show and reset progress bars for active anchors
        self._prog_frame.pack(fill=tk.X, pady=(2,4))
        for a in ["A0","A1","A2","A3"]:
            if a in true_dists:
                self._prog_bars[a]["maximum"] = n
                self._prog_bars[a]["value"]   = 0
                self._prog_labels[a].config(text=f"0/{n}")
                self._prog_bars[a].master.pack(fill=tk.X, padx=2, pady=1)
            else:
                self._prog_bars[a].master.pack_forget()

        self._capture_loop(true_dists, n, {a:[] for a in true_dists})

    def _capture_loop(self, true_dists, target, buf):
        tag=self.cal_tag_var.get(); all_done=True
        for a in true_dists:
            raw=tag_data[tag][a]
            if raw > 0:  # only collect valid (non ---) readings
                buf[a].append(raw)
            count = len(buf[a])
            # update progress bar
            self._prog_bars[a]["value"] = count
            self._prog_labels[a].config(text=f"{count}/{target}")
            if count < target: all_done=False
            if buf[a]: self._cal_cap[a].set_data(buf[a],[true_dists[a]]*len(buf[a]))
        self._cal_mpl.draw_idle()
        if not all_done:
            self.root.after(UPDATE_MS, self._capture_loop, true_dists, target, buf)
        else:
            self._btn_cap.config(text="Fusing...")
            self._animate_fusion(true_dists, buf, 0)

    def _animate_fusion(self, true_dists, buf, frame):
        means={a: sum(d)/len(d) for a,d in buf.items() if d}
        total=15
        if frame<=total:
            t=frame/float(total)
            for a,data in buf.items():
                m=means[a]
                self._cal_cap[a].set_data([x+(m-x)*t for x in data],[true_dists[a]]*len(data))
            self._cal_mpl.draw_idle()
            self.root.after(30, self._animate_fusion, true_dists, buf, frame+1)
        else:
            tag=self.cal_tag_var.get()
            for a,data in buf.items():
                if not data: continue
                self.cal_pts[tag][a].append((means[a], true_dists[a]))
                self._cal_cap[a].set_data([],[])
                self.true_dist_vars[a].set("")
            self._cal_mpl.draw_idle()
            self._recalc_all()
            self.is_capturing=False
            self._btn_cap.config(state=tk.NORMAL, text="Add Point")
            self._prog_frame.pack_forget()

    def _clear_cal(self):
        tag=self.cal_tag_var.get()
        for a in ["A0","A1","A2","A3"]:
            self.cal_pts[tag][a].clear()
            self.cal_func[tag][a]=lambda x: x
            self._cal_sc[a].set_data([],[])
            self._cal_fl[a].set_data([],[])
        self._cal_mpl.draw_idle()
        self._refresh_listbox()
        self._recalc_all()

    def _save_cal(self):
        # saves calibration equations to C:\RTLS\User_info, overwrites if same tag+timestamp file exists
        tag = self.cal_tag_var.get()
        save_dir = r"C:\RTLS\User_info"
        os.makedirs(save_dir, exist_ok=True)
        # use a fixed per-tag filename so it overwrites
        path = os.path.join(save_dir, f"cal_equations_{tag}.json")
        out = {}
        for a in ["A0","A1","A2","A3"]:
            mode = self.fit_mode_vars[a].get()
            try: pd = int(self.poly_deg_vars[a].get())
            except: pd = 4
            try: mp = int(self.ma_period_vars[a].get())
            except: mp = 4
            pts = self.cal_pts[tag][a]
            if len(pts) >= 2:
                X=np.array([p[0] for p in pts]); Y=np.array([p[1] for p in pts])
                _,eq = build_eval_func(mode,X,Y,pd,mp,self.ma_type_vars[a].get())
            elif len(pts) == 1:
                eq = f"Raw + {pts[0][1]-pts[0][0]:.5f}"
            else:
                eq = "Raw (no data)"
            out[a] = {"equation": eq, "mode": mode, "points": [[p[0],p[1]] for p in pts]}
        payload = {
            "tag": tag,
            "timestamp": datetime.now(EST).strftime("%Y%m%d_%H%M%S"),
            "matrix": {
                "anchors":   ["A0","A1","A2","A3"],
                "equations": [out[a]["equation"] for a in ["A0","A1","A2","A3"]]
            },
            "detail": out
        }
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        messagebox.showinfo("Saved", f"Calibration equations saved (overwritten):\n{path}")

    def _save_settings(self):
        save_dir = r"C:\RTLS\User_info"
        os.makedirs(save_dir, exist_ok=True)
        ts   = datetime.now(EST).strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            initialdir=save_dir,
            initialfile=f"rtls_settings_{ts}.json",
            defaultextension=".json",
            filetypes=[("JSON files","*.json"),("All files","*.*")],
            title="Save RTLS Settings"
        )
        if not path: return

        tag = self.cal_tag_var.get()
        cal_detail = {}
        for a in ["A0","A1","A2","A3"]:
            mode = self.fit_mode_vars[a].get()
            try: pd = int(self.poly_deg_vars[a].get())
            except: pd = 4
            try: mp = int(self.ma_period_vars[a].get())
            except: mp = 4
            pts = self.cal_pts[tag][a]
            if len(pts) >= 2:
                X=np.array([p[0] for p in pts]); Y=np.array([p[1] for p in pts])
                _,eq = build_eval_func(mode,X,Y,pd,mp,self.ma_type_vars[a].get())
            elif len(pts) == 1:
                eq = f"Raw + {pts[0][1]-pts[0][0]:.5f}"
            else:
                eq = "Raw (no data)"
            cal_detail[a] = {
                "equation":    eq,
                "mode":        mode,
                "poly_degree": pd,
                "ma_period":   mp,
                "ma_type":     self.ma_type_vars[a].get(),
                "preset":      self.preset_vars[a].get(),
                "points":      [[p[0],p[1]] for p in pts]
            }

        payload = {
            "timestamp":    ts,
            "active_tag":   tag,
            "anchor_layout": {
                "connection_order": self.anchor_order,
                "positions": {a: list(self.anchor_pos[a]) for a in self.anchor_pos}
            },
            "calibration": cal_detail
        }
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        messagebox.showinfo("Saved", f"Settings saved:\n{path}")

    def _load_settings(self):
        path = filedialog.askopenfilename(
            initialdir=r"C:\RTLS\User_info",
            filetypes=[("JSON files","*.json"),("All files","*.*")],
            title="Load RTLS Settings"
        )
        if not path: return
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Load Error", f"Could not read file:\n{e}"); return

        # anchor layout
        layout = data.get("anchor_layout", {})
        if "positions" in layout:
            for a, pos in layout["positions"].items():
                if a in self.anchor_pos:
                    self.anchor_pos[a] = list(pos)
        if "connection_order" in layout:
            self.anchor_order = layout["connection_order"]
            self._refresh_order_listbox()

        # calibration
        tag = data.get("active_tag", self.cal_tag_var.get())
        if tag in self.cal_pts:
            self.cal_tag_var.set(tag)
        cal = data.get("calibration", {})
        for a in ["A0","A1","A2","A3"]:
            if a not in cal: continue
            d = cal[a]
            if "mode"        in d: self.fit_mode_vars[a].set(d["mode"])
            if "poly_degree" in d: self.poly_deg_vars[a].set(str(d["poly_degree"]))
            if "ma_period"   in d: self.ma_period_vars[a].set(str(d["ma_period"]))
            if "ma_type"     in d: self.ma_type_vars[a].set(d["ma_type"])
            if "preset"      in d: self.preset_vars[a].set(bool(d["preset"]))
            if "points"      in d:
                self.cal_pts[tag][a] = [tuple(p) for p in d["points"]]

        self._recalc_all()
        self._reset_view()
        messagebox.showinfo("Loaded", f"Settings loaded from:\n{path}")

    # ──────────────────────────────────────
    # CLOSE
    # ──────────────────────────────────────
    def _on_close(self):
        try: plt.close('all')
        except: pass
        self.root.destroy()
        sys.exit(0)


# the entry point
if __name__ == "__main__":
    ble_thread = threading.Thread(target=run_ble_thread, daemon=True)
    ble_thread.start()

    root = tk.Tk()
    app  = App(root)
    root.mainloop()

###