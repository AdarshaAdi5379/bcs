from scheduler.rules.base import SoftRule


class IndividualWaitRule(SoftRule):
    name = "individual"
    weight_key = "individual"

    def evaluate(self, schedule, weights) -> float:
        max_wait = 0
        for tl in schedule.bus_timelines:
            for ev in tl.charging_events:
                max_wait = max(max_wait, ev.wait_time)
        return float(max_wait)
