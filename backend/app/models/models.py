from sqlalchemy import Column, Integer, String, DateTime, func, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.db.session import Base

class File(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, index=True)
    original_name = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    sha256 = Column(String, nullable=False, unique=True)
    size = Column(Integer, nullable=False)
    mime_type = Column(String)
    source_type = Column(String, nullable=False)
    parser = Column(String)
    parser_version = Column(String)
    created_at = Column(DateTime, default=func.now())
    import_batch_id = Column(Integer, ForeignKey("import_batches.id"))

class ImportBatch(Base):
    __tablename__ = "import_batches"
    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String, nullable=False)
    filename = Column(String)
    parser = Column(String)
    parser_version = Column(String)
    status = Column(String, default="IMPORTED")
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime)
    error_message = Column(String)
    stats_json = Column(JSON, nullable=True)

class RawTransaction(Base):
    __tablename__ = "raw_transactions"
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    source_transaction_id = Column(String)
    raw_data_json = Column(JSON, nullable=False)
    row_number = Column(Integer)
    status = Column(String, default="IMPORTED")
    created_at = Column(DateTime, default=func.now())

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    raw_transaction_id = Column(Integer, ForeignKey("raw_transactions.id"))
    date = Column(String, nullable=False)
    time = Column(String)
    amount = Column(String, nullable=False)
    currency = Column(String, default="CNY")
    merchant = Column(String)
    description = Column(String)
    payment_method = Column(String)
    counterparty = Column(String)
    direction = Column(String, default="支出")
    source_type = Column(String)
    source_transaction_id = Column(String, index=True)
    raw_hash = Column(String, index=True)
    canonical_fingerprint = Column(String, index=True)
    review_reason = Column(String, nullable=True)
    duplicate_reason = Column(String, nullable=True)
    status = Column(String, default="NORMALIZED")
    created_at = Column(DateTime, default=func.now())
    splits = relationship("TransactionSplit", back_populates="transaction")

class TransactionSplit(Base):
    __tablename__ = "transaction_splits"
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    account = Column(String, nullable=False)
    amount = Column(String, nullable=False)
    transaction = relationship("Transaction", back_populates="splits")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String)
    entity_id = Column(Integer)
    action = Column(String)
    old_value = Column(JSON)
    new_value = Column(JSON)
    timestamp = Column(DateTime, default=func.now())
    user_note = Column(String)

class ExportRecord(Base):
    __tablename__ = "export_records"
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    file_path = Column(String, nullable=False)
    file_sha256 = Column(String, nullable=False)
    status = Column(String, default="PENDING")
    error_message = Column(String)
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime)

class Rule(Base):
    __tablename__ = "rules"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    priority = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)
    conditions = relationship("RuleCondition", back_populates="rule")
    actions = relationship("RuleAction", back_populates="rule")

class RuleCondition(Base):
    __tablename__ = "rule_conditions"
    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("rules.id"), nullable=False)
    key = Column(String, nullable=False)
    pattern = Column(String, nullable=False)
    rule = relationship("Rule", back_populates="conditions")

class RuleAction(Base):
    __tablename__ = "rule_actions"
    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("rules.id"), nullable=False)
    action_type = Column(String, nullable=False)
    value = Column(String, nullable=False)
    rule = relationship("Rule", back_populates="actions")

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    open_date = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
