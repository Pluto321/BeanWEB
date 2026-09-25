import hashlib
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import Account, AuditLog, ExportRecord, Rule, Transaction
from app.services.review import AuditService
from app.services.export_service import ExportService
from app.core.config import settings

router = APIRouter(prefix="/api")


@router.get("/config/defaults")
def config_defaults():
    """只读：返回来源对应的默认账户（不写入任何数据）"""
    return {
        "default_assets_account": settings.DEFAULT_ASSETS_ACCOUNT,
        "default_expenses_account": settings.DEFAULT_EXPENSES_ACCOUNT,
        "default_income_account": settings.DEFAULT_INCOME_ACCOUNT,
        "source_defaults": {
            "ALIPAY": settings.DEFAULT_ASSETS_ACCOUNT,
            "BANK": settings.DEFAULT_ASSETS_ACCOUNT,
        },
    }


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db)):
    accounts = db.query(Account).order_by(Account.name).all()
    return [
        {"name": a.name, "aliases": a.aliases or [], "open_date": a.open_date}
        for a in accounts
    ]


@router.post("/accounts")
def create_account(data: dict, db: Session = Depends(get_db)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="账户名不能为空")
    if ":" not in name or len(name.split(":")) < 2:
        raise HTTPException(status_code=400, detail="账户名不合法，需至少包含类型前缀，如 Assets:Bank")
    if db.query(Account).filter(Account.name == name).first():
        raise HTTPException(status_code=409, detail="账户已存在")
    aliases = [str(a).strip() for a in (data.get("aliases") or []) if str(a).strip()]
    account = Account(name=name, open_date=datetime.now().strftime("%Y-%m-%d"), aliases=aliases)
    db.add(account)
    db.commit()
    return {"status": "success", "name": name}


@router.patch("/accounts/{name}")
def update_account(name: str, data: dict, db: Session = Depends(get_db)):
    """修改账户（目前支持编辑 aliases：收/付款方式关键词，用于导入时自动匹配支付账户）"""
    account = db.query(Account).filter(Account.name == name).first()
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    if "aliases" in data:
        aliases = [str(a).strip() for a in (data.get("aliases") or []) if str(a).strip()]
        old = account.aliases or []
        account.aliases = aliases
        AuditService.log_change(db, "account", account.id, "UPDATE_ALIASES",
                                {"aliases": old}, {"aliases": aliases}, "Update payment method aliases")
    db.commit()
    return {"status": "success", "name": name, "aliases": account.aliases or []}


@router.get("/rules")
def list_rules(db: Session = Depends(get_db)):
    rules = db.query(Rule).order_by(Rule.priority.desc(), Rule.id).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "priority": r.priority,
            "enabled": r.enabled,
            "conditions": [{"key": c.key, "pattern": c.pattern} for c in r.conditions],
            "actions": [{"action_type": a.action_type, "value": a.value} for a in r.actions],
        }
        for r in rules
    ]


