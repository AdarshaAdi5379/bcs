from copy import deepcopy
from scheduler.domain import Scenario, Bus, BusTimeline, ScheduleResult
from scheduler.simulator import simulate_bus_on_state, ChargerState


class SchedulingState:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.committed_plans: dict[str, list[str]] = {}
        self.timelines: dict[str, BusTimeline] = {}
        self.charger_states: dict[str, ChargerState] = {
            sid: ChargerState(
                available_times=[0] * scenario.chargers_per_station.get(sid, 1),
            )
            for sid in scenario.station_ids
        }

    def add_bus(self, bus: Bus, plan: list[str]) -> BusTimeline:
        tl = simulate_bus_on_state(self.scenario, bus, plan, self.charger_states)
        self.committed_plans[bus.id] = plan
        self.timelines[bus.id] = tl
        return tl

    def clone(self) -> "SchedulingState":
        new = SchedulingState.__new__(SchedulingState)
        new.scenario = self.scenario
        new.committed_plans = dict(self.committed_plans)
        new.timelines = dict(self.timelines)
        new.charger_states = {
            sid: ChargerState(
                available_times=list(cs.available_times),
                queue=list(cs.queue),
            )
            for sid, cs in self.charger_states.items()
        }
        return new

    def to_schedule_result(self) -> ScheduleResult:
        return ScheduleResult(
            scenario_name=self.scenario.name,
            bus_timelines=list(self.timelines.values()),
            station_logs={},
            scores={},
            weights_used=dict(self.scenario.weights),
        )
