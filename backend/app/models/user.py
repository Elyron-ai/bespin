from sqlalchemy import Column, Integer, String, DateTime, Enum
from sqlalchemy.sql import func
from app.database import Base
import enum

class SubscriptionStatus(enum.Enum):
    active = "active"
    canceled = "canceled"
    expired = "expired"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    stripe_customer_id = Column(String, nullable=True)
    subscription_status = Column(Enum(SubscriptionStatus), nullable=True)
    subscription_id = Column(String, nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
