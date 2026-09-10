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
import app.services.alipay_importer  # noqa: F401  注册内置 Importer

router = APIRouter(prefix="/api/imports")
storage = StorageService()


@router.post("/")
async def upload_import(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1. 初始化 Batch
    batch = ImportBatch(source_type="UNKNOWN", filename=file.filename)
    db.add(batch)
    db.commit()
    db.refresh(batch)

    # 2. 保存文件
    temp_path = f"temp_{uuid.uuid4()}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        storage_path = storage.save(temp_path, batch.id)
        sha256 = storage._calculate_sha256(storage_path)

        # 3. 检查文件是否已导入
        if db.query(DBFile).filter(DBFile.sha256 == sha256).first():
            raise HTTPException(status_code=409, detail="File already imported")

        db_file = DBFile(original_name=file.filename, storage_path=storage_path,
                         sha256=sha256, size=os.path.getsize(storage_path), source_type="UNKNOWN")
        db.add(db_file)
        db.flush()

        # 4. 识别与解析：先用文件首行内容 detect，再解析
        importer = ImporterRegistry.get_importer(storage_path)
        raw_data_list = importer.parse(storage_path)
        batch.source_type = "ALIPAY" if "alipay" in file.filename.lower() else "BANK"
        db_file.source_type = batch.source_type

        # 5. Pipeline 执行
        dedup = DeduplicationService()
        engine = RuleService.build_engine(db)
        txn_count = 0
        review_count = 0

        for row in raw_data_list:
            raw = RawTransaction(file_id=db_file.id, raw_data_json=row)
            db.add(raw)
            db.flush()

            # Normalize
            norm_txn = importer.normalize(row)

            # Deduplicate
            if dedup.check(norm_txn.source_transaction_id, row, norm_txn.model_dump()) == "UNIQUE":
                # Rule Engine 分类（可能返回空 dict）
                actions = engine.apply(norm_txn.model_dump())
                txn = Transaction(
                    raw_transaction_id=raw.id,
                    date=norm_txn.date,
                    time=norm_txn.time,
                    amount=str(norm_txn.amount),
                    currency=norm_txn.currency,
                    merchant=norm_txn.merchant,
                    description=norm_txn.description,
                    payment_method=norm_txn.payment_method,
                    counterparty=norm_txn.counterparty,
                    status="REVIEW_REQUIRED",
                )
                db.add(txn)
                db.flush()

                # Split：来源账户为负（资产流出），分类账户为正
                split = TransactionSplit(
                    transaction_id=txn.id,
                    account=actions.get("account", "Expenses:Uncategorized"),
                    amount=str(norm_txn.amount),
                )
                db.add(split)
                review_count += 1
            txn_count += 1

        batch.status = "COMPLETED"
        db.commit()

        return {
            "import_id": batch.id,
            "filename": file.filename,
            "status": "COMPLETED",
            "transaction_count": txn_count,
            "review_required_count": review_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        batch.status = "IMPORT_ERROR"
        batch.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
