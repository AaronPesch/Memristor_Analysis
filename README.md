# memristor-analysis
A Python GUI for the analysis and visualization of Memristor(RRAM) I–V characteristics as part of TU Darmstadt's Team Project Software Engineering (TPSE).

## Features
**Data import**
- Import measurement data (`.xlsx`) at **device** or **stack** level into a local database
- Automatic parsing of stack/device/measurement metadata from folder structure

**Plots** (interactive, one tab per type)
- Endurance performance vs cycle
- Boxplots per parameter (V_set, V_reset, R_LRS, R_HRS, I_reset_max, V_forming, I_leakage, Memory Window)
- Cumulative distribution (CDF) per parameter
- Characteristic plots: |Current| vs Voltage, Normalized Conductance vs Voltage, Butterfly curve
- Correlation scatter plots (parameter pairs) and correlation matrix heatmaps
- Combined comparison plots: |V_set| vs |V_reset| and |R_HRS| vs |R_LRS| (boxplot, CDF, scatter)
- Memory window (R_HRS / R_LRS) distributions
- Spatial stack map: per-device grid heatmap by physical row/column position

**Interactivity**
- Toggle any plot's y-axis between log and linear, with per-plot defaults remembered between sessions
- Filter individual devices/sets on/off via the legend
- Per-cycle color gradient on characteristic plots

**Export**
- Export the current plot or all plots to PNG, JPEG, EPS, SVG, or PDF
- Export underlying data to CSV or TXT
- Combined multi-page PDF (one plot per page) and PowerPoint (one plot per slide)
- Legends automatically expand on export so no entries are cut off

**General**
- Cross-platform (Windows/macOS/Linux); results cached in the user's app-data folder
- Built-in link to the project wiki (Help menu / F1)

To set up the needed dependencies run the following commands:
1. pip install virtualenv (if not already installed)
2. virtualenv venv
3. source venv/bin/activate
4. pip install -r requirements.txt

For developers:
After adding a new package to the venv, the current state can be saved with the following command.
pip freeze > requirements.txt