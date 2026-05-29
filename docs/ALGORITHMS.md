# Algorithms

## Core Problem

Given a set of buses, each with a set of feasible charging plans (station combinations), select one plan per bus to minimize a weighted combination of:

- **Individual wait**: max single-bus wait time
- **Operator fairness**: max operator disadvantage
- **Overall time**: network makespan

Subject to:
- **Battery range**: no segment exceeds `battery_range_km`
- **Route order**: stations visited monotonically
- **Charger capacity**: station chargers are not overloaded

## Algorithm 1 — Plan Generation

### `route()` in `router.py`

For each bus direction, find all station subsets that satisfy the battery range constraint.

**Input**: Route segments + battery range  
**Output**: `list[list[StationID]]` — all feasible station combinations

**Algorithm**:

```
For each direction (BK, KB):
  Order stations by route position
  For each combination size k (1 to N):
    Generate combinations of k stations from N
    For each combination:
      Check: for every consecutive pair (including start and end),
             is the distance ≤ battery_range?
      If all pass, keep this combination
  Return all valid combinations
```

This is O(N! / (k!(N-k)!)) worst case, but N (number of stations) is small (< 10 in practice).

### `generate_candidate_plans()` in `planner.py`

For each bus, enumerate all feasible station combinations and produce `CandidatePlan` objects:

```python
@dataclass
class CandidatePlan:
    bus_id: str
    stations: list[tuple[StationID, charge_duration]]
```

Each candidate plan is a valid way for this bus to complete its route.

**Complexity**: O(buses × valid_combinations). Typically 10–30 plans per bus.

## Algorithm 2 — Greedy Search

**File**: `engine.py`, function `run(..., strategy="greedy")`

Processes buses in order. For each bus, evaluates every candidate plan against the current state, picks the one with the lowest score, and commits it.

```
state = empty
for each bus (in bus list order):
    best_plan = None
    best_score = ∞
    for each candidate plan for this bus:
        new_state = state.clone_and_extend(plan)
        score = soft_rules.evaluate(new_state)
        if score < best_score:
            best_score = score
            best_plan = plan
    state.commit(best_plan)
return state.as_result()
```

**Complexity**: O(n · p · s) where n = buses, p = plans per bus, s = score evaluation cost.

**Strengths**: Fast, simple, deterministic.  
**Weaknesses**: Greedy choices early can force poor choices later (no backtracking).

## Algorithm 3 — Beam Search

**File**: `engine.py`, function `run(..., strategy="beam")`

Maintains K partial solutions (beams). For each bus, extends each beam with all candidate plans, keeps the K lowest-scoring extensions.

```
K = 3  # beam width
beams = [empty_state]
for each bus (in bus list order):
    candidates = []
    for each beam in beams:
        for each candidate plan for this bus:
            new_state = beam.clone_and_extend(plan)
            score = soft_rules.evaluate(new_state)
            candidates.append((score, new_state))
    sort candidates by score
    beams = candidates[0:K]  # keep K best
return beams[0].as_result()  # return the best
```

**Complexity**: O(K · n · p · s). With K=3, roughly 3× greedy.

**Strengths**: Better global solutions. Can recover from locally suboptimal choices.  
**Weaknesses**: Memory usage (K deep copies of state per step). No guarantee of global optimum.

## Algorithm 4 — Queue Simulation

**File**: `simulator.py`

Discrete-event simulation that grounds abstract plans into concrete times:

1. For each bus, compute arrival times at each station based on speed and segment distances
2. Process events in chronological order:
   - **Arrive**: check charger availability; start charging or enqueue
   - **ChargeStart**: allocate charger, schedule completion timer
   - **ChargeComplete**: free charger, dequeue next bus
3. Track wait times, charge durations, and departure times per bus per station

**Complexity**: O(E log E) where E = total events ≈ buses × stations × 3.

## Algorithm 5 — State Extension

**File**: `state.py`, method `clone_and_extend()`

```python
def clone_and_extend(self, plan: CandidatePlan) -> SchedulingState:
    new_state = copy.deepcopy(self)
    new_state.bus_index += 1
    new_state.selected_plans[plan.bus_id] = plan
    # Re-simulate from scratch with the new plan added
    result = simulate(self.scenario, new_state.selected_plans)
    new_state.bus_timelines = result.bus_timelines
    new_state.station_queues = result.station_queues
    return new_state
```

Deep copy is used to avoid mutating shared state between beams.

## Comparison

| Criterion | Greedy | Beam Search |
|-----------|--------|-------------|
| Time | O(n·p·s) | O(K·n·p·s) |
| Memory | O(1) | O(K·state_size) |
| Optimality | Local only | Near-optimal (K-trades) |
| Determinism | Yes | Yes |
| Use case | Exploration, quick runs | Final schedule, accuracy |

## Extensibility

To add a new search strategy:

```python
# In engine.py
def run(strategy="custom"):
    if strategy == "custom":
        return custom_search(scenario)
```

The engine dispatches on strategy name. Add a new branch and implement your search using the same `SchedulingState`, `clone_and_extend()`, and `score_candidate()` primitives.
