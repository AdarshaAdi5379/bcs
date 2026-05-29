# Architecture

## Scheduling Approach: Rule-Based Greedy Construction + Discrete-Event Simulation

### Why This Approach

The bus charging scheduling problem sits in a specific sweet spot: it has hard physical constraints (range, charge time, one charger per station) that must always hold, and soft operational preferences (fairness, speed) that should be optimized but can be traded off.

I evaluated several approaches:

| Approach | Strengths | Weaknesses | Verdict |
|----------|-----------|------------|---------|
| **Mixed-Integer Linear Programming** | Optimal solutions | Scale poorly (exponential with buses/stations); hard to add soft rules; expensive per-scenario solve | Wrong fit |
| **Constraint Programming** | Clean constraint modeling | Poor with weighted soft objectives; commercial solvers needed for scale | Wrong fit |
| **Reinforcement Learning** | Adaptive, flexible | Massive state space; needs training; opaque results; overkill for 20 buses | Wrong fit |
| **Heuristic / Greedy + DES** | Fast, deterministic, transparent; easy to add rules; scales linearly | Not provably optimal | Right fit |

I chose **rule-based greedy construction with discrete-event simulation** because:

1. **Deterministic and explainable**: Every schedule decision can be traced back to a specific rule evaluation. When an operator asks "why did bus X wait 15 minutes at station B?", the answer is in the event log.

2. **Linearly scalable**: Adding 100 more buses means 5x the processing, not 25x. The greedy algorithm processes each bus once, evaluating O(plans) × O(rules) per bus.

3. **Rule extensibility without engine changes**: The soft rule registry pattern means adding a new objective is a single file addition. The engine iterates over all registered rules — it never needs to know about specific rules.

4. **Weight tunability**: Since all optimization happens through weighted rule evaluation, changing any weight is a single value edit. No solver warm-starts, no model retraining.

5. **Data-driven**: The entire problem definition lives in scenario YAML files. The scheduler code never references "A", "B", "KPN", or "20 buses" — it all comes from data.

## Data Structure Design

The domain model is designed around the concept that **everything is data**. The code is a generic interpreter of scenario descriptions.

### Core Classes (`scheduler/domain.py`)

```
Segment(from_station, to_station, distance_km)
  ↓ (ordered list)
Route(name, segments)
  ├── stations_bk() → [A, B, C, D]         (order for BK direction)
  ├── stations_kb() → [D, C, B, A]         (order for KB direction)
  ├── cumulative_bk() → {Bengaluru: 0, A: 100, ...}
  ├── cumulative_kb() → {Kochi: 0, D: 100, ...}
  └── distance_between(a, b, direction) → km

Bus(id, operator, direction, departure_time_minutes)

Operator(id, name)

Scenario(name, route, operators, station_ids, chargers_per_station, buses, weights, constants)
  ↑ All inputs for one scheduling problem.
  ↑ Loaded from YAML, never hardcoded.

ChargingEvent(station_id, arrival_time, charge_start_time, charge_end_time, departure_time)

BusTimeline(bus, charging_events)
  ├── total_wait → sum of wait times
  ├── final_arrival_time → last departure time
  └── stations_used → list of station IDs

StationChargeEntry(bus_id, arrival, charge_start, charge_end, wait)

StationLog(station_id, entries)  → ordered list of charging sessions

ScheduleResult(scenario_name, bus_timelines, station_logs, scores, weights_used)
  ↑ Complete output of a scheduling run.
```

### Key Design Decisions

- **Integer minutes internally**: All times are stored as minutes offset from 19:00 (the reference departure time). This avoids floating-point drift and makes comparison/ordering trivial.
- **Cumulative route distances**: Rather than storing segment distances, the Route computes cumulative distances in each direction once. Feasibility checks become simple range comparisons: `distance_between(a, b) ≤ battery_range`.
- **Direction-aware station ordering**: The Route provides `station_order_for_direction(direction)`, which returns different station sequences for BK vs KB directions. This keeps feasibility logic direction-agnostic — the same code works for both.
- **Charger count per station**: Stored as `dict[str, int]` even though all current stations have 1 charger. The simulator uses `available_time` (tracking when each charger slot is free) and supports multiple slots natively.

## Anticipated Changes and How the Design Handles Them

### 1. Changing a Weight
**Change**: One value in scenario YAML.
**Why no code change**: The engine reads weights from the Scenario object. Scoring functions receive weights as a parameter. The rule evaluation loop is `for name, func in _rules.items(): w * func(result, weights)`. No code references weight values by name in the engine.

### 2. Adding a New Soft Rule
**Change**: One new function + one `register_rule()` call in `scoring.py`. Plus an optional weight in YAML.
**Why no code change**: The engine iterates `scoring.registered_rules()`. New rules are automatically picked up. The scoring registry pattern decouples rule definition from execution.

### 3. Adding a Station
**Change**: Add a segment to the YAML route + a station entry.
**Why no code change**: The Route is built dynamically from segments. The router finds feasible plans by inspecting station lists and cumulative distances at runtime. Station IDs are strings, never hardcoded.

### 4. Changing Charger Count Per Station
**Change**: Edit the `chargers` field in a station's YAML entry (e.g., from 1 to 2).
**Why no code change**: The simulator's `ChargerState.available_time` tracks when each charger slot is free. Multiple chargers are modeled as multiple independent slots. No hardcoded "1 charger" assumption.

### 5. Changing Battery Range or Charge Time
**Change**: Edit `constants` in YAML.
**Why no code change**: The router reads `battery_range_km` to check feasibility. The simulator reads `charge_time_min` for charging duration. Both are parameters, not constants.

