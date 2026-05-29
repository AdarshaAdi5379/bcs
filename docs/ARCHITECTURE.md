# Architecture

## Overview

The bus charging scheduler is a rule-based, data-driven scheduling engine. It reads scenario files (YAML), generates feasible charging plans per bus, selects the best global plan combination via greedy or beam search optimization, simulates the schedule with discrete-event simulation, and scores results against configurable soft rules.

The system follows a **pipeline architecture** with four stages:

```
Scenario File → Plan Generation → Plan Selection → Simulation → Scoring → Result
```

## Pipeline Stages

### 1. Input Loading — `scenario_loader.py`

Reads a YAML scenario file and parses it into a `Scenario` domain object. Validates basic YAML structure (required keys present).

### 2. Plan Generation — `planner.py` + `router.py`

- `route(Scenario)` computes all feasible station combinations per bus direction. A bus needs to charge at enough stations to never exceed `battery_range_km` between charges. All combinations of available stations that satisfy this constraint are generated.
- `generate_candidate_plans(Scenario)` produces a list of `CandidatePlan` objects per bus. Each plan specifies which stations the bus charges at and the order.

### 3. Plan Selection — `engine.py`

Two strategies:

| Strategy | Approach | Use Case |
|----------|----------|----------|
| `greedy` | Iterates buses in order, picks the plan with the lowest score increase at insertion | Speed (~O(n·p)) |
| `beam` | Beam search with K=3. Maintains K partial solutions, extends each with the next bus's plans, keeps the K lowest-scoring extensions | Better global quality (~O(K·n·p)) |

Both strategies use `score_candidate(State, CandidatePlan, …)` to evaluate plan quality via soft rules.

### 4. Simulation — `simulator.py`

Discrete-event simulation that converts selected plans into a grounded timeline:

- **Input**: For each bus, the selected `(stations, charge_order)` plus departure time, speed, battery range, charge time.
- **Process**: Events are processed in chronological order:
  1. **Bus arrives** at a station → enters FIFO queue if all chargers are busy
  2. **Bus starts charging** → a charger slot is allocated; a `CHARGE_COMPLETE` event is scheduled
  3. **Bus finishes charging** → charger slot freed; next queued bus starts
- **Output**: `ScheduleResult` containing `PerBusTimeline` for every bus and per-station charge logs.

### 5. Scoring — `rules/`

Hard rules are constraints — violations make a plan invalid or trigger validation errors.

Soft rules contribute weighted scores to plan quality:

| Rule | File | Measures |
|------|------|----------|
| Individual Wait | `soft/individual_wait.py` | Max wait any single bus experiences at any station |
| Operator Fairness | `soft/operator_fairness.py` | Max disadvantage of any operator vs the best-performing one |
| Overall Time | `soft/overall_time.py` | Total network makespan (last bus arrival at destination) |

Each soft rule implements `evaluate(state_or_result) → float`. Scores are combined as weighted sum using scenario weights, then normalized.

## Key Classes — `domain.py`

| Class | Role |
|-------|------|
| `Route` | Direction + ordered segments with distances |
| `Station` | ID, name, charger count |
| `Bus` | ID, operator, direction, departure time |
| `Operator` | ID + display name |
| `Scenario` | Root: route, stations, operators, buses, weights, constants |
| `CandidatePlan` | Bus + list of `(StationID, expected_charge_duration)` |
| `PerBusTimeline` | Simulated schedule for one bus: station visits, times, wait |
| `StationChargeLog` | One station's complete charge order |
| `ScheduleResult` | All timelines + logs + scores |
| `Scores` | Individual, operator, overall, combined |

## Rule Engine — `rules/`

Rules follow the **Strategy pattern** with a registry.

```
RuleRegistry (singleton)
├── HardRule (base)
│   ├── BatteryRangeHardRule    # No segment > battery_range_km
│   ├── RouteOrderHardRule      # Station visits are monotonic
│   └── ChargerCapacityHardRule # No overlapping charges
└── SoftRule (base)
    ├── IndividualWaitSoftRule
    ├── OperatorFairnessSoftRule
    └── OverallTimeSoftRule
```

Rules are registered via `@RuleRegistry.register()` class decorator and auto-discovered in `__init__.py`.

## State Machine — `state.py`

`SchedulingState` is an incremental accumulator:

```
SchedulingState
  .bus_index          → nth bus being scheduled (0..n-1)
  .selected_plans     → dict[bus_id, CandidatePlan]
  .bus_timelines      → list[PerBusTimeline] (simulated)
  .station_queues     → dict[StationID, list[...]]
  .clone_and_extend(plan) → SchedulingState
```

Each `clone_and_extend` call:
1. Copies all mutable state (deep copy)
2. Simulates the new bus's plan on top of existing state
3. Recalculates scores

Beam search clones K states per step.

## UI — `app.py`

Single-page Streamlit app with sidebar + 3 tabs.

```
app.py
├── Sidebar
│   ├── Scenario dropdown (auto-discovered from data/scenarios/)
│   ├── Strategy selector (greedy / beam)
│   └── Run button
├── Tab 1: "Scenario Input"
│   ├── Route segments table
│   ├── Operators table
│   ├── Stations table
│   ├── Buses table
│   ├── Weights
│   └── Constants
├── Tab 2: "Per-Bus Timetable"
│   └── Expandable per-bus section
│       ├── Station timeline (arrival, charge, departure, wait)
│       ├── Plan comparison (all alternatives with scores)
│       └── ↪ "Why this plan wins?" explanation
└── Tab 3: "Per-Station View"
    └── Per-station expandable section
        └── Charge log table (bus, arr, dep, wait)
└── Footer bar
    └── Scores display
```

## Design Decisions

1. **Data-driven over hardcoded** — everything in YAML. Adding a new scenario, station, or bus requires zero code changes.
2. **Plans before simulation** — plan generation enumerates all feasible station combinations first, then simulation grounds them. This separates combinatorial exploration from temporal resolution.
3. **Rule registry pattern** — rules are auto-registered via decorator and discovered by convention. Adding a new rule means writing one file — no wiring.
4. **Beam search with deep copy** — beam search clones state via Python's `copy.deepcopy`. This is simple but memory-heavy for large scenarios.

## Data Flow Diagram

```
YAML ──→ Scenario ──→ route() ──→ feasible_stations
                    ──→ generate_candidate_plans() ──→ list[CandidatePlan] per bus
                                                      │
                                          engine (greedy|beam)
                                                      │
                    schedule ←─ simulate() ←─ selected_plans
                    score ←─ rules evaluate
                    ──→ ScheduleResult ──→ Streamlit UI
```
