import tkinter as tk
from tkinter import ttk
import random
import numpy as np
import warnings
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import asyncio
import sys
from bleak import BleakClient

# Handle NumPy 2.0+ RankWarning location change
try:
    from numpy.exceptions import RankWarning
except ImportError:
    from numpy import RankWarning

warnings.simplefilter('ignore', RankWarning)

# ==========================================
# BLE CONFIGURATION & STATE
# ==========================================
TAG_MACS = {
    "T0": "DC:B4:D9:22:3B:B9",
    "T1": "DC:B4:D9:22:3A:55",
    "T2": "DC:B4:D9:31:8F:59"
}

CHAR_UUID = "deadbeef-0000-0000-0000-000000000001"

# Framework for all tags/anchors is preserved
tag_data = {
    "T0": {"A0": -1.0, "A1": -1.0, "A2": -1.0, "A3": -1.0},
    "T1": {"A0": -1.0, "A1": -1.0, "A2": -1.0, "A3": -1.0},
    "T2": {"A0": -1.0, "A1": -1.0, "A2": -1.0, "A3": -1.0}
}

tag_status = {"T0": "Disconnected", "T1": "Disconnected", "T2": "Disconnected"}


# --- BLE Async Threading ---
def parse_and_store(data_str):
    """Parses the BLE string (e.g., T0 | A0:3.50 | A1:---) into the dictionary."""
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
            print(f"[*] Connecting to {tag_name} [{mac}]...")
            tag_status[tag_name] = "Connecting..."
            async with BleakClient(mac) as client:
                print(f"[+] {tag_name} Connected!")
                tag_status[tag_name] = "Connected"
                await client.start_notify(CHAR_UUID, notification_handler)
                while client.is_connected:
                    await asyncio.sleep(1)
        except Exception as e:
            tag_status[tag_name] = "Disconnected"
            tag_data[tag_name] = {"A0": -1.0, "A1": -1.0, "A2": -1.0, "A3": -1.0}
            print(f"[-] {tag_name} dropped. Reconnecting in 3s...")
            await asyncio.sleep(3.0)


async def ble_main_loop():
    print("Initializing BLE Background Service...")
    tasks = []
    for name, mac in TAG_MACS.items():
        tasks.append(asyncio.create_task(connect_and_listen(name, mac)))
        await asyncio.sleep(3.0)  # Stagger connections to prevent radio dropouts
    await asyncio.gather(*tasks)


def run_ble_thread():
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(ble_main_loop())


# ==========================================
# CALIBRATION TOOL
# ==========================================
UPDATE_INTERVAL_MS = 50
calibration_points = []
eval_func = lambda x: x
current_raw = 0.0
is_capturing = False


def compute_true_distance():
    """Reads X (horizontal) and Y (elevation) fields and returns sqrt(x^2 + y^2)."""
    try:
        x = float(entry_dist_x.get())
        y = float(entry_dist_y.get())
        return np.sqrt(x**2 + y**2)
    except ValueError:
        return None


def on_xy_change(*args):
    """Updates the computed true distance label whenever X or Y changes."""
    result = compute_true_distance()
    if result is not None:
        lbl_true_computed.config(text=f"True Dist: {result:.3f} ft", fg="#006600")
    else:
        lbl_true_computed.config(text="True Dist: ---", fg="gray")


def update_live_feed():
    """Pulls data directly from the BLE dictionary for T0->A0 and updates UI."""
    global current_raw

    # 1. Update BLE Connection Status UI
    t0_status = tag_status["T1"]
    lbl_ble_status.config(
        text=f"BLE T1 Status: {t0_status}",
        fg="green" if t0_status == "Connected" else ("orange" if "Connecting" in t0_status else "red")
    )

    # 2. Extract specific TWR Data (T1 to A0)
    raw_val = tag_data["T1"]["A0"]
    if raw_val > 0:
        current_raw = raw_val

    # 3. Apply the Calibration Equation dynamically
    try:
        calibrated_value = eval_func(current_raw)
    except Exception:
        calibrated_value = 0.0

    # 4. Update the Live Feed UI text
    lbl_raw_feed.config(text=f"{current_raw:.2f} ft")
    lbl_cal_feed.config(text=f"{calibrated_value:.2f} ft")

    # 5. Update the live green dot on the graph
    if raw_val > 0 or t0_status == "Connected":
        live_dot.set_data([current_raw], [calibrated_value])
        canvas.draw_idle()

    # 6. Loop
    root.after(UPDATE_INTERVAL_MS, update_live_feed)


