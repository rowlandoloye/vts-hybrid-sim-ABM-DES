import os
# server.py — FULLY INTERACTIVE (sliders + checkboxes) for Render deployment
from mesa.visualization import ModularServer
from mesa.visualization.modules import ChartModule
from mesa.visualization.UserParam import Slider, Checkbox
from model import BuildingModel

# Real-time chart (same as before)
chart = ChartModule(
    [
        {"Label": "Avg_Wait_Time", "Color": "#FF0000"},
        {"Label": "Avg_Satisfaction", "Color": "#00FF00"},
        {"Label": "Crowding", "Color": "#0000FF"},
    ],
    data_collector_name="datacollector",
)

# INTERACTIVE PARAMETERS — this is the magic!
model_params = {
    "N_floors": Slider("Number of Floors", value=6, min_value=2, max_value=30, step=1),
    "N_elevators": Slider("Number of Elevators", value=2, min_value=1, max_value=8, step=1),
    "peak_hour": Checkbox("Peak Hour Demand (High Arrival Rate)", value=True),
    "backup_power": Checkbox("Backup Power Available", value=True),
    "door_time": Slider("Door Open/Close Time (s)", value=10.6, min_value=5.0, max_value=25.0, step=0.5),
    "capacity": Slider("Elevator Capacity (persons)", value=16, min_value=8, max_value=30, step=1),
    "vibration": Slider("Vibration Level", value=1.01, min_value=0.5, max_value=3.0, step=0.1),
    "noise": Slider("Cabin Noise (dB)", value=55.9, min_value=40.0, max_value=80.0, step=1.0),
    "speed": Slider("Elevator Speed (m/s)", value=3.0, min_value=1.0, max_value=6.0, step=0.5),
}

server = ModularServer(
    BuildingModel,
    [chart],
    "VTS Hybrid ABM-DES — Interactive Simulation (Rowland PhD)",
    model_params,                     
)

# Critical for Render/Heroku/etc.
port = int(os.environ.get('PORT', 10000))  # Default to 10000 if not set
server.port = port
server.launch(host="0.0.0.0", port=port)