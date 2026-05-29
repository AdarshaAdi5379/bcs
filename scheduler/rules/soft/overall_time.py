from scheduler.rules.base import SoftRule


class OverallNetworkTimeRule(SoftRule):
    name = "overall"
    weight_key = "overall"

    def evaluate(self, schedule, weights) -> float:
        if not schedule.bus_timelines:
            return 0.0
        arrivals = [tl.final_arrival_time for tl in schedule.bus_timelines]
        departures = [tl.bus.departure_time_minutes for tl in schedule.bus_timelines]
        makespan = max(arrivals) - min(departures)
        return float(makespan)
