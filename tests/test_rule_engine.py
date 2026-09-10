import pytest
from decimal import Decimal
from app.services.rule_engine import RuleEngine, Rule, RuleCondition, RuleAction

def test_rule_priority():
    engine = RuleEngine()
    # 规则1: 商户匹配，低优先级
    r1 = Rule("r1", 1, [RuleCondition("merchant", "美团")], [RuleAction("category", "餐饮")])
    # 规则2: 商户+描述匹配，高优先级
    r2 = Rule("r2", 10, [RuleCondition("merchant", "美团"), RuleCondition("description", "午餐")], [RuleAction("category", "快餐")])
    
    engine.add_rule(r1)
    engine.add_rule(r2)
    
    txn = {"merchant": "美团", "description": "午餐"}
    actions = engine.apply(txn)
    assert actions["category"] == "快餐"

def test_decimal_precision():
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")
    assert Decimal("1234.56") == Decimal("1234.56")