def get_best_fit_mode_and_params():
    """Evaluates all regression models AND their parameters using BIC."""
    if len(calibration_points) < 3:
        return fit_mode_var.get(), {}

    pts = sorted(calibration_points)
    X = np.array([p[0] for p in pts], dtype=float)
    Y = np.array([p[1] for p in pts], dtype=float)
    n = len(X)

    best_mode = fit_mode_var.get()
    best_params = {}
    best_bic = float('inf')

    modes_to_try = ["Linear", "Exponential", "Polynomial", "Logarithmic", "Power Series", "Moving Average"]

    for mode in modes_to_try:
        try:
            if mode == "Linear":
                m, b = np.polyfit(X, Y, 1)
                Y_pred = m * X + b
                ssr = np.sum((Y - Y_pred) ** 2)
                bic = n * np.log(max(ssr, 1e-10) / n) + 2 * np.log(n)
                if bic < best_bic:
                    best_bic, best_mode, best_params = bic, mode, {}

            elif mode == "Exponential":
                valid = Y > 0
                if sum(valid) > 2:
                    b, ln_a = np.polyfit(X[valid], np.log(Y[valid]), 1)
                    Y_pred = np.exp(ln_a) * np.exp(b * X)
                    ssr = np.sum((Y - Y_pred) ** 2)
                    bic = n * np.log(max(ssr, 1e-10) / n) + 2 * np.log(n)
                    if bic < best_bic:
                        best_bic, best_mode, best_params = bic, mode, {}

            elif mode == "Logarithmic":
                valid = X > 0
                if sum(valid) > 2:
                    a, b = np.polyfit(np.log(X[valid]), Y[valid], 1)
                    Y_pred = np.where(X > 0, a * np.log(np.maximum(X, 1e-10)) + b, 0)
                    ssr = np.sum((Y - Y_pred) ** 2)
                    bic = n * np.log(max(ssr, 1e-10) / n) + 2 * np.log(n)
                    if bic < best_bic:
                        best_bic, best_mode, best_params = bic, mode, {}

            elif mode == "Power Series":
                valid = (X > 0) & (Y > 0)
                if sum(valid) > 2:
                    b, ln_a = np.polyfit(np.log(X[valid]), np.log(Y[valid]), 1)
                    Y_pred = np.where(X > 0, np.exp(ln_a) * (np.maximum(X, 1e-10) ** b), 0)
                    ssr = np.sum((Y - Y_pred) ** 2)
                    bic = n * np.log(max(ssr, 1e-10) / n) + 2 * np.log(n)
                    if bic < best_bic:
                        best_bic, best_mode, best_params = bic, mode, {}

            elif mode == "Polynomial":
                max_d = min(10, n - 2)
                if max_d >= 2:
                    for d in range(2, max_d + 1):
                        coeffs = np.polyfit(X, Y, d)
                        Y_pred = sum(coeffs[i] * (X ** (d - i)) for i in range(d + 1))
                        ssr = np.sum((Y - Y_pred) ** 2)
                        k = d + 1
                        bic = n * np.log(max(ssr, 1e-10) / n) + k * np.log(n)
                        if bic < best_bic:
                            best_bic, best_mode, best_params = bic, mode, {"degree": d}

            elif mode == "Moving Average":
                for p in [2, 3, 4, 5, 6, 8, 10]:
                    if p > n: continue
                    for ma_type in ["Trailing", "Centered"]:
                        ma_X, ma_Y = [], []
                        for i in range(len(X)):
                            if ma_type == "Trailing":
                                start = max(0, i - p + 1)
                                end = i + 1
                            else:
                                half = p // 2
                                start = max(0, i - half)
                                end = min(len(X), i + half + 1)
                            segment = Y[start:end]
                            ma_X.append(X[i])
                            ma_Y.append(sum(segment) / len(segment))

                        if len(ma_X) > 1:
                            Y_pred = np.interp(X, ma_X, ma_Y)
                            ssr = np.sum((Y - Y_pred) ** 2)
                            k = n / p
                            bic = n * np.log(max(ssr, 1e-10) / n) + k * np.log(n)
                            if bic < best_bic:
                                best_bic, best_mode, best_params = bic, mode, {"period": p, "type": ma_type}
        except Exception:
            pass

    return best_mode, best_params


