import os
import yaml
from pathlib import Path
from scheduler.domain import Scenario, Route, Segment, Operator, Bus


def _parse_time(time_str: str) -> int:
    parts = time_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    ref = 19 * 60
    return (hours * 60 + minutes) - ref


def load_scenario(filepath: str) -> Scenario:
    with open(filepath, "r") as f:
        data = yaml.safe_load(f)

    segments = [
        Segment(from_station=s["from"], to_station=s["to"], distance_km=float(s["distance_km"]))
        for s in data["route"]["segments"]
    ]
    route = Route(name=data["route"]["name"], segments=segments)

    operators = [Operator(id=o["id"], name=o["name"]) for o in data.get("operators", [])]

    station_ids = [s["id"] for s in data.get("stations", [])]
    chargers_per_station = {s["id"]: s.get("chargers", 1) for s in data.get("stations", [])}

    buses = []
    for b in data["buses"]:
        dep = _parse_time(b["departure_time"])
        buses.append(Bus(
            id=b["id"],
            operator=b["operator"],
            direction=b["direction"],
            departure_time_minutes=dep,
        ))

    weights = data.get("weights", {"individual": 1.0, "operator": 1.0, "overall": 1.0})
    constants = data.get("constants", {})

    return Scenario(
        name=data["name"],
        description=data.get("description", ""),
        route=route,
        operators=operators,
        station_ids=station_ids,
        chargers_per_station=chargers_per_station,
        buses=buses,
        weights=weights,
        constants=constants,
    )


def list_scenario_files(scenarios_dir: str) -> list[str]:
    p = Path(scenarios_dir)
    if not p.exists():
        return []
    return sorted([str(f) for f in p.glob("*.yaml")])


def scenario_name_from_file(filepath: str) -> str:
    try:
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)
        return data.get("name", os.path.basename(filepath))
    except Exception:
        return os.path.basename(filepath)
