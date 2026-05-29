from scheduler.domain import Scenario, ScheduleResult, PlanExplanation, AlternativePlan
from scheduler.planner import Planner
from scheduler.state import SchedulingState
from scheduler.simulator import simulate
from scheduler.rules import registry
from scheduler.validator import Validator


def run(
    scenario: Scenario,
    strategy: str = "greedy",
) -> ScheduleResult:
    registry.initialize()

    validator = Validator()
    validation = validator.validate_scenario(scenario)
    if not validation.is_valid:
        error_result = ScheduleResult(
            scenario_name=scenario.name,
            bus_timelines=[],
            station_logs={},
            scores={"error": 1e9, "combined": 1e9, "messages": validation.errors},
            weights_used=dict(scenario.weights),
        )
        return error_result

    if strategy == "greedy":
        state, explanations = _run_greedy(scenario)
    else:
        state, explanations = _run_beam(scenario)

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
    full_result.explanations = explanations
    return full_result


def _run_greedy(scenario: Scenario) -> tuple[SchedulingState, dict[str, PlanExplanation]]:
    planner = Planner(scenario)
    state = SchedulingState(scenario)
    explanations: dict[str, PlanExplanation] = {}

    for bus in planner.buses_sorted:
        plans = planner.generate_candidates(bus)
        best_plan = plans[0]
        best_score = float("inf")
        scored_alts: list[tuple[float, dict[str, float], list[str]]] = []

        for plan in plans:
            branch = state.clone()
            branch.add_bus(bus, plan)
            breakdown = planner.score_state_breakdown(branch)
            combined = breakdown.get("combined", 0.0)
            scored_alts.append((combined, breakdown, plan))
            if combined < best_score:
                best_score = combined
                best_plan = plan

        state.add_bus(bus, best_plan)
        explanations[bus.id] = _build_explanation(bus.id, best_plan, best_score, scored_alts)

    return state, explanations


def _run_beam(scenario: Scenario, beam_width: int = 3) -> tuple[SchedulingState, dict[str, PlanExplanation]]:
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

    best_state = states[0] if states else SchedulingState(scenario)
    explanations = _build_explanations_for_state(scenario, best_state)

    return best_state, explanations


def _build_explanations_for_state(
    scenario: Scenario,
    state: SchedulingState,
) -> dict[str, PlanExplanation]:
    planner = Planner(scenario)
    explanations: dict[str, PlanExplanation] = {}

    replay = SchedulingState(scenario)
    for bus in planner.buses_sorted:
        plans = planner.generate_candidates(bus)
        chosen_plan = state.committed_plans.get(bus.id, [])
        best_score = float("inf")
        scored_alts: list[tuple[float, dict[str, float], list[str]]] = []

        for plan in plans:
            branch = replay.clone()
            branch.add_bus(bus, plan)
            breakdown = planner.score_state_breakdown(branch)
            combined = breakdown.get("combined", 0.0)
            scored_alts.append((combined, breakdown, plan))
            if combined < best_score:
                best_score = combined

        replay.add_bus(bus, chosen_plan)
        explanations[bus.id] = _build_explanation(
            bus.id, chosen_plan, best_score, scored_alts,
        )

    return explanations


def _build_explanation(
    bus_id: str,
    chosen_plan: list[str],
    chosen_score: float,
    scored_alts: list[tuple[float, dict[str, float], list[str]]],
) -> PlanExplanation:
    chosen_breakdown: dict[str, float] = {}
    alternatives = []
    for score, breakdown, plan in scored_alts:
        if plan == chosen_plan:
            chosen_breakdown = breakdown
        else:
            alternatives.append(AlternativePlan(
                plan=plan,
                score=score,
                breakdown=dict(breakdown),
            ))

    key_reason = ""
    if alternatives:
        next_best = min(alternatives, key=lambda a: a.score)
        diffs = []
        for k in chosen_breakdown:
            if k == "combined":
                continue
            if k in next_best.breakdown:
                diff = next_best.breakdown[k] - chosen_breakdown[k]
                if abs(diff) > 0.01:
                    direction = "lower" if diff > 0 else "higher"
                    diffs.append(f"{abs(diff):.0f} pt {direction} {k}")
        if diffs:
            plan_str = ", ".join(next_best.plan) if next_best.plan else "(direct)"
            key_reason = f"vs {plan_str}: {', '.join(diffs)}"
        else:
            key_reason = f"Best combined score ({chosen_score:.0f})"

    return PlanExplanation(
        bus_id=bus_id,
        chosen_plan=chosen_plan,
        chosen_score=chosen_score,
        alternatives=alternatives,
        key_reason=key_reason,
    )