def on_fit_mode_change(event=None):
    mode = fit_mode_var.get()
    frame_poly_opts.pack_forget()
    frame_ma_opts.pack_forget()

    if mode == "Polynomial":
        frame_poly_opts.pack(pady=(0, 10))
    elif mode == "Moving Average":
        frame_ma_opts.pack(pady=(0, 10))

    calculate_calibration()


def on_manual_eq_edit(event=None):
    global eval_func
    if default_preset_var.get():
        default_preset_var.set(False)

    eq_string = text_equation.get("1.0", tk.END).strip()
    if any(keyword in eq_string for keyword in ["Moving Average", "Not enough data", "Error", "Capped", "Preset"]):
        text_equation.config(fg="gray")
        return

    safe_str = eq_string.replace('^', '**')
    math_env = {
        "ln": np.log, "log": np.log10, "e": np.e, "pi": np.pi,
        "sin": np.sin, "cos": np.cos, "tan": np.tan,
        "abs": abs, "sqrt": np.sqrt
    }
    try:
        code_obj = compile(safe_str, '<string>', 'eval')
        test_env = dict(math_env, Raw=1.0)
        eval(code_obj, {"__builtins__": {}}, test_env)
        text_equation.config(fg="black")

        def manual_func(raw_val):
            try:
                env = dict(math_env, Raw=float(raw_val))
                return float(eval(code_obj, {"__builtins__": {}}, env))
            except:
                return 0.0

        eval_func = manual_func
        update_graph_static_elements(is_manual=True)
    except SyntaxError:
        text_equation.config(fg="red")
    except Exception:
        text_equation.config(fg="red")


