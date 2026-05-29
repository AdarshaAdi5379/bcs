from scheduler.rules.base import HardRule


class RouteOrderHardRule(HardRule):
    name = "route_order"

    def validate(self, target, context) -> list[str]:
        errors: list[str] = []
        bus = context.get("bus")
        route = context.get("route")
        if not bus or not route:
            return errors

        stations_in_order = route.station_order_for_direction(bus.direction)
        positions = []
        for s in target:
            if s not in stations_in_order:
                errors.append(f"Station {s} not on route for direction {bus.direction}")
                return errors
            positions.append(stations_in_order.index(s))

        if positions != sorted(positions):
            errors.append(
                f"Route order violation: {list(target)} not in "
                f"{stations_in_order}"
            )
        return errors
