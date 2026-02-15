from datetime import date
from typing import Optional

from sqlalchemy import Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Skin(Base):
    __tablename__ = "skins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    rarity: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    listing_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    thesis: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    prices: Mapped[list["PriceSnapshot"]] = relationship(back_populates="skin", cascade="all, delete-orphan")


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (UniqueConstraint("skin_id", "snapshot_date", name="uq_skin_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    skin_id: Mapped[int] = mapped_column(ForeignKey("skins.id"), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    price_usd: Mapped[float] = mapped_column(Float, nullable=False)
    volume_24h: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    source_ref: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    skin: Mapped[Skin] = relationship(back_populates="prices")