def calculate_calibration(*args):
    global eval_func

    if default_preset_var.get():
        eval_func = lambda x: (0.7514969 * x) + 0.0295246
        text_equation.delete("1.0", tk.END)
        text_equation.insert("1.0", "True = (0.7514969 * Raw) + 0.0295246")
        text_equation.config(fg="purple")
        update_graph_static_elements(is_preset=True)
        return

    n = len(calibration_points)
    mode = fit_mode_var.get()
    eq_text = "Raw (Not enough data)"
    eval_func = lambda x: x

    if n == 1:
        offset = calibration_points[0][1] - calibration_points[0][0]
        eval_func = lambda x, o=offset: x + o
        eq_text = f"Raw + {offset:.4f}"
    elif n > 1:
        X = np.array([p[0] for p in calibration_points], dtype=float)
        Y = np.array([p[1] for p in calibration_points], dtype=float)

        try:
            if mode == "Linear":
                m, b = np.polyfit(X, Y, 1)
                eval_func = lambda x, m=m, b=b: m * x + b
                eq_text = f"({m:.4f} * Raw) + {b:.4f}"
            elif mode == "Exponential":
                valid = Y > 0
                if sum(valid) > 1:
                    b, ln_a = np.polyfit(X[valid], np.log(Y[valid]), 1)
                    a = np.exp(ln_a)
                    eval_func = lambda x, a=a, b=b: a * np.exp(b * x)
                    eq_text = f"{a:.4f} * e^({b:.4f} * Raw)"
                else:
                    eq_text = "Error: Exponential requires True Dist > 0"
            elif mode == "Polynomial":
                try:
                    requested_degree = int(spin_poly_degree.get())
                except ValueError:
                    requested_degree = 2
                max_possible_degree = len(X) - 1
                degree = min(requested_degree, max_possible_degree)
                if degree < 1: degree = 1
                coeffs = np.polyfit(X, Y, degree)

                def make_poly_func(c, d):
                    return lambda x: sum(c[i] * (x ** (d - i)) for i in range(d + 1))

                eval_func = make_poly_func(coeffs, degree)
                terms = []
                for i, c_val in enumerate(coeffs):
                    power = degree - i
                    if power > 1:
                        terms.append(f"{c_val:.4f}*Raw^{power}")
                    elif power == 1:
                        terms.append(f"{c_val:.4f}*Raw")
                    else:
                        terms.append(f"{c_val:.4f}")
                full_eq = " + ".join(terms)
                if requested_degree > max_possible_degree:
                    eq_text = full_eq + f"\n\n(Capped at d={degree}: Need {requested_degree + 1} points for d={requested_degree})"
                else:
                    eq_text = full_eq
            elif mode == "Logarithmic":
                valid = X > 0
                if sum(valid) > 1:
                    a, b = np.polyfit(np.log(X[valid]), Y[valid], 1)
                    eval_func = lambda x, a=a, b=b: a * np.log(x) + b if x > 0 else 0
                    eq_text = f"{a:.4f} * ln(Raw) + {b:.4f}"
                else:
                    eq_text = "Error: Logarithmic requires Raw Dist > 0"
            elif mode == "Power Series":
                valid = (X > 0) & (Y > 0)
                if sum(valid) > 1:
                    b, ln_a = np.polyfit(np.log(X[valid]), np.log(Y[valid]), 1)
                    a = np.exp(ln_a)
                    eval_func = lambda x, a=a, b=b: a * (x ** b) if x > 0 else 0
                    eq_text = f"{a:.4f} * Raw^{b:.4f}"
                else:
                    eq_text = "Error: Power requires Raw > 0, True > 0"
            elif mode == "Moving Average":
                try:
                    window = int(combo_ma_period.get())
                except ValueError:
                    window = 2
                actual_window = min(window, len(X))
                ma_type = combo_ma_type.get()
                pts = sorted(zip(X, Y))
                sX = np.array([p[0] for p in pts])
                sY = np.array([p[1] for p in pts])
                ma_X, ma_Y = [], []
                for i in range(len(sX)):
                    if ma_type == "Trailing":
                        start_idx = max(0, i - actual_window + 1)
                        end_idx = i + 1
                    else:
                        half = actual_window // 2
                        start_idx = max(0, i - half)
                        end_idx = min(len(sX), i + half + 1)
                    segment = sY[start_idx:end_idx]
                    ma_X.append(sX[i])
                    ma_Y.append(sum(segment) / len(segment))

                if len(ma_X) > 1:
                    eval_func = lambda x, mx=ma_X, my=ma_Y: np.interp(x, mx, my)
                elif len(ma_X) == 1:
                    eval_func = lambda x, my=ma_Y[0]: my

                if window > len(X):
                    eq_text = f"{ma_type} MA (Period={actual_window})\n(Capped: Need {window} points for Period {window})"
                else:
                    eq_text = f"{ma_type} Moving Average (Period={actual_window})"
        except Exception:
            eq_text = f"Math Error: Data shape unsupported"

    text_equation.delete("1.0", tk.END)
    text_equation.insert("1.0", eq_text)
    text_equation.config(fg="blue")
    update_graph_static_elements()


def update_graph_static_elements(is_manual=False, is_preset=False):
    if calibration_points:
        x_vals = [p[0] for p in calibration_points]
        y_vals = [p[1] for p in calibration_points]
        scatter_points.set_data(x_vals, y_vals)
    else:
        scatter_points.set_data([], [])

    line_x = np.linspace(0.01, 30, 100)
    line_y = []
    for x in line_x:
        try:
            line_y.append(eval_func(x))
        except:
            line_y.append(0)

    fit_line.set_data(line_x, line_y)

    mode_str = fit_mode_var.get()
    if is_preset:
        mode_str = "Default Hardware Preset"
    elif is_manual:
        mode_str = "Manual Override"
    elif mode_str == "Polynomial":
        mode_str += f" (d={min(int(spin_poly_degree.get() if spin_poly_degree.get() else 1), len(calibration_points) - 1)})"
    elif mode_str == "Moving Average":
        mode_str = f"{combo_ma_type.get()[:4]}. MA ({min(int(combo_ma_period.get() if combo_ma_period.get() else 2), len(calibration_points))})"

    fit_line.set_label(f'Curve: {mode_str}')
    ax.legend(loc='upper left')
    canvas.draw_idle()


