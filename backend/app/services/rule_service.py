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
    def rerun_rules(db: Session, dry_run: bool = True, transaction_ids: list[int] | None = None) -> dict:
        """对存量交易重跑规则：预填支出分类腿（role=expense 的 split account）。

        范围与语义（用户裁决权优先）：
        - 只处理非 CONFIRMED 交易；CONFIRMED 已含人工确认结果，不覆盖
        - 规则引擎只服务支出侧：direction=收入 的分类腿保持 Income:BeanWEB
        - 不改变交易状态；dry_run=True 只返回变更计划不落库
        - 无 expense split 的交易跳过（不凭空造分录）
        """
        engine = RuleService.build_engine(db)
        q = db.query(Transaction).filter(Transaction.status != "CONFIRMED")
        if transaction_ids:
            q = q.filter(Transaction.id.in_(transaction_ids))
        txns = q.order_by(Transaction.id).all()

        result = {
            "dry_run": dry_run,
            "total": len(txns),
            "updated": 0,
            "unchanged_no_rule": 0,
            "unchanged_same_account": 0,
            "skipped_income": 0,
            "skipped_no_expense_split": 0,
            "changes": [],
        }
        for txn in txns:
            if txn.direction == "收入":
                result["skipped_income"] += 1
                continue
            splits = db.query(TransactionSplit).filter(TransactionSplit.transaction_id == txn.id).all()

            def _is_expense(s) -> bool:
                # 与 render_preview 同口径：历史数据无 role 时按 Assets: 前缀推断支付腿
                if s.role:
                    return s.role == "expense"
                return not s.account.startswith("Assets:")

            expense_split = next((s for s in splits if _is_expense(s)), None)
            if not expense_split:
                result["skipped_no_expense_split"] += 1
                continue
            # 与 import 路径同口径的匹配字段（NormalizedTransaction.model_dump 的键）
            txn_dict = {
                "date": txn.date,
                "time": txn.time,
                "amount": txn.amount,
                "currency": txn.currency,
                "merchant": txn.merchant,
                "description": txn.description,
                "payment_method": txn.payment_method,
                "counterparty": txn.counterparty,
                "direction": txn.direction,
                "source_transaction_id": txn.source_transaction_id,
            }
            actions, rule_name = engine.apply_with_rule(txn_dict)
            new_account = actions.get("account")
            if not new_account:
                result["unchanged_no_rule"] += 1
                continue
            if new_account == expense_split.account:
                result["unchanged_same_account"] += 1
                continue
            change = {
                "transaction_id": txn.id,
                "merchant": txn.merchant,
                "date": txn.date,
                "old_account": expense_split.account,
                "new_account": new_account,
                "rule": rule_name,
            }
            result["changes"].append(change)
            if not dry_run:
                expense_split.account = new_account
            result["updated"] += 1

        if result["changes"] and not dry_run:
            from app.services.review import AuditService
            AuditService.log_change(
                db, "rule", 0, "RERUN", None,
                {"updated": result["updated"], "changes": result["changes"]},
                "Re-run rules on existing transactions (prefill expense split)",
            )
        return result

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
