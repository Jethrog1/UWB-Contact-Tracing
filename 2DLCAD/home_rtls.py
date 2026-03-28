import json
import os
import tkinter as tk
from tkinter import ttk, messagebox

# Window / app setup
APP_TITLE = "RTLS User Profile Manager"
DIR_PATH = r"C:\RTLS\User_info"
FILE_PATH = os.path.join(DIR_PATH, "user_info.json")

DEVICE_TYPES = ["Wrist Band", "Arm Band", "Belt Clip-on", "Breast Pocket"]
STATUS_TYPES = ["Active", "Inactive", "Maintenance", "Lost"]

DEFAULT_DATA = {
    "sailors": [],
    "rooms": []
}


# File I/O
def ensure_json_file():
    os.makedirs(DIR_PATH, exist_ok=True)
    if not os.path.exists(FILE_PATH):
        with open(FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_DATA, f, indent=4)


def load_json():
    ensure_json_file()
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = DEFAULT_DATA.copy()

    if "sailors" not in data or not isinstance(data["sailors"], list):
        data["sailors"] = []
    if "rooms" not in data or not isinstance(data["rooms"], list):
        data["rooms"] = []
    return data


def save_json(data):
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# Record templates
def empty_sailor(tag_id=""):
    return {
        "tag_id": tag_id,
        "identity": {
            "profile_id": "",
            "name": "",
            "height_ft": "",
            "description": ""
        },
        "device": {
            "mac_address": "",
            "device_type": DEVICE_TYPES[0],
            "wrist_to_floor_ft": "",
            "arm_to_floor_ft": "",
            "hip_to_floor_ft": "",
            "breast_to_floor_ft": "",
            "description": ""
        },
        "calibration": {
            "equations": {
                "A0": "",
                "A1": "",
                "A2": "",
                "A3": ""
            },
            "last_calibration_date": ""
        },
        "history": {
            "disease_type": "",
            "close_contact_threshold": "",
            "duration_threshold": ""
        },
        "status": {
            "state": STATUS_TYPES[0]
        },
        "notes": ""
    }


def empty_room():
    return {
        "room_id": "",
        "room": {
            "description": "",
            "dimensions_ft": {
                "width": "",
                "height": ""
            },
            "anchor_placement": {
                "A0": "",
                "A1": "",
                "A2": "",
                "A3": ""
            },
            "anchor_elevation_ft": ""
        },
        "notes": ""
    }


# Search helpers
def find_sailor_index(data, search_text):
    s = search_text.strip().lower()
    if not s:
        return None
    for i, sailor in enumerate(data["sailors"]):
        tag_id = str(sailor.get("tag_id", "")).strip().lower()
        profile_id = str(sailor.get("identity", {}).get("profile_id", "")).strip().lower()
        name = str(sailor.get("identity", {}).get("name", "")).strip().lower()
        if s in (tag_id, profile_id, name):
            return i
    return None


def find_room_index(data, search_text):
    s = search_text.strip().lower()
    if not s:
        return None
    for i, room in enumerate(data["rooms"]):
        room_id = str(room.get("room_id", "")).strip().lower()
        desc = str(room.get("room", {}).get("description", "")).strip().lower()
        if s in (room_id, desc):
            return i
    return None


def get_next_tag_id(data):
    used = set()
    for sailor in data["sailors"]:
        tid = str(sailor.get("tag_id", "")).strip().upper()
        if tid.startswith("T"):
            try:
                used.add(int(tid[1:]))
            except ValueError:
                pass
    n = 0
    while n in used:
        n += 1
    return f"T{n}"


# Reusable UI sections
class LabeledEntry(tk.Frame):
    def __init__(self, parent, label_text, width=32):
        super().__init__(parent, bg=parent.cget("bg"))
        self.label = tk.Label(self, text=label_text, anchor="w", bg=parent.cget("bg"))
        self.label.pack(side="left", padx=(0, 10))
        self.entry = tk.Entry(self, width=width)
        self.entry.pack(side="right", fill="x", expand=True)

    def get(self):
        return self.entry.get().strip()

    def set(self, value):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, "" if value is None else str(value))

    def clear(self):
        self.entry.delete(0, tk.END)


