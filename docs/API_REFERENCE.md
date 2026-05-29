# API Reference

## `scheduler/scenario_loader.py`

### `load_scenario(path: str) -> Scenario`

Parses a YAML scenario file into a `Scenario` domain object.

```python
scenario = load_scenario("data/scenarios/scenario_01.yaml")
scenario.route.name         # "Bengaluru → Kochi"
scenario.buses[0].id        # "bus-BK-01"
```

**Raises**: `FileNotFoundError`, `yaml.YAMLError`, `ValueError` for missing required fields.

### `load_all_scenarios(directory: str) -> dict[str, Scenario]`

Loads all `.yaml` files from a directory. Returns `{filename_without_ext: Scenario}`.

---

## `scheduler/domain.py`

### `Segment`
```python
@dataclass
class Segment:
    from_loc: str
    to_loc: str
    distance_km: float
```

### `Route`
```python
@dataclass
class Route:
    name: str
    segments: list[Segment]
```

### `Station`
```python
@dataclass
class Station:
    id: str
    name: str
    chargers: int
```

### `Operator`
```python
@dataclass
class Operator:
    id: str
    name: str
```

### `Bus`
```python
@dataclass
class Bus:
    id: str
    operator: str
    direction: str          # "BK" or "KB"
    departure_time: str     # "HH:MM" format
```

### `Weights`
```python
@dataclass
class Weights:
    individual: float
    operator: float
    overall: float
```

### `Constants`
```python
@dataclass
class Constants:
    battery_range_km: float
    charge_time_min: float
    speed_kmh: float
```

### `Scenario`
```python
@dataclass
class Scenario:
    name: str
    description: str
    route: Route
    operators: list[Operator]
    stations: list[Station]
    weights: Weights
    constants: Constants
    buses: list[Bus]
```

### `CandidatePlan`
```python
@dataclass
class CandidatePlan:
    bus_id: str
    stations: list[tuple[str, float]]  # [(station_id, charge_duration_min)]
```

### `ChargeEntry`
```python
@dataclass
class ChargeEntry:
    bus_id: str
    arrival_time: float
    charge_start: float
    charge_end: float
    wait_duration: float
```

### `StationChargeLog`
```python
@dataclass
class StationChargeLog:
    station: Station
    charges: list[ChargeEntry]
```

### `PerBusTimeline`
```python
@dataclass
class PerBusTimeline:
    bus: Bus
    stations_used: list[str]
    station_arrivals: dict[str, float]
    station_departures: dict[str, float]
    wait_durations: dict[str, float]
    charge_durations: dict[str, float]
    total_wait: float
    final_arrival: float
```

### `Scores`
```python
@dataclass
class Scores:
    individual: float
    operator: float
    overall: float
    combined: float  # weighted sum
```

### `ScheduleResult`
```python
@dataclass
class ScheduleResult:
    timelines: list[PerBusTimeline]
    station_logs: list[StationChargeLog]
    scores: Scores
    all_plans: dict[str, list[CandidatePlan]]   # all considered plans per bus
    selected_plans: dict[str, CandidatePlan]     # chosen plans
    plan_explanations: dict[str, PlanExplanation]
```

### `PlanExplanation`
```python
@dataclass
class PlanExplanation:
    bus_id: str
    selected_plan: CandidatePlan
    alternatives: list[ScoredPlan]
    winner_reason: str
```

### `ScoredPlan`
```python
@dataclass
class ScoredPlan:
    plan: CandidatePlan
    score: Scores
    simulated: PerBusTimeline
```

---

## `scheduler/engine.py`

### `run(scenario: Scenario, strategy: str = "greedy") -> ScheduleResult`

Main entry point. Orchestrates plan generation, selection, and simulation.

```python
result = run(scenario, strategy="beam")
result.scores.combined    # final combined score
```

**Parameters**:
- `scenario` — a loaded `Scenario`
- `strategy` — `"greedy"` (default) or `"beam"`

**Strategy dispatch**:
- `"greedy"` → `_greedy_search(scenario)`
- `"beam"` → `_beam_search(scenario, K=3)`

---

## `scheduler/router.py`

### `route(scenario: Scenario) -> dict[str, list[list[str]]]`

Computes all feasible station combinations for both directions.

```python
feasible = route(scenario)
feasible["BK"]   # [[A], [A, C], [B], [B, D], [C], [D], ...]
feasible["KB"]   # similarly for reverse direction
```

Returns `{direction: [list_of_station_lists]}`. Each inner list is a valid charging stop set for that direction.

---

## `scheduler/planner.py`

### `generate_candidate_plans(scenario: Scenario, feasible_stations: dict) -> dict[str, list[CandidatePlan]]`

Generates all candidate plans for all buses.

```python
plans = generate_candidate_plans(scenario, feasible_stations)
plans["bus-BK-01"]  # [CandidatePlan, CandidatePlan, ...]
```

Returns `{bus_id: [CandidatePlan, ...]}`.

---

## `scheduler/simulator.py`

### `simulate(scenario: Scenario, selected_plans: dict[str, CandidatePlan]) -> ScheduleResult`

Simulates the selected plans through discrete-event simulation.

```python
result = simulate(scenario, selected_plans)
```

Used internally by `SchedulingState.clone_and_extend()` and by `engine.run()`.

---

## `scheduler/state.py`

### `SchedulingState`

Incremental state for building schedules one bus at a time.

```python
state = SchedulingState(scenario, plans)
state.bus_index                    # current position (0 before any plans)
state.clone_and_extend(plan)       # → new SchedulingState with plan added
state.as_result()                  # → ScheduleResult
```

**Methods**:

| Method | Returns | Description |
|--------|---------|-------------|
| `clone_and_extend(plan)` | `SchedulingState` | Deep copies state and adds one bus's plan |
| `as_result()` | `ScheduleResult` | Finalizes into a result object with plan explanations |

---

## `scheduler/validator.py`

### `validate(scenario: Scenario) -> list[str]`

Runs all hard rule checks against the scenario.

```python
errors = validate(scenario)
if errors:
    for e in errors:
        print(f"Validation error: {e}")
```

Returns a list of error messages (empty list = valid).

**Checks performed**:
- Route segments form a connected chain
- All operator references in buses exist in operators list
- All station IDs referenced in route exist in stations list
- `battery_range_km` and `charge_time_min` are positive
- All weights are non-negative
- Bus departure times are valid `HH:MM` format
- Each bus has at least one feasible charging plan

---

## `scheduler/rules/base.py`

### `SoftRule`

```python
class SoftRule(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def evaluate(self, state: SchedulingState) -> float: ...
```

### `HardRule`

```python
class HardRule(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def check(self, scenario: Scenario) -> list[str]: ...
```

### `RuleRegistry`

```python
RuleRegistry.register("rule_name")  # decorator
RuleRegistry.get("rule_name")       # → class
RuleRegistry.get_all()              # → list[class]
```

---

## `app.py`

### Streamlit Entry Point

Run with:

```bash
streamlit run app.py
```

No Python API — the app is purely a UX layer. It reads from `scheduler/` modules and displays results via Streamlit components.
