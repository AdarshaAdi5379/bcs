class SoftRule:
    name: str = "unnamed"
    weight_key: str = "unnamed"

    def evaluate(self, schedule, weights) -> float:
        raise NotImplementedError


class HardRule:
    name: str = "unnamed"

    def validate(self, target, context) -> list[str]:
        raise NotImplementedError
