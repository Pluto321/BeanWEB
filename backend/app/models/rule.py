from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, JSON
from app.db.session import Base

class Rule(Base):
    __tablename__ = "rules"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    priority = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)

class RuleCondition(Base):
    __tablename__ = "rule_conditions"
    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("rules.id"), nullable=False)
    key = Column(String, nullable=False)
    pattern = Column(String, nullable=False)

class RuleAction(Base):
    __tablename__ = "rule_actions"
    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("rules.id"), nullable=False)
    action_type = Column(String, nullable=False)
    value = Column(String, nullable=False)
