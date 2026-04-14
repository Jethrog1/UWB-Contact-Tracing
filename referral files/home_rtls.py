import sys
import math
import threading
import time
import random
from collections import deque
from copy import deepcopy
import os
import csv
from datetime import datetime

import pytz

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QLabel, QPushButton, QFrame, QSizePolicy, QLineEdit,
    QScrollArea, QMenu, QTabBar, QTabWidget, QMessageBox, QStatusBar,
    QComboBox, QProgressBar, QCheckBox, QSlider, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt, QSize, QPointF, QRectF, QEvent, QTimer, QPoint
from PyQt6.QtGui import (
    QColor, QPalette, QPainter, QPen, QBrush, QFont, QWheelEvent,
    QMouseEvent, QKeyEvent, QFontMetrics, QCursor, QPixmap
)
import numpy as np
import warnings
try:
    from numpy.exceptions import RankWarning
except ImportError:
    from numpy import RankWarning
warnings.simplefilter('ignore', RankWarning)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import serial
import serial.tools.list_ports

# ── TAG MAC MAP ───────────────────────────────────────────────────────────────
TAG_MACS = {
    "T0": "DC:B4:D9:22:3B:B9",
    "T1": "DC:B4:D9:22:3A:55",
    "T2": "DC:B4:D9:31:8F:59"
}
MAC_TO_TAG = {v.lower(): k for k, v in TAG_MACS.items()}

tag_data   = {t: {"A0":-1,"A1":-1,"A2":-1,"A3":-1} for t in ["T0","T1","T2"]}
tag_status = {"T0":"Disconnected","T1":"Disconnected","T2":"Disconnected"}
_prev_tag_status = {"T0":"Disconnected","T1":"Disconnected","T2":"Disconnected"}

def parse_and_store(data_str):
    try:
        parts = [p.strip() for p in data_str.split('|')]
        if len(parts) >= 2:
            t_id = parts[0]
            if t_id in tag_data:
                for i in range(1, len(parts)):
                    p_clean = parts[i].replace(':', ' ').strip()
                    tokens = p_clean.split()
                    if len(tokens) >= 2:
                        a_id = tokens[0]
                        val_str = tokens[1]
                        if a_id in tag_data[t_id]:
                            if val_str in ["---", "--", "nan"]:
                                tag_data[t_id][a_id] = -1.0
                            else:
                                try:
                                    tag_data[t_id][a_id] = float(val_str)
                                except ValueError:
                                    tag_data[t_id][a_id] = -1.0
    except Exception:
        pass

def parse_dongle_status(line):
    if " -> " in line:
        line = line.split(" -> ", 1)[1]
    line = line.strip()

    if "[*] Attempting to connect to" in line:
        mac = line.split("to")[-1].strip().rstrip(".")
        tag = MAC_TO_TAG.get(mac.lower())
        if tag:
            tag_status[tag] = "Connecting..."
            parse_dongle_status._last_attempting = tag
        return

    if "[+] Connected to" in line:
        mac = line.split("to")[-1].strip().rstrip("!").rstrip(".")
        tag = MAC_TO_TAG.get(mac.lower())
        if tag:
            tag_status[tag] = "Connected"
            parse_dongle_status._last_attempting = None
        return

    if "[-]" in line:
        tag = getattr(parse_dongle_status, "_last_attempting", None)
        if tag:
            tag_status[tag] = "Disconnected"
            tag_data[tag] = {"A0": -1, "A1": -1, "A2": -1, "A3": -1}
            parse_dongle_status._last_attempting = None
        return

parse_dongle_status._last_attempting = None

# ── ESP32-C6 AUTO-DETECT ──────────────────────────────────────────────────────
ESP32_C6_IDENTIFIERS = [
    ("303a", "1001"),
    ("303a", "4001"),
    ("1a86", "55d4"),
    ("10c4", "ea60"),
    ("0403", "6001"),
]

def auto_detect_esp32_port():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        vid = f"{p.vid:04x}" if p.vid else ""
        pid = f"{p.pid:04x}" if p.pid else ""
        for ev, ep in ESP32_C6_IDENTIFIERS:
            if vid == ev and pid == ep:
                return p.device
        desc = (p.description or "").lower()
        if any(k in desc for k in ("esp32", "xiao", "ch343", "cp210", "ft232")):
            return p.device
    return None

# ── SERIAL STATE ──────────────────────────────────────────────────────────────
serial_port = None
serial_thread_running = False

def serial_reader_thread(port, baud=115200):
    global serial_port, serial_thread_running
    try:
        serial_port = serial.Serial(port, baud, timeout=1)
    except Exception:
        serial_thread_running = False
        return

    serial_thread_running = True
    while serial_thread_running:
        try:
            raw = serial_port.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            stripped = line
            if " -> " in line:
                stripped = line.split(" -> ", 1)[1].strip()
            if stripped and stripped[0] == "T" and "|" in stripped:
                parse_and_store(stripped)
            else:
                parse_dongle_status(line)
        except Exception:
            time.sleep(0.5)

    if serial_port and serial_port.is_open:
        serial_port.close()

def start_serial(port):
    global serial_thread_running
    stop_serial()
    t = threading.Thread(target=serial_reader_thread, args=(port,), daemon=True)
    t.start()

def stop_serial():
    global serial_thread_running, serial_port
    serial_thread_running = False
    if serial_port and serial_port.is_open:
        try:
            serial_port.close()
        except Exception:
            pass
    time.sleep(0.2)

# ── CSV LOGGING ───────────────────────────────────────────────────────────────
EST = pytz.timezone("America/New_York")
CSV_DIR  = r"C:\RTLS"
CSV_PATH = None
ROOM_ID  = "Room1"

def init_csv():
    global CSV_PATH
    os.makedirs(CSV_DIR, exist_ok=True)
    date_str  = datetime.now(EST).strftime("%Y%m%d")
    base_name = f"RTLS_{ROOM_ID}_{date_str}"
    suffix = ""; counter = 1
    while True:
        path = os.path.join(CSV_DIR, f"{base_name}{suffix}.csv")
        if not os.path.exists(path):
            CSV_PATH = path
            break
        suffix = f"({counter})"; counter += 1
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Tag1", "Tag2", "Distance_ft", "Delta_s"])

def write_csv_row(ts, t1, t2, dist, dt):
    if CSV_PATH is None:
        return
    try:
        with open(CSV_PATH, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([ts, t1, t2, f"{dist:.1f}ft", f"{dt:.2f}s"])
    except Exception:
        pass

def get_est_timestamp():
    now = datetime.now(EST)
    return now.strftime(f"{now.month}.{now.day}.{now.year} %H:%M:%S")

# ── colors ────────────────────────────────────────────────────────────────────
DARK_BG        = "#141414"
PANEL_BG       = "#1c1c1c"
SURFACE        = "#242424"
SURFACE2       = "#2a2a2a"
BORDER         = "#333333"
ACCENT         = "#00c8a0"
TEXT_PRIMARY   = "#e8e8e8"
TEXT_SECONDARY = "#888888"
TEXT_MUTED     = "#444444"
GRID_COLOR     = "#2a2a2a"

ANCHOR_COLORS = {"A0":"#e74c3c","A1":"#27ae60","A2":"#8e44ad","A3":"#f39c12"}
TAG_COLORS    = {"T0":"#3498db","T1":"#e67e22","T2":"#9b59b6"}

QSS = f"""
QMainWindow, QWidget {{
    background:{DARK_BG}; color:{TEXT_PRIMARY};
    font-family:"Segoe UI",sans-serif; font-size:13px;
}}
QFrame#mainPanel,QFrame#bottomPanel,QFrame#rightPanel {{
    background:{PANEL_BG}; border:1px solid {BORDER}; border-radius:0px;
}}
QFrame#sectionBox {{
    background:{SURFACE}; border:1px solid {BORDER}; border-radius:5px;
}}
QFrame#popupRight {{
    background:{PANEL_BG}; border-left:1px solid {BORDER};
}}
QFrame#popupBottom {{
    background:{SURFACE2}; border-top:1px solid {BORDER};
}}
QSplitter {{ background:{DARK_BG}; }}
QSplitter::handle {{ background:{BORDER}; }}
QSplitter::handle:hover {{ background:{ACCENT}; }}
QSplitter::handle:horizontal {{ width:4px; }}
QSplitter::handle:vertical   {{ height:4px; }}
QLabel#sectionTitle {{
    color:{ACCENT}; font-size:10px; font-weight:600; letter-spacing:2px;
}}
QLabel#panelTitle {{
    color:{TEXT_PRIMARY}; font-size:12px; font-weight:700; letter-spacing:1px;
    padding:6px 12px;
}}
QLabel#floatTitle {{
    color:{TEXT_PRIMARY}; font-size:15px; font-weight:700; background:transparent;
}}
QPushButton#hideBtn {{
    background:transparent; color:{TEXT_SECONDARY};
    border:1px solid {BORDER}; border-radius:4px;
    padding:3px 10px; font-size:11px; min-width:52px;
}}
QPushButton#hideBtn:hover {{ border-color:{ACCENT}; color:{ACCENT}; }}
QPushButton#resetBtn {{
    background:{SURFACE}; color:{TEXT_SECONDARY};
    border:1px solid {BORDER}; border-radius:4px;
    padding:3px 10px; font-size:11px;
}}
QPushButton#resetBtn:hover {{ border-color:{ACCENT}; color:{ACCENT}; }}
QPushButton#paramBtn {{
    background:{SURFACE}; color:{TEXT_SECONDARY};
    border:1px solid {BORDER}; border-radius:4px;
    padding:4px 8px; font-size:11px;
}}
QPushButton#paramBtn:hover {{ border-color:{ACCENT}; color:{ACCENT}; }}
QPushButton#deleteBtn {{
    background:transparent; color:#e74c3c;
    border:1px solid #5a2020; border-radius:4px;
    padding:3px 6px; font-size:10px;
}}
QPushButton#deleteBtn:hover {{ border-color:#e74c3c; background:#2a1010; }}
QPushButton#noticeClose {{
    background:transparent; color:#e74c3c;
    border:none; font-size:13px; font-weight:700;
    padding:0px 3px;
}}
QPushButton#noticeClose:hover {{ color:#ff2222; }}
QPushButton#anchorSelectBtn {{
    background:{SURFACE}; color:{TEXT_SECONDARY};
    border:1px solid {BORDER}; border-radius:4px;
    padding:4px 6px; font-size:11px; font-weight:600;
}}
QPushButton#anchorSelectBtn[selected="true"] {{
    background:{ACCENT}; color:#000; border-color:{ACCENT};
}}
QLineEdit {{
    background:{SURFACE}; color:{TEXT_PRIMARY};
    border:1px solid {BORDER}; border-radius:3px;
    padding:2px 6px; font-size:11px; font-family:"Consolas",monospace;
}}
QLineEdit:focus {{ border-color:{ACCENT}; }}
QFrame#hLine {{ background:{BORDER}; max-height:1px; border:none; }}
QScrollArea {{ border:none; background:transparent; }}
QScrollBar:vertical {{
    background:{SURFACE}; width:6px; border-radius:3px;
}}
QScrollBar::handle:vertical {{ background:{BORDER}; border-radius:3px; min-height:20px; }}
QScrollBar::handle:vertical:hover {{ background:{ACCENT}; }}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{ height:0px; }}
QTabWidget::pane {{ border:none; background:{PANEL_BG}; }}
QTabBar::tab {{
    background:{SURFACE}; color:{TEXT_SECONDARY};
    border:1px solid {BORDER}; border-bottom:none;
    padding:5px 14px; font-size:11px;
    border-radius:3px 3px 0 0; margin-right:2px;
}}
QTabBar::tab:selected {{ background:{PANEL_BG}; color:{TEXT_PRIMARY}; border-color:{ACCENT}; }}
QTabBar::tab:hover {{ color:{ACCENT}; }}

QLabel#calGraphTitle{{color:{TEXT_PRIMARY};font-size:10px;font-weight:600;letter-spacing:2px;}}
QPushButton#accentBtn{{
    background:{ACCENT};
    color:#000;
    border:1px solid {ACCENT};
    border-radius:3px;
    padding:5px 14px;
    font-size:11px;
    font-weight:600;
}}
QPushButton#accentBtn:hover{{
    background:{PANEL_BG};
    color:{ACCENT};
    border:1px solid {ACCENT};
    border-radius:3px;
    padding:5px 14px;
    font-size:11px;
    font-weight:600;
}}
QLineEdit#lockedEdit{{background:#1a2a1a;color:{ACCENT};border:1px solid {ACCENT};
    border-radius:3px;padding:2px 6px;font-size:11px;font-family:"Consolas",monospace;}}
"""

def h_line():
    f = QFrame(); f.setObjectName("hLine")
    f.setFrameShape(QFrame.Shape.HLine); return f

def section_label(text):
    l = QLabel(text); l.setObjectName("sectionTitle"); return l

def section_box():
    f = QFrame(); f.setObjectName("sectionBox"); return f

def _parse_coord(text):
    parts = [p.strip() for p in text.strip().split(",")]
    if len(parts) != 2:
        return False, 0, 0, f"Expected 'x, y' — got {len(parts)} value(s)."
    try:
        return True, float(parts[0]), float(parts[1]), ""
    except ValueError:
        bad = [p for p in parts if not _is_float(p)]
        return False, 0, 0, f"Non-numeric: '{', '.join(bad)}'"

def _is_float(s):
    try: float(s); return True
    except: return False

def build_eval_func(mode, X, Y, poly_deg=4, ma_period=4, ma_type="Trailing"):
    n = len(X)
    if n == 0: return lambda x: x, "Raw (no data)"
    try:
        if mode == "Linear":
            m, b = np.polyfit(X, Y, 1)
            return (lambda x, m=m, b=b: m*x+b), f"({m:.5f}*Raw)+{b:.5f}"
        elif mode == "Exponential":
            v = Y > 0
            if v.sum() > 1:
                b, la = np.polyfit(X[v], np.log(Y[v]), 1); a = np.exp(la)
                return (lambda x, a=a, b=b: a*np.exp(b*x)), f"{a:.5f}*e^({b:.5f}*Raw)"
        elif mode == "Polynomial":
            d = min(poly_deg, n-1); d = max(d, 1)
            c = np.polyfit(X, Y, d)
            def pf(c, d): return lambda x: sum(c[i]*(x**(d-i)) for i in range(d+1))
            terms = []
            for i, cv in enumerate(c):
                pw = d-i
                if pw > 1: terms.append(f"{cv:.4f}*Raw^{pw}")
                elif pw == 1: terms.append(f"{cv:.4f}*Raw")
                else: terms.append(f"{cv:.4f}")
            return pf(c, d), " + ".join(terms)
        elif mode == "Logarithmic":
            v = X > 0
            if v.sum() > 1:
                a, b = np.polyfit(np.log(X[v]), Y[v], 1)
                return (lambda x, a=a, b=b: a*np.log(x)+b if x > 0 else 0), f"{a:.5f}*ln(Raw)+{b:.5f}"
        elif mode == "Power Series":
            v = (X > 0) & (Y > 0)
            if v.sum() > 1:
                b, la = np.polyfit(np.log(X[v]), np.log(Y[v]), 1); a = np.exp(la)
                return (lambda x, a=a, b=b: a*(x**b) if x > 0 else 0), f"{a:.5f}*Raw^{b:.5f}"
        elif mode == "Moving Average":
            w = min(ma_period, n)
            pts = sorted(zip(X, Y))
            sX = np.array([p[0] for p in pts]); sY = np.array([p[1] for p in pts])
            mX, mY = [], []
            for i in range(len(sX)):
                if ma_type == "Trailing": s, e = max(0, i-w+1), i+1
                else:
                    h = w//2; s, e = max(0, i-h), min(len(sX), i+h+1)
                seg = sY[s:e]; mX.append(sX[i]); mY.append(seg.mean())
            if len(mX) > 1:
                return (lambda x, mx=mX, my=mY: float(np.interp(x, mx, my))), f"{ma_type} MA(period={w})"
    except Exception:
        pass
    if n >= 2:
        m, b = np.polyfit(X, Y, 1)
        return (lambda x, m=m, b=b: m*x+b), f"({m:.5f}*Raw)+{b:.5f}"
    return lambda x: x, "Raw"

# ── MULTI-LATERATION (2, 3, or 4 anchors) ────────────────────────────────────
def calc_pos(anchor_positions, distances_dict):
    valid = [(anchor_positions[a][0], anchor_positions[a][1], r)
             for a, r in distances_dict.items()
             if r > 0 and a in anchor_positions]
    if len(valid) < 2:
        return None, None

    if len(valid) == 2:
        x1, y1, r1 = valid[0]; x2, y2, r2 = valid[1]
        d = math.hypot(x2-x1, y2-y1)
        if d == 0:
            return None, None
        # Robust clamp — prevents frame drops on noisy measurements
        a = (r1**2 - r2**2 + d**2) / (2*d)
        a = max(-r1, min(r1, a))
        h2 = r1**2 - a**2
        h = math.sqrt(h2) if h2 > 0.0 else 0.0
        x3 = x1 + a*(x2-x1)/d; y3 = y1 + a*(y2-y1)/d
        ix1 = x3 + h*(y2-y1)/d; iy1 = y3 - h*(x2-x1)/d
        ix2 = x3 - h*(y2-y1)/d; iy2 = y3 + h*(x2-x1)/d
        # Pick intersection closest to centroid of all anchor positions
        cx = sum(p[0] for p in anchor_positions.values()) / len(anchor_positions)
        cy = sum(p[1] for p in anchor_positions.values()) / len(anchor_positions)
        if (ix1-cx)**2+(iy1-cy)**2 < (ix2-cx)**2+(iy2-cy)**2:
            return round(ix1, 3), round(iy1, 3)
        return round(ix2, 3), round(iy2, 3)

    # 3 or 4 anchors — Linear Least Squares
    x0, y0, r0 = valid[0]; A, B = [], []
    for xi, yi, ri in valid[1:]:
        A.append([2*(xi-x0), 2*(yi-y0)])
        B.append(r0**2 - ri**2 - x0**2 - y0**2 + xi**2 + yi**2)
    a11 = sum(row[0]**2 for row in A)
    a12 = sum(row[0]*row[1] for row in A)
    a22 = sum(row[1]**2 for row in A)
    b1  = sum(A[i][0]*B[i] for i in range(len(B)))
    b2  = sum(A[i][1]*B[i] for i in range(len(B)))
    det = a11*a22 - a12**2
    if abs(det) < 1e-6:
        return None, None
    return round((a22*b1 - a12*b2)/det, 3), round((-a12*b1 + a11*b2)/det, 3)

def _show_coord_error(parent, msg):
    mb = QMessageBox(parent)
    mb.setWindowTitle("Invalid Coordinates")
    mb.setText(f"Could not parse coordinates.\n\n{msg}\n\nExpected: x, y  (e.g. 5.0, 12.3)")
    mb.setIcon(QMessageBox.Icon.Warning)
    mb.setStyleSheet(f"background:{PANEL_BG}; color:{TEXT_PRIMARY};"); mb.exec()

def correct_slant_distance(slant_d, height_offset):
    """Convert UWB slant distance H to floor distance X: X = sqrt(H^2 - Y^2)"""
    if height_offset <= 0 or slant_d <= 0:
        return slant_d
    h2 = slant_d ** 2 - height_offset ** 2
    return math.sqrt(max(h2, 0.0001))

# ── undo/redo ─────────────────────────────────────────────────────────────────
class History:
    def __init__(self, maxlen=50):
        self._undo = deque(maxlen=maxlen); self._redo = deque(maxlen=maxlen)
    def push(self, state):
        self._undo.append(deepcopy(state)); self._redo.clear()
    def undo(self, cur):
        if not self._undo: return None
        self._redo.append(deepcopy(cur)); return deepcopy(self._undo.pop())
    def redo(self, cur):
        if not self._redo: return None
        self._undo.append(deepcopy(cur)); return deepcopy(self._redo.pop())

# ── inline coord editor ───────────────────────────────────────────────────────
class CoordEditor(QLineEdit):
    def __init__(self, parent, anchor_id, x, y, commit_cb, cancel_cb):
        super().__init__(parent)
        self.anchor_id = anchor_id; self.commit_cb = commit_cb; self.cancel_cb = cancel_cb
        self.setText(f"{x:.1f}, {y:.1f}"); self.setFixedWidth(120)
        self.setStyleSheet(f"background:{SURFACE};color:{TEXT_PRIMARY};"
                           f"border:1px solid {ACCENT};border-radius:3px;"
                           f"padding:2px 6px;font-size:11px;font-family:Consolas,monospace;")
        self.selectAll(); self.show(); self.setFocus()
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter): self._commit()
        elif e.key() == Qt.Key.Key_Escape: self.cancel_cb(); self.deleteLater()
        else: super().keyPressEvent(e)
    def focusOutEvent(self, e): self._commit(); super().focusOutEvent(e)
    def _commit(self):
        ok, nx, ny, err = _parse_coord(self.text())
        if not ok: _show_coord_error(self.parent(), err); self.deleteLater(); return
        self.commit_cb(self.anchor_id, nx, ny); self.deleteLater()

