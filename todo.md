# Bus Charging Scheduler — Implementation Plan

## Overview
Build a Python + Streamlit app that reads scenario files, computes charging plans for electric buses on a fixed route, and visualizes results. Rule-based discrete-event simulation with tunable soft constraints.

---

## Phase 1: Project Scaffolding

### 1.1 Directory Structure
```
busChargingScheduler/
├── app.py                         # Streamlit entry point
├── requirements.txt               # streamlit, pyyaml
├── README.md                      # User documentation
├── ARCHITECTURE.md                # Design documentation
├── todo.md                        # This file
├── scheduler/
│   ├── __init__.py
│   ├── domain.py                  # Dataclasses (Route, Station, Bus, Scenario, etc.)
│   ├── scenario_loader.py         # YAML → Scenario object
│   ├── router.py                  # Feasible charging station combinations
│   ├── simulator.py               # Discrete-event simulation engine
│   ├── scoring.py                 # Soft rule classes (extensible registry)
│   └── engine.py                  # Orchestrator: plan → simulate → score
└── data/
    └── scenarios/
        ├── scenario_01.yaml       # Even spacing (baseline)
        ├── scenario_02.yaml       # Bunched start (high contention)
        ├── scenario_03.yaml       # Asymmetric load (BK-heavy)
        ├── scenario_04.yaml       # Operator-heavy (KPN dominates)
        └── scenario_05.yaml       # Worst case convergence (max contention)
```

### 1.2 Create requirements.txt
```
streamlit>=1.28.0
pyyaml>=6.0
```

### 1.3 Create `scheduler/__init__.py`
Empty init file.

---

## Phase 2: Domain Model (`scheduler/domain.py`)

### 2.1 Classes

#### `Segment`
- `from_station: str`
- `to_station: str`
- `distance_km: float`

#### `Route`
- `name: str`
- `segments: list[Segment]`
- Methods:
  - `stations_ordered_bk() -> list[str]` — Bengaluru→Kochi station order (A, B, C, D)
  - `stations_ordered_kb() -> list[str]` — Kochi→Bengaluru station order (D, C, B, A)
  - `cumulative_distance_bk() -> dict[str, float]` — cumulative km from Bengaluru
  - `cumulative_distance_kb() -> dict[str, float]` — cumulative km from Kochi
  - `distance_between(station_a, station_b) -> float` — shortest path distance
  - `total_distance_km() -> float`

#### `Bus`
- `id: str` (e.g. "bus-BK-01")
- `operator: str` (e.g. "kpn")
- `direction: str` ("BK" or "KB")
- `departure_time_minutes: int` — minutes from 19:00

#### `Operator`
- `id: str`
- `name: str`

#### `ChargingEvent`
- `station_id: str`
- `arrival_time: int` — minutes from 19:00
- `charge_start_time: int`
- `charge_end_time: int`
- `departure_time: int`
- `wait_time: int` = charge_start - arrival

#### `Scenario`
- `name: str`
- `description: str`
- `route: Route`
- `operators: list[Operator]`
- `stations: list[str]` — list of station IDs (A, B, C, D)
- `num_chargers: dict[str, int]` — chargers per station (default 1)
- `buses: list[Bus]`
- `weights: dict[str, float]` — {"individual": 1.0, "operator": 1.0, "overall": 1.0}
- `constants: dict[str, Any]` — {"battery_range_km": 240, "charge_time_min": 25, "speed_kmh": 60}

#### `BusTimeline`
- `bus: Bus`
- `charging_events: list[ChargingEvent]`
- `total_wait: int`
- `final_arrival_time: int`
- `stations_used: list[str]`

#### `StationLog`
- `station_id: str`
- `charge_order: list[dict]` — each entry: {"bus_id": str, "arrival": int, "charge_start": int, "charge_end": int, "wait": int}

#### `ScheduleResult`
- `scenario_name: str`
- `bus_timelines: list[BusTimeline]`
- `station_logs: dict[str, StationLog]`
- `scores: dict[str, float]` — {"individual": ..., "operator": ..., "overall": ..., "combined": ...}
- `weights_used: dict[str, float]`

---

## Phase 3: Scenario Loader (`scheduler/scenario_loader.py`)

### 3.1 Function: `load_scenario(filepath: str) -> Scenario`
- Read YAML file
- Parse segments into Route
- Parse buses (convert HH:MM → minutes from 19:00)
- Build Scenario object
- Validate: all bus IDs unique, directions valid (BK/KB), stations referenced exist in route

### 3.2 Function: `list_scenarios(scenarios_dir: str) -> list[str]`
- Return sorted list of scenario file paths

