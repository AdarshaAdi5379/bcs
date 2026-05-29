from scheduler.rules.base import SoftRule


class OperatorFairnessRule(SoftRule):
    name = "operator"
    weight_key = "operator"

    def evaluate(self, schedule, weights) -> float:
        op_waits: dict[str, list[int]] = {}
        for tl in schedule.bus_timelines:
            op = tl.bus.operator
            if op not in op_waits:
                op_waits[op] = []
            total = sum(ev.wait_time for ev in tl.charging_events)
            op_waits[op].append(total)

        avgs = []
        for waits in op_waits.values():
            if waits:
                avgs.append(sum(waits) / len(waits))
            else:
                avgs.append(0.0)

        if len(avgs) <= 1:
            return 0.0
        return max(avgs) - min(avgs)