### 6. Adding a New Operator
**Change**: Add an operator entry + assign operator IDs to buses in YAML.
**Why no code change**: Operator is a string field on Bus. The operator fairness rule aggregates by `bus.operator`. Additional operators just add more entries to the aggregation dictionary.

### 7. Changing Route Distances
**Change**: Edit segment `distance_km` values in YAML.
**Why no code change**: The Route recomputes cumulative distances from segments. Feasibility checks use the new distances automatically.

### 8. Adding a Second Route
**Change**: Add a second route entry in YAML (if the data format evolves) or create a new scenario file with a different route definition.
**Why minimal code change**: The Route class stores its own segments and computations. A multi-route extension would need a `Route` reference on each bus, but the Route model itself wouldn't change.

### 9. Time-of-Day Electricity Costs
**Change**: Add a new scoring rule that penalizes charging during peak hours.
**Why no code change**: This is a new soft rule. Register it in `scoring.py`. The rule receives the full schedule (with charge times) and can compute costs based on time-of-day pricing tables.

### 10. Priority Buses
**Change**: Add a `priority: true` field to certain buses in YAML.
**Why no code change**: The queue ordering in the simulator would need to be updated to sort by priority first, then by arrival. This is a single change to the queue data structure in `simulator.py`, not the engine architecture.

### 11. Driver Shift Constraints
**Change**: Add `max_drive_time` or `shift_start` fields to bus entries.
**Why minimal code change**: This would require a new hard constraint check (not a soft rule). The cleanest approach is a new `validator.py` module that the engine calls post-simulation. The existing architecture separates concerns cleanly enough that this doesn't require rewriting anything.

## How to Change a Weight

In the scenario YAML file, find the `weights:` section and edit the value:

```yaml
# data/scenarios/scenario_01.yaml
weights:
  individual: 1.0
  operator: 3.0    # changed from 1.0 to 3.0
  overall: 1.0
```

That's it. The engine will use the new weight on the next `Run Schedule` click.

## How to Add a New Rule

In `scheduler/scoring.py`, add:

```python
def peak_hour_penalty_rule(result: ScheduleResult, weights: dict) -> float:
    penalty = 0.0
    for tl in result.bus_timelines:
        for ev in tl.charging_events:
            # Penalize charging between 17:00 and 21:00 (peak hours)
            hour_minutes = 19 * 60  # reference is 19:00
            charge_hour = (hour_minutes + ev.charge_start_time) // 60 % 24
            if 17 <= charge_hour <= 21:
                penalty += 10.0
    return penalty

register_rule("peak_hour", peak_hour_penalty_rule)
```

Add the weight to your scenario YAML:

```yaml
weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0
  peak_hour: 0.5    # new weight
```

The engine automatically picks up the new rule via `registered_rules()`.

## How the Scheduler Works (End-to-End)

### Step 1: Load Scenario
`scenario_loader.load_scenario()` reads YAML → validates → returns a `Scenario` object.

### Step 2: Generate Feasible Plans
For each bus, `router.find_feasible_plans()` computes all station subsets (size N to N) that satisfy range constraints. For a BK bus with 240 km range, feasible 2-station plans are: {A,C}, {B,C}, {B,D}. Three-station plans (e.g., {A,B,C}) are also generated.

### Step 3: Greedy Construction
Buses sorted by departure time. For each bus:
1. For each feasible plan, simulate the bus's timeline on a copy of current charger states
2. Build a partial schedule including previously committed buses plus this candidate
3. Score it using all registered soft rules with the scenario's weights
4. Pick the lowest-scoring plan
5. Commit the plan (update charger states)

### Step 4: Final Simulation
Run the full discrete-event simulation with all committed plans to produce the final timeline.

### Step 5: Score
Evaluate the complete schedule against all soft rules. Display results in the UI.

## Discrete-Event Simulation Details

### Event Types (processed chronologically via min-heap)
1. **BUS_ARRIVAL**: Bus arrives at a station. If charger free → charge immediately. If busy → enqueue.
2. **CHARGE_END**: Bus finishes charging. Dequeue next waiting bus (FIFO, tie-break by bus ID). Schedule next destination arrival.
3. **BUS_ARRIVAL_DEST**: Bus reaches final terminal. No further action.

### Deterministic Tie-Breaking
- Same-time events: CHARGE_END > BUS_ARRIVAL > BUS_ARRIVAL_DEST
- Queue order: arrival time ascending, then bus ID lexicographic
- Plan selection tie-break: plan index (first generated wins)

## Assumptions

1. **Speed = 60 km/h**: Travel time in minutes equals distance in km. No traffic, no speed variation.
2. **All times relative to 19:00**: The reference time is when the first bus departs. Days are irrelevant.
3. **Buses depart with full charge (240 km range)**: Both terminals have slow chargers. This is an external precondition, not part of the scheduling problem.
4. **Fixed charging time (25 min)**: Always charges to full. No partial charging.
5. **One charger per station (default)**: Configurable via YAML, but scenarios use 1.
6. **All buses identical**: Same range, same charge time, same speed.
7. **Minimum 2 charges**: The 540 km route requires at least 2 charging stops with 240 km range.
8. **No bus can skip charging**: The route is 540 km, range is 240 km. Every bus must charge at least twice.
9. **FIFO queuing**: No preemption. First-come-first-served with deterministic bus ID tie-breaking.
10. **Static scenario**: All inputs known upfront. No real-time disruptions or dynamic re-routing.
