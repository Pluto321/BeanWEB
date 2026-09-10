import pytest
from app.models.models import Transaction
from app.services.review import ReviewService
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import Base

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_status_transition_with_audit(db_session):
    txn = Transaction(date="2026-09-08", amount="100", status="REVIEW_REQUIRED")
    db_session.add(txn)
    db_session.commit()
    
    ReviewService.change_status(db_session, txn.id, "CONFIRMED", "Testing confirmation")
    
    db_session.refresh(txn)
    assert txn.status == "CONFIRMED"
    
    from app.models.models import AuditLog
    log = db_session.query(AuditLog).filter(AuditLog.entity_id == txn.id).first()
    assert log is not None
    assert log.action == "STATUS_CHANGE"
