import tkinter as tk
from tkinter import ttk
import threading
import asyncio
import sys
from bleak import BleakClient

# ==========================================
# BLE CONFIGURATION & STATE
# ==========================================
TAG_MACS = {
    "T0": "DC:B4:D9:22:3B:B9",
    "T1": "DC:B4:D9:22:3A:55",
    "T2": "DC:B4:D9:31:8F:59"
}

CHAR_UUID = "deadbeef-0000-0000-0000-000000000001"

tag_data = {
    "T0": {"A0": -1.0, "A1": -1.0, "A2": -1.0, "A3": -1.0},
    "T1": {"A0": -1.0, "A1": -1.0, "A2": -1.0, "A3": -1.0},
    "T2": {"A0": -1.0, "A1": -1.0, "A2": -1.0, "A3": -1.0}
}

tag_status = {"T0": "Disconnected", "T1": "Disconnected", "T2": "Disconnected"}

is_logging = False


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
            tag_status[tag_name] = "Connecting..."
            async with BleakClient(mac) as client:
                tag_status[tag_name] = "Connected"
                await client.start_notify(CHAR_UUID, notification_handler)
                while client.is_connected:
                    await asyncio.sleep(1)
        except Exception:
            tag_status[tag_name] = "Disconnected"
            tag_data[tag_name] = {"A0": -1.0, "A1": -1.0, "A2": -1.0, "A3": -1.0}
            await asyncio.sleep(3.0)


async def ble_main_loop():
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
# POLYNOMIAL
# ==========================================
def apply_poly(x):
    result = (
        1.46
        + -4.29       * x
        + 4.39        * x**2
        + -1.8        * x**3
        + 0.428       * x**4
        + -0.0626     * x**5
        + 5.81e-03    * x**6
        + -3.44e-04   * x**7
        + 1.25e-05    * x**8
        + -2.57e-07   * x**9
        + 2.26e-09    * x**10
    )
    return max(result, 0.0)


# ==========================================
# UI UPDATE LOOP
# ==========================================
UPDATE_INTERVAL_MS = 50
selected_tag = "T1"
selected_anchor = "A0"


def update_live_feed():
    # Status labels
    for tag, lbl in status_labels.items():
        s = tag_status[tag]
        lbl.config(
            text=f"{tag}: {s}",
            fg="green" if s == "Connected" else ("orange" if "Connecting" in s else "red")
        )

    # Live raw + corrected
    tag = combo_tag.get()
    anchor = combo_anchor.get()
    raw_val = tag_data.get(tag, {}).get(anchor, -1.0)

    if raw_val > 0:
        corrected = apply_poly(raw_val)
        lbl_raw.config(text=f"{raw_val:.4f} ft", fg="black")
        lbl_corrected.config(text=f"{corrected:.4f} ft", fg="green")

        if is_logging:
            log_reading(raw_val, corrected)
    else:
        lbl_raw.config(text="--- ft", fg="gray")
        lbl_corrected.config(text="--- ft", fg="gray")

    root.after(UPDATE_INTERVAL_MS, update_live_feed)


# ==========================================
# LOGGING
# ==========================================
logged_rows = []


def log_reading(raw, corrected):
    row = f"{raw:.4f}\t{corrected:.4f}"
    logged_rows.append(row)
    text_log.config(state=tk.NORMAL)
    text_log.insert(tk.END, row + "\n")
    text_log.see(tk.END)


def toggle_logging():
    global is_logging
    is_logging = not is_logging
    if is_logging:
        btn_log.config(text="Stop Logging", bg="#f1d0d0")
        lbl_log_status.config(text="Logging...", fg="orange")
    else:
        btn_log.config(text="Start Logging", bg="#d0e8f1")
        lbl_log_status.config(text=f"Stopped. {len(logged_rows)} rows captured.", fg="gray")


def clear_log():
    global logged_rows
    logged_rows = []
    text_log.config(state=tk.NORMAL)
    text_log.delete("1.0", tk.END)
    text_log.insert(tk.END, "Raw_ft\tCorrected_ft\n")
    lbl_log_status.config(text="Cleared.", fg="gray")


def run_manual_conversion():
    text_log.config(state=tk.NORMAL)
    raw_text = text_manual_input.get("1.0", tk.END).strip()
    if not raw_text:
        return
    text_log.delete("1.0", tk.END)
    text_log.insert(tk.END, "Raw_ft\tCorrected_ft\n")
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            x = float(line)
            y = apply_poly(x)
            text_log.insert(tk.END, f"{x:.4f}\t{y:.4f}\n")
        except ValueError:
            text_log.insert(tk.END, f"ERROR\t'{line}'\n")
    text_log.see(tk.END)


