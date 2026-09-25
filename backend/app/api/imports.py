import os
import uuid
import shutil
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import File as DBFile, ImportBatch, RawTransaction, Transaction, TransactionSplit
from app.services.storage import StorageService
from app.services.importer import ImporterRegistry
from app.services.deduplication import DeduplicationService
from app.services.rule_service import RuleService
from app.models.models import Account
import app.services.alipay_importer  # noqa: F401  注册内置 Importer

router = APIRouter(prefix="/api/imports")
storage = StorageService()


def match_payment_account(db: Session, payment_method: str | None) -> str | None:
    """按收/付款方式文本与账户 aliases（及账户名本身）模糊匹配 Assets 账户。
    返回最匹配的账户名；无匹配返回 None（由默认账户兜底）。"""
    if not payment_method:
        return None
    text = payment_method.lower()
    best: tuple[int, str] | None = None
    accounts = db.query(Account).filter(Account.name.startswith("Assets:")).all()
    for acc in accounts:
        candidates = [acc.name.lower()] + [str(a).lower() for a in (acc.aliases or [])]
        for kw in candidates:
            if kw and kw in text:
                # 关键词越长越具体，优先
                if best is None or len(kw) > best[0]:
                    best = (len(kw), acc.name)
                break
    return best[1] if best else None

BATCH_STATUS_ANALYZED = "PENDING_ANALYZED"
BATCH_STATUS_COMPLETED = "COMPLETED"
BATCH_STATUS_ERROR = "IMPORT_ERROR"

ACTIVE_TXN_STATUS = ("REVIEW_REQUIRED", "POSSIBLE_DUPLICATE", "CONFIRMED")


def _save_upload(file: UploadFile, db: Session, batch: ImportBatch) -> tuple[str, DBFile]:
    """保存上传文件到 storage 并创建 File 记录（Raw 不可变）。返回 (storage_path, db_file)"""
    temp_path = f"temp_{uuid.uuid4()}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    try:
        storage_path = storage.save(temp_path, batch.id)
        sha256 = storage._calculate_sha256(storage_path)

        # 文件级去重：同一文件已导入过 → 复用已有 File 记录，不阻塞分析。
        # Raw 数据不可变，重复分析同一文件是安全的（commit 阶段有交易级 Dedup 兜底）。
        existing_file = db.query(DBFile).filter(DBFile.sha256 == sha256).first()
        if existing_file:
            # 关键修复：文件记录必须跟随最新批次，否则新批次 commit 时
            # 按 import_batch_id 查不到文件 → "批次缺少文件记录"
            existing_file.import_batch_id = batch.id
            db_file = existing_file
            storage_path = existing_file.storage_path
        else:
            db_file = DBFile(original_name=file.filename, storage_path=storage_path,
                             sha256=sha256, size=os.path.getsize(storage_path), source_type="UNKNOWN",
                             import_batch_id=batch.id)
            db.add(db_file)
        db.flush()
        return storage_path, db_file
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _analyze_rows(db: Session, importer, raw_data_list: list[dict], db_file: DBFile) -> dict:
    """对解析出的行做 Normalize + Dedup 分析。只统计，不写 Transaction。"""
    dedup = DeduplicationService()
    stats = {"total": 0, "new": 0, "existing": 0, "possible_duplicate": 0, "invalid": 0}
    invalid_rows: list[dict] = []
    duplicates: list[dict] = []

    for idx, row in enumerate(raw_data_list, start=1):
        stats["total"] += 1
        try:
            norm = importer.normalize(row)
            if not norm.date or not norm.amount or not norm.source_transaction_id:
                raise ValueError("缺少必要字段（日期/金额/交易订单号）")
        except Exception as e:
            stats["invalid"] += 1
            invalid_rows.append({
                "row_number": idx,
                "error": str(e),
                "raw": {k: (str(v)[:40] if v else "") for k, v in row.items()},
            })
            continue

        raw_hash = dedup.get_raw_hash(row)
        fingerprint = dedup.get_canonical_fingerprint(norm.model_dump())
        result, reason = dedup.check_against_db(db, norm.source_transaction_id, raw_hash, fingerprint)
        if result == "UNIQUE":
            stats["new"] += 1
        elif result == "EXACT_DUPLICATE":
            stats["existing"] += 1
        else:
            stats["possible_duplicate"] += 1
            duplicates.append({
                "row_number": idx,
                "date": norm.date,
                "merchant": norm.merchant,
                "amount": str(norm.amount),
                "reason": reason,
                "raw": {k: (str(v)[:40] if v else "") for k, v in row.items()},
            })

    return {"stats": stats, "invalid_rows": invalid_rows, "duplicates": duplicates}


