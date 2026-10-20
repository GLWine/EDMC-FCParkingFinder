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
* **Monthly Permit List Refresh**: A scheduled GitHub Action fetches every system Spansh marks as requiring a permit and commits the complete, paginated result and update timestamp to `data/known_permits.json`. When the local copy is at least 30 days old, the plugin downloads this published JSON from GitHub in the background; the plugin does not query Spansh for the permit list.
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
The integration retrieves nearby systems from Spansh using the reference system and a 25 Ly search radius. When Spansh returns an exact-name match for the requested system, the core evaluates it first; if it is inaccessible or estimated full, the core checks the remaining candidates in ascending distance order. If Spansh omits the target, the nearest eligible returned candidate is used. Missing system information remains unknown rather than being treated as a report that access is allowed.

The core filters known and API-reported permit-locked systems and calculates theoretical capacity from body counts (16 slots per body, capped at 128 per system). If the body count is missing or non-positive, the estimate falls back to one body; this is still only theoretical. Spansh's systems response includes station records, from which the core counts entries of type `Drake-Class Carrier` only when they have a valid `distance_to_arrival`; carriers without a distance are omitted and noted at debug level. The core subtracts that reported count from the theoretical capacity and skips a system when the count fills that capacity. If the system's `updated_at` timestamp is more than 24 hours old, the result marks provider data as stale and logs that fact; stale data does not exempt a system from the full-capacity rejection rule. When carrier and body arrival distances are present, it estimates body assignments by nearest radial-distance difference, up to 16 carriers per body, then proceeds to the next closest body. Remaining estimated slots are distributed by nearest arrival-distance relationship without exceeding the global 128-slot cap. `body_assignment_complete` indicates whether all listed carriers and bodies had usable arrival distances; incomplete assignments contain only mappable carrier records and must be treated as partial estimates. This distance comparison is only a heuristic: it does not establish an exact carrier-to-body location, guarantee that Spansh's station list is fresh, or confirm real-time occupancy. Missing station lists leave estimated availability unknown; confirmed availability remains unknown in all cases. See the [Spansh API documentation](https://docs.spansh.co.uk/) for the provider schema.

## Search Result Contract
The core and service return a selected system as a result with `name`, `distance`, `access_status`, `access_reason`, and `parking`. The `parking` object includes `theoretical_slots`, the Spansh-reported `spansh_reported_carrier_count`, a separate `estimated_available_slots`, `body_assignment_complete`, `provider_data_stale`, optional confirmed occupancy data as `confirmed_available_slots`, and `body_details` with per-body estimated counts. `provider_data_stale: true` means Spansh's system record is older than 24 hours; absent or invalid timestamps leave freshness unknown. Stale data is logged, and systems estimated full are still rejected. Incomplete body assignments contain only mappable records and are identified by `body_assignment_complete: false`. A `null` availability estimate means Spansh did not provide a station list; a `null` confirmed count means real availability was not confirmed. The existing `slots`, `body_name_list`, and `is_empirical` fields remain for compatibility; `slots` is the theoretical count. The UI currently continues to display theoretical capacity; presenting the new provider estimate and freshness is tracked in the UI roadmap.

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
3. The system field tracks your current system from journal events. You can also enter another system name; press **Search** to scan nearby systems. Results show theoretical capacity; journal telemetry may identify body details but does not confirm total system occupancy.

---

## Troubleshooting & Support
For Spansh connectivity or API errors, check the EDMC log for details. Search failures are shown in the plugin interface.
If the GitHub permit-list download fails or the published file is invalid or stale, the existing local JSON file is preserved; the plugin retries after 24 hours while running. The scheduled workflow can also be started manually from the repository's Actions tab.

---

## Acknowledgments & AI Assistance
This project was developed and optimized with the assistance of **Google Gemini** for software engineering/coding practices and multi-language localization.

---

## License
This project is licensed under the terms of the **Apache-2.0 License**. See the [LICENSE](LICENSE) file for details. Original parking algorithm inspired and adapted from [**lekeno/EDR**](https://github.com/lekeno/EDR).
