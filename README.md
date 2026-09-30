# EDMC Fleet Carrier Parking Finder

A lightweight, standalone plugin for **EDMC (Elite Dangerous Market Connector)** designed to help commanders identify potential Fleet Carrier parking availability in nearby star systems. 

This project extracts and adapts the parking search logic from the renowned **EDR (ED Recon)** project, ensuring high standards of code quality and full API compatibility.

## Features
* **Automatic System Tracking**: Automatically syncs with your current in-game location via EDMC journal events (`FSDJump`, `Location`).
* **Manual Search**: Allows searching for parking availability around any arbitrary star system by name.
* **Theoretical Parking Calculation**: Estimates available slots based on system body counts retrieved via public EDSM APIs.
* **EDMC Native Standards**: Utilizes EDMC's built-in `plug` utilities for logging and translations.

## Installation
1. Download or clone this repository into your EDMC plugins directory (typically `%LOCALAPPDATA%\EDMarketConnector\plugins` on Windows).
2. Ensure the folder contains:
   * `load.py`
   * `parking_finder.py`
3. Restart EDMC.

## License
This project is licensed under the terms of the **Apache-2.0 License**. See the [LICENSE](LICENSE) file for details. Original parking algorithm inspired and adapted from **EDR**.
