from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import Base
import pytest

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_transaction_splits(db_session):
    from app.models.models import Transaction, TransactionSplit
    txn = Transaction(date="2026-09-08", amount="-100")
    db_session.add(txn)
    db_session.flush()
    
    s1 = TransactionSplit(transaction_id=txn.id, account="Expenses:Food", amount="20")
    s2 = TransactionSplit(transaction_id=txn.id, account="Assets:Bank", amount="-100")
    db_session.add_all([s1, s2])
    db_session.commit()
    
    assert len(txn.splits) == 2
