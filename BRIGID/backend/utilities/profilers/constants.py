
DEVICE_TYPES = ["Wrist Band", "Arm Band", "Belt Clip-on", "Breast Pocket"]

DEVICE_HEIGHT_FIELD_MAP: dict[str, str] = {
    "Wrist Band":    "wrist_to_floor_ft",
    "Arm Band":      "arm_to_floor_ft",
    "Belt Clip-on":  "hip_to_floor_ft",
    "Breast Pocket": "breast_to_floor_ft",
}

FIT_MODES = [
    "Linear",
    "Polynomial",
    "Logarithmic",
    "Power Series",
    "Exponential",
    "Moving Average",
]

ANCHOR_IDS = ["A0", "A1", "A2", "A3"]

FIELD_HELP: dict[str, str] = {
    "tag_id":             "Unique identifier for this tag (used as the filename). Required.",
    "profile_id":         "Human-readable profile code (e.g., TAG-001). Optional.",
    "name":               "Display name for this tag profile.",
    "description":        "Optional notes about the tag or wearer.",
    "mac_address":        "BLE MAC address of the physical device (e.g., AA:BB:CC:DD:EE:FF).",
    "device_type":        "Form factor of the wearable. Determines which height field is active.",
    "wrist_to_floor_ft":  "Distance from wrist to floor in feet. Used for Wrist Band device type.",
    "arm_to_floor_ft":    "Distance from arm to floor in feet. Used for Arm Band device type.",
    "hip_to_floor_ft":    "Distance from hip to floor in feet. Used for Belt Clip-on device type.",
    "breast_to_floor_ft": "Distance from breast pocket to floor in feet.",
    "A0":                 "Calibration correction equation for anchor A0. Leave blank for raw distance.",
    "A1":                 "Calibration correction equation for anchor A1.",
    "A2":                 "Calibration correction equation for anchor A2.",
    "A3":                 "Calibration correction equation for anchor A3.",
    "notes":              "Free-form operational notes (deployment, observations, etc.).",
}
