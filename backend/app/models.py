"""Database models.

Tables:
- customers           : the 3 seeded customer profiles (from the data pack)
- bookings            : bookings / flights per customer (from the data pack)
- rebooking_inventory : assumed next-available flights (ASSUMPTION, see README)
- conversations       : one chat thread per customer
- messages            : individual chat messages
- audit_log           : every tool call + decision (the audit trail)
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    loyalty_tier: Mapped[str] = mapped_column(String(20))  # Gold | Silver | Platinum
    email: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(40))
    flights_last_12m: Mapped[int] = mapped_column(Integer)
    prior_complaints: Mapped[str] = mapped_column(Text)  # free text from data pack

    bookings: Mapped[list["Booking"]] = relationship(back_populates="customer")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pnr: Mapped[str] = mapped_column(String(20), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    flight_label: Mapped[str] = mapped_column(String(40))  # "SK-204" or "Return"
    flight_number: Mapped[str] = mapped_column(String(20))  # "SK-204" / "" for return leg
    route: Mapped[str] = mapped_column(String(80))  # "Delhi → Goa"
    origin: Mapped[str] = mapped_column(String(40))
    destination: Mapped[str] = mapped_column(String(40))
    scheduled_departure: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(60))  # Cancelled / Delayed / Unaffected / Rebooked
    delay_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_departure: Mapped[str | None] = mapped_column(String(60), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(60))  # ORIGINAL payment method (refund rule)
    is_disrupted_leg: Mapped[bool] = mapped_column(Boolean, default=False)
    fare: Mapped[float] = mapped_column(Float, default=0.0)

    customer: Mapped[Customer] = relationship(back_populates="bookings")


class RebookingInventory(Base):
    """ASSUMPTION: the data pack does not include flight inventory for rebooking.

    We seed plausible next-available flights so `execute_rebooking` is demoable.
    Marked as an assumption in the README. No policy or customer data invented.
    """

    __tablename__ = "rebooking_inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_number: Mapped[str] = mapped_column(String(20))
    origin: Mapped[str] = mapped_column(String(40))
    destination: Mapped[str] = mapped_column(String(40))
    departure: Mapped[str] = mapped_column(String(60))
    arrival: Mapped[str] = mapped_column(String(60))
    fare: Mapped[float] = mapped_column(Float)
    is_higher_fare: Mapped[bool] = mapped_column(Boolean, default=False)  # voluntary-change flag
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    pnr: Mapped[str] = mapped_column(String(20), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # customer | agent
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class AuditLog(Base):
    """One row per tool call / decision. The grading audit trail."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pnr: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_called: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tool_args: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    policy_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    action_taken: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
