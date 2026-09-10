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

    def apply(self, transaction: dict):
        matched_rule = None
        for rule in sorted(self.rules, key=lambda x: x.priority, reverse=True):
            if all(transaction.get(c.key) == c.pattern for c in rule.conditions):
                matched_rule = rule
                break
        
        if matched_rule:
            return {a.action_type: a.value for a in matched_rule.actions}
        return {}