---

## Phase 4: Router (`scheduler/router.py`)

### 4.1 Core Logic
For a given bus direction and route, find all subsets of stations (of feasible sizes) such that:
- Distance from start to first charging station ≤ battery_range_km
- Distance between consecutive charging stations ≤ battery_range_km
- Distance from last charging station to destination ≤ battery_range_km
- Stations visited in route order (no backtracking)

### 4.2 Station Ordering for Directions
- **BK direction**: stations in order [A, B, C, D], distances measured from Bengaluru
- **KB direction**: stations in order [D, C, B, A], distances measured from Kochi

### 4.3 Feasibility Check Example (BK, 240 km range)
Segments: Bengaluru→A=100, A→B=120, B→C=100, C→D=120, D→Kochi=100
Cumulative from Bengaluru: A=100, B=220, C=320, D=440, Kochi=540

- Must charge first within 240 km → must charge at A (100 km) or B (220 km)
- After first charge (full 240), can go up to 240 more
- Min 2 charges for 540 km trip

Feasible 2-charge plans for BK: {A,C}, {B,C}, {B,D}, {A,D} (A→D=340 > 240? No, A=100, D=440, distance=340 > 240 ✗)

Wait, let me recalculate:
- A→C: C(320) - A(100) = 220 ≤ 240 ✓; C→Kochi: 540-320 = 220 ≤ 240 ✓
- B→C: C(320) - B(220) = 100 ≤ 240 ✓; C→Kochi: 220 ≤ 240 ✓
- B→D: D(440) - B(220) = 220 ≤ 240 ✓; D→Kochi: 100 ≤ 240 ✓
- A→D: D(440) - A(100) = 340 > 240 ✗

Feasible 2-charge plans for KB: {D,B}, {C,B}, {C,A}
  D→B: B(320) - D(100 from Kochi... wait, need to use KB distances)
  
KB distances: K=0, D=100, C=220, B=320, A=440, Bengaluru=540
  D→B: 320-100=220 ✓; B→Bengaluru: 540-320=220 ✓
  C→B: 320-220=100 ✓; B→Bengaluru: 220 ✓
  C→A: 440-220=220 ✓; A→Bengaluru: 100 ✓

Also feasible 3-charge plans: {A,B,C}, {A,B,D}, {B,C,D}, {A,C,D} (for BK)

### 4.4 Function: `find_feasible_plans(bus: Bus, route: Route, battery_range_km: float) -> list[list[str]]`
Returns list of station-id lists, each a feasible charging plan.

### 4.5 Function: `get_station_order_for_direction(direction: str, route: Route) -> list[str]`
Returns stations in visit order for the given direction.
- BK: [A, B, C, D]
- KB: [D, C, B, A]

---

## Phase 5: Scoring (`scheduler/scoring.py`)

### 5.1 Rule Registry
```python
# Dict[str, Callable[[ScheduleResult, dict], float]]
# Each rule returns a score (lower is better)
_rules: dict[str, Callable] = {}
```

### 5.2 Rule Interface
Each rule is a function: `(result: ScheduleResult, weights: dict) -> float`

### 5.3 Built-in Rules

#### `individual_wait_rule(result, weights)`
- Max wait time across all buses
- Wait = charge_start - arrival (per charging event, summed per bus if multiple waits)
- Lower is better

#### `operator_fairness_rule(result, weights)`
- For each operator, compute avg wait per bus
- Compute variance of these averages
- Lower variance = fairer

#### `overall_network_time_rule(result, weights)`
- Makespan = last arrival time - first departure time (in minutes)
- Lower = better schedule density

### 5.4 Function: `register_rule(name: str, func: Callable)`
### 5.5 Function: `evaluate(result: ScheduleResult, weights: dict) -> dict`
Returns dict of {rule_name: score} plus {"combined": weighted_sum}

Adding a new rule = call `register_rule()` once in engine initialization. No engine changes needed.

---

## Phase 6: Simulator (`scheduler/simulator.py`)

### 6.1 Approach: Discrete-Event Simulation

#### State
- `charger_queues: dict[str, list[BusTimelineEvent]]` — per station, FIFO queue of buses waiting
- `charger_available_times: dict[str, int]` — when each station's charger becomes free
- `bus_states: dict[str, BusState]` — tracking each bus's position/status

#### Events
Three event types, processed in chronological order:
1. **BUS_ARRIVAL** — bus arrives at a station
   - If charger free → start charging immediately (schedule CHARGE_END)
   - If charger busy → add to queue
