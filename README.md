# Bus Charging Scheduler

A rule-based, data-driven scheduling engine for electric bus fleets. Reads scenario files describing routes, stations, buses, and operational weights, then computes optimal charging plans and charger queue orders using discrete-event simulation with beam search optimization.

## Features

- **Data-driven input** — all route geometry, station configurations, bus schedules, operators, and optimization weights live in YAML scenario files. No hardcoded values.
- **Rule engine architecture** — soft rules (individual wait, operator fairness, overall network time) drive optimization with tunable weights. Hard rules (battery range, route order, charger capacity) enforce physical and operational constraints.
- **Dual optimization strategies** — greedy construction for speed, beam search (K=3) for globally better schedules. Selectable per run.
- **Discrete-event simulation** — processes bus arrivals, charge starts, and charge completions as timestamped events with deterministic FIFO queuing.
- **Plan explainability** — for each bus, the UI shows the chosen charging plan, all alternatives considered, their scores, and why the winner was selected.
- **Multi-charger support** — each station supports any number of charger slots. Configured in the scenario file.
- **Input validation** — pre-scheduling validation checks route continuity, operator references, station definitions, bus feasibility, and weight ranges.
- **Three-tab Streamlit UI** — scenario input viewer, per-bus timetable with expandable plan explanations, and per-station charging order view.

## Installation

```bash
git clone <repo-url>
cd busChargingScheduler
pip install -r requirements.txt
```

Requirements: Python 3.10+, streamlit, pyyaml.

## Running Locally

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. Select a scenario from the sidebar dropdown and click **Run Schedule**.

## Running Without the UI (Headless)

```python
from scheduler.scenario_loader import load_scenario
from scheduler.engine import run

scenario = load_scenario("data/scenarios/scenario_01.yaml")
result = run(scenario, strategy="beam")

print(result.scores)
for tl in result.bus_timelines:
    print(f"{tl.bus.id}: {tl.stations_used}, wait={tl.total_wait}")
```

## Project Structure

```
├── app.py                          # Streamlit UI (scenario picker, 3 tabs)
├── requirements.txt                # streamlit, pyyaml
├── scheduler/
│   ├── domain.py                   # Data classes (Route, Bus, Scenario, ScheduleResult, etc.)
│   ├── scenario_loader.py          # YAML → Scenario parser
│   ├── router.py                   # Feasible station combination finder
│   ├── simulator.py                # Discrete-event simulation engine
│   ├── state.py                    # SchedulingState for incremental construction
│   ├── planner.py                  # Candidate generation and state scoring
│   ├── engine.py                   # Orchestrator: greedy or beam search
│   ├── validator.py                # Input validation and constraint checking
│   └── rules/
│       ├── __init__.py             # RuleRegistry singleton
│       ├── base.py                 # SoftRule and HardRule base classes
│       ├── soft/
│       │   ├── individual_wait.py  # Max single-bus wait time
│       │   ├── operator_fairness.py# Max disadvantage across operators
│       │   └── overall_time.py     # Network makespan
│       └── hard/
│           ├── battery_range.py    # No segment exceeds battery range
│           ├── route_order.py      # Stations visited in monotonic order
│           └── charger_capacity.py # No overlapping charges at a station
└── data/
    └── scenarios/
        ├── scenario_01.yaml        # Even spacing (baseline)
        ├── scenario_02.yaml        # Bunched start (heavy early contention)
        ├── scenario_03.yaml        # Asymmetric load (BK-heavy)
        ├── scenario_04.yaml        # Operator-heavy (KPN dominates, operator weight=2)
        └── scenario_05.yaml        # Worst case convergence (max contention)
```

## Usage

### Step 1: Select a Scenario
The dropdown in the sidebar auto-discovers all `.yaml` files in `data/scenarios/`. Selecting a scenario loads and displays its input data in the "Scenario Input" tab.

### Step 2: Run Schedule
Click **Run Schedule**. The engine:
1. Validates the scenario against all hard rules
2. Generates feasible charging plans for each bus
3. Runs greedy or beam search to select the best global plan set
4. Simulates the full schedule via discrete-event simulation
5. Scores the result against all soft rules
6. Builds per-bus plan explanations

### Step 3: Explore Results

| Tab | Content |
|-----|---------|
| **Scenario Input** | Route segments, operators, stations, bus roster, weights and constants |
| **Per-Bus Timetable** | Expandable per-bus timeline: each charging station visited, arrival/charge/departure times, wait durations. Also shows plan selection with alternatives and scoring breakdown. |
| **Per-Station View** | Charging order at stations A, B, C, D — which bus charged when, with arrival and departure times |
| **Scores bar** | At page bottom: individual, operator, overall, and combined scores |

## Configuration

All configuration lives in YAML scenario files. No code changes needed.

### Changing a Weight

```yaml
weights:
  individual: 1.0
  operator: 3.0    # ← increase operator fairness importance
  overall: 1.0
```

### Adding a Station

```yaml
route:
  segments:
    - from: D
      to: E
      distance_km: 80
    - from: E
      to: Kochi
      distance_km: 20
stations:
  - id: E
    name: "Station E"
    chargers: 2
```

### Adding a Bus

```yaml
buses:
  - id: bus-BK-11
    operator: kpn
    direction: BK
    departure_time: "21:30"
```

### Adding a Scenario
Create a new `.yaml` file in `data/scenarios/`. The UI auto-discovers it.

## Future Improvements

- **Route graph model** — replace linear segment list with a graph of station nodes and weighted edges, enabling multiple route paths and shared stations between routes
- **Time-of-day electricity pricing** — new soft rule penalizing peak-hour charging
- **Priority buses** — extend queue ordering to support priority fields
- **Driver shift constraints** — hard rule enforcing maximum consecutive driving time
- **Real-time disruption handling** — dynamic re-scheduling when buses are delayed
- **Multi-route support** — extend Scenario to contain multiple Route definitions with per-bus route assignment