class LabeledCombo(tk.Frame):
    def __init__(self, parent, label_text, values, width=29):
        super().__init__(parent, bg=parent.cget("bg"))
        self.label = tk.Label(self, text=label_text, anchor="w", bg=parent.cget("bg"))
        self.label.pack(side="left", padx=(0, 10))
        self.combo = ttk.Combobox(self, values=values, width=width, state="readonly")
        self.combo.pack(side="right", fill="x", expand=True)

    def get(self):
        return self.combo.get().strip()

    def set(self, value):
        self.combo.set("" if value is None else str(value))

    def clear(self):
        self.combo.set("")


class LabeledText(tk.Frame):
    def __init__(self, parent, label_text, width=32, height=4):
        super().__init__(parent, bg=parent.cget("bg"))
        self.label = tk.Label(self, text=label_text, anchor="nw", bg=parent.cget("bg"))
        self.label.pack(side="top", anchor="w", pady=(0, 4))
        self.text = tk.Text(self, width=width, height=height)
        self.text.pack(side="top", fill="x", expand=True)

    def get(self):
        return self.text.get("1.0", tk.END).strip()

    def set(self, value):
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", "" if value is None else str(value))

    def clear(self):
        self.text.delete("1.0", tk.END)


class SectionFrame(tk.LabelFrame):
    def __init__(self, parent, title):
        super().__init__(parent, text=title, padx=10, pady=8, font=("Segoe UI", 10, "bold"))


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1180x900")
        self.root.minsize(1020, 780)

        self.data = load_json()

        self.current_sailor_index = None
        self.current_room_index = None

        self.build_ui()
        self.refresh_explorers()
        self.prepare_new_sailor()
        self.prepare_new_room()

    # UI building
    def build_ui(self):
        main = tk.Frame(self.root, padx=12, pady=12)
        main.pack(fill="both", expand=True)

        title = tk.Label(main, text="RTLS User Profile and Room Manager", font=("Segoe UI", 14, "bold"))
        title.pack(anchor="w", pady=(0, 10))

        columns = tk.Frame(main)
        columns.pack(fill="both", expand=True)

        self.left_col = tk.Frame(columns)
        self.left_col.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.right_col = tk.Frame(columns)
        self.right_col.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self.build_sailor_panel()
        self.build_room_panel()

    def build_sailor_panel(self):
        top = SectionFrame(self.left_col, "Sailor Profile")
        top.pack(fill="both", expand=True)

        explorer = SectionFrame(top, "Explorer")
        explorer.pack(fill="x", pady=(0, 10))

        search_row = tk.Frame(explorer)
        search_row.pack(fill="x")

        tk.Label(search_row, text="Search Sailor").pack(side="left", padx=(0, 8))
        self.sailor_search = ttk.Combobox(search_row, width=40, state="readonly")
        self.sailor_search.pack(side="left", padx=(0, 8))
        tk.Button(search_row, text="Open", width=10, command=self.open_selected_sailor).pack(side="left", padx=(0, 6))
        tk.Button(search_row, text="New", width=10, command=self.prepare_new_sailor).pack(side="left", padx=(0, 6))
        tk.Button(search_row, text="Refresh", width=10, command=self.reload_all).pack(side="left")

        self.sailor_record_label = tk.Label(explorer, text="Current Sailor: New Record", anchor="w")
        self.sailor_record_label.pack(fill="x", pady=(8, 0))

        self.tag_number_frame = SectionFrame(top, "Tag")
        self.tag_number_frame.pack(fill="x", pady=(0, 10))
        self.tag_id = LabeledEntry(self.tag_number_frame, "Tag #")
        self.tag_id.pack(fill="x")

        identity = SectionFrame(top, "Identity")
        identity.pack(fill="x", pady=(0, 10))
        self.profile_id = LabeledEntry(identity, "Profile ID")
        self.profile_id.pack(fill="x", pady=2)
        self.name = LabeledEntry(identity, "Name")
        self.name.pack(fill="x", pady=2)
        self.height_ft = LabeledEntry(identity, "Height")
        self.height_ft.pack(fill="x", pady=2)
        self.identity_description = LabeledText(identity, "Description", height=3)
        self.identity_description.pack(fill="x", pady=2)

        device = SectionFrame(top, "Device")
        device.pack(fill="x", pady=(0, 10))
        self.device_mac = LabeledEntry(device, "Device MAC")
        self.device_mac.pack(fill="x", pady=2)
        self.device_type = LabeledCombo(device, "Device Type", DEVICE_TYPES)
        self.device_type.pack(fill="x", pady=2)
        self.wrist_to_floor = LabeledEntry(device, "Wrist-to-floor Measurement")
        self.wrist_to_floor.pack(fill="x", pady=2)
        self.arm_to_floor = LabeledEntry(device, "Arm-to-floor Measurement")
        self.arm_to_floor.pack(fill="x", pady=2)
        self.hip_to_floor = LabeledEntry(device, "Hip-to-floor Measurement")
        self.hip_to_floor.pack(fill="x", pady=2)
        self.breast_to_floor = LabeledEntry(device, "Breast-to-floor Measurement")
        self.breast_to_floor.pack(fill="x", pady=2)
        self.device_description = LabeledText(device, "Description", height=3)
        self.device_description.pack(fill="x", pady=2)

        calibration = SectionFrame(top, "Calibration")
        calibration.pack(fill="x", pady=(0, 10))
        self.eq_a0 = LabeledEntry(calibration, "Calibration Equation - A0")
        self.eq_a0.pack(fill="x", pady=2)
        self.eq_a1 = LabeledEntry(calibration, "Calibration Equation - A1")
        self.eq_a1.pack(fill="x", pady=2)
        self.eq_a2 = LabeledEntry(calibration, "Calibration Equation - A2")
        self.eq_a2.pack(fill="x", pady=2)
        self.eq_a3 = LabeledEntry(calibration, "Calibration Equation - A3")
        self.eq_a3.pack(fill="x", pady=2)
        self.last_cal_date = LabeledEntry(calibration, "Last Calibration Date")
        self.last_cal_date.pack(fill="x", pady=2)

        history = SectionFrame(top, "History")
        history.pack(fill="x", pady=(0, 10))
        self.disease_type = LabeledEntry(history, "Disease Type")
        self.disease_type.pack(fill="x", pady=2)
        self.close_contact_threshold = LabeledEntry(history, "Close-Contact Threshold")
        self.close_contact_threshold.pack(fill="x", pady=2)
        self.duration_threshold = LabeledEntry(history, "Duration Threshold")
        self.duration_threshold.pack(fill="x", pady=2)

        status = SectionFrame(top, "Status")
        status.pack(fill="x", pady=(0, 10))
        self.status = LabeledCombo(status, "Status", STATUS_TYPES)
        self.status.pack(fill="x", pady=2)

        notes = SectionFrame(top, "Notes")
        notes.pack(fill="x", pady=(0, 10))
        self.sailor_notes = LabeledText(notes, "Notes", height=4)
        self.sailor_notes.pack(fill="x")

        btns = tk.Frame(top)
        btns.pack(fill="x", pady=(6, 0))
        tk.Button(btns, text="Save Sailor", width=18, command=self.save_sailor).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Clear Sailor Fields", width=18, command=self.prepare_new_sailor).pack(side="left")

    def build_room_panel(self):
        top = SectionFrame(self.right_col, "Room Profile")
        top.pack(fill="both", expand=True)

        explorer = SectionFrame(top, "Explorer")
        explorer.pack(fill="x", pady=(0, 10))

        search_row = tk.Frame(explorer)
        search_row.pack(fill="x")

        tk.Label(search_row, text="Search Room").pack(side="left", padx=(0, 8))
        self.room_search = ttk.Combobox(search_row, width=40, state="readonly")
        self.room_search.pack(side="left", padx=(0, 8))
        tk.Button(search_row, text="Open", width=10, command=self.open_selected_room).pack(side="left", padx=(0, 6))
        tk.Button(search_row, text="New", width=10, command=self.prepare_new_room).pack(side="left", padx=(0, 6))
        tk.Button(search_row, text="Refresh", width=10, command=self.reload_all).pack(side="left")

        self.room_record_label = tk.Label(explorer, text="Current Room: New Record", anchor="w")
        self.room_record_label.pack(fill="x", pady=(8, 0))

        room = SectionFrame(top, "Room")
        room.pack(fill="x", pady=(0, 10))
        self.room_id = LabeledEntry(room, "Room ID")
        self.room_id.pack(fill="x", pady=2)
        self.room_description = LabeledText(room, "Room Description", height=3)
        self.room_description.pack(fill="x", pady=2)

        dims = SectionFrame(top, "Room Dimensions")
        dims.pack(fill="x", pady=(0, 10))
        self.room_width = LabeledEntry(dims, "Width (ft)")
        self.room_width.pack(fill="x", pady=2)
        self.room_height = LabeledEntry(dims, "Height (ft)")
        self.room_height.pack(fill="x", pady=2)

        anchors = SectionFrame(top, "Anchor Placement")
        anchors.pack(fill="x", pady=(0, 10))
        self.room_a0 = LabeledEntry(anchors, "Anchor Placement - A0")
        self.room_a0.pack(fill="x", pady=2)
        self.room_a1 = LabeledEntry(anchors, "Anchor Placement - A1")
        self.room_a1.pack(fill="x", pady=2)
        self.room_a2 = LabeledEntry(anchors, "Anchor Placement - A2")
        self.room_a2.pack(fill="x", pady=2)
        self.room_a3 = LabeledEntry(anchors, "Anchor Placement - A3")
        self.room_a3.pack(fill="x", pady=2)
        self.anchor_elevation = LabeledEntry(anchors, "Anchor Elevation from Ground")
        self.anchor_elevation.pack(fill="x", pady=2)

        notes = SectionFrame(top, "Notes")
        notes.pack(fill="x", pady=(0, 10))
        self.room_notes = LabeledText(notes, "Notes", height=5)
        self.room_notes.pack(fill="x")

        btns = tk.Frame(top)
        btns.pack(fill="x", pady=(6, 0))
        tk.Button(btns, text="Save Room", width=18, command=self.save_room).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Clear Room Fields", width=18, command=self.prepare_new_room).pack(side="left")

    # Explorer
    def refresh_explorers(self):
        sailor_items = []
        for sailor in self.data["sailors"]:
            tid = sailor.get("tag_id", "")
            pid = sailor.get("identity", {}).get("profile_id", "")
            name = sailor.get("identity", {}).get("name", "")
            label = " | ".join([x for x in [tid, pid, name] if x])
            sailor_items.append(label if label else "Unnamed Sailor")
        self.sailor_search["values"] = sailor_items if sailor_items else ["N/A"]
        if not sailor_items:
            self.sailor_search.set("N/A")

        room_items = []
        for room in self.data["rooms"]:
            rid = room.get("room_id", "")
            desc = room.get("room", {}).get("description", "")
            label = " | ".join([x for x in [rid, desc] if x])
            room_items.append(label if label else "Unnamed Room")
        self.room_search["values"] = room_items if room_items else ["N/A"]
        if not room_items:
            self.room_search.set("N/A")

    def reload_all(self):
        self.data = load_json()
        self.refresh_explorers()
        messagebox.showinfo("Refreshed", "Data reloaded from user_info.json")

    # Sailor actions
    def prepare_new_sailor(self):
        self.current_sailor_index = None
        self.sailor_record_label.config(text="Current Sailor: New Record")

        self.tag_id.set(get_next_tag_id(self.data))
        self.profile_id.clear()
        self.name.clear()
        self.height_ft.clear()
        self.identity_description.clear()

        self.device_mac.clear()
        self.device_type.set(DEVICE_TYPES[0])
        self.wrist_to_floor.clear()
        self.arm_to_floor.clear()
        self.hip_to_floor.clear()
        self.breast_to_floor.clear()
        self.device_description.clear()

        self.eq_a0.clear()
        self.eq_a1.clear()
        self.eq_a2.clear()
        self.eq_a3.clear()
        self.last_cal_date.clear()

        self.disease_type.clear()
        self.close_contact_threshold.clear()
        self.duration_threshold.clear()

        self.status.set(STATUS_TYPES[0])
        self.sailor_notes.clear()

    def open_selected_sailor(self):
        if self.sailor_search.get() == "N/A":
            messagebox.showinfo("No Records", "No sailor records exist yet.")
            return

        selected = self.sailor_search.get()
        idx = None
        for i, sailor in enumerate(self.data["sailors"]):
            tid = sailor.get("tag_id", "")
            pid = sailor.get("identity", {}).get("profile_id", "")
            name = sailor.get("identity", {}).get("name", "")
            label = " | ".join([x for x in [tid, pid, name] if x])
            if label == selected:
                idx = i
                break

        if idx is None:
            messagebox.showwarning("Not Found", "Selected sailor was not found.")
            return

        self.load_sailor_into_form(idx)

    def load_sailor_into_form(self, idx):
        sailor = self.data["sailors"][idx]
        self.current_sailor_index = idx
        self.sailor_record_label.config(text=f"Current Sailor: Record {idx + 1}")

        self.tag_id.set(sailor.get("tag_id", ""))
        self.profile_id.set(sailor.get("identity", {}).get("profile_id", ""))
        self.name.set(sailor.get("identity", {}).get("name", ""))
        self.height_ft.set(sailor.get("identity", {}).get("height_ft", ""))
        self.identity_description.set(sailor.get("identity", {}).get("description", ""))

        self.device_mac.set(sailor.get("device", {}).get("mac_address", ""))
        self.device_type.set(sailor.get("device", {}).get("device_type", DEVICE_TYPES[0]))
        self.wrist_to_floor.set(sailor.get("device", {}).get("wrist_to_floor_ft", ""))
        self.arm_to_floor.set(sailor.get("device", {}).get("arm_to_floor_ft", ""))
        self.hip_to_floor.set(sailor.get("device", {}).get("hip_to_floor_ft", ""))
        self.breast_to_floor.set(sailor.get("device", {}).get("breast_to_floor_ft", ""))
        self.device_description.set(sailor.get("device", {}).get("description", ""))

        self.eq_a0.set(sailor.get("calibration", {}).get("equations", {}).get("A0", ""))
        self.eq_a1.set(sailor.get("calibration", {}).get("equations", {}).get("A1", ""))
        self.eq_a2.set(sailor.get("calibration", {}).get("equations", {}).get("A2", ""))
        self.eq_a3.set(sailor.get("calibration", {}).get("equations", {}).get("A3", ""))
        self.last_cal_date.set(sailor.get("calibration", {}).get("last_calibration_date", ""))

        self.disease_type.set(sailor.get("history", {}).get("disease_type", ""))
        self.close_contact_threshold.set(sailor.get("history", {}).get("close_contact_threshold", ""))
        self.duration_threshold.set(sailor.get("history", {}).get("duration_threshold", ""))

        self.status.set(sailor.get("status", {}).get("state", STATUS_TYPES[0]))
        self.sailor_notes.set(sailor.get("notes", ""))

    def build_sailor_record(self):
        return {
            "tag_id": self.tag_id.get(),
            "identity": {
                "profile_id": self.profile_id.get(),
                "name": self.name.get(),
                "height_ft": self.height_ft.get(),
                "description": self.identity_description.get()
            },
            "device": {
                "mac_address": self.device_mac.get(),
                "device_type": self.device_type.get() or DEVICE_TYPES[0],
                "wrist_to_floor_ft": self.wrist_to_floor.get(),
                "arm_to_floor_ft": self.arm_to_floor.get(),
                "hip_to_floor_ft": self.hip_to_floor.get(),
                "breast_to_floor_ft": self.breast_to_floor.get(),
                "description": self.device_description.get()
            },
            "calibration": {
                "equations": {
                    "A0": self.eq_a0.get(),
                    "A1": self.eq_a1.get(),
                    "A2": self.eq_a2.get(),
                    "A3": self.eq_a3.get()
                },
                "last_calibration_date": self.last_cal_date.get()
            },
            "history": {
                "disease_type": self.disease_type.get(),
                "close_contact_threshold": self.close_contact_threshold.get(),
                "duration_threshold": self.duration_threshold.get()
            },
            "status": {
                "state": self.status.get() or STATUS_TYPES[0]
            },
            "notes": self.sailor_notes.get()
        }

    def save_sailor(self):
        record = self.build_sailor_record()
        tag_id = record["tag_id"]
        profile_id = record["identity"]["profile_id"]

        if not tag_id:
            messagebox.showwarning("Missing Tag #", "Tag # is required.")
            return

        target_idx = None
        if self.current_sailor_index is not None:
            target_idx = self.current_sailor_index
        else:
            if profile_id:
                target_idx = find_sailor_index(self.data, profile_id)
            if target_idx is None and tag_id:
                target_idx = find_sailor_index(self.data, tag_id)

        if target_idx is None:
            self.data["sailors"].append(record)
            self.current_sailor_index = len(self.data["sailors"]) - 1
            action = "added"
        else:
            self.data["sailors"][target_idx] = record
            self.current_sailor_index = target_idx
            action = "updated"

        save_json(self.data)
        self.refresh_explorers()
        self.sailor_record_label.config(text=f"Current Sailor: Record {self.current_sailor_index + 1}")
        messagebox.showinfo("Sailor Saved", f"Sailor record {action} in user_info.json")

    # Room actions
    def prepare_new_room(self):
        self.current_room_index = None
        self.room_record_label.config(text="Current Room: New Record")

        self.room_id.clear()
        self.room_description.clear()
        self.room_width.clear()
        self.room_height.clear()
        self.room_a0.clear()
        self.room_a1.clear()
        self.room_a2.clear()
        self.room_a3.clear()
        self.anchor_elevation.clear()
        self.room_notes.clear()

    def open_selected_room(self):
        if self.room_search.get() == "N/A":
            messagebox.showinfo("No Records", "No room records exist yet.")
            return

        selected = self.room_search.get()
        idx = None
        for i, room in enumerate(self.data["rooms"]):
            rid = room.get("room_id", "")
            desc = room.get("room", {}).get("description", "")
            label = " | ".join([x for x in [rid, desc] if x])
            if label == selected:
                idx = i
                break

        if idx is None:
            messagebox.showwarning("Not Found", "Selected room was not found.")
            return

        self.load_room_into_form(idx)

    def load_room_into_form(self, idx):
        room = self.data["rooms"][idx]
        self.current_room_index = idx
        self.room_record_label.config(text=f"Current Room: Record {idx + 1}")

        self.room_id.set(room.get("room_id", ""))
        self.room_description.set(room.get("room", {}).get("description", ""))
        self.room_width.set(room.get("room", {}).get("dimensions_ft", {}).get("width", ""))
        self.room_height.set(room.get("room", {}).get("dimensions_ft", {}).get("height", ""))
        self.room_a0.set(room.get("room", {}).get("anchor_placement", {}).get("A0", ""))
        self.room_a1.set(room.get("room", {}).get("anchor_placement", {}).get("A1", ""))
        self.room_a2.set(room.get("room", {}).get("anchor_placement", {}).get("A2", ""))
        self.room_a3.set(room.get("room", {}).get("anchor_placement", {}).get("A3", ""))
        self.anchor_elevation.set(room.get("room", {}).get("anchor_elevation_ft", ""))
        self.room_notes.set(room.get("notes", ""))

    def build_room_record(self):
        return {
            "room_id": self.room_id.get(),
            "room": {
                "description": self.room_description.get(),
                "dimensions_ft": {
                    "width": self.room_width.get(),
                    "height": self.room_height.get()
                },
                "anchor_placement": {
                    "A0": self.room_a0.get(),
                    "A1": self.room_a1.get(),
                    "A2": self.room_a2.get(),
                    "A3": self.room_a3.get()
                },
                "anchor_elevation_ft": self.anchor_elevation.get()
            },
            "notes": self.room_notes.get()
        }

    def save_room(self):
        record = self.build_room_record()
        room_id = record["room_id"]

        if not room_id:
            messagebox.showwarning("Missing Room ID", "Room ID is required.")
            return

        target_idx = None
        if self.current_room_index is not None:
            target_idx = self.current_room_index
        else:
            target_idx = find_room_index(self.data, room_id)

        if target_idx is None:
            self.data["rooms"].append(record)
            self.current_room_index = len(self.data["rooms"]) - 1
            action = "added"
        else:
            self.data["rooms"][target_idx] = record
            self.current_room_index = target_idx
            action = "updated"

        save_json(self.data)
        self.refresh_explorers()
        self.room_record_label.config(text=f"Current Room: Record {self.current_room_index + 1}")
        messagebox.showinfo("Room Saved", f"Room record {action} in user_info.json")


if __name__ == "__main__":
    ensure_json_file()
    root = tk.Tk()
    app = App(root)
    root.mainloop()