# ── map drawing ───────────────────────────────────────────────────────────────
def draw_map_scene(painter, w, h, scale, origin,
                   anchors, lines, anchor_r,
                   selected_line=None, hover_line=None,
                   rclick_anchor=None, hover_anchor=None,
                   mouse_screen=None, tag_raw=None, tag_cal=None,
                   ref_dot=None):
    p = painter
    p.fillRect(0, 0, w, h, QColor(DARK_BG))

    def ts(wx, wy): return QPointF(origin.x()+wx*scale, origin.y()-wy*scale)

    # grid
    wl=(0-origin.x())/scale; wr=(w-origin.x())/scale
    wt=(origin.y()-0)/scale;  wb=(origin.y()-h)/scale
    raw_step = max(w/scale,0.001)/8
    if raw_step <= 0: raw_step = 1
    mag = 10**math.floor(math.log10(raw_step))
    step = mag
    for s in [1,2,5,10]:
        if s*mag >= raw_step: step = s*mag; break
    x0 = math.floor(wl/step)*step; y0 = math.floor(wb/step)*step

    p.setPen(QPen(QColor(GRID_COLOR),1))
    gx=x0
    while gx<=wr+step:
        sx=origin.x()+gx*scale; p.drawLine(int(sx),0,int(sx),h); gx+=step
    gy=y0
    while gy<=wt+step:
        sy=origin.y()-gy*scale; p.drawLine(0,int(sy),w,int(sy)); gy+=step

    p.setPen(QPen(QColor("#383838"),1,Qt.PenStyle.DashLine))
    p.drawLine(int(origin.x()),0,int(origin.x()),h)
    p.drawLine(0,int(origin.y()),w,int(origin.y()))

    lsz=max(7,min(9,int(scale*0.12)))
    p.setFont(QFont("Segoe UI",lsz)); p.setPen(QColor(TEXT_MUTED))
    gx=x0
    while gx<=wr+step:
        if abs(gx)>0.001:
            sx=origin.x()+gx*scale
            if 10<sx<w-10: p.drawText(int(sx)+3,int(origin.y())-4,f"{gx:.0f}")
        gx+=step
    gy=y0
    while gy<=wt+step:
        if abs(gy)>0.001:
            sy=origin.y()-gy*scale
            if 10<sy<h-10: p.drawText(int(origin.x())+4,int(sy)-3,f"{gy:.0f}")
        gy+=step

    # lines
    lw = max(1.0, min(scale*0.04, 3.0))
    for (a,b) in lines:
        if a not in anchors or b not in anchors: continue
        ax,ay=anchors[a]; bx,by=anchors[b]
        sa=ts(ax,ay); sb=ts(bx,by)
        is_sel   = selected_line in ((a,b),(b,a))
        is_hover = hover_line    in ((a,b),(b,a))
        if is_sel:
            col,w2 = "#ff4444", lw*2.0
        elif is_hover:
            col,w2 = "#ffffff", lw*2.2
        else:
            col,w2 = "#cccccc", lw*1.0
        p.setPen(QPen(QColor(col), w2))
        p.drawLine(sa.toPoint(), sb.toPoint())
        dist=math.hypot(bx-ax,by-ay)
        mx=(sa.x()+sb.x())/2; my=(sa.y()+sb.y())/2
        p.setFont(QFont("Segoe UI",max(7,min(9,int(scale*0.10)))))
        p.setPen(QColor(TEXT_SECONDARY if not is_hover else TEXT_PRIMARY))
        p.drawText(int(mx)+4,int(my)-4,f"{dist:.1f} ft")

    # live line-draw preview
    if (rclick_anchor is not None and rclick_anchor in anchors
            and mouse_screen is not None):
        sp = ts(*anchors[rclick_anchor])
        if hover_anchor and hover_anchor != rclick_anchor and hover_anchor in anchors:
            end = ts(*anchors[hover_anchor])
        else:
            end = mouse_screen
        if math.hypot(end.x()-sp.x(), end.y()-sp.y()) > 5:
            p.setPen(QPen(QColor("white"), lw, Qt.PenStyle.DashLine))
            p.drawLine(int(sp.x()), int(sp.y()), int(end.x()), int(end.y()))

    # anchors
    r=anchor_r
    lsz2=max(8,min(11,int(scale*0.14))); csz=max(7,min(10,int(scale*0.11)))
    for aid,(wx,wy) in anchors.items():
        sp=ts(wx,wy); col=QColor(ANCHOR_COLORS.get(aid,"#fff"))
        if aid==rclick_anchor:
            p.setPen(QPen(col,2)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(sp,r+6,r+6)
        if aid==hover_anchor and rclick_anchor is not None and aid!=rclick_anchor:
            p.setPen(QPen(QColor("white"),2)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(sp,r+5,r+5)
        p.setPen(QPen(QColor("white"),max(1,int(lw*0.7)))); p.setBrush(QBrush(col))
        p.drawEllipse(sp,r,r)
        p.setFont(QFont("Segoe UI",lsz2,QFont.Weight.Bold)); p.setPen(col)
        p.drawText(int(sp.x())+r+4,int(sp.y())-2,aid)
        p.setFont(QFont("Segoe UI",csz)); p.setPen(QColor(TEXT_SECONDARY))
        p.drawText(int(sp.x())+r+4,int(sp.y())+csz+2,f"({wx:.1f}, {wy:.1f})")

    # reference calculator dot
    if ref_dot:
        rx, ry = ref_dot
        sp = ts(rx, ry)
        arm = 14
        p.setPen(QPen(QColor(ACCENT), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(int(sp.x()) - arm, int(sp.y()), int(sp.x()) + arm, int(sp.y()))
        p.drawLine(int(sp.x()), int(sp.y()) - arm, int(sp.x()), int(sp.y()) + arm)
        p.setPen(QPen(QColor(ACCENT), 1, Qt.PenStyle.DashLine))
        for (awx, awy) in anchors.values():
            asp = ts(awx, awy)
            floor_d = math.hypot(rx - awx, ry - awy)
            p.drawLine(int(sp.x()), int(sp.y()), int(asp.x()), int(asp.y()))
            mx = (sp.x() + asp.x()) / 2
            my = (sp.y() + asp.y()) / 2
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(QColor(ACCENT))
            p.drawText(int(mx) + 4, int(my) - 4, f"{floor_d:.2f} ft")
            p.setPen(QPen(QColor(ACCENT), 1, Qt.PenStyle.DashLine))
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(ACCENT))
        p.drawText(int(sp.x()) + arm + 4, int(sp.y()) - arm, f"({rx:.1f}, {ry:.1f})")

    # build tag_display — cal preferred, raw fallback
    tag_display = {}
    if tag_cal:
        for tid, pos in tag_cal.items():
            if pos is not None: tag_display[tid] = pos
    if tag_raw:
        for tid, pos in tag_raw.items():
            if tid not in tag_display and pos is not None:
                tag_display[tid] = pos

    # inter-tag distance lines
    tag_ids = list(tag_display.keys())
    for i in range(len(tag_ids)):
        for j in range(i + 1, len(tag_ids)):
            tid_a = tag_ids[i]; tid_b = tag_ids[j]
            pos_a = tag_display[tid_a]; pos_b = tag_display[tid_b]
            sa = ts(*pos_a); sb = ts(*pos_b)
            dist = math.hypot(pos_b[0] - pos_a[0], pos_b[1] - pos_a[1])
            pen = QPen(QColor("#e67e22"), max(1.0, lw * 0.8), Qt.PenStyle.DashLine)
            pen.setDashPattern([6, 4])
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(int(sa.x()), int(sa.y()), int(sb.x()), int(sb.y()))
            mx = (sa.x() + sb.x()) / 2; my = (sa.y() + sb.y()) / 2
            label = f"{dist:.2f} ft"
            p.setFont(QFont("Segoe UI", max(7, min(9, int(scale * 0.10))), QFont.Weight.Bold))
            fm = QFontMetrics(p.font())
            tw = fm.horizontalAdvance(label); th = fm.height()
            bg_rect = QRectF(mx - tw/2 - 3, my - th/2 - 2, tw + 6, th + 4)
            p.setBrush(QBrush(QColor(20, 20, 20, 210))); p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(bg_rect, 3, 3)
            p.setPen(QColor("#e67e22")); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawText(int(mx - tw/2), int(my + th/2 - 2), label)

    # tag dots
    for tid, pos in tag_display.items():
        sp = ts(*pos)
        col = QColor(TAG_COLORS.get(tid, "#fff"))
        tr = max(7, min(int(scale * 0.22), 14))
        p.setPen(QPen(QColor("white"), 1.5)); p.setBrush(QBrush(col))
        p.drawEllipse(sp, tr, tr)
        p.setFont(QFont("Segoe UI", max(7, lsz2 - 1), QFont.Weight.Bold)); p.setPen(col)
        p.drawText(int(sp.x()) + tr + 3, int(sp.y()) - 2, tid)

# ── map canvas ────────────────────────────────────────────────────────────────
class MapCanvas(QWidget):
    SNAP_PX = 20

    def __init__(self, right_panel_ref=None):
        super().__init__()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.right_panel_ref = right_panel_ref

        self.scale  = 30.0
        self.origin = QPointF(0,0)
        self._view_ok = False

        self.anchors = {"A0":[0.0,0.0],"A1":[0.0,10.0],"A2":[10.0,10.0],"A3":[10.0,0.0]}
        self.lines   = [("A0","A1"),("A1","A2"),("A2","A3"),("A3","A0")]
        self.tag_raw = {"T0":None,"T1":None,"T2":None}
        self.tag_cal = {"T0":None,"T1":None,"T2":None}

        self._history = History(); self._push_history()
        self._panning=False; self._pan_start=QPointF(); self._origin_start=QPointF()
        self._dragging_anchor=None; self._drag_offset=(0.0,0.0)
        self._rclick_anchor=None; self._hover_anchor=None
        self._mouse_screen=QPointF(0,0)
        self._selected_line=None; self._hover_line=None
        self._ext_hover_line=None
        self._ref_dot_mode = False
        self.ref_dot = None
        self._dragging_ref_dot = False
        self._ref_drag_offset = (0.0, 0.0)

    def _push_history(self):
        self._history.push({"anchors":deepcopy(self.anchors),"lines":list(self.lines)})

    def _restore(self, state):
        self.anchors=deepcopy(state["anchors"]); self.lines=list(state["lines"])
        self._notify_right(); self.update()

    def undo(self):
        s=self._history.undo({"anchors":deepcopy(self.anchors),"lines":list(self.lines)})
        if s: self._restore(s)
    def redo(self):
        s=self._history.redo({"anchors":deepcopy(self.anchors),"lines":list(self.lines)})
        if s: self._restore(s)

    def _anchor_r(self): return max(5,min(int(self.scale*0.25),18))

    def _center_on_anchors(self):
        if not self.anchors: return
        xs=[v[0] for v in self.anchors.values()]; ys=[v[1] for v in self.anchors.values()]
        cx=(min(xs)+max(xs))/2; cy=(min(ys)+max(ys))/2
        span=max(max(xs)-min(xs),max(ys)-min(ys),1)
        w=self.width() or 900; h=self.height() or 600
        self.scale=min(w,h)*0.45/span
        self.origin=QPointF(w/2-cx*self.scale,h/2+cy*self.scale)
        self._view_ok=True

    def reset_view(self): self._center_on_anchors(); self.update()
    def showEvent(self,e): super().showEvent(e); self._center_on_anchors() if not self._view_ok else None
    def resizeEvent(self,e): super().resizeEvent(e); self._center_on_anchors(); self.update()

    def to_screen(self,wx,wy): return QPointF(self.origin.x()+wx*self.scale,self.origin.y()-wy*self.scale)
    def to_world(self,sx,sy):  return ((sx-self.origin.x())/self.scale,(self.origin.y()-sy)/self.scale)

    def nearest_anchor(self, sx, sy, exclude=None):
        best,bd=None,float('inf')
        for aid,(wx,wy) in self.anchors.items():
            if aid==exclude: continue
            sp=self.to_screen(wx,wy); d=math.hypot(sx-sp.x(),sy-sp.y())
            if d<self.SNAP_PX and d<bd: best,bd=aid,d
        return best

    def hit_anchor(self,sx,sy,extra=0):
        r=self._anchor_r()+extra
        for aid,(wx,wy) in self.anchors.items():
            sp=self.to_screen(wx,wy)
            if math.hypot(sx-sp.x(),sy-sp.y())<=r: return aid
        return None

    def hit_label(self,sx,sy):
        fm=QFontMetrics(QFont("Segoe UI",9))
        for aid,(wx,wy) in self.anchors.items():
            sp=self.to_screen(wx,wy); r=self._anchor_r()
            text=f"{aid} ({wx:.1f}, {wy:.1f})"; tw=fm.horizontalAdvance(text)
            rect=QRectF(int(sp.x())+r+4,int(sp.y())-r-fm.ascent(),tw,fm.height()*2+4)
            if rect.contains(sx,sy): return aid
        return None

    def hit_line(self, sx, sy, thresh=8):
        for (a,b) in self.lines:
            if a not in self.anchors or b not in self.anchors: continue
            p1=self.to_screen(*self.anchors[a]); p2=self.to_screen(*self.anchors[b])
            dx,dy=p2.x()-p1.x(),p2.y()-p1.y(); length=math.hypot(dx,dy)
            if length<1: continue
            t=max(0.0,min(1.0,((sx-p1.x())*dx+(sy-p1.y())*dy)/(length*length)))
            px=p1.x()+t*dx; py=p1.y()+t*dy
            if math.hypot(sx-px,sy-py)<=thresh: return (a,b)
        return None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hl = self._ext_hover_line if self._ext_hover_line else self._hover_line
        draw_map_scene(
            p, self.width(), self.height(), self.scale, self.origin,
            self.anchors, self.lines, self._anchor_r(),
            selected_line=self._selected_line,
            hover_line=hl,
            rclick_anchor=self._rclick_anchor,
            hover_anchor=self._hover_anchor,
            mouse_screen=self._mouse_screen,
            tag_raw=self.tag_raw,
            tag_cal=self.tag_cal,
            ref_dot=self.ref_dot
        )
        p.end()

    def wheelEvent(self,e:QWheelEvent):
        mouse=e.position(); wx,wy=self.to_world(mouse.x(),mouse.y())
        f=1.15 if e.angleDelta().y()>0 else 1/1.15
        self.scale=max(1.0,self.scale*f)
        self.origin=QPointF(mouse.x()-wx*self.scale,mouse.y()+wy*self.scale); self.update()

    def mousePressEvent(self, e: QMouseEvent):
        sx, sy = e.position().x(), e.position().y()
        if e.button() == Qt.MouseButton.LeftButton:
            if self._ref_dot_mode:
                wx, wy = self.to_world(sx, sy)
                self.ref_dot = [round(wx, 2), round(wy, 2)]
                self._ref_dot_mode = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.update()
                if self.right_panel_ref:
                    self.right_panel_ref.on_ref_dot_placed(self.ref_dot)
                return
            if self.ref_dot is not None:
                sp = self.to_screen(*self.ref_dot)
                if math.hypot(sx - sp.x(), sy - sp.y()) <= 16:
                    self._dragging_ref_dot = True
                    self._ref_drag_offset = (sx - sp.x(), sy - sp.y())
                    return
            if self._rclick_anchor is not None:
                snap = self.nearest_anchor(sx, sy, exclude=self._rclick_anchor)
                if snap: self._finish_line(snap)
                else:    self._cancel_line_draw()
                return
            hit = self.hit_anchor(sx, sy)
            if hit:
                self._push_history()
                self._dragging_anchor = hit
                sp = self.to_screen(*self.anchors[hit])
                self._drag_offset = (sx - sp.x(), sy - sp.y())
                self._selected_line = None
            else:
                line = self.hit_line(sx, sy)
                if line:
                    self._selected_line = line
                    self._notify_right_line_select(line)
                else:
                    self._selected_line = None
                    self._panning = True
                    self._pan_start = e.position()
                    self._origin_start = QPointF(self.origin)
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
        elif e.button() == Qt.MouseButton.RightButton:
            if self._rclick_anchor is not None:
                snap = self.nearest_anchor(sx, sy, exclude=self._rclick_anchor)
                if snap: self._finish_line(snap)
                else:    self._cancel_line_draw()
                return
            hit = self.hit_anchor(sx, sy, extra=4)
            if hit:
                self._rclick_anchor = hit
                self._mouse_screen = e.position()
                self.update()
            else:
                line = self.hit_line(sx, sy)
                if line:
                    self._selected_line = line
                    self._show_line_menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e: QMouseEvent):
        sx, sy = e.position().x(), e.position().y()
        self._mouse_screen = e.position()
        if self._dragging_ref_dot and self.ref_dot is not None:
            wx = (sx - self._ref_drag_offset[0] - self.origin.x()) / self.scale
            wy = (self.origin.y() - (sy - self._ref_drag_offset[1])) / self.scale
            self.ref_dot = [round(wx, 2), round(wy, 2)]
            if self.right_panel_ref:
                self.right_panel_ref.on_ref_dot_placed(self.ref_dot)
            self.update()
            return
        if self._dragging_anchor:
            wx = (sx - self._drag_offset[0] - self.origin.x()) / self.scale
            wy = (self.origin.y() - (sy - self._drag_offset[1])) / self.scale
            self.anchors[self._dragging_anchor] = [round(wx, 2), round(wy, 2)]
            self._notify_right()
        elif self._panning:
            self.origin = self._origin_start + (e.position() - self._pan_start)
        excl = self._rclick_anchor
        prev_ha = self._hover_anchor
        self._hover_anchor = self.nearest_anchor(sx, sy, exclude=excl)
        prev_hl = self._hover_line
        if self._rclick_anchor is None:
            self._hover_line = self.hit_line(sx, sy)
        else:
            self._hover_line = None
        if (self._dragging_anchor or self._panning
                or self._hover_anchor != prev_ha
                or self._hover_line != prev_hl
                or self._rclick_anchor is not None):
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging_ref_dot = False
            self._dragging_anchor = None
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, e: QMouseEvent):
        sx, sy = e.position().x(), e.position().y()
        if self.ref_dot is not None:
            sp = self.to_screen(*self.ref_dot)
            if math.hypot(sx - sp.x(), sy - sp.y()) <= 20:
                ed = CoordEditor(self, "__ref_dot__",
                                 self.ref_dot[0], self.ref_dot[1],
                                 commit_cb=self._commit_ref_dot,
                                 cancel_cb=lambda: None)
                ed.move(int(sp.x()) + 16, int(sp.y()) - 10)
                return
            fm = QFontMetrics(QFont("Segoe UI", 8))
            label = f"({self.ref_dot[0]:.1f}, {self.ref_dot[1]:.1f})"
            lx = int(sp.x()) + 18; ly = int(sp.y()) - 14
            rect = QRectF(lx, ly - fm.ascent(), fm.horizontalAdvance(label), fm.height() + 4)
            if rect.contains(sx, sy):
                ed = CoordEditor(self, "__ref_dot__",
                                 self.ref_dot[0], self.ref_dot[1],
                                 commit_cb=self._commit_ref_dot,
                                 cancel_cb=lambda: None)
                ed.move(lx, ly)
                return
        hit = self.hit_anchor(sx, sy, extra=4) or self.hit_label(sx, sy)
        if hit:
            wx, wy = self.anchors[hit]
            sp = self.to_screen(wx, wy); r = self._anchor_r()
            ed = CoordEditor(self, hit, wx, wy,
                             commit_cb=self._commit_coord,
                             cancel_cb=lambda: None)
            ed.move(int(sp.x()) + r + 2, int(sp.y()) + 6)

    def keyPressEvent(self,e:QKeyEvent):
        ctrl=e.modifiers()==Qt.KeyboardModifier.ControlModifier
        if ctrl and e.key()==Qt.Key.Key_Z: self.undo(); return
        if ctrl and e.key()==Qt.Key.Key_Y: self.redo(); return
        if e.key()==Qt.Key.Key_Escape:
            self._cancel_line_draw(); self._selected_line=None
        elif e.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace):
            if self._selected_line:
                self._push_history(); a,b=self._selected_line
                self.lines=[l for l in self.lines if l not in ((a,b),(b,a))]
                self._selected_line=None; self._notify_right()
        self.update()

    def _finish_line(self,target):
        self._push_history(); a,b=self._rclick_anchor,target
        if (a,b) not in self.lines and (b,a) not in self.lines:
            self.lines.append((a,b)); self._notify_right()
        self._rclick_anchor=None; self._hover_anchor=None; self.update()

    def _cancel_line_draw(self):
        self._rclick_anchor=None; self._hover_anchor=None; self.update()

    def _commit_coord(self,aid,nx,ny):
        self._push_history(); self.anchors[aid]=[round(nx,2),round(ny,2)]
        self._notify_right(); self.update()

    def _show_line_menu(self,gpos):
        menu=QMenu(self)
        menu.setStyleSheet(f"QMenu{{background:{SURFACE};color:{TEXT_PRIMARY};border:1px solid {BORDER};}}"
                           f"QMenu::item:selected{{background:{ACCENT};color:#000;}}")
        da=menu.addAction("Delete Line"); act=menu.exec(gpos)
        if act==da and self._selected_line:
            self._push_history(); a,b=self._selected_line
            self.lines=[l for l in self.lines if l not in ((a,b),(b,a))]
            self._selected_line=None; self._notify_right(); self.update()

    def _notify_right(self):
        if self.right_panel_ref:
            self.right_panel_ref.refresh_map_params(self.anchors,self.lines)

    def _notify_right_line_select(self, line):
        if self.right_panel_ref:
            self.right_panel_ref.highlight_line_row(line)

    def set_ext_hover_line(self, line):
        self._ext_hover_line = line; self.update()

    def arm_ref_dot(self):
        self._ref_dot_mode = True
        self.setCursor(Qt.CursorShape.CrossCursor)

    def clear_ref_dot(self):
        self.ref_dot = None
        self.update()

    def _commit_ref_dot(self, dummy_id, nx, ny):
        self.ref_dot = [round(nx, 2), round(ny, 2)]
        self.update()
        if self.right_panel_ref:
            self.right_panel_ref.on_ref_dot_placed(self.ref_dot)