@router.post("/rules")
def create_rule(data: dict, db: Session = Depends(get_db)):
    from app.services.rule_service import RuleService
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="规则名不能为空")
    rule = RuleService.create_rule(db, data)
    AuditService.log_change(db, "rule", rule.id, "CREATE", None, {"name": rule.name}, "Create rule")
    db.commit()
    return {"status": "success", "id": rule.id}


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, data: dict, db: Session = Depends(get_db)):
    from app.services.rule_service import RuleService
    try:
        rule = RuleService.update_rule(db, rule_id, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    AuditService.log_change(db, "rule", rule_id, "UPDATE", None, data, "Update rule")
    db.commit()
    return {"status": "success", "id": rule.id}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    from app.services.rule_service import RuleService
    try:
        RuleService.delete_rule(db, rule_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    AuditService.log_change(db, "rule", rule_id, "DELETE", None, None, "Delete rule")
    db.commit()
    return {"status": "success"}


@router.post("/exports/batch")
def batch_export(data: dict, db: Session = Depends(get_db)):
    ids = data.get("transaction_ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="transaction_ids 不能为空")

    results = []
    exported = failed = skipped = 0
    for tid in ids:
        try:
            record = ExportService.export_transaction(db, tid)
            db.commit()
            results.append({"transaction_id": tid, "status": record.status, "file": record.file_path})
            exported += 1
        except ValueError as e:
            db.rollback()
            msg = str(e)
            if "already exported" in msg:
                results.append({"transaction_id": tid, "status": "SKIPPED", "error": "已导出，跳过"})
                skipped += 1
            else:
                results.append({"transaction_id": tid, "status": "FAILED", "error": msg})
                failed += 1
        except Exception as e:
            db.rollback()
            results.append({"transaction_id": tid, "status": "FAILED", "error": str(e)})
            failed += 1

    AuditService.log_change(
        db, "export", 0, "EXPORT_BATCH", None,
        {"requested": len(ids), "exported": exported, "failed": failed, "skipped": skipped},
        "Batch export",
    )
    db.commit()
    return {"total": len(ids), "exported": exported, "failed": failed, "skipped": skipped, "results": results}


@router.post("/transactions/{txn_id}/export")
def export_one(txn_id: int, db: Session = Depends(get_db)):
    try:
        record = ExportService.export_transaction(db, txn_id)
        db.commit()
        return {"status": record.status, "file_path": record.file_path, "file_sha256": record.file_sha256}
    except ValueError as e:
        db.rollback()
        msg = str(e)
        raise HTTPException(status_code=409 if "already exported" in msg else 400, detail=msg)


@router.get("/exports")
def export_history(
    transaction_id: int | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    q = db.query(ExportRecord)
    if transaction_id:
        q = q.filter(ExportRecord.transaction_id == transaction_id)
    if status:
        q = q.filter(ExportRecord.status == status)
    total = q.count()
    rows = (
        q.order_by(ExportRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "page": page, "page_size": page_size, "items": [
        {
            "id": r.id,
            "transaction_id": r.transaction_id,
            "status": r.status,
            "file_path": r.file_path,
            "file_sha256": r.file_sha256,
            "error_message": r.error_message,
            "created_at": str(r.created_at),
            "completed_at": str(r.completed_at) if r.completed_at else None,
        }
        for r in rows
    ]}


@router.get("/exports/{record_id}")
def export_detail(record_id: int, db: Session = Depends(get_db)):
    """导出详情：ExportRecord + Transaction + Splits + Import 溯源链（含 Beancount 预览）"""
    from app.models.models import RawTransaction, TransactionSplit, File as DBFile, ImportBatch

    rec = db.query(ExportRecord).filter(ExportRecord.id == record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="导出记录不存在")

    txn = db.query(Transaction).filter(Transaction.id == rec.transaction_id).first()
    txn_data = None
    import_info = None
    raw_data = None

    if txn:
        splits = db.query(TransactionSplit).filter(TransactionSplit.transaction_id == txn.id).all()
        txn_data = {
            "id": txn.id,
            "date": txn.date,
            "time": txn.time,
            "merchant": txn.merchant,
            "description": txn.description,
            "amount": txn.amount,
            "currency": txn.currency,
            "direction": txn.direction,
            "status": txn.status,
            "payment_method": txn.payment_method,
            "counterparty": txn.counterparty,
            "assets": [{"account": s.account, "amount": s.amount} for s in splits if s.account.startswith("Assets:")],
            "expenses": [{"account": s.account, "amount": s.amount} for s in splits if not s.account.startswith("Assets:")],
        }

        # Import 溯源链：Transaction → RawTransaction → File → ImportBatch
        if txn.raw_transaction_id:
            raw = db.query(RawTransaction).filter(RawTransaction.id == txn.raw_transaction_id).first()
            if raw:
                raw_data = {"row_number": raw.row_number, "raw_data_json": raw.raw_data_json}
                db_file = db.query(DBFile).filter(DBFile.id == raw.file_id).first()
                if db_file:
                    batch = db.query(ImportBatch).filter(ImportBatch.id == db_file.import_batch_id).first()
                    import_info = {
                        "batch_id": db_file.import_batch_id,
                        "source": batch.source_type if batch else None,
                        "batch_status": batch.status if batch else None,
                        "file_name": db_file.original_name,
                        "file_sha256": db_file.sha256,
                    }

    try:
        preview = ExportService._render(db, txn) if txn else ""
    except Exception:
        preview = ""

    return {
        "id": rec.id,
        "status": rec.status,
        "file_path": rec.file_path,
        "file_sha256": rec.file_sha256,
        "error_message": rec.error_message,
        "created_at": str(rec.created_at),
        "completed_at": str(rec.completed_at) if rec.completed_at else None,
        "transaction": txn_data,
        "beancount_preview": preview,
        "import": import_info,
        "raw_data": raw_data,
    }


@router.get("/exports/{record_id}/download")
def export_download(record_id: int, db: Session = Depends(get_db)):
    """下载导出的 .bean 文件（流式返回，浏览器触发下载）"""
    rec = db.query(ExportRecord).filter(ExportRecord.id == record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="导出记录不存在")
    if rec.status != "EXPORTED":
        raise HTTPException(status_code=400, detail="该记录未成功导出，无法下载")
    if not rec.file_path or not os.path.exists(rec.file_path):
        raise HTTPException(status_code=404, detail="导出文件已不存在于服务器")

    # 校验完整性：文件内容与记录的 sha256 一致才允许下载
    actual_sha = hashlib.sha256(open(rec.file_path, "rb").read()).hexdigest()
    if actual_sha != rec.file_sha256:
        raise HTTPException(status_code=409, detail="文件校验失败：内容与导出记录不一致（可能已被修改）")

    filename = os.path.basename(rec.file_path)
    return FileResponse(
        rec.file_path,
        media_type="application/x-beancount",
        filename=f"beanweb_export_{record_id}_{filename}",
    )


@router.get("/ledger/reconciliation")
def reconciliation(db: Session = Depends(get_db)):
    import os
    from app.core.config import settings

    issues = []
    confirmed = db.query(Transaction).filter(Transaction.status == "CONFIRMED").all()
    for txn in confirmed:
        rec = (
            db.query(ExportRecord)
            .filter(ExportRecord.transaction_id == txn.id, ExportRecord.status == "EXPORTED")
            .first()
        )
        if not rec:
            issues.append({"code": "NOT_EXPORTED", "transaction_id": txn.id, "message": "已确认但未导出"})
        else:
            if not rec.file_path or not os.path.exists(rec.file_path):
                issues.append({"code": "MISSING_FILE", "transaction_id": txn.id, "message": f"导出文件缺失: {rec.file_path}"})
            else:
                with open(rec.file_path, "rb") as f:
                    actual = hashlib.sha256(f.read()).hexdigest()
                if actual != rec.file_sha256:
                    issues.append({"code": "HASH_MISMATCH", "transaction_id": txn.id, "message": "导出文件内容与记录不一致"})

    main_bean = os.path.join(settings.LEDGER_DIR, "main.bean")
    if os.path.exists(main_bean):
        ledger_dir = settings.LEDGER_DIR
        with open(main_bean, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith('include "'):
                    target = line.split('"')[1]
                    path = os.path.join(ledger_dir, target)
                    if not os.path.exists(path):
                        issues.append({"code": "BROKEN_INCLUDE", "transaction_id": None, "message": f"include 指向不存在的文件: {target}"})

    return {
        "status": "OK" if not issues else "MISMATCH",
        "summary": {"total": len(confirmed), "issue_count": len(issues)},
        "issues": issues,
    }