@router.post("/analyze")
async def analyze_import(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """阶段 2：分析文件。只保存 Raw 数据（不可变），不创建 Transaction。"""
    batch = ImportBatch(source_type="UNKNOWN", filename=file.filename, status="ANALYZING")
    db.add(batch)
    db.commit()
    db.refresh(batch)

    try:
        storage_path, db_file = _save_upload(file, db, batch)

        importer = ImporterRegistry.get_importer(storage_path)
        raw_data_list = importer.parse(storage_path)
        if not raw_data_list:
            raise ValueError("文件中没有可解析的数据行")

        batch.source_type = importer.name.upper()
        db_file.source_type = batch.source_type

        # 保存 RawTransaction（Raw 不可变）：同一文件重复分析时不重复保存，
        # 否则 raw 行会翻倍，导致 commit 统计错乱
        existing_raw_count = (
            db.query(RawTransaction).filter(RawTransaction.file_id == db_file.id).count()
        )
        if existing_raw_count == 0:
            for idx, row in enumerate(raw_data_list, start=1):
                db.add(RawTransaction(file_id=db_file.id, raw_data_json=row, row_number=idx))
            db.flush()

        analysis = _analyze_rows(db, importer, raw_data_list, db_file)

        batch.status = BATCH_STATUS_ANALYZED
        batch.stats_json = analysis["stats"]
        db.commit()

        return {
            "import_id": batch.id,
            "filename": file.filename,
            "parser": importer.name,
            "batch_status": batch.status,
            **analysis,
        }
    except HTTPException:
        db.rollback()
        batch.status = BATCH_STATUS_ERROR
        batch.error_message = "analyze failed"
        db.commit()
        raise
    except Exception as e:
        db.rollback()
        batch.status = BATCH_STATUS_ERROR
        batch.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/commit/{batch_id}")
def commit_import(batch_id: int, db: Session = Depends(get_db)):
    """阶段 5：正式导入。从已分析的 RawTransaction 创建 Transaction（幂等：Dedup 兜底）。"""
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")
    if batch.status == BATCH_STATUS_COMPLETED:
        raise HTTPException(status_code=409, detail="该批次已经导入完成，不能重复导入")
    if batch.status != BATCH_STATUS_ANALYZED:
        raise HTTPException(status_code=400, detail=f"批次状态为 {batch.status}，不能导入")

    db_file = db.query(DBFile).filter(DBFile.import_batch_id == batch_id).first()
    if not db_file:
        raise HTTPException(status_code=400, detail="批次缺少文件记录")

    importer = ImporterRegistry.get_importer(db_file.storage_path)
    raws = (
        db.query(RawTransaction)
        .filter(RawTransaction.file_id == db_file.id)
        .order_by(RawTransaction.row_number)
        .all()
    )
    if not raws:
        raise HTTPException(status_code=400, detail="批次没有 Raw 数据")

    dedup = DeduplicationService()
    engine = RuleService.build_engine(db)
    stats = {"total": 0, "created": 0, "existing": 0, "possible_duplicate": 0, "review_required": 0}

    for raw in raws:
        stats["total"] += 1
        try:
            norm = importer.normalize(raw.raw_data_json)
        except Exception:
            continue  # 无效行已在 analyze 阶段统计，跳过

        raw_hash = dedup.get_raw_hash(raw.raw_data_json)
        fingerprint = dedup.get_canonical_fingerprint(norm.model_dump())
        result, reason = dedup.check_against_db(db, norm.source_transaction_id, raw_hash, fingerprint)
        if result == "EXACT_DUPLICATE":
            stats["existing"] += 1
            continue
        if result == "POSSIBLE_DUPLICATE":
            stats["possible_duplicate"] += 1
            status = "POSSIBLE_DUPLICATE"
            review_required_status = "POSSIBLE_DUPLICATE"
        else:
            review_required_status = "REVIEW_REQUIRED"

        actions = engine.apply(norm.model_dump())
        txn = Transaction(
            raw_transaction_id=raw.id,
            date=norm.date,
            time=norm.time,
            amount=str(norm.amount),
            currency=norm.currency,
            merchant=norm.merchant,
            description=norm.description,
            payment_method=norm.payment_method,
            counterparty=norm.counterparty,
            direction=norm.direction,
            source_type=batch.source_type,
            source_transaction_id=norm.source_transaction_id,
            raw_hash=raw_hash,
            canonical_fingerprint=fingerprint,
            status=review_required_status,
        )
        db.add(txn)
        db.flush()

        # 支付账户：按收/付款方式自动匹配 Assets 账户（账户管理 aliases），失败由导出阶段默认账户兜底
        payment_account = match_payment_account(db, norm.payment_method)

        db.add(TransactionSplit(
            transaction_id=txn.id,
            account=actions.get("account", "Expenses:Uncategorized"),
            amount=str(norm.amount),
            role="expense",
        ))
        if payment_account:
            db.add(TransactionSplit(
                transaction_id=txn.id,
                account=payment_account,
                amount=str(-norm.amount) if norm.direction != "收入" else str(norm.amount),
                role="payment",
            ))
        if review_required_status == "REVIEW_REQUIRED":
            stats["review_required"] += 1
        stats["created"] += 1

    batch.status = BATCH_STATUS_COMPLETED
    from datetime import datetime
    batch.completed_at = datetime.now()
    batch.stats_json = stats
    db.commit()

    return {"import_id": batch.id, "filename": batch.filename, "status": "COMPLETED", **stats}


@router.get("/")
def import_history(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    q = db.query(ImportBatch)
    if status:
        q = q.filter(ImportBatch.status == status)
    total = q.count()
    rows = q.order_by(ImportBatch.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [
        {
            "id": b.id,
            "filename": b.filename,
            "source_type": b.source_type,
            "status": b.status,
            "error_message": b.error_message,
            "started_at": str(b.started_at),
            "completed_at": str(b.completed_at) if b.completed_at else None,
            "stats": b.stats_json,
        }
        for b in rows
    ]}


@router.get("/{batch_id}")
def import_detail(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")
    db_file = db.query(DBFile).filter(DBFile.import_batch_id == batch_id).first()
    txns = []
    if db_file:
        txns = (
            db.query(Transaction)
            .join(RawTransaction, Transaction.raw_transaction_id == RawTransaction.id)
            .filter(RawTransaction.file_id == db_file.id)
            .order_by(RawTransaction.row_number)
            .all()
        )
    return {
        "id": batch.id,
        "filename": batch.filename,
        "source_type": batch.source_type,
        "status": batch.status,
        "error_message": batch.error_message,
        "started_at": str(batch.started_at),
        "completed_at": str(batch.completed_at) if batch.completed_at else None,
        "stats": batch.stats_json,
        "file": {
            "original_name": db_file.original_name,
            "sha256": db_file.sha256,
            "size": db_file.size,
        } if db_file else None,
        "transactions": [
            {
                "id": t.id,
                "date": t.date,
                "merchant": t.merchant,
                "amount": t.amount,
                "currency": t.currency,
                "direction": t.direction,
                "status": t.status,
            }
            for t in txns
        ],
        "transaction_count": len(txns),
    }


@router.post("/")
async def upload_import(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """兼容旧接口：一步完成 analyze + commit。新前端请使用 /analyze + /commit/{id}。"""
    batch = ImportBatch(source_type="UNKNOWN", filename=file.filename, status="ANALYZING")
    db.add(batch)
    db.commit()
    db.refresh(batch)

    try:
        storage_path, db_file = _save_upload(file, db, batch)
        importer = ImporterRegistry.get_importer(storage_path)
        raw_data_list = importer.parse(storage_path)
        batch.source_type = importer.name.upper()
        db_file.source_type = batch.source_type

        existing_raw_count = (
            db.query(RawTransaction).filter(RawTransaction.file_id == db_file.id).count()
        )
        if existing_raw_count == 0:
            for idx, row in enumerate(raw_data_list, start=1):
                db.add(RawTransaction(file_id=db_file.id, raw_data_json=row, row_number=idx))
            db.flush()

        dedup = DeduplicationService()
        engine = RuleService.build_engine(db)
        stats = {"total": 0, "created": 0, "existing": 0, "possible_duplicate": 0, "review_required": 0}

        for raw in db.query(RawTransaction).filter(RawTransaction.file_id == db_file.id).all():
            stats["total"] += 1
            try:
                norm = importer.normalize(raw.raw_data_json)
            except Exception:
                continue
            raw_hash = dedup.get_raw_hash(raw.raw_data_json)
            fingerprint = dedup.get_canonical_fingerprint(norm.model_dump())
            result, _reason = dedup.check_against_db(db, norm.source_transaction_id, raw_hash, fingerprint)
            if result == "EXACT_DUPLICATE":
                stats["existing"] += 1
                continue
            if result == "POSSIBLE_DUPLICATE":
                stats["possible_duplicate"] += 1
                status = "POSSIBLE_DUPLICATE"
            else:
                status = "REVIEW_REQUIRED"

            actions = engine.apply(norm.model_dump())
            txn = Transaction(
                raw_transaction_id=raw.id,
                date=norm.date,
                time=norm.time,
                amount=str(norm.amount),
                currency=norm.currency,
                merchant=norm.merchant,
                description=norm.description,
                payment_method=norm.payment_method,
                counterparty=norm.counterparty,
                direction=norm.direction,
                source_type=batch.source_type,
                source_transaction_id=norm.source_transaction_id,
                raw_hash=raw_hash,
                canonical_fingerprint=fingerprint,
                status=status,
            )
            db.add(txn)
            db.flush()
            payment_account = match_payment_account(db, norm.payment_method)
            db.add(TransactionSplit(
                transaction_id=txn.id,
                account=actions.get("account", "Expenses:Uncategorized"),
                amount=str(norm.amount),
                role="expense",
            ))
            if payment_account:
                db.add(TransactionSplit(
                    transaction_id=txn.id,
                    account=payment_account,
                    amount=str(-norm.amount) if norm.direction != "收入" else str(norm.amount),
                    role="payment",
                ))
            if status == "REVIEW_REQUIRED":
                stats["review_required"] += 1
            stats["created"] += 1

        batch.status = BATCH_STATUS_COMPLETED
        from datetime import datetime
        batch.completed_at = datetime.now()
        db.commit()
        return {"import_id": batch.id, "filename": file.filename, "status": "COMPLETED", **stats}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        batch.status = BATCH_STATUS_ERROR
        batch.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))