2. **CHARGE_END** — bus finishes charging
   - Record charge_end_time, departure_time = charge_end_time
   - Bus departs, schedules next BUS_ARRIVAL
   - If queue has waiting buses → pick next (FIFO), schedule CHARGE_START
3. **BUS_ARRIVAL_DESTINATION** — bus arrives at final destination

#### Deterministic Tie-Breaking
- When multiple events at same time: process in order CHARGE_END > BUS_ARRIVAL > BUS_ARRIVAL_DESTINATION
- When multiple buses in queue: sort by arrival time, then by bus ID (lexicographic)
- When same bus arrives at station exactly when another bus finishes: charger freed first, then new arrival gets it

### 6.2 Function: `simulate(scenario: Scenario, charging_plans: dict[str, list[str]]) -> ScheduleResult`
Takes scenario + per-bus station assignments, returns full ScheduleResult with timelines.

### 6.3 Function: `simulate_plan(scenario: Scenario, bus: Bus, plan: list[str], current_state: SimState) -> (BusTimeline, SimState)`
Simulate one bus's plan given current charger states. Returns the bus's timeline and updated state.

Used by the greedy engine to evaluate plan quality before committing.

### 6.4 Helper: Travel Time
`travel_time(distance_km, speed_kmh) = distance_km / (speed_kmh / 60)` in minutes.
At 60 km/h: travel time in minutes = distance in km (1 km/min).

### 6.5 ChargingEvent Creation
For each station in the bus's plan:
1. Compute arrival_time from departure/previous departure + travel time
2. Check charger availability:
   - If arrival_time >= charger_available_time[station] → start immediately
   - Else → start at charger_available_time[station], wait = start - arrival
3. charge_end = charge_start + charge_time_min (25)
4. bus departs (available for next segment)
5. Update charger_available_time = charge_end

---

## Phase 7: Engine (`scheduler/engine.py`)

### 7.1 Function: `run(scenario: Scenario) -> ScheduleResult`

#### Algorithm (Greedy Constructive)

```
1. Load rules from scoring registry
2. Sort buses by departure_time_minutes (ascending), tie-break by id
3. Initialize empty state (no buses assigned, chargers free at time 0)
4. For each bus in sorted order:
   a. Generate all feasible charging plans (router.py)
   b. For each plan:
      i. Simulate this bus's plan on top of current state
      ii. Compute preliminary score using weighted rules (based ONLY on what we have so far)
      iii. Store (plan, score)
   c. Pick the plan with minimum combined score (tie-break: plan index)
   d. Commit this bus's plan to the state
5. Run final full simulation with all committed plans
6. Compute final scores on full ScheduleResult
7. Return ScheduleResult
```

#### Score Computation During Greedy Step
Since we're scoring progressively, we evaluate against the partial schedule:
- Individual wait: max wait among buses assigned so far
- Operator fairness: variance among operator averages among assigned buses
- Overall: current makespan among assigned buses

This approximates the final score well enough for greedy selection.

### 7.2 Rule Registration
On startup, register all built-in rules. Future rules added by importing and calling `register_rule()`.

### 7.3 Function: `get_available_rules() -> list[str]`
Returns names of registered rules.

---

## Phase 8: Scenario Files (`data/scenarios/*.yaml`)

### 8.1 Common Template
```yaml
name: "Scenario N — Name"
description: "Description"
route:
  name: "Bengaluru → Kochi"
  segments:
    - from: Bengaluru  to: A  distance_km: 100
    - from: A          to: B  distance_km: 120
    - from: B          to: C  distance_km: 100
    - from: C          to: D  distance_km: 120
    - from: D          to: Kochi  distance_km: 100
operators:
  - id: kpn       name: KPN
  - id: freshbus  name: Freshbus
  - id: flixbus   name: Flixbus
stations:
  - id: A  name: "Station A"  chargers: 1
  - id: B  name: "Station B"  chargers: 1
  - id: C  name: "Station C"  chargers: 1
  - id: D  name: "Station D"  chargers: 1
weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0
constants:
  battery_range_km: 240
  charge_time_min: 25
  speed_kmh: 60
buses:
  - id: bus-BK-01  operator: kpn       direction: BK  departure_time: "19:00"
```

### 8.2 Scenario Files to Create

#### scenario_01.yaml (Even Spacing)
- 10 BK buses: 19:00, 19:15, 19:30, ..., 21:15 (15 min spacing)
- 10 KB buses: 19:00, 19:15, 19:30, ..., 21:15 (15 min spacing)
- Weights: 1.0, 1.0, 1.0