# --- MULTI-SAMPLE CAPTURE ---
def trigger_capture_sequence():
    global is_capturing
    if is_capturing: return

    true_dist = compute_true_distance()
    if true_dist is None:
        print("Cannot capture: Enter valid X and Y distances.")
        return
    if true_dist <= 0:
        print("Cannot capture: True distance must be greater than 0.")
        return

    try:
        num_samples = int(combo_samples.get())
    except ValueError:
        return

    if current_raw <= 0.0:
        print("Cannot capture: No valid UWB data reading.")
        return

    is_capturing = True
    btn_add.config(state=tk.DISABLED, text="Capturing...")
    capture_scatter.set_data([], [])
    capture_loop(true_dist, num_samples, [])


def capture_loop(true_dist, target_samples, captured_data):
    if current_raw > 0:
        captured_data.append(current_raw)

    capture_scatter.set_data(captured_data, [true_dist] * len(captured_data))
    canvas.draw_idle()

    if len(captured_data) < target_samples:
        root.after(UPDATE_INTERVAL_MS, capture_loop, true_dist, target_samples, captured_data)
    else:
        btn_add.config(text="Fusing...")
        animate_fusion(true_dist, captured_data, 0)


def animate_fusion(true_dist, captured_data, frame):
    global is_capturing
    total_frames = 15
    mean_raw = sum(captured_data) / len(captured_data)

    if frame <= total_frames:
        t = frame / float(total_frames)
        animated_x = [x + (mean_raw - x) * t for x in captured_data]
        capture_scatter.set_data(animated_x, [true_dist] * len(captured_data))
        canvas.draw_idle()
        root.after(30, animate_fusion, true_dist, captured_data, frame + 1)
    else:
        capture_scatter.set_data([], [])
        canvas.draw_idle()
        calibration_points.append((mean_raw, true_dist))

        # Show the X, Y components in the listbox for clarity
        try:
            x_val = float(entry_dist_x.get())
            y_val = float(entry_dist_y.get())
            label_str = (f"Raw (Mean of {len(captured_data)}): {mean_raw:.2f} ft -> "
                         f"True: {true_dist:.3f} ft  [X={x_val:.2f}, Y={y_val:.2f}]")
        except ValueError:
            label_str = f"Raw (Mean of {len(captured_data)}): {mean_raw:.2f} ft -> True: {true_dist:.3f} ft"

        listbox_points.insert(tk.END, label_str)
        listbox_points.yview(tk.END)

        # Clear the input fields after capture
        entry_dist_x.delete(0, tk.END)
        entry_dist_y.delete(0, tk.END)
        lbl_true_computed.config(text="True Dist: ---", fg="gray")

        if auto_recommend_var.get() and not default_preset_var.get():
            best_mode, best_params = get_best_fit_mode_and_params()
            if best_mode != fit_mode_var.get():
                fit_mode_var.set(best_mode)
            if best_mode == "Polynomial" and "degree" in best_params:
                spin_poly_degree.delete(0, tk.END)
                spin_poly_degree.insert(0, str(best_params["degree"]))
            elif best_mode == "Moving Average":
                if "period" in best_params:
                    combo_ma_period.set(str(best_params["period"]))
                if "type" in best_params:
                    combo_ma_type.set(best_params["type"])
            on_fit_mode_change()
        else:
            calculate_calibration()

        is_capturing = False
        btn_add.config(state=tk.NORMAL, text="Add Point")


def clear_calibration():
    calibration_points.clear()
    listbox_points.delete(0, tk.END)
    calculate_calibration()


# ==========================================
# GUI SETUP
# ==========================================
# Start BLE Background Thread
threading.Thread(target=run_ble_thread, daemon=True).start()

root = tk.Tk()
root.title("Hardware UWB Trendline Calibrator (BLE: T1 -> A0)")
root.geometry("1050x700")

frame_left = tk.Frame(root, padx=15, pady=15, width=430)
frame_left.pack(side=tk.LEFT, fill=tk.Y)
frame_left.pack_propagate(False)
frame_right = tk.Frame(root, padx=10, pady=10)
frame_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

auto_recommend_var = tk.BooleanVar(value=True)
default_preset_var = tk.BooleanVar(value=False)

