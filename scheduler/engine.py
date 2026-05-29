from scheduler.domain import Scenario, ScheduleResult
from scheduler.planner import Planner
from scheduler.state import SchedulingState
from scheduler.simulator import simulate
from scheduler.rules import registry


def run(
    scenario: Scenario,
    strategy: str = "greedy",
) -> ScheduleResult:
    registry.initialize()

    if strategy == "greedy":
        state = _run_greedy(scenario)
    else:
        state = _run_beam(scenario)

    committed_plans = state.committed_plans
    full_result = simulate(scenario, committed_plans)

    hard_errors = registry.validate_hard(
        full_result,
        {"chargers_per_station": scenario.chargers_per_station},
    )
    if hard_errors:
        full_result.scores = {"error": 1e9, "combined": 1e9, "messages": hard_errors}
        return full_result

    final_scores = registry.evaluate_soft(full_result, scenario.weights)
    full_result.scores = final_scores
    return full_result


def _run_greedy(scenario: Scenario) -> SchedulingState:
    planner = Planner(scenario)
    state = SchedulingState(scenario)

    for bus in planner.buses_sorted:
        plans = planner.generate_candidates(bus)
        best_plan = plans[0]
        best_score = float("inf")

        for plan in plans:
            branch = state.clone()
            branch.add_bus(bus, plan)
            score = planner.score_state(branch)
            if score < best_score:
                best_score = score
                best_plan = plan

        state.add_bus(bus, best_plan)

    return state


def _run_beam(scenario: Scenario, beam_width: int = 3) -> SchedulingState:
    planner = Planner(scenario)
    states = [SchedulingState(scenario)]

    for bus in planner.buses_sorted:
        plans = planner.generate_candidates(bus)
        scored_states: list[tuple[float, SchedulingState]] = []

        for s in states:
            for plan in plans:
                branch = s.clone()
                branch.add_bus(bus, plan)
                score = planner.score_state(branch)
                scored_states.append((score, branch))

        scored_states.sort(key=lambda x: x[0])
        states = [s for _, s in scored_states[:beam_width]]

    return states[0] if states else SchedulingState(scenario)
