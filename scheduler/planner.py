from scheduler.domain import Scenario, Bus
from scheduler.router import find_feasible_plans
from scheduler.state import SchedulingState
from scheduler.rules import registry


class Planner:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self._buses_sorted = sorted(
            scenario.buses,
            key=lambda b: (b.departure_time_minutes, b.id),
        )

    @property
    def buses_sorted(self) -> list[Bus]:
        return self._buses_sorted

    def generate_candidates(self, bus: Bus) -> list[list[str]]:
        battery_range = self.scenario.constants.get("battery_range_km", 240)
        raw = find_feasible_plans(bus, self.scenario.route, battery_range)

        context = {
            "bus": bus,
            "route": self.scenario.route,
            "battery_range": battery_range,
        }
        valid = []
        for p in raw:
            errors = registry.validate_hard(p, context)
            if not errors:
                valid.append(p)

        return valid if valid else [[]]

    def score_state(self, state: SchedulingState) -> float:
        partial = state.to_schedule_result()
        scores = registry.evaluate_soft(partial, self.scenario.weights)
        return scores.get("combined", 0.0)
