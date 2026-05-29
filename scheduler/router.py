from itertools import combinations
from scheduler.domain import Bus, Route


def find_feasible_plans(
    bus: Bus,
    route: Route,
    battery_range_km: float,
) -> list[list[str]]:
    stations = route.station_order_for_direction(bus.direction)
    feasible: list[list[str]] = []
    min_charges = _min_charges_needed(route, battery_range_km)
    max_charges = len(stations)

    for k in range(min_charges, max_charges + 1):
        for combo in combinations(stations, k):
            if _plan_is_feasible(combo, bus.direction, route, battery_range_km):
                feasible.append(list(combo))
    return feasible


def _min_charges_needed(route: Route, battery_range_km: float) -> int:
    total = route.total_distance_km()
    segments = [s.distance_km for s in route.segments]

    remaining = battery_range_km
    charges = 0
    for seg in segments:
        if seg > remaining:
            charges += 1
            remaining = battery_range_km
        remaining -= seg
        if remaining < 0:
            charges += 1
            remaining = battery_range_km - seg

    return max(charges, 1)


def _plan_is_feasible(
    plan: tuple[str, ...],
    direction: str,
    route: Route,
    battery_range_km: float,
) -> bool:
    stations_in_order = route.station_order_for_direction(direction)

    for station in plan:
        if station not in stations_in_order:
            return False

    plan_positions = [stations_in_order.index(s) for s in plan]
    if plan_positions != sorted(plan_positions):
        return False

    origin = route.origin_station(direction)
    dest = route.destination_station(direction)

    prev = origin
    for station in list(plan) + [dest]:
        dist = route.distance_between(prev, station, direction)
        if dist > battery_range_km + 1e-9:
            return False
        prev = station

    return True
