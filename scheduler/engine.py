from scheduler.domain import Scenario, ScheduleResult, BusTimeline
from scheduler.router import find_feasible_plans
from scheduler.simulator import simulate, simulate_bus_on_state, ChargerState
from scheduler.rules import registry


def run(scenario: Scenario) -> ScheduleResult:
    registry.initialize()
    battery_range = scenario.constants.get("battery_range_km", 240)

    sorted_buses = sorted(scenario.buses, key=lambda b: (b.departure_time_minutes, b.id))

    charger_states: dict[str, ChargerState] = {
        sid: ChargerState(available_time=0, queue=[])
        for sid in scenario.station_ids
    }

    committed_plans: dict[str, list[str]] = {}
    committed_timelines: dict[str, BusTimeline] = {}

    for bus in sorted_buses:
        raw_feasible = find_feasible_plans(bus, scenario.route, battery_range)

        feasible = []
        context = {
            "bus": bus,
            "route": scenario.route,
            "battery_range": battery_range,
        }
        for p in raw_feasible:
            errors = registry.validate_hard(p, context)
            if not errors:
                feasible.append(p)

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
            scores = registry.evaluate_soft(partial_result, scenario.weights)
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

    hard_errors = registry.validate_hard(full_result, {"chargers_per_station": scenario.chargers_per_station})
    if hard_errors:
        full_result.scores = {"error": 1e9, "combined": 1e9, "messages": hard_errors}
        return full_result

    final_scores = registry.evaluate_soft(full_result, scenario.weights)
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
