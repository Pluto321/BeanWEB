from sqlalchemy import Column, Integer, String, DateTime, func, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.db.session import Base

class ExportRecord(Base):
    __tablename__ = "export_records"
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    file_path = Column(String, nullable=False)
    file_sha256 = Column(String, nullable=False)
    status = Column(String, default="PENDING") # PENDING, EXPORTING, EXPORTED, FAILED
    error_message = Column(String)
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime)
