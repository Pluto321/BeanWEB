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


def test_generator_channel_metadata(db_session):
    """有来源的交易 → channel metadata（中文渠道标签）；无来源 → 不输出 channel 行"""
    txn = Transaction(date="2026-02-05", amount="3.00", merchant="聚鑫福超市",
                      description="怡宝矿泉水", currency="CNY", status="CONFIRMED",
                      source_type="WECHAT", raw_transaction_id=42)
    db_session.add(txn)
    db_session.flush()
    db_session.add(TransactionSplit(transaction_id=txn.id, account="Expenses:Food:饮料", amount="3.00"))
    db_session.add(TransactionSplit(transaction_id=txn.id, account="Assets:WeChat:零钱", amount="-3.00"))
    db_session.commit()

    output = BeancountGenerator.generate_transaction(txn)
    assert '2026-02-05 * "聚鑫福超市" "怡宝矿泉水"' in output
    assert 'channel: "微信支付"' in output
    assert 'id: "' in output and 'raw_id: "' in output  # 导出保留追踪 ID

    txn.source_type = None
    output2 = BeancountGenerator.generate_transaction(txn)
    assert 'channel:' not in output2
