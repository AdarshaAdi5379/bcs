from scheduler.rules.base import SoftRule, HardRule
from scheduler.rules.soft.individual_wait import IndividualWaitRule
from scheduler.rules.soft.operator_fairness import OperatorFairnessRule
from scheduler.rules.soft.overall_time import OverallNetworkTimeRule
from scheduler.rules.hard.battery_range import BatteryRangeHardRule
from scheduler.rules.hard.route_order import RouteOrderHardRule
from scheduler.rules.hard.charger_capacity import ChargerCapacityHardRule


class RuleRegistry:
    def __init__(self):
        self.soft_rules: dict[str, SoftRule] = {}
        self.hard_rules: dict[str, HardRule] = {}
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return
        self.register(IndividualWaitRule())
        self.register(OperatorFairnessRule())
        self.register(OverallNetworkTimeRule())
        self.register(BatteryRangeHardRule())
        self.register(RouteOrderHardRule())
        self.register(ChargerCapacityHardRule())
        self._initialized = True

    def register(self, rule):
        if isinstance(rule, HardRule):
            self.hard_rules[rule.name] = rule
        elif isinstance(rule, SoftRule):
            self.soft_rules[rule.name] = rule
        else:
            raise TypeError(f"Unknown rule type: {type(rule)}")

    def evaluate_soft(self, schedule, weights: dict[str, float]) -> dict[str, float]:
        scores: dict[str, float] = {}
        combined = 0.0
        for name, rule in self.soft_rules.items():
            w = weights.get(rule.weight_key, 1.0)
            raw = rule.evaluate(schedule, weights)
            scores[name] = raw
            combined += w * raw
        scores["combined"] = combined
        return scores

    def validate_hard(self, target, context=None) -> list[str]:
        errors: list[str] = []
        for rule in self.hard_rules.values():
            errors.extend(rule.validate(target, context or {}))
        return errors

    def registered_soft_rules(self) -> list[str]:
        return list(self.soft_rules.keys())


registry = RuleRegistry()
