from sqlalchemy.orm import Session
from app.models.models import Rule, RuleCondition, RuleAction, Transaction, TransactionSplit


class RuleService:
    @staticmethod
    def load_enabled_rules(db: Session) -> list[Rule]:
        return db.query(Rule).filter(Rule.enabled == True).all()

    @staticmethod
    def build_engine(db: Session):
        from app.services.rule_engine import RuleEngine, Rule, RuleCondition, RuleAction
        engine = RuleEngine()
        for r in RuleService.load_enabled_rules(db):
            conditions = [RuleCondition(c.key, c.pattern) for c in r.conditions]
            actions = [RuleAction(a.action_type, a.value) for a in r.actions]
            engine.add_rule(Rule(r.name, r.priority, conditions, actions))
        return engine

    @staticmethod
    def create_rule(db: Session, data: dict) -> Rule:
        rule = Rule(
            name=data.get("name", "未命名规则"),
            priority=data.get("priority", 0),
            enabled=data.get("enabled", True),
        )
        db.add(rule)
        db.flush()
        for c in data.get("conditions", []):
            db.add(RuleCondition(rule_id=rule.id, key=c["key"], pattern=c["pattern"]))
        for a in data.get("actions", []):
            db.add(RuleAction(rule_id=rule.id, action_type=a["action_type"], value=a["value"]))
        return rule

    @staticmethod
    def update_rule(db: Session, rule_id: int, data: dict) -> Rule:
        rule = db.query(Rule).filter(Rule.id == rule_id).first()
        if not rule:
            raise ValueError("Rule not found")
        if "name" in data:
            rule.name = data["name"]
        if "priority" in data:
            rule.priority = data["priority"]
        if "enabled" in data:
            rule.enabled = data["enabled"]
        if "conditions" in data:
            db.query(RuleCondition).filter(RuleCondition.rule_id == rule.id).delete()
            for c in data["conditions"]:
                db.add(RuleCondition(rule_id=rule.id, key=c["key"], pattern=c["pattern"]))
        if "actions" in data:
            db.query(RuleAction).filter(RuleAction.rule_id == rule.id).delete()
            for a in data["actions"]:
                db.add(RuleAction(rule_id=rule.id, action_type=a["action_type"], value=a["value"]))
        return rule

    @staticmethod
    def delete_rule(db: Session, rule_id: int):
        rule = db.query(Rule).filter(Rule.id == rule_id).first()
        if not rule:
            raise ValueError("Rule not found")
        db.query(RuleCondition).filter(RuleCondition.rule_id == rule_id).delete()
        db.query(RuleAction).filter(RuleAction.rule_id == rule_id).delete()
        db.delete(rule)