#### scenario_02.yaml (Bunched Start)
- BK buses: 19:00, 19:08, 19:16, 19:24, 19:32, 19:40, 19:48, 20:03, 20:18, 20:33
- KB buses: same pattern
- Weights: 1.0, 1.0, 1.0

#### scenario_03.yaml (Asymmetric Load)
- 10 BK: 19:00, 19:15, ..., 21:15
- 4 KB: 19:00, 19:35, 20:10, 20:45
- Weights: 1.0, 1.0, 1.0

#### scenario_04.yaml (Operator-heavy)
- 8 KPN + 1 Freshbus + 1 Flixbus for BK
- 10 mixed for KB
- Weights: individual=1.0, operator=2.0, overall=1.0

#### scenario_05.yaml (Worst Case Convergence)
- All 20 buses between 19:00 and 20:12 (every 8 min from each end)
- Weights: 1.0, 1.0, 1.0

---

## Phase 9: Streamlit App (`app.py`)

### 9.1 Layout
```
Page Title: "Bus Charging Scheduler"
├── Sidebar
│   ├── Scenario dropdown (select from data/scenarios/)
│   ├── Run Schedule button
│   └── Display weights & constants for selected scenario
└── Main Area (3 tabs)
    ├── Tab 1: Scenario Input
    │   ├── Route overview (segments table)
    │   ├── Buses table (ID, operator, direction, departure time)
    │   ├── Weights display
    │   └── Constants display
    ├── Tab 2: Per-Bus Timetable
    │   ├── Per-bus expandable sections
    │   └── Each shows: timeline table with station, arrival, charge, departure, wait
    └── Tab 3: Per-Station View
        ├── 4 columns (A, B, C, D)
        └── Each shows: charging order table with bus ID, arrival, charge start, charge end, wait
```

### 9.2 Key Behaviors
- On scenario select: load and display input data (no computation yet)
- On "Run Schedule" click: compute and cache result using `@st.cache_data`
- Results persist in app session until scenario changes

### 9.3 Helper Functions
- `format_time(minutes_from_1900) -> str` — convert to "HH:MM" display format
- `display_bus_timeline(bus_timeline)` — render per-bus table
- `display_station_log(station_log)` — render station queue table

---

## Phase 10: Documentation

### 10.1 ARCHITECTURE.md
Sections:
1. **Framework Choice** — Why rule-based DES over constraint programming / MILP / RL
2. **Data Structure Design** — Domain model walkthrough
3. **Anticipated Changes** — List of future changes and how each is handled:
   - Changing a weight → edit one value in YAML
   - Adding a charging rule → new class in scoring.py + register
   - Adding stations → add segment + station entry in YAML
   - Changing charger counts → edit station's chargers field
   - Adding operators → add operator entry + assign to buses
   - Changing route distances → edit segment distances
   - Multiple routes → extend Route model
   - Time-of-day electricity costs → new scoring rule
   - Priority buses → new bus field + new scoring rule
   - Driver shifts → new bus field + constraint check
4. **Weight Change Example**
5. **New Rule Example**
6. **Assumptions**

### 10.2 README.md
Sections:
1. **Overview**
2. **Quick Start** — `pip install -r requirements.txt && streamlit run app.py`
3. **Project Structure**
4. **Usage Guide** — How to select scenarios, view results
5. **Customization**
   - Changing weights
   - Adding scenarios
   - Adding rules
6. **Data Format Reference**

---

## Phase 11: Verification & Testing

### 11.1 Manual Verification Checklist
- [ ] All 5 scenarios load without errors
- [ ] Each bus has at least 2 charging events
- [ ] No bus exceeds 240 km between charges
- [ ] Station queues show sensible order (no conflicts)
- [ ] Different weights produce different schedules (compare S1 vs S4)
- [ ] `streamlit run app.py` starts without errors
- [ ] UI shows all 3 tabs with correct data

### 11.2 Edge Cases
- Bus departing and arriving at same time as another
- Multiple buses arriving at same station simultaneously (deterministic tie-break by bus ID)
- Scenario with empty buses list (error handling)
- Invalid station reference in bus route (validation)

---

## Implementation Order Summary
1. Scaffolding (dirs, `__init__.py`, `requirements.txt`)
2. `domain.py` — all data classes
3. `scenario_loader.py` — YAML → Scenario
4. `router.py` — feasible station combinations
5. `scoring.py` — soft rules + registry
6. `simulator.py` — discrete-event simulation
7. `engine.py` — greedy orchestrator
8. 5 scenario YAML files
9. `app.py` — Streamlit UI
10. `ARCHITECTURE.md` + `README.md`
11. Smoke test
