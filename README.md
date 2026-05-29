# Bus Charging Scheduler

A data-driven electric bus charging scheduler built with Python and Streamlit. Reads scenario files, computes charging plans using a rule-based discrete-event simulation, and displays results in a clean web UI.

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the URL shown in the terminal (default: http://localhost:8501).

## Project Structure

```
├── app.py                          # Streamlit UI
├── requirements.txt                # Dependencies
├── README.md                       # This file
├── ARCHITECTURE.md                 # Design documentation
├── scheduler/
│   ├── __init__.py
│   ├── domain.py                   # Data models (Route, Bus, Scenario, etc.)
│   ├── scenario_loader.py          # YAML → Scenario parser
│   ├── router.py                   # Feasible charging station finder
│   ├── simulator.py                # Discrete-event simulation
│   ├── scoring.py                  # Soft rule registry and evaluation
│   └── engine.py                   # Greedy constructive orchestrator
└── data/
    └── scenarios/
        ├── scenario_01.yaml        # Even spacing (baseline)
        ├── scenario_02.yaml        # Bunched start
        ├── scenario_03.yaml        # Asymmetric load
        ├── scenario_04.yaml        # Operator-heavy
        └── scenario_05.yaml        # Worst case convergence
```

## Usage

1. **Select a scenario** from the dropdown in the sidebar
2. Click **Run Schedule**
3. Explore three tabs:
   - **Scenario Input** — raw data: route segments, operators, stations, buses, weights, and constants
   - **Per-Bus Timetable** — expandable timeline per bus showing each charging station visited, arrival/charge/departure times, and wait duration
   - **Per-Station View** — charging order at each station (A, B, C, D) showing which bus charged when

## Customization

### Changing a Weight
Edit the scenario YAML file. Weights are in one obvious place:

```yaml
weights:
  individual: 1.0
  operator: 2.0     # ← change this value
  overall: 1.0
```

The engine reads `weights` directly from the scenario; no code change needed.

### Adding a New Rule
Create a new rule function and register it in `scheduler/scoring.py`:

```python
def my_new_rule(result: ScheduleResult, weights: dict) -> float:
    # Compute your metric. Lower score = better.
    return score

register_rule("my_rule_name", my_new_rule)
```

Add the corresponding weight to your scenario YAML:

```yaml
weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0
  my_rule_name: 1.0    # ← new weight
```

No engine changes required.

### Adding a Station
Add a segment to the route and a station entry in the YAML:

```yaml
route:
  segments:
    - from: D
      to: E              # ← new station
      distance_km: 80
    - from: E
      to: Kochi
      distance_km: 20

stations:
  - id: E                # ← new station
    name: "Station E"
    chargers: 2
```

### Adding a Scenario
Create a new `.yaml` file in `data/scenarios/`. The app auto-discovers it via `list_scenario_files()`.

## Dependencies

- Python 3.10+
- streamlit
- pyyaml
