from typing import List


class RuleCondition:
    def __init__(self, key, pattern):
        self.key = key
        self.pattern = pattern

class RuleAction:
    def __init__(self, action_type, value):
        self.action_type = action_type
        self.value = value

class Rule:
    def __init__(self, name, priority, conditions: List[RuleCondition], actions: List[RuleAction]):
        self.name = name
        self.priority = priority
        self.conditions = conditions
        self.actions = actions

class RuleEngine:
    def __init__(self):
        self.rules: List[Rule] = []

    def add_rule(self, rule: Rule):
        self.rules.append(rule)

    @staticmethod
    def _match(value, pattern) -> bool:
        """子串包含匹配（不区分大小写）。空 pattern 视为不过滤。"""
        if value is None:
            return False
        if pattern is None or pattern == "":
            return True
        return str(pattern).lower() in str(value).lower()

    def apply(self, transaction: dict):
        actions, _ = self.apply_with_rule(transaction)
        return actions

    def apply_with_rule(self, transaction: dict):
        """返回 (actions, rule_name)。rule_name 为 None 表示无规则命中。
        优先级：priority 降序取第一条全条件命中的规则（同 import 路径口径）。"""
        for rule in sorted(self.rules, key=lambda x: x.priority, reverse=True):
            if all(self._match(transaction.get(c.key), c.pattern) for c in rule.conditions):
                return {a.action_type: a.value for a in rule.actions}, rule.name
        return {}, None