# ==========================================
# GUI
# ==========================================
threading.Thread(target=run_ble_thread, daemon=True).start()

root = tk.Tk()
root.title("UWB Polynomial Converter — BLE Live")
root.geometry("700x800")

# --- BLE Status ---
frame_status = tk.LabelFrame(root, text="BLE Connection Status", font=("Arial", 10, "bold"), padx=10, pady=8)
frame_status.pack(fill=tk.X, padx=15, pady=(15, 5))

status_labels = {}
for i, tag in enumerate(TAG_MACS):
    lbl = tk.Label(frame_status, text=f"{tag}: Disconnected", font=("Arial", 10, "bold"), fg="red")
    lbl.grid(row=0, column=i, padx=20)
    status_labels[tag] = lbl

# --- Live Feed ---
frame_live = tk.LabelFrame(root, text="Live Feed", font=("Arial", 10, "bold"), padx=10, pady=10)
frame_live.pack(fill=tk.X, padx=15, pady=5)

frame_selectors = tk.Frame(frame_live)
frame_selectors.pack(anchor="w", pady=(0, 8))

tk.Label(frame_selectors, text="Tag:", font=("Arial", 9)).grid(row=0, column=0, sticky="e")
combo_tag = ttk.Combobox(frame_selectors, values=list(TAG_MACS.keys()), state="readonly", width=5)
combo_tag.set("T1")
combo_tag.grid(row=0, column=1, padx=(3, 15))

tk.Label(frame_selectors, text="Anchor:", font=("Arial", 9)).grid(row=0, column=2, sticky="e")
combo_anchor = ttk.Combobox(frame_selectors, values=["A0", "A1", "A2", "A3"], state="readonly", width=5)
combo_anchor.set("A0")
combo_anchor.grid(row=0, column=3, padx=3)

frame_vals = tk.Frame(frame_live)
frame_vals.pack(anchor="w")

tk.Label(frame_vals, text="Raw:", font=("Arial", 10)).grid(row=0, column=0, sticky="e", padx=(0, 8))
lbl_raw = tk.Label(frame_vals, text="--- ft", font=("Consolas", 14), fg="gray")
lbl_raw.grid(row=0, column=1, sticky="w")

tk.Label(frame_vals, text="Corrected:", font=("Arial", 10)).grid(row=1, column=0, sticky="e", padx=(0, 8), pady=5)
lbl_corrected = tk.Label(frame_vals, text="--- ft", font=("Consolas", 16, "bold"), fg="green")
lbl_corrected.grid(row=1, column=1, sticky="w")

# --- Live Logging ---
frame_logging = tk.LabelFrame(root, text="Live Logger", font=("Arial", 10, "bold"), padx=10, pady=8)
frame_logging.pack(fill=tk.X, padx=15, pady=5)

frame_log_btns = tk.Frame(frame_logging)
frame_log_btns.pack(fill=tk.X)

btn_log = tk.Button(frame_log_btns, text="Start Logging", font=("Arial", 10, "bold"),
                    bg="#d0e8f1", command=toggle_logging)
btn_log.grid(row=0, column=0, padx=(0, 10))

btn_clear = tk.Button(frame_log_btns, text="Clear", font=("Arial", 9), fg="red", command=clear_log)
btn_clear.grid(row=0, column=1)

lbl_log_status = tk.Label(frame_log_btns, text="", font=("Arial", 9), fg="gray")
lbl_log_status.grid(row=0, column=2, padx=15)

# --- Manual Input ---
frame_manual = tk.LabelFrame(root, text="Manual Paste Converter (one raw value per line)", font=("Arial", 10, "bold"), padx=10, pady=8)
frame_manual.pack(fill=tk.X, padx=15, pady=5)

text_manual_input = tk.Text(frame_manual, font=("Consolas", 10), height=4, bg="#f9f9f9")
text_manual_input.pack(fill=tk.X)

tk.Button(frame_manual, text="Convert Pasted Values", font=("Arial", 9, "bold"),
          bg="#d8f1d0", command=run_manual_conversion).pack(anchor="w", pady=5)

# --- Output Table ---
frame_table = tk.LabelFrame(root, text="Output Table (copy-pasteable)", font=("Arial", 10, "bold"), padx=10, pady=8)
frame_table.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 15))

text_log = tk.Text(frame_table, font=("Consolas", 11), bg="#fffbe6")
text_log.pack(fill=tk.BOTH, expand=True)
text_log.insert(tk.END, "Raw_ft\tCorrected_ft\n")

root.after(UPDATE_INTERVAL_MS, update_live_feed)
root.mainloop()