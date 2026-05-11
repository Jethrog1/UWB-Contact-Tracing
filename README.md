# UWB-Contact-Tracing
1st Place 2025-2026 BME Team 6 Senior Design Project

## Project Overview
This project produced a Real-time Locating System for monitoring and mitigating disease spread for naval environments using wearable Ultra-Wideband (UWB) boards for collecting sailor's interpersonal distance between other sailors. The wearables communicate with at least two stationary anchors in each room, which allows for lateration calculations to be conducted for live mapping on a 2D floor plan. The data is transmitted from the hardware to this program via serial port or Bluetooth Low Energy (BLE), where it is ultimately processed into real-time analytics and actionable information, allowing users to identify high-risk individuals and apply early interventions on exposed sailors. 

## BRIGID
This repo holds all code responsible for our app: BRIGID (Behavioral Real-time Interaction Graphing for Infectious Diseases)

BRIGID is a desktop application for disease spread monitoring and mitigation, processing and visualizing data collected via DW3000 UWB hardware modules. It combines an Electron + React frontend with a Python/FastAPI backend to deliver data preprocessing, CAD modeling of floor plans, a profile manager, calibration tools for wearable tags, anchor placement, and machine learning analytics. 

## Features 

- Locally hosted desktop application
- Profile manager to log tag-to-sailor data in .json files
- Calibration tool to create and ship calibration equations to tag profiles
- Custom floor plan CAD tool to maintain confidentiality in loading private floor plans onto the program
- Anchor manager to place real-life anchor locations onto the floor plan for accurate lateration calculations
- Real-time Locating System Dashboard to visualize live data feeds, supported by proximity heat-maps, interpersonal distance lines, and machine learning analytics for digestible and actionable intel

## Local Data Folders

BRIGID creates local workspace/profile data folders when the app runs for the first time.

These folders are used for things like:
- saved profiles
- workspace files
- room data
- RTLS exports
- temporary project data

They are intentionally not tracked in Git, so a fresh clone of the repository will not include populated local user data.

After first run, BRIGID may create local folders such as:

- `BRIGID/profile/`
- `BRIGID/Profile/`
- `BRIGID/.tmp_project/`

This is expected behavior to ensure local data stays isolated per user, supporting privacy, security, and offline reliability requirements for naval applications. 

## Tech Stack

- Frontend: Electron, React, TypeScript, Vite, Blueprint.js
- Backend: Python, FastAPI, Uvicorn
- Device/runtime support: NimBLE, Adafruit SSD1306, ESP32S3 Dev Module (compiler), local ML compatibility environment

## Hardware Code

This repository also includes the embedded code used with the DW3000 UWB hardware modules that feed BRIGID.

- `HardwareCode/tag_code.ino` contains the firmware for wearable tag devices
- `HardwareCode/anchor_code.ino` contains the firmware for fixed anchor devices
- `HardwareCode/Xiao_Serial_reading_RTLS.ino` contains supporting serial-reading logic for RTLS data flow and hardware-side communication testing

## Supplementary Files 

- The `SolidworksDrawings/` folder contains the SolidWorks CAD files for the wearable tag housing assembly and stationary anchor housing assembly, as well as subparts used in each model
- The file `BME-Demo-Day-Poster Team 6.pdf` contains the final presentation poster for this award winning project

## Repository Structure

```text
UWB-Contact-Tracing/
├── BRIGID/
│   ├── frontend/           # Electron + React UI
│   ├── backend/            # FastAPI backend and CAD/RTLS services
│   ├── assets/             # App assets and bundled resources
│   ├── start.sh            # macOS/Linux launcher
│   └── start.ps1           # Windows launcher
├── HardwareCode/           # Arduino / embedded firmware for UWB tags and anchors
├── SoldiworkDrawings/      # SolidWorks assemblies, parts, and enclosure design files
├── BME-Demo-Day-Poster Team 6.pdf   # Project poster / presentation artifact
└── README.md
