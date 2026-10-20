# ED Fleet Carrier Parking Finder (EDR Ported)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![EDMC Compatible](https://img.shields.io/badge/EDMC-Compatible-success.svg)
[![CodeQL](https://github.com/GLWine/EDMC-FCParkingFinder/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/GLWine/EDMC-FCParkingFinder/actions/workflows/github-code-scanning/codeql)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![GitHub Latest Version](https://img.shields.io/github/v/release/GLWine/EDMC-FCParkingFinder?color=orange)](https://github.com/GLWine/EDMC-FCParkingFinder/releases/latest)
[![Github All Releases](https://img.shields.io/github/downloads/GLWine/EDMC-FCParkingFinder/total.svg?color=informational)](https://github.com/GLWine/EDMC-FCParkingFinder/releases/latest)
[![Gemini Coding](https://img.shields.io/badge/Gemini-Coding-6B46C1?logo=google&logoColor=white)](https://gemini.google.com)
[![Gemini Localization](https://img.shields.io/badge/Gemini-Localization-3B82F6?logo=google&logoColor=white)](https://gemini.google.com)

A lightweight, standalone plugin for **EDMC (Elite Dangerous Market Connector)** designed to help commanders identify potential Fleet Carrier parking availability in nearby star systems.

This project extracts and adapts the parking search logic from the renowned **[EDR (ED Recon)](https://github.com/lekeno/EDR)** project by **[@LeKeno](https://github.com/lekeno)**. System data is acquired from the Spansh API through a dedicated client, then passed to the parking-search core.

---

## Features
* **Automatic System Tracking**: Automatically syncs with your current in-game location via EDMC journal events.
* **Manual Search & Dynamic UI**: Allows searching for parking availability around any arbitrary star system by name. Features a smart search button that enables/disables automatically based on input validation and clean placeholder support.
* **Spansh System Search**: Retrieves nearby system records from Spansh and normalizes them in a dedicated service before evaluation.
* **Theoretical Parking Calculation**: Estimates potential capacity from the supplied system body counts, up to 128 slots per system.
* **Multi-language Support**: Fully localized for global commanders across 11 different languages.
* **Separated Components**: Keeps EDMC lifecycle hooks, localized UI, Spansh data acquisition, service integration, and parking evaluation in distinct modules.

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
The integration currently retrieves nearby systems from Spansh using the reference system and a 25 Ly search radius. The service validates and normalizes the returned records, then passes them to the standalone parking core.

The core filters known and API-reported permit-locked systems, orders supplied candidates by distance, and calculates theoretical capacity from body counts (16 slots per body, capped at 128 per system). Direct target-system queries and live carrier-slot assignment are not yet implemented.

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
For Spansh connectivity or API errors, check the EDMC log for details. Search failures are shown in the plugin interface.

---

## Acknowledgments & AI Assistance
This project was developed and optimized with the assistance of **Google Gemini** for software engineering/coding practices and multi-language localization.

---

## License
This project is licensed under the terms of the **Apache-2.0 License**. See the [LICENSE](LICENSE) file for details. Original parking algorithm inspired and adapted from [**lekeno/EDR**](https://github.com/lekeno/EDR).