# Editable Equation Section
frame_eq_top = tk.Frame(frame_left)
frame_eq_top.pack(fill=tk.X, pady=(0, 2))
tk.Label(frame_eq_top, text="Calibration Equation (Editable):", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
chk_default = tk.Checkbutton(frame_eq_top, text="Default Preset", variable=default_preset_var,
                             font=("Arial", 8, "bold"), fg="purple", command=calculate_calibration)
chk_default.pack(side=tk.RIGHT, padx=5)
btn_reset_eq = tk.Button(frame_eq_top, text="⟲ Reset Auto", font=("Arial", 8, "bold"), fg="#555555",
                         command=lambda: [default_preset_var.set(False), calculate_calibration()])
btn_reset_eq.pack(side=tk.RIGHT)

frame_eq_input = tk.Frame(frame_left)
frame_eq_input.pack(fill=tk.X, pady=(0, 15))
tk.Label(frame_eq_input, text="True =", font=("Consolas", 11, "bold")).pack(side=tk.LEFT, anchor="nw")
text_equation = tk.Text(frame_eq_input, font=("Consolas", 10, "bold"), fg="blue", height=3, wrap=tk.WORD)
text_equation.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
text_equation.bind("<KeyRelease>", on_manual_eq_edit)

# Live Feed Section
frame_feed = tk.LabelFrame(frame_left, text="Live Hardware Feed (BLE: T1)", font=("Arial", 10, "bold"), padx=10, pady=10)
frame_feed.pack(fill=tk.X, pady=10)

lbl_ble_status = tk.Label(frame_feed, text="BLE T0 Status: Disconnected", fg="red", font=("Arial", 9, "bold"))
lbl_ble_status.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

tk.Label(frame_feed, text="Raw Input (T1->A0):", font=("Arial", 10)).grid(row=1, column=0, sticky="e")
lbl_raw_feed = tk.Label(frame_feed, text="0.00 ft", font=("Consolas", 14), fg="gray")
lbl_raw_feed.grid(row=1, column=1, padx=20)

tk.Label(frame_feed, text="Calibrated Output:", font=("Arial", 10)).grid(row=2, column=0, sticky="e", pady=10)
lbl_cal_feed = tk.Label(frame_feed, text="0.00 ft", font=("Consolas", 16, "bold"), fg="green")
lbl_cal_feed.grid(row=2, column=1, padx=20, pady=10)

# Fit Mode Dropdown Section
frame_fit_mode_top = tk.Frame(frame_left)
frame_fit_mode_top.pack(fill=tk.X, pady=(0, 2))
tk.Label(frame_fit_mode_top, text="Calibration Curve Type:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
chk_auto = tk.Checkbutton(frame_fit_mode_top, text="Auto-Recommend", variable=auto_recommend_var, font=("Arial", 8))
chk_auto.pack(side=tk.RIGHT)
fit_mode_var = tk.StringVar(value="Polynomial")
combo_fit = ttk.Combobox(frame_left, textvariable=fit_mode_var, state="readonly", font=("Arial", 10))
combo_fit['values'] = ("Linear", "Exponential", "Polynomial", "Logarithmic", "Power Series", "Moving Average")
combo_fit.pack(pady=(0, 5), fill=tk.X)
combo_fit.bind("<<ComboboxSelected>>", on_fit_mode_change)

# Dynamic Options
frame_options_container = tk.Frame(frame_left)
frame_options_container.pack(fill=tk.X)
frame_poly_opts = tk.Frame(frame_options_container)
tk.Label(frame_poly_opts, text="Degree:", font=("Arial", 9)).pack(side=tk.LEFT)
spin_poly_degree = tk.Spinbox(frame_poly_opts, from_=1, to=20, width=5, command=calculate_calibration)
spin_poly_degree.delete(0, tk.END)
spin_poly_degree.insert(0, "4")
spin_poly_degree.pack(side=tk.LEFT, padx=5)
spin_poly_degree.bind("<KeyRelease>", calculate_calibration)

frame_ma_opts = tk.Frame(frame_options_container)
combo_ma_type = ttk.Combobox(frame_ma_opts, values=["Trailing", "Centered"], state="readonly", width=8)
combo_ma_type.set("Trailing")
combo_ma_type.pack(side=tk.LEFT, padx=2)
combo_ma_type.bind("<<ComboboxSelected>>", calculate_calibration)
combo_ma_period = ttk.Combobox(frame_ma_opts, values=["2", "3", "4", "5", "6", "8", "10"], state="readonly", width=3)
combo_ma_period.set("4")
combo_ma_period.pack(side=tk.LEFT, padx=2)
combo_ma_period.bind("<<ComboboxSelected>>", calculate_calibration)

# ==========================================
# Calibration Capture — Pythagorean Input
# ==========================================
frame_cal = tk.LabelFrame(frame_left, text="Multi-Sample Capture", font=("Arial", 10, "bold"), padx=10, pady=10)
frame_cal.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

# Row 0: X and Y distance inputs
frame_cal_inputs = tk.Frame(frame_cal)
frame_cal_inputs.pack(fill=tk.X, pady=(0, 4))

tk.Label(frame_cal_inputs, text="Horiz (X):", font=("Arial", 9)).grid(row=0, column=0, sticky="e")
entry_dist_x = tk.Entry(frame_cal_inputs, width=6, font=("Consolas", 12))
entry_dist_x.grid(row=0, column=1, padx=(3, 8))
entry_dist_x.bind("<KeyRelease>", on_xy_change)

tk.Label(frame_cal_inputs, text="Elev (Y):", font=("Arial", 9)).grid(row=0, column=2, sticky="e")
entry_dist_y = tk.Entry(frame_cal_inputs, width=6, font=("Consolas", 12))
entry_dist_y.grid(row=0, column=3, padx=(3, 0))
entry_dist_y.bind("<KeyRelease>", on_xy_change)

# Row 1: Computed true distance display
frame_true_display = tk.Frame(frame_cal)
frame_true_display.pack(fill=tk.X, pady=(0, 6))
lbl_true_computed = tk.Label(
    frame_true_display,
    text="True Dist: ---",
    font=("Consolas", 11, "bold"),
    fg="gray"
)
lbl_true_computed.pack(side=tk.LEFT, padx=2)

# Row 2: Samples + Add Point button
frame_cal_actions = tk.Frame(frame_cal)
frame_cal_actions.pack(fill=tk.X, pady=(0, 6))

tk.Label(frame_cal_actions, text="Samples:").grid(row=0, column=0, sticky="e")
combo_samples = ttk.Combobox(frame_cal_actions, values=["1", "5", "10", "20", "50", "100"], state="readonly", width=4)
combo_samples.set("20")
combo_samples.grid(row=0, column=1, padx=5)
btn_add = tk.Button(frame_cal_actions, text="Add Point", bg="#d0e8f1", font=("Arial", 9, "bold"),
                    command=trigger_capture_sequence)
btn_add.grid(row=0, column=2, padx=(10, 0))

listbox_points = tk.Listbox(frame_cal, height=4, font=("Consolas", 9))
listbox_points.pack(fill=tk.BOTH, expand=True, pady=5)
btn_clear = tk.Button(frame_cal, text="Clear Data", fg="red", command=clear_calibration)
btn_clear.pack(pady=2)

# Graph
fig, ax = plt.subplots(figsize=(6, 5), dpi=100)
fig.patch.set_facecolor('#f0f0f0')
ax.set_title("Hardware Calibration Curve Mapping (BLE: T1)", fontsize=12, fontweight='bold')
ax.set_xlabel("Raw UWB Distance (ft)")
ax.set_ylabel("True Calibrated Distance (ft)")
ax.set_xlim(0, 30)
ax.set_ylim(0, 30)
ax.grid(True, linestyle='--', alpha=0.6)
capture_scatter, = ax.plot([], [], 'co', markersize=5, alpha=0.5, label='Capturing...', zorder=3)
scatter_points, = ax.plot([], [], 'ro', markersize=6, label='Saved Points', zorder=5)
fit_line, = ax.plot([], [], 'b-', linewidth=2, label='Curve: Polynomial', zorder=4)
live_dot, = ax.plot([], [], 'go', markersize=10, label='Live Sensor Reading', zorder=6)
ax.legend(loc='upper left')
canvas = FigureCanvasTkAgg(fig, master=frame_right)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

on_fit_mode_change()
root.after(UPDATE_INTERVAL_MS, update_live_feed)
root.mainloop()