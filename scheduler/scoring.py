from statistics import variance
from scheduler.domain import ScheduleResult


_rules: dict[str, callable] = {}


def register_rule(name: str, func: callable):
    _rules[name] = func


def registered_rules() -> list[str]:
    return list(_rules.keys())


def evaluate(result: ScheduleResult, weights: dict[str, float]) -> dict[str, float]:
    scores: dict[str, float] = {}
    combined = 0.0
    for name, func in _rules.items():
        w = weights.get(name, 1.0)
        raw = func(result, weights)
        scores[name] = raw
        combined += w * raw
    scores["combined"] = combined
    return scores


def _individual_wait_rule(result: ScheduleResult, weights: dict) -> float:
    max_wait = 0
    for tl in result.bus_timelines:
        for ev in tl.charging_events:
            max_wait = max(max_wait, ev.wait_time)
    return float(max_wait)


def _operator_fairness_rule(result: ScheduleResult, weights: dict) -> float:
    operator_waits: dict[str, list[int]] = {}
    for tl in result.bus_timelines:
        op = tl.bus.operator
        if op not in operator_waits:
            operator_waits[op] = []
        total = sum(ev.wait_time for ev in tl.charging_events)
        operator_waits[op].append(total)

    avgs = []
    for op, waits in operator_waits.items():
        if waits:
            avgs.append(sum(waits) / len(waits))
        else:
            avgs.append(0.0)

    if len(avgs) <= 1:
        return 0.0
    return variance(avgs)


def _overall_network_time_rule(result: ScheduleResult, weights: dict) -> float:
    if not result.bus_timelines:
        return 0.0
    arrivals = [tl.final_arrival_time for tl in result.bus_timelines]
    departures = [tl.bus.departure_time_minutes for tl in result.bus_timelines]
    makespan = max(arrivals) - min(departures)
    return float(makespan)


register_rule("individual", _individual_wait_rule)
register_rule("operator", _operator_fairness_rule)
register_rule("overall", _overall_network_time_rule)
