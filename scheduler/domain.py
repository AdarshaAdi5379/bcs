from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Segment:
    from_station: str
    to_station: str
    distance_km: float


@dataclass(frozen=True)
class Operator:
    id: str
    name: str


class Route:

    def __init__(self, name: str, segments: list[Segment]):
        self.name = name
        self.segments = segments

        all_stations: list[str] = []
        for s in segments:
            if not all_stations:
                all_stations.append(s.from_station)
            all_stations.append(s.to_station)
        self._all_stations_ordered = all_stations

        cumulative = 0.0
        cum_map: dict[str, float] = {}
        cum_map[segments[0].from_station] = 0.0
        for s in segments:
            cumulative += s.distance_km
            cum_map[s.to_station] = cumulative
        self._cumulative = cum_map

        self._charging_stations = [s.to_station for s in segments[:-1]]
        self._bk_stations = list(self._charging_stations)
        self._kb_stations = list(reversed(self._charging_stations))

    def stations_bk(self) -> list[str]:
        return list(self._bk_stations)

    def stations_kb(self) -> list[str]:
        return list(self._kb_stations)

    def station_order_for_direction(self, direction: str) -> list[str]:
        if direction == "BK":
            return self.stations_bk()
        return self.stations_kb()

    def cumulative_bk(self) -> dict[str, float]:
        return dict(self._cumulative)

    def cumulative_kb(self) -> dict[str, float]:
        total = self._cumulative[self._all_stations_ordered[-1]]
        return {s: total - self._cumulative[s] for s in self._cumulative}

    def cumulative_for_direction(self, direction: str) -> dict[str, float]:
        if direction == "BK":
            return self.cumulative_bk()
        return self.cumulative_kb()

    def distance_between(self, a: str, b: str, direction: str) -> float:
        cum = self.cumulative_for_direction(direction)
        if a not in cum or b not in cum:
            raise ValueError(f"Unknown station: {a} or {b}")
        return abs(cum[b] - cum[a])

    def distance_to_end(self, station: str, direction: str) -> float:
        cum = self.cumulative_for_direction(direction)
        total = cum[self._all_stations_ordered[-1]]
        return total - cum[station]

    def distance_from_start(self, station: str, direction: str) -> float:
        cum = self.cumulative_for_direction(direction)
        return cum[station]

    def origin_station(self, direction: str) -> str:
        if direction == "BK":
            return self.segments[0].from_station
        return self.segments[-1].to_station

    def destination_station(self, direction: str) -> str:
        if direction == "BK":
            return self.segments[-1].to_station
        return self.segments[0].from_station

    def total_distance_km(self) -> float:
        return sum(s.distance_km for s in self.segments)


@dataclass
class Bus:
    id: str
    operator: str
    direction: str
    departure_time_minutes: int


@dataclass
class ChargingEvent:
    station_id: str
    arrival_time: int
    charge_start_time: int
    charge_end_time: int
    departure_time: int

    @property
    def wait_time(self) -> int:
        return self.charge_start_time - self.arrival_time


@dataclass
class Scenario:
    name: str
    description: str
    route: Route
    operators: list[Operator]
    station_ids: list[str]
    chargers_per_station: dict[str, int]
    buses: list[Bus]
    weights: dict[str, float]
    constants: dict


@dataclass
class BusTimeline:
    bus: Bus
    charging_events: list[ChargingEvent]

    @property
    def total_wait(self) -> int:
        return sum(e.wait_time for e in self.charging_events)

    @property
    def final_arrival_time(self) -> int:
        if self.charging_events:
            return self.charging_events[-1].departure_time
        return self.bus.departure_time_minutes

    @property
    def stations_used(self) -> list[str]:
        return [e.station_id for e in self.charging_events]


@dataclass
class StationChargeEntry:
    bus_id: str
    arrival_time: int
    charge_start_time: int
    charge_end_time: int
    wait_time: int


@dataclass
class StationLog:
    station_id: str
    entries: list[StationChargeEntry] = field(default_factory=list)


@dataclass
class AlternativePlan:
    plan: list[str]
    score: float
    breakdown: dict[str, float]


@dataclass
class PlanExplanation:
    bus_id: str
    chosen_plan: list[str]
    chosen_score: float
    alternatives: list[AlternativePlan]
    key_reason: str


@dataclass
class ScheduleResult:
    scenario_name: str
    bus_timelines: list[BusTimeline]
    station_logs: dict[str, StationLog]
    scores: dict[str, float]
    weights_used: dict[str, float]
    explanations: dict[str, PlanExplanation] = field(default_factory=dict)
