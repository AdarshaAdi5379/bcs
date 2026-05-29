from scheduler.domain import Scenario, ScheduleResult
from scheduler.router import find_feasible_plans
from scheduler.rules import registry


class ValidationResult:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def merge(self, other: "ValidationResult"):
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


class Validator:
    def validate_scenario(self, scenario: Scenario) -> ValidationResult:
        result = ValidationResult()
        result.merge(self._validate_route(scenario))
        result.merge(self._validate_operators(scenario))
        result.merge(self._validate_stations(scenario))
        result.merge(self._validate_buses(scenario))
        result.merge(self._validate_weights(scenario))
        result.merge(self._validate_constants(scenario))
        result.merge(self._validate_feasibility(scenario))
        return result

    def validate_schedule(self, schedule: ScheduleResult) -> ValidationResult:
        result = ValidationResult()
        result.merge(self._validate_charger_capacity(schedule))
        return result

    def _validate_route(self, scenario: Scenario) -> ValidationResult:
        r = ValidationResult()
        segments = scenario.route.segments
        if not segments:
            r.errors.append("Route has no segments")
            return r
        for i, seg in enumerate(segments):
            if seg.distance_km <= 0:
                r.errors.append(
                    f"Segment {seg.from_station}->{seg.to_station} "
                    f"has non-positive distance {seg.distance_km}"
                )
            if i > 0 and seg.from_station != segments[i - 1].to_station:
                r.errors.append(
                    f"Route discontinuity: {segments[i - 1].to_station} -> "
                    f"{seg.from_station}"
                )
        return r

    def _validate_operators(self, scenario: Scenario) -> ValidationResult:
        r = ValidationResult()
        op_ids = {o.id for o in scenario.operators}
        for b in scenario.buses:
            if b.operator not in op_ids:
                r.errors.append(
                    f"Bus {b.id} references unknown operator '{b.operator}'"
                )
        return r

    def _validate_stations(self, scenario: Scenario) -> ValidationResult:
        r = ValidationResult()
        all_station_ids = set()
        for seg in scenario.route.segments:
            all_station_ids.add(seg.from_station)
            all_station_ids.add(seg.to_station)
        all_station_ids.discard(scenario.route.origin_station("BK"))
        all_station_ids.discard(scenario.route.destination_station("BK"))

        for sid in scenario.station_ids:
            if sid not in all_station_ids:
                r.warnings.append(
                    f"Station '{sid}' defined but not on the route"
                )

        for sid in scenario.station_ids:
            n = scenario.chargers_per_station.get(sid, 1)
            if n < 1:
                r.errors.append(
                    f"Station '{sid}' has {n} charger(s), must be >= 1"
                )
        return r

    def _validate_buses(self, scenario: Scenario) -> ValidationResult:
        r = ValidationResult()
        ids = [b.id for b in scenario.buses]
        if len(ids) != len(set(ids)):
            seen = set()
            dupes = {bid for bid in ids if bid in seen or seen.add(bid)}
            r.errors.append(f"Duplicate bus IDs: {dupes}")
        for b in scenario.buses:
            if b.direction not in ("BK", "KB"):
                r.errors.append(
                    f"Bus {b.id} has invalid direction '{b.direction}'"
                )
        return r

    def _validate_weights(self, scenario: Scenario) -> ValidationResult:
        r = ValidationResult()
        for k, v in scenario.weights.items():
            if v < 0:
                r.errors.append(f"Weight '{k}' is negative ({v})")
        return r

    def _validate_constants(self, scenario: Scenario) -> ValidationResult:
        r = ValidationResult()
        must_be_positive = ["battery_range_km", "charge_time_min", "speed_kmh"]
        for key in must_be_positive:
            val = scenario.constants.get(key, 0)
            if val <= 0:
                r.errors.append(f"Constant '{key}' must be > 0, got {val}")
        return r

    def _validate_feasibility(self, scenario: Scenario) -> ValidationResult:
        r = ValidationResult()
        battery_range = scenario.constants.get("battery_range_km", 240)
        registry.initialize()
        for b in scenario.buses:
            plans = find_feasible_plans(b, scenario.route, battery_range)
            context = {
                "bus": b,
                "route": scenario.route,
                "battery_range": battery_range,
            }
            valid = [p for p in plans if not registry.validate_hard(p, context)]
            if not valid:
                r.errors.append(
                    f"Bus {b.id} has zero feasible charging plans"
                )
        return r

    def _validate_charger_capacity(self, schedule: ScheduleResult) -> ValidationResult:
        r = ValidationResult()
        for sid, log in schedule.station_logs.items():
            entries = log.entries
            for i, a in enumerate(entries):
                for j, b in enumerate(entries):
                    if i < j:
                        overlap = (
                            a.charge_start_time < b.charge_end_time
                            and b.charge_start_time < a.charge_end_time
                        )
                        if overlap:
                            r.warnings.append(
                                f"Station {sid}: overlapping charges "
                                f"({a.bus_id} and {b.bus_id})"
                            )
        return r
