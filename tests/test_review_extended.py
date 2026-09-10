from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import Base, Transaction, AuditLog
from app.services.review import ReviewService
import pytest

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_transaction_update_transactional(db_session):
    # 模拟事务失败场景 (故意触发 ValueError)
    txn = Transaction(date="2026-09-08", amount="100", status="REVIEW_REQUIRED")
    db_session.add(txn)
    db_session.commit()
    
    # 模拟事务场景：在事务开启后进行修改，如果抛出异常则回滚
    txn = Transaction(date="2026-09-08", amount="100", status="REVIEW_REQUIRED")
    db_session.add(txn)
    db_session.commit()
    
    # 重新查询获取对象
    txn = db_session.query(Transaction).get(txn.id)
    
    # 模拟事务场景：修改 merchant 并触发模拟异常
    try:
        # 开启显式事务
        with db_session.begin_nested():
            ReviewService.update_transaction(db_session, txn.id, {"merchant": "WrongName"})
            # 强制触发异常以测试回滚
            raise ValueError("Simulated error")
    except ValueError:
        db_session.rollback()
        
    # 重新加载对象以验证数据库状态
    db_session.expire(txn)
    txn = db_session.query(Transaction).get(txn.id)
    assert txn.merchant != "WrongName"


def test_possible_duplicate_flow(db_session):
    txn = Transaction(date="2026-09-08", amount="100", status="POSSIBLE_DUPLICATE")
    db_session.add(txn)
    db_session.commit()
    
    ReviewService.change_status(db_session, txn.id, "CONFIRMED", "Manual confirm duplicate")
    db_session.refresh(txn)
    assert txn.status == "CONFIRMED"
