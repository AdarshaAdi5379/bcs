import heapq
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional

from scheduler.domain import (
    Scenario, Bus, ChargingEvent, BusTimeline, StationChargeEntry, StationLog, ScheduleResult,
)


class EventType(IntEnum):
    CHARGE_END = 0
    BUS_ARRIVAL = 1
    BUS_ARRIVAL_DEST = 2


@dataclass(order=True)
class SimEvent:
    time: int
    event_type: EventType
    bus_id: str = field(compare=False)
    station_id: str = field(compare=False)


@dataclass
class ChargerState:
    available_times: list[int]
    queue: list[str] = field(default_factory=list)

    @property
    def next_available(self) -> int:
        return min(self.available_times)

    def allocate_slot(self, arrival: int, charge_time: int) -> int:
        idx = min(
            range(len(self.available_times)),
            key=lambda i: self.available_times[i],
        )
        start = max(arrival, self.available_times[idx])
        self.available_times[idx] = start + charge_time
        return start


def _compute_travel_time(distance_km: float, speed_kmh: float) -> int:
    return int(round((distance_km / speed_kmh) * 60))


def _find_next_station(
    bus: Bus,
    plan: list[str],
    current_index: int,
) -> Optional[str]:
    if current_index < len(plan):
        return plan[current_index]
    return None


def simulate(
    scenario: Scenario,
    charging_plans: dict[str, list[str]],
) -> ScheduleResult:
    route = scenario.route
    charge_time = scenario.constants.get("charge_time_min", 25)
    speed = scenario.constants.get("speed_kmh", 60)
    chargers = {
        sid: ChargerState(
            available_times=[0] * scenario.chargers_per_station.get(sid, 1),
        )
        for sid in scenario.station_ids
    }

    bus_dir = {b.id: b.direction for b in scenario.buses}
    bus_plan_index: dict[str, int] = {}
    bus_last_departure: dict[str, int] = {}
    bus_events: dict[str, list[ChargingEvent]] = {b.id: [] for b in scenario.buses}
    station_entries: dict[str, list[StationChargeEntry]] = {
        sid: [] for sid in scenario.station_ids
    }

    for b in scenario.buses:
        bus_last_departure[b.id] = b.departure_time_minutes
        bus_plan_index[b.id] = 0

    event_heap: list[SimEvent] = []

    for b in scenario.buses:
        plan = charging_plans.get(b.id, [])
        if not plan:
            continue
        first_station = plan[0]
        origin = route.origin_station(b.direction)
        dist = route.distance_between(origin, first_station, b.direction)
        travel = _compute_travel_time(dist, speed)
        arrival = b.departure_time_minutes + travel
        heapq.heappush(event_heap, SimEvent(
            time=arrival, event_type=EventType.BUS_ARRIVAL,
            bus_id=b.id, station_id=first_station,
        ))

    while event_heap:
        event = heapq.heappop(event_heap)

        if event.event_type == EventType.BUS_ARRIVAL:
            bus_id = event.bus_id
            station_id = event.station_id
            plan = charging_plans.get(bus_id, [])
            plan_idx = bus_plan_index[bus_id]
            arrival_time = event.time

            cs = chargers[station_id]
            charge_start = cs.allocate_slot(arrival_time, charge_time)

            charge_end = charge_start + charge_time
            departure_time = charge_end

            ev = ChargingEvent(
                station_id=station_id,
                arrival_time=arrival_time,
                charge_start_time=charge_start,
                charge_end_time=charge_end,
                departure_time=departure_time,
            )
            bus_events[bus_id].append(ev)
            station_entries[station_id].append(StationChargeEntry(
                bus_id=bus_id,
                arrival_time=arrival_time,
                charge_start_time=charge_start,
                charge_end_time=charge_end,
                wait_time=charge_start - arrival_time,
            ))

            bus_last_departure[bus_id] = departure_time
            bus_plan_index[bus_id] = plan_idx + 1

            next_station = _find_next_station(
                scenario.route,
                plan,
                bus_plan_index[bus_id],
            )
            if next_station is not None:
                dist = route.distance_between(station_id, next_station, bus_dir[bus_id])
                travel = _compute_travel_time(dist, speed)
                next_arrival = departure_time + travel
                heapq.heappush(event_heap, SimEvent(
                    time=next_arrival, event_type=EventType.BUS_ARRIVAL,
                    bus_id=bus_id, station_id=next_station,
                ))
            else:
                dest = route.destination_station(bus_dir[bus_id])
                last_dist = route.distance_between(station_id, dest, bus_dir[bus_id])
                travel = _compute_travel_time(last_dist, speed)
                final_arrival = departure_time + travel
                heapq.heappush(event_heap, SimEvent(
                    time=final_arrival, event_type=EventType.BUS_ARRIVAL_DEST,
                    bus_id=bus_id, station_id=dest,
                ))

        elif event.event_type == EventType.BUS_ARRIVAL_DEST:
            pass

    bus_timelines_list = []
    for b in scenario.buses:
        bt = BusTimeline(bus=b, charging_events=bus_events.get(b.id, []))
        bus_timelines_list.append(bt)

    station_logs = {}
    for sid in scenario.station_ids:
        station_logs[sid] = StationLog(station_id=sid, entries=station_entries.get(sid, []))

    return ScheduleResult(
        scenario_name=scenario.name,
        bus_timelines=bus_timelines_list,
        station_logs=station_logs,
        scores={},
        weights_used=dict(scenario.weights),
    )


def simulate_bus_on_state(
    scenario: Scenario,
    bus: Bus,
    plan: list[str],
    charger_states: dict[str, ChargerState],
) -> BusTimeline:
    route = scenario.route
    charge_time = scenario.constants.get("charge_time_min", 25)
    speed = scenario.constants.get("speed_kmh", 60)

    events: list[ChargingEvent] = []
    last_departure = bus.departure_time_minutes
    plan_idx = 0

    while plan_idx < len(plan):
        station_id = plan[plan_idx]
        if plan_idx == 0:
            origin = route.origin_station(bus.direction)
            dist = route.distance_between(origin, station_id, bus.direction)
        else:
            prev = plan[plan_idx - 1]
            dist = route.distance_between(prev, station_id, bus.direction)

        travel = _compute_travel_time(dist, speed)
        arrival = last_departure + travel

        cs = charger_states[station_id]
        charge_start = cs.allocate_slot(arrival, charge_time)
        charge_end = charge_start + charge_time
        departure = charge_end

        events.append(ChargingEvent(
            station_id=station_id,
            arrival_time=arrival,
            charge_start_time=charge_start,
            charge_end_time=charge_end,
            departure_time=departure,
        ))

        last_departure = departure
        plan_idx += 1

    return BusTimeline(bus=bus, charging_events=events)
