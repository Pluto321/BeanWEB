import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import Base, Transaction, TransactionSplit
from app.services.generator import BeancountGenerator

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_generator_syntax(db_session):
    txn = Transaction(date="2026-09-08", amount="100.00", merchant="淘宝", description="书", currency="CNY", status="CONFIRMED")
    db_session.add(txn)
    db_session.flush()
    
    s1 = TransactionSplit(transaction_id=txn.id, account="Assets:Alipay", amount="-100.00")
    s2 = TransactionSplit(transaction_id=txn.id, account="Expenses:Book", amount="100.00")
    db_session.add_all([s1, s2])
    db_session.commit()
    
    output = BeancountGenerator.generate_transaction(txn)
    assert '2026-09-08 * "淘宝" "书"' in output
    assert 'Assets:Alipay' in output
    assert '-100.00' in output
