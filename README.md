# EDMC Fleet Carrier Parking Finder (EDR Ported)

![Version](https://img.shields.io/badge/version-1.1.1-blue.svg)
![EDMC Compatible](https://img.shields.io/badge/EDMC-Compatible-success.svg)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
![CI/CD Pipeline](https://github.com/GLWine/EDR-Ported-Parking-Finder/actions/workflows/release.yml/badge.svg)

A lightweight, standalone plugin for **EDMC (Elite Dangerous Market Connector)** designed to help commanders identify potential Fleet Carrier parking availability in nearby star systems[cite: 3].

This project extracts and adapts the parking search logic from the renowned **EDR (ED Recon)** project, ensuring high standards of code quality, centralized network headers (`User-Agent` compliance), and full EDSM API compatibility[cite: 3].

---

## Features
* **Automatic System Tracking**: Automatically syncs with your current in-game location via EDMC journal events[cite: 3].
* **Manual Search**: Allows searching for parking availability around any arbitrary star system by name[cite: 3].
* **Theoretical Parking Calculation**: Estimates available slots based on system body counts retrieved via public EDSM APIs[cite: 3].
* **EDMC Native Standards**: Utilizes centralized user-agent configurations and logging standards in full compliance with `PLUGINS.md`[cite: 3].

---

## Requirements
* **EDMC** (Elite Dangerous Market Connector) version 5.0 or higher[cite: 3].
* Python 3.10+ (bundled with EDMC)[cite: 3].

---

## Installation

### Method 1: Automatic (Recommended)
1. Go to the [Releases](https://github.com/GLWine/EDR-Ported-Parking-Finder/releases/latest) page.
2. Download the latest `EDR-Ported-Parking-Finder-v*.zip` asset.
3. Extract the contents directly into your EDMC plugins directory:
   * **Windows**: `%LOCALAPPDATA%\EDMarketConnector\plugins`[cite: 3]
   * **Linux/Mac**: Check your EDMC configuration paths[cite: 3].

### Method 2: Manual Clone / Copy
Ensure your plugin folder contains the following production files[cite: 3]:
* `load.py`[cite: 3]
* `parking_finder.py`[cite: 3]
* `README.md`[cite: 3]
* `LICENSE`[cite: 3]

---

## Usage
1. Launch EDMC[cite: 3].
2. Open the **EDR Parking Finder** tab/panel from the main interface[cite: 3].
3. View your current system's parking availability or type a target system name to scan nearby stellar bodies[cite: 3].

---

## Troubleshooting & Support
If you encounter 403 errors or connectivity issues with EDSM, ensure your EDMC is fully up to date. This plugin automatically hooks into EDMC's core `config.user_agent` to protect against rate-limiting blocks.

---

## License
This project is licensed under the terms of the **Apache-2.0 License**. See the [LICENSE](LICENSE) file for details. Original parking algorithm inspired and adapted from **EDR**[cite: 3].
