import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import Base, Transaction
from app.services.split import SplitService

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_balance_validation():
    # 正常
    splits = [{"account": "A", "amount": "100.00"}, {"account": "B", "amount": "-100.00"}]
    assert SplitService.validate_balance(splits) is True
    
    # 不平衡
    splits_invalid = [{"account": "A", "amount": "100.00"}, {"account": "B", "amount": "-90.00"}]
    assert SplitService.validate_balance(splits_invalid) is False

def test_update_transaction_splits(db_session):
    txn = Transaction(date="2026-09-08", amount="-100", status="REVIEW_REQUIRED")
    db_session.add(txn)
    db_session.commit()
    
    splits = [
        {"account": "Assets:Bank", "amount": "-100.00"},
        {"account": "Expenses:Food", "amount": "100.00"}
    ]
    SplitService.update_transaction_with_splits(db_session, txn.id, splits)
    
    from app.models.models import TransactionSplit
    saved_splits = db_session.query(TransactionSplit).filter(TransactionSplit.transaction_id == txn.id).all()
    assert len(saved_splits) == 2
    assert sum(Decimal(s.amount) for s in saved_splits) == 0
