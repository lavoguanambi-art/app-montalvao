from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)

    buckets = relationship("Bucket", back_populates="user", cascade="all, delete-orphan")
    giants  = relationship("Giant",  back_populates="user", cascade="all, delete-orphan")

class Bucket(Base):
    __tablename__ = "buckets"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    percent = Column(Float, nullable=False)  # 0..100
    type = Column(String, default="generic")
    balance = Column(Float, default=0.0)

    user = relationship("User", back_populates="buckets")

class Giant(Base):
    __tablename__ = "giants"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    total_to_pay = Column(Float, nullable=False)
    parcels = Column(Integer, default=0)
    months_left = Column(Integer, default=0)
    priority = Column(Integer, default=1)  # 1 = maior prioridade
    status = Column(String, default="active")  # active | defeated

    user = relationship("User", back_populates="giants")

class Movement(Base):
    __tablename__ = "movements"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bucket_id = Column(Integer, ForeignKey("buckets.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String, nullable=False)  # income | expense | transfer
    amount = Column(Float, nullable=False)
    description = Column(String, default="")
    date = Column(Date, nullable=False)

class Bill(Base):
    __tablename__ = "bills"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    due_date = Column(Date, nullable=False)
    is_critical = Column(Boolean, default=False)
    paid = Column(Boolean, default=False)

# Perfil financeiro do usuário (receita/despesa declaradas)
class UserProfile(Base):
    __tablename__ = "user_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    monthly_income  = Column(Float, default=0.0)   # receita mensal declarada
    monthly_expense = Column(Float, default=0.0)   # despesa mensal declarada

# Registros de aportes para cada gigante
class GiantPayment(Base):
    __tablename__ = "giant_payments"
    id = Column(Integer, primary_key=True, index=True)
    user_id  = Column(Integer, ForeignKey("users.id",   ondelete="CASCADE"), nullable=False)
    giant_id = Column(Integer, ForeignKey("giants.id",  ondelete="CASCADE"), nullable=False)
    amount   = Column(Float, nullable=False)   # valor do aporte
    date     = Column(Date,  nullable=False)   # data do aporte
    note     = Column(String, default="")      # observação opcional