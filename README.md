# ED Fleet Carrier Parking Finder (EDR Ported)

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
[![CodeQL](https://github.com/GLWine/EDMC-FCParkingFinder/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/GLWine/EDMC-FCParkingFinder/actions/workflows/github-code-scanning/codeql)
![EDMC Compatible](https://img.shields.io/badge/EDMC-Compatible-success.svg)
[![GitHub Latest Version](https://img.shields.io/github/v/release/GLWine/EDMC-FCParkingFinder)](https://github.com/GLWine/EDMC-FCParkingFinder/releases/latest)
[![Github All Releases](https://img.shields.io/github/downloads/GLWine/EDMC-FCParkingFinder/total.svg)](https://github.com/GLWine/EDMC-FCParkingFinder/releases/latest)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

A lightweight, standalone plugin for **EDMC (Elite Dangerous Market Connector)** designed to help commanders identify potential Fleet Carrier parking availability in nearby star systems.

This project extracts and adapts the parking search logic from the renowned **[EDR (ED Recon)](https://github.com/lekeno/EDR)** project by **[@LeKeno](https://github.com/lekeno)**, ensuring high standards of code quality, centralized network headers (`User-Agent` compliance), and full EDSM API compatibility.

---

## Features
* **Automatic System Tracking**: Automatically syncs with your current in-game location via EDMC journal events.
* **Manual Search & Dynamic UI**: Allows searching for parking availability around any arbitrary star system by name. Features a smart search button that enables/disables automatically based on input validation and clean placeholder support.
* **Theoretical Parking Calculation**: Estimates available slots based on system body counts retrieved via public EDSM APIs.
* **Multi-language Support**: Fully localized for global commanders across 11 different languages.
* **EDMC Native Standards**: Utilizes centralized user-agent configurations and logging standards in full compliance with `PLUGINS.md`.

---

## Supported Languages
The plugin includes native localization support for:
- 🇺🇸 English (`en`)
- 🇮🇹 Italian (`it`)
- 🇩🇪 German (`de`)
- 🇪🇸 Spanish (`es`)
- 🇫🇷 French (`fr`)
- 🇰🇷 Korean (`ko`)
- 🇧🇷 Portuguese - Brazil (`pt-BR`)
- 🇷🇺 Russian (`ru`)
- 🇹🇷 Turkish (`tr`)
- 🇺🇦 Ukrainian (`uk`)
- 🇨🇳 Chinese (`zh`)

---

## Parking Logic & Algorithm
The core logic of the plugin adapts the battle-tested search mechanisms from **EDRecon / lekeno**:
1. **Initial System Check**: When a search is triggered, the system first evaluates the reference star system itself (if rank is set to 0). It queries the EDSM API (`/api-v1/system`) to check permit locks and fetch stellar properties. If accessible and slots are available, it returns it immediately.
2. **Progressive Fallback & Sphere Radius Query**: If the target system lacks available parking slots or requires a permit, the search does not stop. It automatically queries EDSM's spherical database (`/api-v1/sphere-systems`) across the defined radius (default: 25 Ly).
3. **Filtering & Sorting**: Candidate systems are filtered to discard unreachable/permit-locked systems and false positives (such as distant systems improperly returning a 0 distance). Surviving systems are sorted by increasing distance from the origin and scanned sequentially until a valid parking slot is found.
4. **Theoretical Slot Estimation**: Parking capacity is dynamically calculated based on the total body count of the target system (multiplying bodies by 16 slots, up to a strict maximum cap of 128 slots per system).

---

## Requirements
* **EDMC** (Elite Dangerous Market Connector) version 5.0 or higher.
* Python 3.10+ (bundled with EDMC).

---

## Installation

### Method 1: Automatic (Recommended)
1. Go to the [Releases](https://github.com/GLWine/EDMC-FCParkingFinder/releases/latest) page.
2. Download the latest `EDMC-FCParkingFinder.zip` asset.
3. Extract the contents directly into your EDMC plugins directory:
   * **Windows**: `%LOCALAPPDATA%\EDMarketConnector\plugins`
   * **Linux/Mac**: Check your EDMC configuration paths.

### Method 2: Manual Clone / Copy
Ensure your plugin folder contains the required production files (`load.py`, `parking_finder.py`, localizations, `README.md`, `LICENSE`).

---

## Usage
1. Launch EDMC.
2. Go to the **FC Parking Finder** tab/panel from the main interface.
3. View your current system's parking availability automatically or type a target system name (guided by the placeholder text) to scan nearby stellar bodies. The "Search" button will activate once valid input is provided.

---

## Troubleshooting & Support
If you encounter 403 errors or connectivity issues with EDSM, ensure your EDMC is fully up to date. This plugin automatically hooks into EDMC's core configuration to protect against rate-limiting blocks and respect EDSM API guidelines.

---

## License
This project is licensed under the terms of the **Apache-2.0 License**. See the [LICENSE](LICENSE) file for details. Original parking algorithm inspired and adapted from [**lekeno/EDR**](https://github.com/lekeno/EDR).
