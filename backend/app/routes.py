"""HTTP API: chat + audit + data endpoints used by the Next.js frontend."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .agent import run_agent_turn
from .config import GEMINI_API_KEY
from .database import get_db
from .models import AuditLog, Booking, Conversation, Customer, Message
from .offline_agent import run_offline_turn
from .seed import SCENARIO_OPENERS, run_seed
from .tools import ToolContext

router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class ChatRequest(BaseModel):
    content: str


class ConversationOut(BaseModel):
    id: int
    pnr: str
    customer_name: str
    loyalty_tier: str
    escalated: bool
    escalation_reason: str | None
    started_at: datetime
    messages: list[dict]

    class Config:
        from_attributes = True


def _msg_dict(m: Message) -> dict:
    return {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}


# --------------------------------------------------------------------------
# Data endpoints
# --------------------------------------------------------------------------
@router.get("/customers")
def get_customers(db: Session = Depends(get_db)):
    customers = db.query(Customer).all()
    out = []
    for c in customers:
        bookings = db.query(Booking).filter(Booking.customer_id == c.id).all()
        out.append({
            "id": c.id,
            "name": c.name,
            "loyalty_tier": c.loyalty_tier,
            "email": c.email,
            "phone": c.phone,
            "flights_last_12m": c.flights_last_12m,
            "prior_complaints": c.prior_complaints,
            "pnr": bookings[0].pnr if bookings else None,
            "bookings": [{
                "flight": b.flight_label,
                "route": b.route,
                "scheduled_departure": b.scheduled_departure,
                "status": b.status,
                "delay_hours": b.delay_hours,
                "new_departure": b.new_departure,
            } for b in bookings],
            "opener": SCENARIO_OPENERS.get(bookings[0].pnr if bookings else "", ""),
        })
    return out


@router.get("/mode")
def get_mode():
    """Tells the UI whether the real LLM path or offline fallback is active."""
    return {"llm_active": bool(GEMINI_API_KEY), "provider": "gemini" if GEMINI_API_KEY else "offline-fallback"}


# --------------------------------------------------------------------------
# Conversation endpoints
# --------------------------------------------------------------------------
def _get_or_create_conversation(db: Session, pnr: str) -> Conversation:
    booking = db.query(Booking).filter(Booking.pnr == pnr).first()
    if not booking:
        raise HTTPException(404, f"Unknown PNR {pnr}")
    conv = db.query(Conversation).filter(Conversation.pnr == pnr).order_by(Conversation.id.desc()).first()
    if conv is None:
        conv = Conversation(customer_id=booking.customer_id, pnr=pnr)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        # Seed the scenario's opening customer message
        opener = SCENARIO_OPENERS.get(pnr, "")
        if opener:
            db.add(Message(conversation_id=conv.id, role="customer", content=opener))
            db.commit()
    return conv


@router.post("/conversations/{pnr}")
def start_conversation(pnr: str, db: Session = Depends(get_db)):
    conv = _get_or_create_conversation(db, pnr)
    customer = db.query(Customer).filter(Customer.id == conv.customer_id).first()
    return {
        "id": conv.id,
        "pnr": conv.pnr,
        "customer_name": customer.name,
        "loyalty_tier": customer.loyalty_tier,
        "escalated": conv.escalated,
        "escalation_reason": conv.escalation_reason,
        "messages": [_msg_dict(m) for m in conv.messages],
    }


@router.post("/conversations/{pnr}/messages")
def send_message(pnr: str, req: ChatRequest, db: Session = Depends(get_db)):
    """The main chat endpoint: customer message -> agent turn -> reply."""
    conv = _get_or_create_conversation(db, pnr)
    user_text = req.content.strip()
    if not user_text:
        raise HTTPException(400, "Empty message")

    user_msg = Message(conversation_id=conv.id, role="customer", content=user_text)
    db.add(user_msg)
    db.commit()

    ctx = ToolContext(db, conv)
    llm_active = bool(GEMINI_API_KEY)
    try:
        if llm_active:
            result = run_agent_turn(db, conv, user_text, ctx)
            reply, trace, escalated = result.reply, result.tool_trace, result.escalated
            provider = "gemini"
        else:
            reply, trace, escalated = run_offline_turn(db, conv, user_text, ctx)
            provider = "offline-fallback"
    except Exception as exc:  # noqa: BLE001 - never leave the customer without an answer
        db.rollback()
        reply = ("I'm sorry - I'm having a technical issue right now. Please try again "
                 "in a moment, or ask me to escalate this to a human specialist.")
        trace = [{"tool": "error", "args": {}, "result": {"error": str(exc)},
                  "policy_reference": "", "escalated": False}]
        escalated = conv.escalated
        provider = "error"

    agent_msg = Message(conversation_id=conv.id, role="agent", content=reply)
    db.add(agent_msg)
    db.commit()
    db.refresh(agent_msg)

    return {
        "user_message": _msg_dict(user_msg),
        "agent_message": _msg_dict(agent_msg),
        "tool_trace": trace,
        "escalated": escalated or conv.escalated,
        "provider": provider,
    }


@router.post("/reset")
def reset_conversations(db: Session = Depends(get_db)):
    """Reset the demo to a pristine state: clears conversations, messages and
    audit entries AND restores customers/bookings to their seeded values (so a
    demo-rebooking Priya is 'Cancelled' again on the next run)."""
    db.query(AuditLog).delete()
    db.query(Message).delete()
    db.query(Conversation).delete()
    db.query(Booking).delete()
    db.query(Customer).delete()
    db.commit()
    run_seed(verbose=False)
    return {"ok": True}


# --------------------------------------------------------------------------
# Audit endpoints (admin view)
# --------------------------------------------------------------------------
@router.get("/audit")
def get_audit(db: Session = Depends(get_db)):
    rows = db.query(AuditLog).order_by(AuditLog.id).all()
    convos = {c.id: c.pnr for c in db.query(Conversation).all()}
    return [{
        "id": r.id,
        "timestamp": r.timestamp.isoformat(),
        "pnr": r.pnr or convos.get(r.conversation_id),
        "customer_message": r.customer_message,
        "agent_reasoning": r.agent_reasoning,
        "tool_called": r.tool_called,
        "tool_args": r.tool_args,
        "policy_reference": r.policy_reference,
        "action_taken": r.action_taken,
        "escalated": r.escalated,
    } for r in rows]


@router.get("/conversations")
def get_conversations(db: Session = Depends(get_db)):
    out = []
    for conv in db.query(Conversation).order_by(Conversation.id).all():
        customer = db.query(Customer).filter(Customer.id == conv.customer_id).first()
        out.append({
            "id": conv.id,
            "pnr": conv.pnr,
            "customer_name": customer.name if customer else "",
            "loyalty_tier": customer.loyalty_tier if customer else "",
            "escalated": conv.escalated,
            "escalation_reason": conv.escalation_reason,
            "started_at": conv.started_at.isoformat(),
            "messages": [_msg_dict(m) for m in conv.messages],
        })
    return out