# ── main panel ────────────────────────────────────────────────────────────────
class MainPanel(QFrame):
    def __init__(self, right_panel_ref=None):
        super().__init__(); self.setObjectName("mainPanel")
        lay=QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        self.canvas=MapCanvas(right_panel_ref=right_panel_ref)
        lay.addWidget(self.canvas,stretch=1)
        self.title_label=QLabel("RTLS Calibration Software",self)
        self.title_label.setObjectName("floatTitle")
        self.title_label.setContentsMargins(12,8,12,8); self.title_label.adjustSize()
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.title_label.raise_()
        self.reset_btn=QPushButton("⌖ Reset View",self)
        self.reset_btn.setObjectName("resetBtn"); self.reset_btn.setFixedSize(QSize(100,28))
        self.reset_btn.clicked.connect(self.canvas.reset_view); self.reset_btn.raise_()

    def resizeEvent(self,e):
        super().resizeEvent(e)
        self.title_label.move(10,10)
        self.reset_btn.move(self.width()-self.reset_btn.width()-10,10)

# ── calibration graph ─────────────────────────────────────────────────────────
class BottomPanel(QFrame):
    HDR_H=34
    def __init__(self):
        super().__init__(); self.setObjectName("bottomPanel")
        lay=QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        self.hdr_w=QWidget(); self.hdr_w.setStyleSheet(f"background:{PANEL_BG};")
        self.hdr_w.setFixedHeight(self.HDR_H)
        hdr=QHBoxLayout(self.hdr_w); hdr.setContentsMargins(12,4,12,4)
        lbl=QLabel("CALIBRATION GRAPH"); lbl.setObjectName("calGraphTitle")
        hdr.addWidget(lbl); hdr.addStretch()
        self.hide_btn=QPushButton("Hide ∨"); self.hide_btn.setObjectName("hideBtn")
        self.hide_btn.setFixedSize(QSize(72,24)); hdr.addWidget(self.hide_btn)
        lay.addWidget(self.hdr_w); lay.addWidget(h_line())
        self.graph_body=QWidget()
        bl=QVBoxLayout(self.graph_body); bl.setContentsMargins(0,0,0,0)
        self.fig=Figure(facecolor=PANEL_BG,constrained_layout=True)
        self.ax=self.fig.add_subplot(111); self._style_ax()
        self._sc = {}
        self._fl = {}
        self._cap = {}
        for aid in ["A0", "A1", "A2", "A3"]:
            cp, = self.ax.plot([], [], 'o', color=ANCHOR_COLORS[aid],
                               markersize=3, alpha=0.4, zorder=3)
            self._cap[aid] = cp
        for aid in ["A0", "A1", "A2", "A3"]:
            sc, = self.ax.plot([], [], 'o', color=ANCHOR_COLORS[aid], markersize=5,
                               label=f"{aid} pts", zorder=5)
            fl, = self.ax.plot([], [], '-', color=ANCHOR_COLORS[aid], linewidth=1.5, zorder=4)
            self._sc[aid] = sc
            self._fl[aid] = fl
        self.ax.legend(loc="upper left", fontsize=8, facecolor=SURFACE,
                       edgecolor=BORDER, labelcolor=TEXT_SECONDARY)
        self.mpl_canvas=FigureCanvas(self.fig)
        self.mpl_canvas.setStyleSheet(f"background:{PANEL_BG};")
        self.mpl_canvas.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        bl.addWidget(self.mpl_canvas)
        self.mpl_canvas.mpl_connect('resize_event',lambda e:self.mpl_canvas.draw_idle())
        lay.addWidget(self.graph_body,stretch=1); self._graph_shown=True

    def _style_ax(self):
        self.ax.set_facecolor(DARK_BG); self.ax.tick_params(colors=TEXT_SECONDARY,labelsize=8)
        for sp in self.ax.spines.values(): sp.set_color(BORDER)
        self.ax.set_xlabel("Raw UWB (ft)",color=TEXT_SECONDARY,fontsize=9)
        self.ax.set_ylabel("Reference (ft)",color=TEXT_SECONDARY,fontsize=9)
        self.ax.grid(True,color=GRID_COLOR,linewidth=0.8); self.fig.patch.set_facecolor(PANEL_BG)
        self.ax.set_xlim(0, 30); self.ax.set_ylim(0, 30)
    def set_graph_visible(self,v):
        self._graph_shown=v; self.graph_body.setVisible(v)
        self.hide_btn.setText("Hide ∨" if v else "Show ∧")

