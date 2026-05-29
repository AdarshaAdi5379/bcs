from scheduler.rules.base import HardRule


class ChargerCapacityHardRule(HardRule):
    name = "charger_capacity"

    def validate(self, target, context) -> list[str]:
        errors: list[str] = []
        chargers_per_station = context.get("chargers_per_station", {})
        if not chargers_per_station:
            return errors

        if not hasattr(target, "station_logs"):
            return errors

        for sid, log in target.station_logs.items():
            n_chargers = chargers_per_station.get(sid, 1)
            entries = log.entries
            intervals = [(e.charge_start_time, e.charge_end_time) for e in entries]
            intervals.sort()
            active = 0
            for start, end in intervals:
                count = sum(
                    1 for s, e in intervals if s < end and e > start
                )
                if count > n_chargers:
                    errors.append(
                        f"Station {sid}: {count} concurrent charges "
                        f"but only {n_chargers} charger(s)"
                    )
                    break
        return errors
