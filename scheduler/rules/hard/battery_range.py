from scheduler.rules.base import HardRule


class BatteryRangeHardRule(HardRule):
    name = "battery_range"

    def validate(self, target, context) -> list[str]:
        errors: list[str] = []
        bus = context.get("bus")
        route = context.get("route")
        battery_range = context.get("battery_range", 240)
        if not bus or not route:
            return errors

        stations_in_order = (
            [route.origin_station(bus.direction)]
            + list(target)
            + [route.destination_station(bus.direction)]
        )
        for i in range(len(stations_in_order) - 1):
            a, b = stations_in_order[i], stations_in_order[i + 1]
            dist = route.distance_between(a, b, bus.direction)
            if dist > battery_range + 1e-9:
                errors.append(
                    f"Range violation: {a} -> {b} = {dist:.0f}km > {battery_range}km"
                )
        return errors