# ── floating ghost label ──────────────────────────────────────────────────────
class DragGhost(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        lay=QHBoxLayout(self); lay.setContentsMargins(8,4,8,4)
        lbl=QLabel(text)
        lbl.setStyleSheet(f"background:{SURFACE};color:{TEXT_PRIMARY};"
                          f"border:1px solid {ACCENT};border-radius:4px;"
                          f"padding:4px 10px;font-size:12px;")
        lay.addWidget(lbl); self.adjustSize()

# ── detachable tab widget ─────────────────────────────────────────────────────
class DetachableTabWidget(QTabWidget):
    DRAG_THRESHOLD = 15

    def __init__(self, get_data_cb, register_popup_cb, parent=None):
        super().__init__(parent)
        self.get_data_cb       = get_data_cb
        self.register_popup_cb = register_popup_cb
        self._drag_tab    = -1
        self._drag_origin = None
        self._ghost       = None
        self._dragging    = False
        self.tabBar().setMouseTracking(True)
        self.tabBar().installEventFilter(self)

    def eventFilter(self, obj, e):
        if obj is not self.tabBar(): return super().eventFilter(obj,e)
        if e.type()==QEvent.Type.MouseButtonPress and e.button()==Qt.MouseButton.LeftButton:
            self._drag_tab    = self.tabBar().tabAt(e.position().toPoint())
            self._drag_origin = e.globalPosition().toPoint()
            self._dragging    = False
            if self._ghost: self._ghost.hide(); self._ghost=None
        elif e.type()==QEvent.Type.MouseMove and self._drag_tab>=0 and self._drag_origin:
            delta = e.globalPosition().toPoint()-self._drag_origin
            if (not self._dragging and (abs(delta.x())+abs(delta.y())) > self.DRAG_THRESHOLD):
                self._dragging = True
                text = self.tabText(self._drag_tab).strip()
                self._ghost = DragGhost(f"  {text}  "); self._ghost.show()
            if self._dragging and self._ghost:
                self._ghost.move(e.globalPosition().toPoint()+QPoint(12,12))
        elif e.type()==QEvent.Type.MouseButtonRelease and e.button()==Qt.MouseButton.LeftButton:
            if self._dragging and self._drag_tab>=0:
                tid = self.tabText(self._drag_tab).strip()
                data = self.get_data_cb(tid)
                if data:
                    popup = TagPopup(tid, data["anchors"], data["lines"],
                                     data["raw_pos"], data["cal_pos"],
                                     data["anchor_raws"], data["anchor_cals"])
                    popup.show()
                    popup.move(e.globalPosition().toPoint()-QPoint(450,30))
                    self.register_popup_cb(tid, popup)
            if self._ghost: self._ghost.hide(); self._ghost=None
            self._drag_tab=-1; self._drag_origin=None; self._dragging=False
        return super().eventFilter(obj,e)

# ── floating notice banner ────────────────────────────────────────────────────
class NoticeBanner(QWidget):
    def __init__(self, text, color, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:rgba(10,10,10,210);border-radius:5px;")
        lay=QHBoxLayout(self); lay.setContentsMargins(10,5,6,5); lay.setSpacing(8)
        icon=QLabel("●"); icon.setStyleSheet(f"color:{color};font-size:14px;background:transparent;")
        msg=QLabel(text); msg.setStyleSheet(f"color:{color};font-size:11px;font-weight:600;background:transparent;")
        close=QPushButton("✕"); close.setObjectName("noticeClose"); close.setFixedSize(QSize(22,22))
        close.clicked.connect(self.hide)
        lay.addWidget(icon); lay.addWidget(msg); lay.addStretch(); lay.addWidget(close)
        self.adjustSize(); self.hide()

    def show_at(self, x, y):
        self.adjustSize(); self.move(x,y); self.show()
        QTimer.singleShot(6000, self.hide)

# ── detached tag popup ────────────────────────────────────────────────────────
class TagPopup(QWidget):
    def __init__(self, tag_id, anchors_snap, lines_snap,
                 raw_pos, cal_pos, anchor_raws=None, anchor_cals=None):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle(f"Tag {tag_id} — Detached View")
        self.resize(1000,660); self.setMinimumSize(700,450); self.setStyleSheet(QSS)
        self.tag_id          = tag_id
        self.anchors_snapshot= deepcopy(anchors_snap)
        self.lines_snapshot  = list(lines_snap)
        self.raw_pos=raw_pos; self.cal_pos=cal_pos
        self.anchor_raws=anchor_raws or {}; self.anchor_cals=anchor_cals or {}
        self._coord_changed=False

        main_lay=QHBoxLayout(self); main_lay.setContentsMargins(0,0,0,0); main_lay.setSpacing(0)
        left_wrap=QWidget(); lw_lay=QVBoxLayout(left_wrap)
        lw_lay.setContentsMargins(0,0,0,0); lw_lay.setSpacing(0)
        self.map_widget=QWidget()
        self.map_widget.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        lw_lay.addWidget(self.map_widget,stretch=1)
        bot_bar=QFrame(); bot_bar.setObjectName("popupBottom"); bot_bar.setFixedHeight(28)
        lw_lay.addWidget(bot_bar)
        main_lay.addWidget(left_wrap,stretch=3)

        right=QFrame(); right.setObjectName("popupRight"); right.setFixedWidth(270)
        rl=QVBoxLayout(right); rl.setContentsMargins(12,12,12,12); rl.setSpacing(8)
        rl.addWidget(section_label("DATA")); rl.addWidget(h_line())
        hdr_row=QHBoxLayout(); hdr_row.addWidget(QLabel(""))
        rh=QLabel("RAW"); rh.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rh.setStyleSheet(f"color:{ACCENT};font-size:10px;font-weight:600;letter-spacing:1px;")
        ch=QLabel("CAL"); ch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ch.setStyleSheet(f"color:{ACCENT};font-size:10px;font-weight:600;letter-spacing:1px;")
        hdr_row.addWidget(rh,stretch=1); hdr_row.addWidget(ch,stretch=1)
        rl.addLayout(hdr_row); rl.addWidget(h_line())
        self._popup_vals={}
        for aid in ["A0","A1","A2","A3"]:
            arow=QHBoxLayout(); arow.setSpacing(4)
            dot=QLabel("●"); dot.setStyleSheet(f"color:{ANCHOR_COLORS[aid]};font-size:11px;"); dot.setFixedWidth(14)
            albl=QLabel(aid); albl.setStyleSheet(f"color:{ANCHOR_COLORS[aid]};font-size:10px;font-weight:600;"); albl.setFixedWidth(22)
            rv=QLabel("---"); rv.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rv.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:10px;font-family:Consolas;")
            cv=QLabel("---"); cv.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cv.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:10px;font-family:Consolas;")
            arow.addWidget(dot); arow.addWidget(albl); arow.addWidget(rv,stretch=1); arow.addWidget(cv,stretch=1)
            rl.addLayout(arow)
            self._popup_vals[f"{aid}_raw"]=rv; self._popup_vals[f"{aid}_cal"]=cv
        rl.addWidget(h_line())
        xy_row=QHBoxLayout(); xy_row.setSpacing(6)
        for key,title,val in [
            ("raw_xy","✛ RAW X,Y", f"{raw_pos[0]:.2f}, {raw_pos[1]:.2f}" if raw_pos else "---, ---"),
            ("cal_xy","✛ CAL X,Y", f"{cal_pos[0]:.2f}, {cal_pos[1]:.2f}" if cal_pos else "---, ---"),
        ]:
            f=QFrame(); f.setStyleSheet(f"background:{SURFACE};border-radius:3px;border:1px solid {BORDER};")
            fl=QVBoxLayout(f); fl.setContentsMargins(6,4,6,4); fl.setSpacing(2)
            tl=QLabel(title); tl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:9px;letter-spacing:1px;")
            vl=QLabel(val);   vl.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:10px;font-family:Consolas;font-weight:600;")
            fl.addWidget(tl); fl.addWidget(vl)
            xy_row.addWidget(f,stretch=1); self._popup_vals[key]=vl
        rl.addLayout(xy_row)
        rv_btn=QPushButton("⌖ Reset View"); rv_btn.setObjectName("resetBtn")
        rv_btn.clicked.connect(self._center_map); rl.addWidget(rv_btn)
        rl.addStretch()
        main_lay.addWidget(right)
        for aid in ["A0","A1","A2","A3"]:
            r=self.anchor_raws.get(aid,-1); c=self.anchor_cals.get(aid,-1)
            self._popup_vals[f"{aid}_raw"].setText("---" if r<0 else f"{r:.2f}")
            self._popup_vals[f"{aid}_cal"].setText("---" if c<0 else f"{c:.2f}")
        self._notice_coord=NoticeBanner("Anchor coordinates changed in main software","#ff4444",self.map_widget)
        self._notice_conn =NoticeBanner(f"Tag {tag_id} Connected","#00c8a0",self.map_widget)
        self._notice_disc =NoticeBanner(f"Tag {tag_id} Disconnected","#e74c3c",self.map_widget)
        self._scale=30.0; self._origin=QPointF(0,0); self._view_ok=False
        self._panning=False; self._pan_start=QPointF(); self._origin_start=QPointF()
        self.map_widget.installEventFilter(self); self.map_widget.setMouseTracking(True)

    def notify_coord_changed(self):
        self._coord_changed=True; self._notice_coord.show_at(10,10)
    def notify_connected(self):    self._notice_conn.show_at(10,10)
    def notify_disconnected(self): self._notice_disc.show_at(10,10)

    def _center_map(self):
        if not self.anchors_snapshot: return
        xs=[v[0] for v in self.anchors_snapshot.values()]; ys=[v[1] for v in self.anchors_snapshot.values()]
        cx=(min(xs)+max(xs))/2; cy=(min(ys)+max(ys))/2
        span=max(max(xs)-min(xs),max(ys)-min(ys),1)
        w=self.map_widget.width() or 700; h=self.map_widget.height() or 450
        self._scale=min(w,h)*0.45/span
        self._origin=QPointF(w/2-cx*self._scale,h/2+cy*self._scale)
        self._view_ok=True; self.map_widget.update()

    def _position_notices(self):
        self._notice_coord.move(10,10); self._notice_conn.move(10,10); self._notice_disc.move(10,10)

    def eventFilter(self,obj,e):
        if obj==self.map_widget:
            if e.type()==QEvent.Type.Paint:
                if not self._view_ok: self._center_map()
                p=QPainter(self.map_widget); p.setRenderHint(QPainter.RenderHint.Antialiasing)
                raw={self.tag_id:self.raw_pos} if self.raw_pos else {}
                cal={self.tag_id:self.cal_pos} if self.cal_pos else {}
                draw_map_scene(p,self.map_widget.width(),self.map_widget.height(),
                               self._scale,self._origin,self.anchors_snapshot,self.lines_snapshot,
                               max(5,min(int(self._scale*0.25),18)),tag_raw=raw,tag_cal=cal)
                p.end(); return True
            elif e.type()==QEvent.Type.Resize:
                self._center_map(); self._position_notices()
            elif e.type()==QEvent.Type.Wheel:
                mouse=e.position()
                wx=(mouse.x()-self._origin.x())/self._scale
                wy=(self._origin.y()-mouse.y())/self._scale
                f=1.15 if e.angleDelta().y()>0 else 1/1.15
                self._scale=max(1.0,self._scale*f)
                self._origin=QPointF(mouse.x()-wx*self._scale,mouse.y()+wy*self._scale)
                self.map_widget.update(); return True
            elif e.type()==QEvent.Type.MouseButtonPress:
                if e.button()==Qt.MouseButton.LeftButton:
                    self._panning=True; self._pan_start=e.position()
                    self._origin_start=QPointF(self._origin)
            elif e.type()==QEvent.Type.MouseMove:
                if self._panning:
                    self._origin=self._origin_start+(e.position()-self._pan_start)
                    self.map_widget.update()
            elif e.type()==QEvent.Type.MouseButtonRelease:
                self._panning=False
        return super().eventFilter(obj,e)

# ── line row widget ───────────────────────────────────────────────────────────
class LineRow(QWidget):
    def __init__(self, a, b, canvas_ref, delete_cb, parent=None):
        super().__init__(parent)
        self.a=a; self.b=b; self.canvas_ref=canvas_ref; self.delete_cb=delete_cb
        self.setStyleSheet(f"background:{SURFACE};border-radius:3px;")
        self.setMouseTracking(True)
        lay=QHBoxLayout(self); lay.setContentsMargins(6,3,6,3); lay.setSpacing(4)
        ca=QLabel("●"); ca.setStyleSheet(f"color:{ANCHOR_COLORS.get(a,'#fff')};font-size:11px;")
        cb=QLabel("●"); cb.setStyleSheet(f"color:{ANCHOR_COLORS.get(b,'#fff')};font-size:11px;")
        lbl=QLabel(f"{a} → {b}"); lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        db=QPushButton("✕"); db.setObjectName("deleteBtn"); db.setFixedSize(QSize(22,20))
        db.clicked.connect(lambda:self.delete_cb(a,b))
        lay.addWidget(ca); lay.addWidget(cb); lay.addWidget(lbl); lay.addStretch(); lay.addWidget(db)

    def enterEvent(self,e):
        if self.canvas_ref: self.canvas_ref.set_ext_hover_line((self.a,self.b))
        self.setStyleSheet(f"background:{SURFACE2};border-radius:3px;border:1px solid {BORDER};")
        super().enterEvent(e)

    def leaveEvent(self,e):
        if self.canvas_ref: self.canvas_ref.set_ext_hover_line(None)
        self.setStyleSheet(f"background:{SURFACE};border-radius:3px;")
        super().leaveEvent(e)

    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton and self.canvas_ref:
            self.canvas_ref._selected_line=(self.a,self.b); self.canvas_ref.update()
        super().mousePressEvent(e)

# ── right panel ───────────────────────────────────────────────────────────────
class RightPanel(QFrame):
    def __init__(self):
        super().__init__(); self.setObjectName("rightPanel")
        self.canvas_ref=None; self._popups={}

        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        tb=QWidget(); tb.setStyleSheet(f"background:{SURFACE2};"); tb.setFixedHeight(40)
        tbl=QHBoxLayout(tb); tbl.setContentsMargins(12,0,12,0)
        pt=QLabel("Control's Panel"); pt.setObjectName("panelTitle"); tbl.addWidget(pt)
        outer.addWidget(tb)

        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content=QWidget(); content.setStyleSheet(f"background:{PANEL_BG};")
        self.lay=QVBoxLayout(content); self.lay.setContentsMargins(10,10,10,10); self.lay.setSpacing(8)
        scroll.setWidget(content)

        # ── COM PORT ──────────────────────────────────────
        com_box = section_box()
        comi = QVBoxLayout(com_box); comi.setContentsMargins(10,8,10,8); comi.setSpacing(6)
        comi.addWidget(section_label("COM PORT")); comi.addWidget(h_line())

        self._com_port_var = ""
        self._user_overrode_port = False

        com_row = QHBoxLayout(); com_row.setSpacing(4)
        self._com_dropdown = QComboBox()
        self._com_dropdown.setStyleSheet(
            f"QComboBox{{background:{SURFACE};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
            f"border-radius:3px;padding:2px 6px;font-size:11px;}}"
            f"QComboBox::drop-down{{border:none;}}"
            f"QComboBox QAbstractItemView{{background:{SURFACE};color:{TEXT_PRIMARY};border:1px solid {BORDER};}}")
        self._com_dropdown.setFixedWidth(100)
        self._com_dropdown.activated.connect(self._on_user_select_port)
        com_row.addWidget(self._com_dropdown)

        refresh_btn = QPushButton("↺ Refresh"); refresh_btn.setObjectName("paramBtn")
        refresh_btn.clicked.connect(self.refresh_com_ports)
        com_row.addWidget(refresh_btn)

        disc_btn = QPushButton("Disconnect"); disc_btn.setObjectName("deleteBtn")
        disc_btn.clicked.connect(self.disconnect_com_port)
        com_row.addWidget(disc_btn)
        comi.addLayout(com_row)

        self._com_status_lbl = QLabel("Scanning...", )
        self._com_status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:9px;")
        comi.addWidget(self._com_status_lbl)
        self.lay.addWidget(com_box)

        # ── CONNECTIVITY ──────────────────────────────────
        ble_box=section_box(); bi=QVBoxLayout(ble_box); bi.setContentsMargins(10,8,10,8); bi.setSpacing(6)
        bi.addWidget(section_label("CONNECTIVITY")); bi.addWidget(h_line())
        self._ble_labels={}
        for tid in ["T0","T1","T2"]:
            row=QHBoxLayout(); row.setSpacing(8)
            dot=QLabel("●"); dot.setFixedWidth(16); dot.setStyleSheet(f"color:{TEXT_MUTED};font-size:14px;")
            nm=QLabel(tid); nm.setStyleSheet(f"color:{TAG_COLORS[tid]};font-weight:600;font-size:11px;"); nm.setFixedWidth(26)
            st=QLabel("Disconnected"); st.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
            row.addWidget(dot); row.addWidget(nm); row.addWidget(st); row.addStretch()
            bi.addLayout(row); self._ble_labels[tid]={"dot":dot,"status":st}
        self.lay.addWidget(ble_box)

        # ── MAP PARAMETERS ────────────────────────────────
        mp_box = section_box()
        mi = QVBoxLayout(mp_box); mi.setContentsMargins(10, 8, 10, 8); mi.setSpacing(6)
        mi.addWidget(section_label("MAP PARAMETERS")); mi.addWidget(h_line())
        self.anchor_edits = {}
        for aid in ["A0", "A1", "A2", "A3"]:
            row = QHBoxLayout(); row.setSpacing(6)
            dot = QLabel("●"); dot.setStyleSheet(f"color:{ANCHOR_COLORS[aid]};font-size:13px;"); dot.setFixedWidth(16)
            id_lbl = QLabel(aid); id_lbl.setStyleSheet(f"color:{ANCHOR_COLORS[aid]};font-weight:600;font-size:11px;"); id_lbl.setFixedWidth(26)
            edit = QLineEdit("0.0, 0.0"); edit.setFixedHeight(24)
            edit.returnPressed.connect(lambda a=aid, e=edit: self._commit_anchor(a, e))
            edit.editingFinished.connect(lambda a=aid, e=edit: self._commit_anchor(a, e))
            row.addWidget(dot); row.addWidget(id_lbl); row.addWidget(edit, stretch=1)
            self.anchor_edits[aid] = edit; mi.addLayout(row)
        mi.addSpacing(4)
        ll = QLabel("LINES"); ll.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;letter-spacing:1px;")
        mi.addWidget(ll)
        self.lines_container = QVBoxLayout(); self.lines_container.setSpacing(3)
        mi.addLayout(self.lines_container)
        self.add_line_btn = QPushButton("+ Add Line"); self.add_line_btn.setObjectName("paramBtn")
        self.add_line_btn.clicked.connect(self._show_picker); mi.addWidget(self.add_line_btn)
        self._picker = QWidget(); self._picker.setStyleSheet(f"background:{SURFACE};border-radius:4px;")
        pk = QVBoxLayout(self._picker); pk.setContentsMargins(6, 6, 6, 6); pk.setSpacing(4)
        pk.addWidget(QLabel("Select two anchors:"))
        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        self._picker_btns = {}; self._picker_sel = []
        for aid in ["A0", "A1", "A2", "A3"]:
            btn = QPushButton(aid); btn.setObjectName("anchorSelectBtn")
            btn.setProperty("selected", "false"); btn.setFixedHeight(28)
            btn.clicked.connect(lambda c, a=aid: self._picker_click(a))
            btn_row.addWidget(btn); self._picker_btns[aid] = btn
        pk.addLayout(btn_row)
        cpk = QPushButton("Esc / Cancel"); cpk.setObjectName("hideBtn"); cpk.clicked.connect(self._cancel_picker)
        pk.addWidget(cpk); self._picker.hide(); mi.addWidget(self._picker)
        mi.addSpacing(6); mi.addWidget(h_line())
        height_row = QHBoxLayout(); height_row.setSpacing(6)
        ht_icon = QLabel("↕"); ht_icon.setStyleSheet(f"color:{ACCENT};font-size:13px;font-weight:700;"); ht_icon.setFixedWidth(16)
        ht_lbl = QLabel("Anchor to Tag height (ft):"); ht_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;font-weight:600;")
        self._height_offset_edit = QLineEdit("0.0"); self._height_offset_edit.setFixedHeight(24)
        self._height_offset_edit.setPlaceholderText("0.0")
        self._height_offset_edit.setToolTip(
            "Vertical distance Y between anchors and tag (ft).\n"
            "UWB measures slant H. RTLS uses floor distance X = sqrt(H²-Y²).")
        height_row.addWidget(ht_icon); height_row.addWidget(ht_lbl); height_row.addWidget(self._height_offset_edit, stretch=1)
        mi.addLayout(height_row)
        self.lay.addWidget(mp_box)

        # ── DATA ─────────────────────────────────────────
        data_box=section_box(); di=QVBoxLayout(data_box); di.setContentsMargins(10,8,10,8); di.setSpacing(6)
        di.addWidget(section_label("DATA")); di.addWidget(h_line())
        self.data_tabs=DetachableTabWidget(get_data_cb=self._get_popup_data,
                                            register_popup_cb=self._register_popup,parent=self)
        self.data_tabs.setMinimumHeight(260); di.addWidget(self.data_tabs)
        self._data_labels={}
        for tid in ["T0","T1","T2"]:
            tab=QWidget(); tab.setStyleSheet(f"background:{PANEL_BG};")
            tl=QVBoxLayout(tab); tl.setContentsMargins(4,6,4,6); tl.setSpacing(4)
            hdr_row=QHBoxLayout(); hdr_row.addWidget(QLabel(""))
            for htxt in ["RAW","CALIBRATED"]:
                hl2=QLabel(htxt); hl2.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hl2.setStyleSheet(f"color:{ACCENT};font-size:10px;font-weight:600;letter-spacing:1px;")
                hdr_row.addWidget(hl2,stretch=1)
            tl.addLayout(hdr_row); tl.addWidget(h_line())
            lbls={}
            for aid in ["A0","A1","A2","A3"]:
                arow=QHBoxLayout(); arow.setSpacing(4)
                adot=QLabel("●"); adot.setStyleSheet(f"color:{ANCHOR_COLORS[aid]};font-size:11px;"); adot.setFixedWidth(14)
                albl=QLabel(aid); albl.setStyleSheet(f"color:{ANCHOR_COLORS[aid]};font-size:10px;font-weight:600;"); albl.setFixedWidth(22)
                rv=QLabel("---"); rv.setAlignment(Qt.AlignmentFlag.AlignCenter)
                rv.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:10px;font-family:Consolas;")
                cv=QLabel("---"); cv.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cv.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:10px;font-family:Consolas;")
                arow.addWidget(adot); arow.addWidget(albl); arow.addWidget(rv,stretch=1); arow.addWidget(cv,stretch=1)
                tl.addLayout(arow); lbls[f"{aid}_raw"]=rv; lbls[f"{aid}_cal"]=cv
            tl.addWidget(h_line())
            xy_row=QHBoxLayout(); xy_row.setSpacing(6)
            for key,title in [("raw_xy","✛ RAW X,Y"),("cal_xy","✛ CAL X,Y")]:
                f2=QFrame(); f2.setStyleSheet(f"background:{SURFACE};border-radius:3px;border:1px solid {BORDER};")
                fl=QVBoxLayout(f2); fl.setContentsMargins(6,4,6,4); fl.setSpacing(2)
                tl2=QLabel(title); tl2.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:9px;letter-spacing:1px;")
                vl=QLabel("---, ---"); vl.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:10px;font-family:Consolas;font-weight:600;")
                fl.addWidget(tl2); fl.addWidget(vl); xy_row.addWidget(f2,stretch=1); lbls[key]=vl
            tl.addLayout(xy_row)
            hint=QLabel("Drag tab to detach"); hint.setStyleSheet(f"color:{TEXT_MUTED};font-size:9px;font-style:italic;")
            hint.setAlignment(Qt.AlignmentFlag.AlignRight); tl.addWidget(hint)
            self.data_tabs.addTab(tab,f" {tid} "); self._data_labels[tid]=lbls
        self.lay.addWidget(data_box)

        # ── REFERENCE DISTANCE ────────────────────────────────────────────────
        ref_box = section_box()
        ri = QVBoxLayout(ref_box); ri.setContentsMargins(10,8,10,8); ri.setSpacing(6)
        ri.addWidget(section_label("REFERENCE DISTANCE")); ri.addWidget(h_line())
        self.ref_tabs = QTabWidget(); self.ref_tabs.setMinimumHeight(240)
        self._ref_dist_edits = {}
        self._ref_height_edits = {}

        for tid in ["T0","T1","T2"]:
            tab = QWidget(); tab.setStyleSheet(f"background:{PANEL_BG};")
            tl = QVBoxLayout(tab); tl.setContentsMargins(4,6,4,6); tl.setSpacing(4)
            DOT_W = 14; AID_W = 24
            hdr_row = QHBoxLayout(); hdr_row.setSpacing(4); hdr_row.setContentsMargins(0,0,0,0)
            sp_w = QWidget(); sp_w.setFixedWidth(DOT_W+AID_W+8); hdr_row.addWidget(sp_w)
            dh = QLabel("Distance (X) ft"); dh.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dh.setStyleSheet(f"color:{ACCENT};font-size:10px;font-weight:600;letter-spacing:1px;")
            hdr_row.addWidget(dh, stretch=1); tl.addLayout(hdr_row)
            sep = QFrame(); sep.setObjectName("hLine"); sep.setFrameShape(QFrame.Shape.HLine); tl.addWidget(sep)
            dist_edits = {}
            for aid in ["A0","A1","A2","A3"]:
                col = ANCHOR_COLORS[aid]
                arow = QHBoxLayout(); arow.setSpacing(4); arow.setContentsMargins(0,0,0,0)
                dot = QLabel("●"); dot.setStyleSheet(f"color:{col};font-size:11px;"); dot.setFixedWidth(DOT_W)
                albl = QLabel(aid); albl.setStyleSheet(f"color:{col};font-size:10px;font-weight:600;"); albl.setFixedWidth(AID_W)
                dist_e = QLineEdit(); dist_e.setPlaceholderText("---"); dist_e.setFixedHeight(24)
                dist_e.textEdited.connect(lambda txt, t=tid, a=aid: self._on_ref_edit(t, a, txt))
                arow.addWidget(dot); arow.addWidget(albl); arow.addWidget(dist_e, stretch=1)
                tl.addLayout(arow); dist_edits[aid] = dist_e
            self._ref_dist_edits[tid] = dist_edits
            tl.addSpacing(6)
            place_btn = QPushButton("Place on Map"); place_btn.setObjectName("paramBtn")
            place_btn.clicked.connect(lambda c, t=tid: self._arm_ref_dot(t))
            tl.addWidget(place_btn)
            tl.addSpacing(6)
            ht_row = QHBoxLayout(); ht_row.setSpacing(6)
            ht_lbl = QLabel("Height (Y) ft:"); ht_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
            ht_e = QLineEdit(); ht_e.setPlaceholderText("0.0"); ht_e.setFixedHeight(24)
            ht_row.addWidget(ht_lbl); ht_row.addWidget(ht_e, stretch=1)
            tl.addLayout(ht_row); self._ref_height_edits[tid] = ht_e
            tl.addSpacing(6)
            calc_btn = QPushButton("Calculate Reference"); calc_btn.setObjectName("paramBtn")
            calc_btn.clicked.connect(lambda c, t=tid: self._calc_reference(t))
            tl.addWidget(calc_btn)
            self.ref_tabs.addTab(tab, f" {tid} ")

        ri.addWidget(self.ref_tabs)
        self.ref_tabs.currentChanged.connect(self._on_ref_tab_changed)
        self.lay.addWidget(ref_box)

        # ── CALIBRATION ──────────────────────────────────────────────────────
        cal_box = section_box()
        ci = QVBoxLayout(cal_box); ci.setContentsMargins(10,8,10,8); ci.setSpacing(6)
        self._cal_title_label = section_label("CALIBRATION  [T0]")
        ci.addWidget(self._cal_title_label); ci.addWidget(h_line())

        DOT_W2 = 14; AID_W2 = 24
        cal_hdr = QHBoxLayout(); cal_hdr.setSpacing(4); cal_hdr.setContentsMargins(0,0,0,0)
        sp_w2 = QWidget(); sp_w2.setFixedWidth(DOT_W2+AID_W2+8); cal_hdr.addWidget(sp_w2)
        rh = QLabel("REFERENCE (ft)"); rh.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rh.setStyleSheet(f"color:{ACCENT};font-size:10px;font-weight:600;letter-spacing:1px;")
        cal_hdr.addWidget(rh, stretch=1); ci.addLayout(cal_hdr)
        sep3 = QFrame(); sep3.setObjectName("hLine"); sep3.setFrameShape(QFrame.Shape.HLine); ci.addWidget(sep3)

        self._cal_locked_labels = {}
        for aid in ["A0","A1","A2","A3"]:
            col = ANCHOR_COLORS[aid]
            row = QHBoxLayout(); row.setSpacing(4); row.setContentsMargins(0,0,0,0)
            dot = QLabel("●"); dot.setStyleSheet(f"color:{col};font-size:11px;"); dot.setFixedWidth(DOT_W2)
            albl = QLabel(aid); albl.setStyleSheet(f"color:{col};font-size:10px;font-weight:600;"); albl.setFixedWidth(AID_W2)
            locked = QLineEdit("---"); locked.setObjectName("lockedEdit"); locked.setReadOnly(True); locked.setFixedHeight(24)
            row.addWidget(dot); row.addWidget(albl); row.addWidget(locked, stretch=1)
            ci.addLayout(row); self._cal_locked_labels[aid] = locked

        ci.addWidget(h_line())

        cap_lbl = QLabel("MULTI-SAMPLE CAPTURE")
        cap_lbl.setStyleSheet(f"color:{ACCENT};font-size:10px;font-weight:600;letter-spacing:1px;margin-top:4px;")
        ci.addWidget(cap_lbl)

        cap_row = QHBoxLayout(); cap_row.setSpacing(6)
        n_lbl = QLabel("n:"); n_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
        cap_row.addWidget(n_lbl)
        self._cal_n_combo = QComboBox()
        self._cal_n_combo.addItems(["1","5","10","20","50","100"])
        self._cal_n_combo.setCurrentText("20"); self._cal_n_combo.setFixedWidth(60)
        self._cal_n_combo.setStyleSheet(
            f"QComboBox{{background:{SURFACE};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
            f"border-radius:3px;padding:2px 6px;font-size:11px;}}"
            f"QComboBox::drop-down{{border:none;}}"
            f"QComboBox QAbstractItemView{{background:{SURFACE};color:{TEXT_PRIMARY};border:1px solid {BORDER};}}")
        cap_row.addWidget(self._cal_n_combo)
        self._capture_btn = QPushButton("Capture"); self._capture_btn.setObjectName("paramBtn")
        self._capture_btn.clicked.connect(self._start_capture)
        cap_row.addWidget(self._capture_btn, stretch=1); ci.addLayout(cap_row)

        self._cap_prog_bars = {}; self._cap_prog_labels = {}
        for aid in ["A0","A1","A2","A3"]:
            col = ANCHOR_COLORS[aid]
            prow = QHBoxLayout(); prow.setSpacing(6); prow.setContentsMargins(0,1,0,1)
            pdot = QLabel("●"); pdot.setStyleSheet(f"color:{col};font-size:11px;"); pdot.setFixedWidth(14)
            paid = QLabel(aid); paid.setStyleSheet(f"color:{col};font-size:10px;font-weight:600;"); paid.setFixedWidth(22)
            pbar = QProgressBar(); pbar.setRange(0,1); pbar.setValue(0); pbar.setFixedHeight(8)
            pbar.setTextVisible(False)
            pbar.setStyleSheet(
                f"QProgressBar{{background:{SURFACE};border-radius:3px;border:1px solid {BORDER};}}"
                f"QProgressBar::chunk{{background:{col};border-radius:3px;}}")
            plbl = QLabel("0/0"); plbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:9px;font-family:Consolas;"); plbl.setFixedWidth(36)
            prow.addWidget(pdot); prow.addWidget(paid); prow.addWidget(pbar, stretch=1); prow.addWidget(plbl)
            ci.addLayout(prow); self._cap_prog_bars[aid] = pbar; self._cap_prog_labels[aid] = plbl

        ci.addWidget(h_line())

        eq_type_lbl = QLabel("EQUATION TYPE")
        eq_type_lbl.setStyleSheet(f"color:{ACCENT};font-size:10px;font-weight:600;letter-spacing:1px;margin-top:2px;")
        ci.addWidget(eq_type_lbl)

        self._eq_anchor_tabs = QTabWidget()
        self._eq_anchor_tabs.setFixedHeight(145)
        self._eq_anchor_tabs.tabBar().setExpanding(True)
        self._eq_anchor_tabs.tabBar().setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._eq_anchor_tabs.setStyleSheet(
            f"QTabWidget::pane{{border:1px solid {BORDER};background:{SURFACE};border-radius:0px 4px 4px 4px;}}"
            f"QTabBar{{qproperty-expanding:true;}}"
            f"QTabBar::tab{{background:{SURFACE};color:{TEXT_SECONDARY};"
            f"border:1px solid {BORDER};padding:3px 20px;font-size:10px;"
            f"border-radius:3px 3px 0 0;margin-right:0px;min-width:0px;}}"
            f"QTabBar::tab:selected{{background:{PANEL_BG};color:{TEXT_PRIMARY};border-color:{ACCENT};border-bottom:none;}}"
            f"QTabBar::tab:hover{{color:{ACCENT};}}")

        FIT_MODES = ["Linear","Exponential","Polynomial","Logarithmic","Power Series","Moving Average"]
        self._fit_mode_combos  = {}
        self._auto_cal_checks  = {}
        self._poly_deg_combos  = {}
        self._poly_deg_labels  = {}
        self._ma_period_combos = {}
        self._ma_type_combos   = {}
        self._cal_pts   = {t: {a: [] for a in ["A0","A1","A2","A3"]} for t in ["T0","T1","T2"]}
        self._cal_funcs = {t: {a: (lambda x: x) for a in ["A0","A1","A2","A3"]} for t in ["T0","T1","T2"]}
        self._is_capturing = False

        for aid in ["A0","A1","A2","A3"]:
            atab = QWidget(); atab.setStyleSheet(f"background:{SURFACE};")
            al = QVBoxLayout(atab); al.setContentsMargins(6,4,6,4); al.setSpacing(3)

            auto_row = QHBoxLayout(); auto_row.setSpacing(6)
            auto_chk = QPushButton("X"); auto_chk.setCheckable(True); auto_chk.setChecked(True)
            auto_chk.setFixedSize(QSize(18,18))
            auto_chk.setStyleSheet(
                f"QPushButton{{background:{ACCENT};color:#000;border:1px solid {ACCENT};"
                f"border-radius:2px;font-size:9px;font-weight:700;padding:0px;}}"
                f"QPushButton:!checked{{background:{SURFACE};color:{ACCENT};border:1px solid {ACCENT};border-radius:2px;}}")
            auto_lbl = QLabel("Auto-Calibrate"); auto_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
            auto_row.addWidget(auto_chk); auto_row.addWidget(auto_lbl); auto_row.addStretch()
            al.addLayout(auto_row); self._auto_cal_checks[aid] = auto_chk

            fit_combo = QComboBox(); fit_combo.addItems(FIT_MODES); fit_combo.setCurrentText("Polynomial")
            fit_combo.setEnabled(False)
            fit_combo.setStyleSheet(
                f"QComboBox{{background:{SURFACE2};color:{TEXT_SECONDARY};border:1px solid {BORDER};"
                f"border-radius:3px;padding:2px 6px;font-size:10px;}}"
                f"QComboBox:enabled{{color:{TEXT_PRIMARY};}}"
                f"QComboBox::drop-down{{border:none;}}"
                f"QComboBox QAbstractItemView{{background:{SURFACE};color:{TEXT_PRIMARY};border:1px solid {BORDER};}}")
            fit_combo.currentTextChanged.connect(lambda txt, a=aid: self._on_fit_mode_change(a, txt))
            al.addWidget(fit_combo); self._fit_mode_combos[aid] = fit_combo

            opts_container = QWidget(); opts_container.setFixedHeight(24); opts_container.setStyleSheet("background:transparent;")
            opts_row = QHBoxLayout(opts_container); opts_row.setSpacing(4); opts_row.setContentsMargins(0,0,0,0)

            poly_lbl = QLabel("Deg:"); poly_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:9px;")
            poly_combo = QComboBox(); poly_combo.addItems([str(i) for i in range(1,11)]); poly_combo.setCurrentText("4")
            poly_combo.setFixedWidth(44)
            poly_combo.setStyleSheet(
                f"QComboBox{{background:{SURFACE2};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
                f"border-radius:3px;padding:1px 4px;font-size:9px;}}"
                f"QComboBox::drop-down{{border:none;}}"
                f"QComboBox QAbstractItemView{{background:{SURFACE};color:{TEXT_PRIMARY};border:1px solid {BORDER};}}")
            poly_combo.currentTextChanged.connect(lambda txt, a=aid: self._recalc_cal())
            self._poly_deg_combos[aid] = poly_combo; self._poly_deg_labels[aid] = [poly_lbl]
            opts_row.addWidget(poly_lbl); opts_row.addWidget(poly_combo)

            ma_period_combo = QComboBox(); ma_period_combo.addItems(["2","3","4","5","6","8","10"]); ma_period_combo.setCurrentText("4")
            ma_period_combo.setFixedWidth(44)
            ma_period_combo.setStyleSheet(
                f"QComboBox{{background:{SURFACE2};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
                f"border-radius:3px;padding:1px 4px;font-size:9px;}}"
                f"QComboBox::drop-down{{border:none;}}"
                f"QComboBox QAbstractItemView{{background:{SURFACE};color:{TEXT_PRIMARY};border:1px solid {BORDER};}}")
            ma_period_combo.currentTextChanged.connect(lambda txt, a=aid: self._recalc_cal())
            self._ma_period_combos[aid] = ma_period_combo; opts_row.addWidget(ma_period_combo)

            ma_type_combo = QComboBox(); ma_type_combo.addItems(["Trailing","Centered"]); ma_type_combo.setCurrentText("Trailing")
            ma_type_combo.setFixedWidth(76)
            ma_type_combo.setStyleSheet(
                f"QComboBox{{background:{SURFACE2};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
                f"border-radius:3px;padding:1px 4px;font-size:9px;}}"
                f"QComboBox::drop-down{{border:none;}}"
                f"QComboBox QAbstractItemView{{background:{SURFACE};color:{TEXT_PRIMARY};border:1px solid {BORDER};}}")
            ma_type_combo.currentTextChanged.connect(lambda txt, a=aid: self._recalc_cal())
            self._ma_type_combos[aid] = ma_type_combo; opts_row.addWidget(ma_type_combo)
            opts_row.addStretch(); al.addWidget(opts_container)

            poly_lbl.setVisible(True); poly_combo.setVisible(True)
            ma_period_combo.setVisible(False); ma_type_combo.setVisible(False)

            auto_chk.toggled.connect(lambda checked, a=aid: self._on_auto_cal_toggle(a))
            self._eq_anchor_tabs.addTab(atab, aid)

        for i, aid in enumerate(["A0","A1","A2","A3"]):
            self._eq_anchor_tabs.tabBar().setTabTextColor(i, QColor(ANCHOR_COLORS[aid]))
        ci.addWidget(self._eq_anchor_tabs)
        ci.addWidget(h_line())

        eq_col_lbl = QLabel("CALIBRATION EQUATIONS")
        eq_col_lbl.setStyleSheet(f"color:{ACCENT};font-size:10px;font-weight:600;letter-spacing:1px;margin-top:2px;")
        ci.addWidget(eq_col_lbl)

        self._eq_text_edits = {}; self._preset_checks = {}
        for aid in ["A0","A1","A2","A3"]:
            col = ANCHOR_COLORS[aid]
            eq_row = QHBoxLayout(); eq_row.setSpacing(4); eq_row.setContentsMargins(0,1,0,1)
            preset_btn = QPushButton("P"); preset_btn.setCheckable(True); preset_btn.setChecked(False)
            preset_btn.setFixedSize(QSize(18,18)); preset_btn.setToolTip("Use preset equation for this anchor")
            preset_btn.setStyleSheet(
                f"QPushButton{{background:{SURFACE};color:{TEXT_SECONDARY};border:1px solid {BORDER};"
                f"border-radius:2px;font-size:8px;font-weight:700;padding:0px;}}"
                f"QPushButton:checked{{background:#8e44ad;color:#fff;border:1px solid #8e44ad;border-radius:2px;}}")
            preset_btn.toggled.connect(lambda checked, a=aid: self._on_preset_toggle(a, checked))
            eq_row.addWidget(preset_btn); self._preset_checks[aid] = preset_btn
            dot = QLabel("●"); dot.setStyleSheet(f"color:{col};font-size:11px;"); dot.setFixedWidth(14)
            albl = QLabel(aid); albl.setStyleSheet(f"color:{col};font-size:10px;font-weight:600;"); albl.setFixedWidth(22)
            eq_row.addWidget(dot); eq_row.addWidget(albl)
            eq_edit = QLineEdit("Raw (no data)")
            eq_edit.setStyleSheet(
                f"background:{DARK_BG};color:{col};border:1px solid {BORDER};"
                f"border-radius:3px;padding:2px 6px;font-size:9px;font-family:Consolas;")
            eq_edit.setFixedHeight(22)
            eq_edit.textEdited.connect(lambda txt, a=aid: self._on_eq_manual_edit(a, txt))
            eq_row.addWidget(eq_edit, stretch=1); ci.addLayout(eq_row)
            self._eq_text_edits[aid] = eq_edit

        self.lay.addWidget(cal_box)

        # ── Captured Points Log ──────────────────────────────────────────────
        pts_box = section_box()
        pi = QVBoxLayout(pts_box); pi.setContentsMargins(10, 8, 10, 8); pi.setSpacing(6)
        pi.addWidget(section_label("CAPTURED POINTS")); pi.addWidget(h_line())
        self._pts_list = QLabel("No data captured yet.")
        self._pts_list.setStyleSheet(
            f"color:{TEXT_SECONDARY};font-size:9px;font-family:Consolas;"
            f"background:{DARK_BG};border-radius:3px;padding:4px;")
        self._pts_list.setWordWrap(True)
        self._pts_list.setAlignment(Qt.AlignmentFlag.AlignTop)
        pi.addWidget(self._pts_list)
        clear_btn = QPushButton("Clear Captured Data"); clear_btn.setObjectName("paramBtn")
        clear_btn.clicked.connect(self._clear_cal_data); pi.addWidget(clear_btn)
        self.lay.addWidget(pts_box)

        # ── SMOOTHING FILTER ─────────────────────────────────────────────────
        sf_box = section_box()
        sfi = QVBoxLayout(sf_box); sfi.setContentsMargins(10,8,10,8); sfi.setSpacing(6)
        sfi.addWidget(section_label("SMOOTHING FILTER")); sfi.addWidget(h_line())

        mode_row = QHBoxLayout(); mode_row.setSpacing(8)
        self._filter_mode = "EMA"; self._filter_btns = {}
        btn_group = QButtonGroup(sf_box)
        for mode in ["EMA","Rolling","Kalman"]:
            rb = QRadioButton(mode); rb.setChecked(mode == "EMA")
            rb.setStyleSheet(
                f"QRadioButton{{color:{TEXT_SECONDARY};font-size:10px;}}"
                f"QRadioButton:checked{{color:{TEXT_PRIMARY};}}"
                f"QRadioButton::indicator{{width:12px;height:12px;}}"
                f"QRadioButton::indicator:checked{{background:{ACCENT};border-radius:6px;border:2px solid {ACCENT};}}"
                f"QRadioButton::indicator:unchecked{{background:{SURFACE};border-radius:6px;border:2px solid {BORDER};}}")
            rb.toggled.connect(lambda checked, m=mode: self._on_filter_mode(m, checked))
            btn_group.addButton(rb); mode_row.addWidget(rb); self._filter_btns[mode] = rb
        sfi.addLayout(mode_row)

        def _slider_row(parent_layout, label, init_val, lo, hi, step, fmt, key):
            row = QHBoxLayout(); row.setSpacing(6)
            lbl = QLabel(label); lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:9px;"); lbl.setFixedWidth(150)
            val_lbl = QLabel(fmt.format(init_val))
            val_lbl.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:9px;font-weight:600;font-family:Consolas;"); val_lbl.setFixedWidth(36)
            row.addWidget(lbl); row.addWidget(val_lbl); parent_layout.addLayout(row)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(int(lo/step), int(hi/step)); slider.setValue(int(init_val/step))
            slider.setStyleSheet(
                f"QSlider::groove:horizontal{{background:{SURFACE};height:4px;border-radius:2px;}}"
                f"QSlider::handle:horizontal{{background:{ACCENT};width:12px;height:12px;margin:-4px 0;border-radius:6px;}}"
                f"QSlider::sub-page:horizontal{{background:{ACCENT};height:4px;border-radius:2px;}}")
            slider.valueChanged.connect(lambda v, vl=val_lbl, f=fmt, s=step, k=key: (
                vl.setText(f.format(v*s)), setattr(self, k, v*s)))
            parent_layout.addWidget(slider); setattr(self, key, init_val)
            return slider

        _slider_row(sfi, "EMA α  (0=smooth, 1=raw):", 0.2,  0.01, 1.0,  0.01, "{:.2f}", "_filt_ema_alpha")
        _slider_row(sfi, "Rolling window (frames):",   8,    2,    30,   1,    "{:.0f}", "_filt_roll_n")
        _slider_row(sfi, "Kalman Q (process noise):",  0.1,  0.01, 2.0,  0.01, "{:.2f}", "_filt_kal_q")
        _slider_row(sfi, "Kalman R (meas. noise):",    2.0,  0.1,  10.0, 0.1,  "{:.1f}", "_filt_kal_r")
        self.lay.addWidget(sf_box)
        self.lay.addStretch()

        self._last_raws = {t: {} for t in ["T0","T1","T2"]}
        self._last_cals = {t: {} for t in ["T0","T1","T2"]}

    # ── COM PORT helpers ──────────────────────────────────────────────────────
    def _populate_dropdown_only(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self._com_dropdown.blockSignals(True)
        self._com_dropdown.clear()
        if ports:
            for p in ports:
                self._com_dropdown.addItem(p)
        else:
            self._com_dropdown.addItem("No ports")
            self._com_status_lbl.setText("No ports found.")
        self._com_dropdown.blockSignals(False)

    def auto_connect_on_startup(self):
        self._populate_dropdown_only()
        detected = auto_detect_esp32_port()
        if detected:
            idx = self._com_dropdown.findText(detected)
            if idx >= 0:
                self._com_dropdown.setCurrentIndex(idx)
            self._do_connect(detected, auto=True)
        else:
            self._com_status_lbl.setText("ESP32-C6 not detected. Select manually.")
            self._com_status_lbl.setStyleSheet(f"color:#f39c12;font-size:9px;")

    def refresh_com_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self._com_dropdown.blockSignals(True)
        self._com_dropdown.clear()
        if not ports:
            self._com_dropdown.addItem("No ports")
            self._com_status_lbl.setText("No ports found.")
            self._com_status_lbl.setStyleSheet(f"color:#e74c3c;font-size:9px;")
            self._com_dropdown.blockSignals(False)
            return
        for p in ports:
            self._com_dropdown.addItem(p)
        self._com_dropdown.blockSignals(False)

        if not self._user_overrode_port:
            detected = auto_detect_esp32_port()
            if detected and detected in ports:
                self._com_dropdown.setCurrentIndex(self._com_dropdown.findText(detected))
                self._do_connect(detected, auto=True)
            else:
                self._com_status_lbl.setText("ESP32-C6 not detected. Select manually.")
                self._com_status_lbl.setStyleSheet(f"color:#f39c12;font-size:9px;")
        else:
            current = self._com_dropdown.currentText()
            if current in ports:
                self._do_connect(current, auto=False)
            else:
                self._user_overrode_port = False
                self._com_status_lbl.setText("Previous port lost. Select manually.")
                self._com_status_lbl.setStyleSheet(f"color:#f39c12;font-size:9px;")

    def _on_user_select_port(self, index):
        port = self._com_dropdown.itemText(index)
        if port and port != "No ports":
            self._user_overrode_port = True
            self._do_connect(port, auto=False)

    def _do_connect(self, port, auto=False):
        label = "Auto" if auto else "Manual"
        self._com_status_lbl.setText(f"Connecting ({label}): {port}...")
        self._com_status_lbl.setStyleSheet(f"color:#f39c12;font-size:9px;")
        start_serial(port)
        QTimer.singleShot(800, lambda: self._com_status_lbl.setText(
            f"Connected: {port}" if serial_thread_running else f"Failed: {port}"
        ) or self._com_status_lbl.setStyleSheet(
            f"color:{ACCENT};font-size:9px;" if serial_thread_running else f"color:#e74c3c;font-size:9px;"
        ))

    def disconnect_com_port(self):
        stop_serial()
        self._user_overrode_port = False
        self._com_status_lbl.setText("Disconnected.")
        self._com_status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:9px;")

    def _arm_ref_dot(self, tid):
        self.ref_tabs.setCurrentIndex(["T0","T1","T2"].index(tid))
        if self.canvas_ref: self.canvas_ref.arm_ref_dot()

    def on_ref_dot_placed(self, pos):
        if not self.canvas_ref: return
        tid = ["T0","T1","T2"][self.ref_tabs.currentIndex()]
        wx, wy = pos
        for aid, (ax, ay) in self.canvas_ref.anchors.items():
            floor_d = math.hypot(wx - ax, wy - ay)
            self._ref_dist_edits[tid][aid].setText(f"{floor_d:.3f}")

    def _on_ref_edit(self, tid, aid, txt):
        pass

    def _calc_reference(self, tid):
        ht_txt = self._ref_height_edits[tid].text().strip()
        if not _is_float(ht_txt):
            mb = QMessageBox(self); mb.setWindowTitle("Missing Height")
            mb.setText("Enter the tag height y (ft) before calculating.")
            mb.setIcon(QMessageBox.Icon.Warning)
            mb.setStyleSheet(f"background:{PANEL_BG};color:{TEXT_PRIMARY};"); mb.exec(); return
        y = float(ht_txt)
        missing = [a for a in ["A0","A1","A2","A3"]
                   if not _is_float(self._ref_dist_edits[tid][a].text().strip())]
        if missing:
            mb = QMessageBox(self); mb.setWindowTitle("Missing Distances")
            mb.setText(f"Fill floor distance x for: {', '.join(missing)}")
            mb.setIcon(QMessageBox.Icon.Warning)
            mb.setStyleSheet(f"background:{PANEL_BG};color:{TEXT_PRIMARY};"); mb.exec(); return
        for aid in ["A0","A1","A2","A3"]:
            x = float(self._ref_dist_edits[tid][aid].text().strip())
            h = math.sqrt(x**2 + y**2)
            self._cal_locked_labels[aid].setText(f"{h:.3f}")

    def _on_ref_tab_changed(self, idx):
        tid = ["T0","T1","T2"][idx]
        self._cal_title_label.setText(f"CALIBRATION  [{tid}]")

    def _on_auto_cal_toggle(self, aid):
        is_auto = self._auto_cal_checks[aid].isChecked()
        self._fit_mode_combos[aid].setEnabled(not is_auto)
        self._poly_deg_combos[aid].setEnabled(not is_auto)
        self._ma_period_combos[aid].setEnabled(not is_auto)
        self._ma_type_combos[aid].setEnabled(not is_auto)
        self._recalc_cal()

    def _on_fit_mode_change(self, aid, mode):
        is_poly = (mode == "Polynomial")
        is_ma   = (mode == "Moving Average")
        self._poly_deg_combos[aid].setVisible(is_poly)
        for lbl in self._poly_deg_labels.get(aid, []):
            lbl.setVisible(is_poly)
        self._ma_period_combos[aid].setVisible(is_ma)
        self._ma_type_combos[aid].setVisible(is_ma)
        self._recalc_cal()

    def _on_preset_toggle(self, aid, checked):
        col = ANCHOR_COLORS[aid]
        if checked:
            self._eq_text_edits[aid].setText("(0.7514969*Raw)+0.0295246")
            self._eq_text_edits[aid].setStyleSheet(
                f"background:{DARK_BG};color:#8e44ad;border:1px solid #8e44ad;"
                f"border-radius:3px;padding:2px 6px;font-size:9px;font-family:Consolas;")
            tid = ["T0","T1","T2"][self.ref_tabs.currentIndex()]
            self._cal_funcs[tid][aid] = lambda x: (0.7514969*x)+0.0295246
        else:
            self._eq_text_edits[aid].setStyleSheet(
                f"background:{DARK_BG};color:{col};border:1px solid {BORDER};"
                f"border-radius:3px;padding:2px 6px;font-size:9px;font-family:Consolas;")
            self._recalc_cal()

    def _on_eq_manual_edit(self, aid, txt):
        if self._preset_checks[aid].isChecked(): return
        col = ANCHOR_COLORS[aid]
        safe = txt.replace("^","**")
        math_env = {"ln": math.log, "log": math.log10, "e": math.e, "pi": math.pi,
                    "sin": math.sin, "cos": math.cos, "sqrt": math.sqrt, "abs": abs}
        try:
            code = compile(safe, "<string>", "eval")
            eval(code, {"__builtins__": {}}, dict(math_env, Raw=1.0))
            self._eq_text_edits[aid].setStyleSheet(
                f"background:{DARK_BG};color:{col};border:1px solid {ACCENT};"
                f"border-radius:3px;padding:2px 6px;font-size:9px;font-family:Consolas;")
            tid = ["T0","T1","T2"][self.ref_tabs.currentIndex()]
            def mfunc(x, c=code, me=math_env):
                try: return float(eval(c, {"__builtins__": {}}, dict(me, Raw=float(x))))
                except: return float(x)
            self._cal_funcs[tid][aid] = mfunc
        except Exception:
            self._eq_text_edits[aid].setStyleSheet(
                f"background:{DARK_BG};color:#e74c3c;border:1px solid #e74c3c;"
                f"border-radius:3px;padding:2px 6px;font-size:9px;font-family:Consolas;")

    def _recalc_cal(self):
        tid = ["T0","T1","T2"][self.ref_tabs.currentIndex()]
        for aid in ["A0","A1","A2","A3"]:
            if self._preset_checks[aid].isChecked(): continue
            pts = self._cal_pts[tid][aid]; col = ANCHOR_COLORS[aid]
            if len(pts) < 2:
                if not pts:
                    self._eq_text_edits[aid].setText("Raw (no data)")
                    self._cal_funcs[tid][aid] = lambda x: x
                else:
                    off = pts[0][1] - pts[0][0]
                    self._eq_text_edits[aid].setText(f"Raw + {off:.4f}")
                    self._cal_funcs[tid][aid] = lambda x, o=off: x + o
                continue
            X = np.array([p[0] for p in pts]); Y = np.array([p[1] for p in pts])
            if self._auto_cal_checks[aid].isChecked():
                best_err, best_f, best_eq, best_mode_name = float('inf'), None, "", "Linear"
                for mode in ["Linear", "Polynomial", "Logarithmic", "Power Series", "Exponential"]:
                    try:
                        deg = int(self._poly_deg_combos[aid].currentText())
                        f, eq = build_eval_func(mode, X, Y, poly_deg=deg)
                        err = sum(abs(f(x) - y) for x, y in pts) / len(pts)
                        if err < best_err:
                            best_err, best_f, best_eq, best_mode_name = err, f, f"[Auto:{mode}] {eq}", mode
                    except Exception:
                        pass
                self._cal_funcs[tid][aid] = best_f if best_f else (lambda x: x)
                self._eq_text_edits[aid].setText(best_eq)
                self._eq_text_edits[aid].setStyleSheet(
                    f"background:{DARK_BG};color:{col};border:1px solid {BORDER};"
                    f"border-radius:3px;padding:2px 6px;font-size:9px;font-family:Consolas;")
                self._fit_mode_combos[aid].blockSignals(True)
                self._fit_mode_combos[aid].setCurrentText(best_mode_name)
                self._fit_mode_combos[aid].blockSignals(False)
                is_poly = (best_mode_name == "Polynomial")
                is_ma = (best_mode_name == "Moving Average")
                self._poly_deg_combos[aid].setVisible(is_poly)
                for lbl in self._poly_deg_labels.get(aid, []):
                    lbl.setVisible(is_poly)
                self._ma_period_combos[aid].setVisible(is_ma)
                self._ma_type_combos[aid].setVisible(is_ma)
            else:
                mode = self._fit_mode_combos[aid].currentText()
                try:
                    deg  = int(self._poly_deg_combos[aid].currentText())
                    per  = int(self._ma_period_combos[aid].currentText())
                    mtyp = self._ma_type_combos[aid].currentText()
                    f, eq = build_eval_func(mode, X, Y, poly_deg=deg, ma_period=per, ma_type=mtyp)
                    self._cal_funcs[tid][aid] = f; self._eq_text_edits[aid].setText(eq)
                    self._eq_text_edits[aid].setStyleSheet(
                        f"background:{DARK_BG};color:{col};border:1px solid {BORDER};"
                        f"border-radius:3px;padding:2px 6px;font-size:9px;font-family:Consolas;")
                except Exception:
                    self._cal_funcs[tid][aid] = lambda x: x
                    self._eq_text_edits[aid].setText("Error fitting")
        if hasattr(self, '_bottom_panel_ref') and self._bottom_panel_ref:
            self._update_cal_graph(self._bottom_panel_ref)
        self._refresh_pts_list()

    def _update_cal_graph(self, bottom_panel=None):
        if bottom_panel is None: return
        tid = ["T0","T1","T2"][self.ref_tabs.currentIndex()]
        has_data = False
        for aid in ["A0","A1","A2","A3"]:
            pts = self._cal_pts[tid][aid]
            if pts:
                has_data = True
                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                bottom_panel._sc[aid].set_data(xs, ys)
                func = self._cal_funcs[tid][aid]
                if func and len(pts) >= 2:
                    lx = np.linspace(0.01, 30, 120)
                    try:
                        ly = [func(x) for x in lx]
                        bottom_panel._fl[aid].set_data(lx, ly)
                    except Exception:
                        bottom_panel._fl[aid].set_data([], [])
                else:
                    bottom_panel._fl[aid].set_data([], [])
            else:
                bottom_panel._sc[aid].set_data([], [])
                bottom_panel._fl[aid].set_data([], [])
        if has_data:
            bottom_panel.ax.relim()
            bottom_panel.ax.autoscale_view()
        else:
            bottom_panel.ax.set_xlim(0, 30); bottom_panel.ax.set_ylim(0, 30)
        bottom_panel.mpl_canvas.draw_idle()

    def _start_capture(self):
        if self._is_capturing: return
        try: n = int(self._cal_n_combo.currentText())
        except: return
        tid = ["T0","T1","T2"][self.ref_tabs.currentIndex()]
        true_dists = {}
        for aid in ["A0","A1","A2","A3"]:
            txt = self._cal_locked_labels[aid].text().strip()
            if _is_float(txt) and float(txt) > 0: true_dists[aid] = float(txt)
        if not true_dists:
            mb = QMessageBox(self); mb.setWindowTitle("No Reference Values")
            mb.setText("Calculate Reference distances first before capturing.")
            mb.setIcon(QMessageBox.Icon.Warning)
            mb.setStyleSheet(f"background:{PANEL_BG};color:{TEXT_PRIMARY};"); mb.exec(); return
        self._is_capturing = True
        self._capture_btn.setText("Capturing..."); self._capture_btn.setEnabled(False)
        for aid in ["A0","A1","A2","A3"]:
            self._cap_prog_bars[aid].setRange(0, n); self._cap_prog_bars[aid].setValue(0)
            self._cap_prog_labels[aid].setText(f"0/{n}")
        self._capture_buf = {aid: [] for aid in true_dists}
        self._capture_target = n; self._capture_true = true_dists; self._capture_tid = tid
        self._capture_tick()

    def _capture_tick(self):
        tid = self._capture_tid; n = self._capture_target; all_done = True
        bp = getattr(self, '_bottom_panel_ref', None)
        for aid in self._capture_true:
            raw = tag_data.get(tid, {}).get(aid, -1)
            if raw > 0: self._capture_buf[aid].append(raw)
            count = len(self._capture_buf[aid])
            self._cap_prog_bars[aid].setValue(count)
            self._cap_prog_labels[aid].setText(f"{count}/{n}")
            if count < n: all_done = False
            if bp and self._capture_buf[aid]:
                bp._cap[aid].set_data(
                    self._capture_buf[aid],
                    [self._capture_true[aid]] * len(self._capture_buf[aid])
                )
        if bp: bp.mpl_canvas.draw_idle()
        if not all_done:
            QTimer.singleShot(100, self._capture_tick)
        else:
            self._capture_btn.setText("Fusing..."); self._capture_btn.setEnabled(False)
            self._animate_capture_fusion(0)

    def _animate_capture_fusion(self, frame):
        bp = getattr(self, '_bottom_panel_ref', None)
        total = 15
        means = {aid: sum(s)/len(s) for aid, s in self._capture_buf.items() if s}
        if frame <= total:
            t = frame / float(total)
            if bp:
                for aid, samples in self._capture_buf.items():
                    if not samples: continue
                    m = means[aid]
                    animated = [x + (m - x) * t for x in samples]
                    bp._cap[aid].set_data(animated, [self._capture_true[aid]] * len(samples))
                bp.mpl_canvas.draw_idle()
            QTimer.singleShot(30, lambda: self._animate_capture_fusion(frame + 1))
        else:
            for aid, samples in self._capture_buf.items():
                if samples:
                    mean_raw = sum(samples) / len(samples)
                    self._cal_pts[self._capture_tid][aid].append((mean_raw, self._capture_true[aid]))
                if bp: bp._cap[aid].set_data([], [])
            if bp: bp.mpl_canvas.draw_idle()
            self._is_capturing = False
            self._capture_btn.setText("Capture"); self._capture_btn.setEnabled(True)
            self._recalc_cal()

    def highlight_line_row(self, line): pass

    def update_ble_status(self, ts_dict):
        colors = {"Connected":ACCENT,"Connecting...":"#f39c12","Disconnected":TEXT_MUTED}
        for tid,info in self._ble_labels.items():
            s=ts_dict.get(tid,"Disconnected"); col=colors.get(s,TEXT_MUTED)
            info["dot"].setStyleSheet(f"color:{col};font-size:14px;")
            info["status"].setStyleSheet(f"color:{col};font-size:11px;")
            info["status"].setText(s)

    def notify_popups_ble(self, tid, status):
        for popup in self._popups.get(tid,[]):
            if popup.isVisible():
                if status=="Connected":    popup.notify_connected()
                elif status=="Disconnected": popup.notify_disconnected()

    def update_data(self, tid, anchor_raws, anchor_cals, raw_xy, cal_xy):
        if tid not in self._data_labels: return
        self._last_raws[tid] = anchor_raws; self._last_cals[tid] = anchor_cals
        lbls = self._data_labels[tid]
        for aid in ["A0","A1","A2","A3"]:
            r = anchor_raws.get(aid,-1); c = anchor_cals.get(aid,-1)
            lbls[f"{aid}_raw"].setText("---" if r < 0 else f"{r:.2f}")
            lbls[f"{aid}_cal"].setText("---" if c < 0 else f"{c:.2f}")
        lbls["raw_xy"].setText(f"{raw_xy[0]:.2f}, {raw_xy[1]:.2f}" if raw_xy else "---, ---")
        lbls["cal_xy"].setText(f"{cal_xy[0]:.2f}, {cal_xy[1]:.2f}" if cal_xy else "---, ---")

    def _get_popup_data(self, tid):
        if not self.canvas_ref: return None
        return {"anchors": self.canvas_ref.anchors, "lines": self.canvas_ref.lines,
                "raw_pos": self.canvas_ref.tag_raw.get(tid),
                "cal_pos": self.canvas_ref.tag_cal.get(tid),
                "anchor_raws": self._last_raws.get(tid,{}),
                "anchor_cals": self._last_cals.get(tid,{})}

    def _register_popup(self, tid, popup):
        self._popups.setdefault(tid,[]).append(popup)

    def _notify_popups_coord(self):
        for tid,plist in self._popups.items():
            for popup in plist:
                if popup.isVisible(): popup.notify_coord_changed()

    def set_canvas(self, canvas):
        self.canvas_ref=canvas; self.refresh_map_params(canvas.anchors,canvas.lines)

    def refresh_map_params(self, anchors, lines):
        for aid,edit in self.anchor_edits.items():
            if not edit.hasFocus():
                x,y=anchors.get(aid,[0,0]); edit.setText(f"{x:.1f}, {y:.1f}")
        while self.lines_container.count():
            item=self.lines_container.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for (a,b) in lines:
            row=LineRow(a,b,self.canvas_ref,self._delete_line)
            self.lines_container.addWidget(row)
        self._notify_popups_coord()

    def _commit_anchor(self,aid,edit):
        if not self.canvas_ref: return
        ok,nx,ny,err=_parse_coord(edit.text())
        if not ok: _show_coord_error(self,err); edit.clearFocus(); return
        self.canvas_ref._commit_coord(aid,nx,ny); edit.clearFocus()

    def _delete_line(self,a,b):
        if not self.canvas_ref: return
        self.canvas_ref.lines=[l for l in self.canvas_ref.lines if l not in ((a,b),(b,a))]
        self.canvas_ref._selected_line=None; self.canvas_ref.update()
        self.refresh_map_params(self.canvas_ref.anchors,self.canvas_ref.lines)

    def _show_picker(self):
        self._picker_sel=[]
        for btn in self._picker_btns.values():
            btn.setProperty("selected","false"); btn.style().unpolish(btn); btn.style().polish(btn)
        self._picker.show(); self.add_line_btn.hide()

    def _picker_click(self,aid):
        if aid in self._picker_sel: return
        self._picker_sel.append(aid)
        btn=self._picker_btns[aid]; btn.setProperty("selected","true")
        btn.style().unpolish(btn); btn.style().polish(btn)
        if len(self._picker_sel)==2:
            a,b=self._picker_sel
            if self.canvas_ref and (a,b) not in self.canvas_ref.lines and (b,a) not in self.canvas_ref.lines:
                self.canvas_ref.lines.append((a,b)); self.canvas_ref.update()
                self.refresh_map_params(self.canvas_ref.anchors,self.canvas_ref.lines)
            self._cancel_picker()

    def _cancel_picker(self):
        self._picker.hide(); self.add_line_btn.show(); self._picker_sel=[]

    def keyPressEvent(self,e):
        if e.key()==Qt.Key.Key_Escape: self._cancel_picker()
        super().keyPressEvent(e)

    def _on_filter_mode(self, mode, checked):
        if checked: self._filter_mode = mode

    def _refresh_pts_list(self):
        tid = ["T0", "T1", "T2"][self.ref_tabs.currentIndex()]
        lines = []
        for aid in ["A0", "A1", "A2", "A3"]:
            pts = self._cal_pts[tid][aid]
            if pts:
                for i, (raw, true) in enumerate(pts):
                    lines.append(f"{aid} [{i + 1}]  Raw:{raw:.3f} → True:{true:.3f} ft")
        self._pts_list.setText("\n".join(lines) if lines else "No data captured yet.")

    def _clear_cal_data(self):
        tid = ["T0", "T1", "T2"][self.ref_tabs.currentIndex()]
        for aid in ["A0", "A1", "A2", "A3"]:
            self._cal_pts[tid][aid].clear()
            self._cal_funcs[tid][aid] = lambda x: x
            self._eq_text_edits[aid].setText("Raw (no data)")
        self._refresh_pts_list()
        if hasattr(self, '_bottom_panel_ref') and self._bottom_panel_ref:
            self._update_cal_graph(self._bottom_panel_ref)

# ── main window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTLS Calibration Software")
        self.setMinimumSize(900,600)
        self.bottom_visible=True; self.bottom_saved_h=0

        self._ema_pos   = {t: None for t in ["T0","T1","T2"]}
        self._roll_buf  = {t: deque(maxlen=20) for t in ["T0","T1","T2"]}
        self._kal_state = {t: None for t in ["T0","T1","T2"]}
        self._kal_P     = {t: None for t in ["T0","T1","T2"]}

        # inter-tag CSV logging timestamps
        self._last_log_time = {"T0-T1": time.time(), "T1-T2": time.time(), "T0-T2": time.time()}

        self.build_ui(); self.showMaximized()

        self._conn_timer=QTimer(); self._conn_timer.timeout.connect(self._poll_connectivity); self._conn_timer.start(500)
        self._rtls_timer=QTimer(); self._rtls_timer.timeout.connect(self._rtls_loop); self._rtls_timer.start(50)

        self._cal_graph_timer = QTimer()
        self._cal_graph_timer.timeout.connect(self._update_cal_graph_live)
        self._cal_graph_timer.start(100)

        # Auto-connect COM port on startup
        QTimer.singleShot(200, self.right_panel.auto_connect_on_startup)

    def build_ui(self):
        central=QWidget(); self.setCentralWidget(central)
        self.outer_split=QSplitter(Qt.Orientation.Horizontal)
        self.outer_split.setHandleWidth(4); self.outer_split.setChildrenCollapsible(False)
        self.right_panel=RightPanel()
        self.right_panel.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Expanding)
        self.left_split=QSplitter(Qt.Orientation.Vertical)
        self.left_split.setHandleWidth(4); self.left_split.setChildrenCollapsible(False)
        self.main_panel=MainPanel(right_panel_ref=self.right_panel)
        self.bottom_panel=BottomPanel()
        self.left_split.addWidget(self.main_panel); self.left_split.addWidget(self.bottom_panel)
        self.left_split.setStretchFactor(0,1); self.left_split.setStretchFactor(1,0)
        self.left_split.setSizes([520,280])
        self.outer_split.addWidget(self.left_split); self.outer_split.addWidget(self.right_panel)
        self.outer_split.setStretchFactor(0,3); self.outer_split.setStretchFactor(1,1)
        self.outer_split.setSizes([1050,350])
        root_lay=QVBoxLayout(central); root_lay.setContentsMargins(0,0,0,0); root_lay.setSpacing(0)
        root_lay.addWidget(self.outer_split)
        self.right_panel.set_canvas(self.main_panel.canvas)
        self.right_panel._bottom_panel_ref = self.bottom_panel
        self.bottom_panel.hide_btn.clicked.connect(self.toggle_bottom_panel)

    def toggle_bottom_panel(self):
        HDR=BottomPanel.HDR_H+1
        if self.bottom_visible:
            self.bottom_saved_h=self.left_split.sizes()[1]
            self.bottom_panel.set_graph_visible(False)
            self.left_split.widget(1).setMinimumHeight(HDR)
            self.left_split.widget(1).setMaximumHeight(HDR)
            total=sum(self.left_split.sizes())
            self.left_split.setSizes([total-HDR,HDR]); self.bottom_visible=False
        else:
            h=self.bottom_saved_h if self.bottom_saved_h>80 else 280
            self.left_split.widget(1).setMinimumHeight(0)
            self.left_split.widget(1).setMaximumHeight(16777215)
            total=sum(self.left_split.sizes())
            self.left_split.setSizes([total-h,h]); self.bottom_panel.set_graph_visible(True)
            self.bottom_visible=True

    def changeEvent(self,e):
        if e.type()==QEvent.Type.WindowStateChange and self.isMinimized():
            screen=QApplication.primaryScreen().availableGeometry()
            w,h=1280,800; x=(screen.width()-w)//2; y=(screen.height()-h)//2
            self.setWindowState(Qt.WindowState.WindowNoState); self.setGeometry(x,y,w,h)
        super().changeEvent(e)

    def _poll_connectivity(self):
        self.right_panel.update_ble_status(tag_status)
        for tid in ["T0","T1","T2"]:
            cur=tag_status[tid]; prev=_prev_tag_status[tid]
            if cur!=prev:
                self.right_panel.notify_popups_ble(tid,cur)
                _prev_tag_status[tid]=cur

    def _update_cal_graph_live(self):
        rp = self.right_panel
        if not hasattr(rp, '_bottom_panel_ref') or not rp._bottom_panel_ref: return
        tid = ["T0", "T1", "T2"][rp.ref_tabs.currentIndex()]
        needs_redraw = False
        for aid in ["A0", "A1", "A2", "A3"]:
            raw = tag_data.get(tid, {}).get(aid, -1)
            if raw > 0:
                needs_redraw = True
                break
        if needs_redraw:
            rp._update_cal_graph(self.bottom_panel)

    def _smooth(self, tid, rx, ry):
        mode = self.right_panel._filter_mode
        if mode == "EMA":     return self._ema(tid, rx, ry)
        if mode == "Rolling": return self._rolling(tid, rx, ry)
        if mode == "Kalman":  return self._kalman(tid, rx, ry)
        return rx, ry

    def _ema(self, tid, rx, ry):
        a = getattr(self.right_panel, '_filt_ema_alpha', 0.2)
        p = self._ema_pos[tid]
        if p is None: self._ema_pos[tid] = (rx, ry)
        else: self._ema_pos[tid] = (a*rx+(1-a)*p[0], a*ry+(1-a)*p[1])
        return self._ema_pos[tid]

    def _rolling(self, tid, rx, ry):
        n = int(getattr(self.right_panel, '_filt_roll_n', 8))
        buf = self._roll_buf[tid]
        if buf.maxlen != n:
            self._roll_buf[tid] = deque(list(buf)[-n:], maxlen=n); buf = self._roll_buf[tid]
        buf.append((rx, ry))
        return sum(p[0] for p in buf)/len(buf), sum(p[1] for p in buf)/len(buf)

    def _kalman(self, tid, rx, ry):
        q = getattr(self.right_panel, '_filt_kal_q', 0.1)
        r = getattr(self.right_panel, '_filt_kal_r', 2.0)
        dt = 0.05
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
        if self._kal_state[tid] is None:
            self._kal_state[tid]=[[rx],[ry],[0.0],[0.0]]; self._kal_P[tid]=eye(4)
        x=self._kal_state[tid]; P=self._kal_P[tid]
        xp=mm(F,x); Pp=ma(mm(mm(F,P),mt(F)),Q)
        z=[[rx],[ry]]; yk=ms(z,mm(H,xp))
        S=ma(mm(mm(H,Pp),mt(H)),R); K=mm(mm(Pp,mt(H)),mi2(S))
        xn=ma(xp,mm(K,yk)); Pn=mm(ms(eye(4),mm(K,H)),Pp)
        self._kal_state[tid]=xn; self._kal_P[tid]=Pn
        return xn[0][0], xn[1][0]

    def _reset_filter(self, tid):
        self._ema_pos[tid]=None
        self._roll_buf[tid]=deque(maxlen=20)
        self._kal_state[tid]=None; self._kal_P[tid]=None

    def _rtls_loop(self):
        canvas = self.main_panel.canvas
        rp = self.right_panel
        anchor_positions = {aid: canvas.anchors[aid] for aid in canvas.anchors}

        try:
            h_offset = float(rp._height_offset_edit.text().strip())
        except (ValueError, AttributeError):
            h_offset = 0.0

        tag_positions = {}

        for t_id in ["T0","T1","T2"]:
            if tag_status[t_id] != "Connected":
                if canvas.tag_raw.get(t_id) is not None:
                    self._reset_filter(t_id)
                canvas.tag_raw[t_id] = None
                canvas.tag_cal[t_id] = None
                continue

            raw_d = {}
            for aid in ["A0","A1","A2","A3"]:
                slant = tag_data[t_id][aid]
                if slant > 0:
                    raw_d[aid] = correct_slant_distance(slant, h_offset)

            rx, ry = calc_pos(anchor_positions, raw_d)
            canvas.tag_raw[t_id] = (rx, ry) if rx is not None else None

            cal_d = {}
            for aid, floor_dist in raw_d.items():
                func = rp._cal_funcs.get(t_id, {}).get(aid, lambda x: x)
                try: cal_d[aid] = func(floor_dist)
                except: cal_d[aid] = floor_dist

            cx, cy = calc_pos(anchor_positions, cal_d)
            if cx is not None:
                sx, sy = self._smooth(t_id, cx, cy)
                canvas.tag_cal[t_id] = (round(sx,3), round(sy,3))
                tag_positions[t_id] = canvas.tag_cal[t_id]
            else:
                canvas.tag_cal[t_id] = None

            rp.update_data(
                t_id,
                raw_d,
                cal_d,
                canvas.tag_raw[t_id],
                canvas.tag_cal[t_id]
            )

        # ── Inter-tag distance CSV logging ────────────────────────────────────
        now = time.time()
        pairs = [("T0","T1"), ("T1","T2"), ("T0","T2")]
        for t1, t2 in pairs:
            p1 = tag_positions.get(t1)
            p2 = tag_positions.get(t2)
            if p1 and p2:
                dist = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
                pair_key = f"{t1}-{t2}"
                dt = now - self._last_log_time[pair_key]
                ts = get_est_timestamp()
                write_csv_row(ts, t1, t2, dist, dt)
                self._last_log_time[pair_key] = now

        canvas.update()


def main():
    init_csv()
    app=QApplication(sys.argv); app.setStyleSheet(QSS)
    palette=app.palette()
    palette.setColor(QPalette.ColorRole.Window,     QColor(DARK_BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base,       QColor(PANEL_BG))
    palette.setColor(QPalette.ColorRole.Text,       QColor(TEXT_PRIMARY))
    app.setPalette(palette)
    win=MainWindow(); sys.exit(app.exec())

if __name__=="__main__":
    main()