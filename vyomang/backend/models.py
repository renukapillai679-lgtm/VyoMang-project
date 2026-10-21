"""Database tables."""
from sqlalchemy import Column, DateTime, Float, Integer, String, func

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String)
    picture_url = Column(String)
    google_id = Column(String, unique=True, index=True)       # Google's "sub" value
    salt = Column(String, nullable=False, default="")         # empty for Google-only accounts
    pw_hash = Column(String, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class Sku(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    festival_sens = Column(Float, nullable=False)
    lead_time = Column(Integer, nullable=False)
    on_hand = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)


class Sale(Base):
    """Weekly units sold. week_no 0 is the oldest week."""
    __tablename__ = "sales"

    sku_id = Column(String, primary_key=True)
    week_no = Column(Integer, primary_key=True)
    units = Column(Float, nullable=False)


class SaleOriginal(Base):
    """Untouched sample data, used by 'Reset sample data'."""
    __tablename__ = "sales_original"

    sku_id = Column(String, primary_key=True)
    week_no = Column(Integer, primary_key=True)
    units = Column(Float, nullable=False)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku_id = Column(String, nullable=False)
    qty = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    created = Column(String, nullable=False)                  # ISO date-time text
