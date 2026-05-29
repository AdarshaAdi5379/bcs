# Scenario Guide

## What Is a Scenario?

A scenario is a YAML file describing a complete scheduling problem: route geometry, stations, operators, buses, weights, and constants. Placing a `.yaml` file in `data/scenarios/` makes it available in the UI dropdown.

## Anatomy of a Scenario

```yaml
name: "Descriptive Name"
description: "What this scenario tests"

route:
  name: "Bengaluru → Kochi"
  segments:
    - from: Bengaluru
      to: A
      distance_km: 100

operators:
  - id: kpn
    name: KPN

stations:
  - id: A
    name: "Station A"
    chargers: 1

weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0

constants:
  battery_range_km: 240
  charge_time_min: 25
  speed_kmh: 60

buses:
  - id: bus-BK-01
    operator: kpn
    direction: BK
    departure_time: "19:00"
```

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable scenario name |
| `route` | object | Route with segments (from, to, distance_km) |
| `operators` | list | Operators with `id` and `name` |
| `stations` | list | Stations with `id`, `name`, `chargers` |
| `weights` | object | Soft rule weights (at least `individual`, `operator`, `overall`) |
| `constants` | object | `battery_range_km`, `charge_time_min`, `speed_kmh` |
| `buses` | list | Buses with `id`, `operator`, `direction`, `departure_time` |

## Route Segments

Segments define road portions in order. The route has two directions:
- **BK** (e.g., Bengaluru → Kochi) — traverses segments in listed order
- **KB** (e.g., Kochi → Bengaluru) — traverses segments in reverse order

Segments must form a contiguous chain: `A→B, B→C, C→D, ...`

## Stations

Station IDs must match the intermediate points in route segments (e.g., A, B, C, D). The terminal points (Bengaluru, Kochi) are not stations.

Each station has a `chargers` count (1+).

## Direction Convention

Buses have a `direction` field:
- `BK` — goes from start city to end city (terminal A → terminal B)
- `KB` — goes from end city to start city

The scheduler treats directions independently; buses in different directions can overlap at shared stations.

## Bus ID Convention

```yaml
  - id: bus-BK-03    # bus-{direction}-{sequence}
  - id: bus-KB-07
```

IDs must be unique. The prefix (`bus-`) is a convention, not enforced.

## Weights

Each weight can be any non-negative float. Setting a weight to 0 effectively disables that rule.

```yaml
weights:
  individual: 1.0    # Max single-bus wait time importance
  operator: 1.0      # Operator fairness importance
  overall: 1.0       # Network makespan importance
```

The combined score is: `sum(weight_i · score_i)` for each soft rule.

## Constants

| Constant | Default | Description |
|----------|---------|-------------|
| `battery_range_km` | 240 | Max km a bus can travel on a full charge |
| `charge_time_min` | 25 | Minutes a bus needs to charge at a station |
| `speed_kmh` | 60 | Average bus speed |

## Provided Scenarios

### Scenario 1 — Even Spacing (Baseline)

Buses depart every 15 minutes in each direction starting 19:00. Well-balanced traffic from both directions. Each station has 1 charger.

**Behavior**: Low contention. Most buses experience zero or minimal wait. All plans are close in score.

### Scenario 2 — Bunched Start

All 20 buses depart at 19:00. Heavy early contention at Station A.

**Behavior**: High congestion. Large queues build at Station A. The scheduler must spread buses across alternative charging plans to minimize makespan and operator disadvantage.

### Scenario 3 — Asymmetric Load

18 BK-direction buses depart at 19:00 (spread across 5 minutes), but only 2 KB-direction buses. Station A (nearest to BK start) has 3 chargers, B and C have 1.

**Behavior**: Massively asymmetric load. Tests whether the scheduler can utilize the extra chargers at A to absorb the BK surge while not over-penalizing KB buses.

### Scenario 4 — Operator-Fairness Stress

Similar to Scenario 2 (bunched start) but with uneven operator distribution: KPN has 10 buses, Freshbus 6, Flixbus 4. Operator weight is 2.0.

**Behavior**: The high operator weight forces the scheduler to spread wait times evenly across operators even when one operator has many more buses.

### Scenario 5 — Worst-Case Convergence

All 20 buses, same operator (KPN), all depart at 19:00, each station has 1 charger, operator weight is 0.

**Behavior**: Pure test of makespan minimization with no other constraints. All buses are identical in operator, so operator fairness has no effect. The scheduler should find the plan set that minimizes overall completion time.
