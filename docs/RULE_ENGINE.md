# Rule Engine

## Overview

The rule engine uses a **Strategy + Registry pattern**. Soft rules are weighted components of the objective function; hard rules are validation gates. All rules inherit from a common base class and are auto-discovered via a decorator-based registry.

## Architecture

```
RuleRegistry (module-level singleton)
├── _rules: dict[str, type] — maps rule_name → class
├── register(name) → decorator
├── get(name) → class
└── get_all() → list[type]

SoftRule (ABC)                     HardRule (ABC)
├── name: str                      ├── name: str
├── weight: float                  ├── check(scenario) → list[str]
├── evaluate(state) → float        └── (failures returned as messages)
└── (lower is better)
```

## Soft Rules — Objective Function

The combined score is:

```
combined = w_individual · individual_wait
         + w_operator    · operator_disadvantage
         + w_overall     · overall_time
```

Each rule is normalized so scores are comparable across scenarios.

### Individual Wait

**Class**: `IndividualWaitSoftRule`  
**File**: `rules/soft/individual_wait.py`  
**Measures**: The maximum wait time any single bus experiences across all stations.

A bus "waits" when it arrives at a station but all chargers are occupied. Wait is the time from arrival to charge start.

```python
class IndividualWaitSoftRule(SoftRule):
    def evaluate(self, state: SchedulingState) -> float:
        max_wait = max(
            (tl.total_wait for tl in state.bus_timelines),
            default=0.0
        )
        return max_wait / state.scenario.constants.normalization_factor
```

Lower is better. This rule penalizes schedules where one bus gets stuck waiting at a station while others have smooth service.

### Operator Fairness

**Class**: `OperatorFairnessSoftRule`  
**File**: `rules/soft/operator_fairness.py`  
**Measures**: The maximum disadvantage of any operator relative to the best-performing operator.

Operator disadvantage for operator O is:

```
disadvantage(O) = max(0, avg_wait(O) - min_avg_wait_across_operators)
```

The score is the maximum disadvantage across all operators.

This rule prevents the scheduler from systematically favoring one operator's buses over others.

### Overall Time (Makespan)

**Class**: `OverallTimeSoftRule`  
**File**: `rules/soft/overall_time.py`  
**Measures**: The total network makespan — the time from the first bus departure to the last bus reaching its destination.

This captures the overall efficiency of the schedule.

## Hard Rules — Constraints

Hard rules are checked in two places:
1. During **validation** (`validator.py`) — all hard rules check the scenario itself
2. During **simulation** — `ChargerCapacityHardRule` is enforced implicitly by the simulator's FIFO queue

### Battery Range

**Class**: `BatteryRangeHardRule`  
**File**: `rules/hard/battery_range.py`  
**Constraint**: No road segment between consecutive charging stations may exceed `battery_range_km`.

Applied in `route()` to filter station combinations and in validation to verify input constants.

### Route Order

**Class**: `RouteOrderHardRule`  
**File**: `rules/hard/route_order.py`  
**Constraint**: Stations must be visited in the order they appear in the route (monotonic traversal). A bus cannot skip ahead and come back.

Applied in `route()` when generating feasible station combinations.

### Charger Capacity

**Class**: `ChargerCapacityHardRule`  
**File**: `rules/hard/charger_capacity.py`  
**Constraint**: At any given time, at most `N` buses can be charging at a station with `N` chargers.

This is enforced by the discrete-event simulator's queue: when a bus arrives and all chargers are occupied, it enters a FIFO queue and waits.

## Adding a New Soft Rule

1. Create `scheduler/rules/soft/my_rule.py`:

```python
from scheduler.rules.base import SoftRule, RuleRegistry

@RuleRegistry.register("my_rule")
class MyRule(SoftRule):
    @property
    def name(self) -> str:
        return "my_rule"

    def evaluate(self, state: "SchedulingState") -> float:
        # Return a score (lower = better)
        return 0.0
```

2. Import it in `scheduler/rules/soft/__init__.py`:

```python
from . import my_rule
```

3. Add a weight in the scenario YAML:

```yaml
weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0
  my_rule: 0.5
```

## Adding a New Hard Rule

1. Create `scheduler/rules/hard/my_rule.py`:

```python
from scheduler.rules.base import HardRule, RuleRegistry

@RuleRegistry.register("my_hard_rule")
class MyHardRule(HardRule):
    @property
    def name(self) -> str:
        return "my_hard_rule"

    def check(self, scenario) -> list[str]:
        failures = []
        if not condition:
            failures.append("Something is wrong")
        return failures
```

2. Register in `scheduler/rules/hard/__init__.py`:

```python
from . import my_rule
```

## Rule Registry

The `RuleRegistry` is a singleton auto-populated via decorators at import time.

```python
class RuleRegistry:
    _instance = None
    _rules: dict[str, type] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(rule_cls: type):
            cls._rules[name] = rule_cls
            return rule_cls
        return decorator

    @classmethod
    def get_all(cls) -> list[type]:
        return list(cls._rules.values())
```

All rule modules are imported in their respective `__init__.py` files, which triggers the `@register` decorator and populates the registry.
