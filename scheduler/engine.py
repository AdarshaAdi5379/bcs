from copy import deepcopy
from scheduler.domain import Scenario, ScheduleResult, BusTimeline, ChargingEvent
from scheduler.router import find_feasible_plans
from scheduler.simulator import simulate, simulate_bus_on_state, ChargerState
from scheduler.scoring import evaluate, registered_rules


def run(scenario: Scenario) -> ScheduleResult:
    battery_range = scenario.constants.get("battery_range_km", 240)

    sorted_buses = sorted(scenario.buses, key=lambda b: (b.departure_time_minutes, b.id))

    charger_states: dict[str, ChargerState] = {
        sid: ChargerState(available_time=0, queue=[])
        for sid in scenario.station_ids
    }

    committed_plans: dict[str, list[str]] = {}
    committed_timelines: dict[str, BusTimeline] = {}

    for bus in sorted_buses:
        feasible = find_feasible_plans(bus, scenario.route, battery_range)
        if not feasible:
            feasible = [[]]

        best_plan = None
        best_score = float("inf")

        for plan in feasible:
            cs_copy = _clone_charger_states(charger_states)
            tl = simulate_bus_on_state(scenario, bus, plan, cs_copy)

            temp_timelines = dict(committed_timelines)
            temp_timelines[bus.id] = tl

            partial_result = _build_partial_result(scenario, temp_timelines)
            scores = evaluate(partial_result, scenario.weights)
            combined = scores.get("combined", 0.0)

            if combined < best_score:
                best_score = combined
                best_plan = plan

        if best_plan is None:
            best_plan = feasible[0] if feasible else []

        committed_plans[bus.id] = best_plan
        real_tl = simulate_bus_on_state(scenario, bus, best_plan, charger_states)
        committed_timelines[bus.id] = real_tl

    full_result = simulate(scenario, committed_plans)
    final_scores = evaluate(full_result, scenario.weights)
    full_result.scores = final_scores

    return full_result


def _clone_charger_states(states: dict[str, ChargerState]) -> dict[str, ChargerState]:
    return {sid: ChargerState(available_time=cs.available_time, queue=list(cs.queue))
            for sid, cs in states.items()}


def _build_partial_result(
    scenario: Scenario,
    timelines: dict[str, BusTimeline],
) -> ScheduleResult:
    tl_list = list(timelines.values())
    return ScheduleResult(
        scenario_name=scenario.name,
        bus_timelines=tl_list,
        station_logs={},
        scores={},
        weights_used=dict(scenario.weights),
    )
