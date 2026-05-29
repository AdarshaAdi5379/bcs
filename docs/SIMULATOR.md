# Simulator

## Overview

The discrete-event simulator (`simulator.py`) transforms selected charging plans into grounded timelines. It processes bus arrivals, charging, and departure events in chronological order, respecting charger capacity with FIFO queuing.

## Core Loop

The simulator drives a single function:

```python
def simulate(scenario, selected_plans) -> ScheduleResult
```

**Input**: A `Scenario` and a `dict[bus_id, CandidatePlan]` mapping each bus to its selected charging plan.

**Output**: A `ScheduleResult` containing per-bus timelines and per-station charge logs.

## Event Types

Three event types are processed in chronological order:

| Event | Trigger | Effect |
|-------|---------|--------|
| `ARRIVE` | Bus reaches a station | If a charger is free → schedule `CHARGE_START` immediately. Else → enter FIFO queue. |
| `CHARGE_START` | Charger allocated | Schedule `CHARGE_COMPLETE` at `now + charge_time_min`. Mark charger as busy. |
| `CHARGE_COMPLETE` | Timer expires | Free charger slot. If queue is non-empty → dequeue next bus → schedule its `CHARGE_START`. |

## Bus Lifecycle

```
Departure (terminal)
    │
    ▼
Travel to Station 1
    │
    ▼
Arrive at Station 1
    │
    ├── Charger free? ──YES──→ Start charging (CHARGE_START)
    └── All busy? ────NO───→ Enter FIFO queue
                                  │
                              (waiting...)
                                  │
                              Charger freed → Dequeue → Start charging
                                  │
                              CHARGE_COMPLETE
                                  │
                              ▼
                         Travel to Station 2
                              │
                            ...
                              │
                         Arrive at destination
```

## Charger Allocation

Each station has a fixed number of chargers (from `stations.[].chargers`).

```python
charger_availability: dict[StationID, int]
# Initialized: station.chargers for each station
# Decremented on CHARGE_START
# Incremented on CHARGE_COMPLETE
```

When a bus arrives and `charger_availability[station] > 0`, charging begins immediately. Otherwise, the bus is appended to `station_queues[station]` (a FIFO list).

When a charger frees up, the first bus in that station's queue is dequeued and begins charging.

## Queue Model

```python
station_queues: dict[StationID, list[tuple[bus_id, arrival_time]]]
```

- **Discipline**: FIFO (first arrived, first charged)
- **No preemption**: Once a bus starts charging, it runs to completion
- **No lookahead**: The queue doesn't consider which bus "needs" charging sooner

## Edge Cases

### Same-time arrivals
If two buses arrive at the same station simultaneously, order is determined by their position in the bus list (deterministic by bus ID).

### Missed depot charge
If a bus's departure time is before its first planned charge, the bus simply starts its first segment with a full battery (depot-charged assumption).

### Overnight schedules
Times can cross midnight. The simulator uses minutes-from-midnight as the time axis.

## Data Structures

### PerBusTimeline

```python
@dataclass
class PerBusTimeline:
    bus: Bus
    stations_used: list[StationID]
    station_arrivals: dict[StationID, float]  # minutes-from-midnight
    station_departures: dict[StationID, float]
    wait_durations: dict[StationID, float]     # arrival → charge start delay
    charge_durations: dict[StationID, float]
    total_wait: float
    final_arrival: float                        # time at destination
```

### StationChargeLog

```python
@dataclass
class StationChargeLog:
    station: Station
    charges: list[ChargeEntry]

@dataclass
class ChargeEntry:
    bus_id: str
    arrival_time: float
    charge_start: float
    charge_end: float
    wait_duration: float
```

## Integration

The simulator is called from:
1. `engine.py` — to evaluate plan selections (during beam search scoring)
2. `state.py` — `clone_and_extend()` simulates one more bus on existing state
3. `app.py` — final result is passed to UI for display
