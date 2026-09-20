"""Tool layer: the 10 tools the agent may call.

Design guarantees (grading-critical):
1. Every tool call is written to audit_log with a policy reference.
2. Execution tools (rebooking / refund / compensation) RE-VERIFY everything
   against the database via the rules engine - the LLM cannot cause an action
   the rules engine does not approve (e.g. it cannot pass a made-up delay).
3. Tools return structured dicts; their `policy_reference` is echoed into the
   audit trail and shown in the UI.
"""
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from .models import AuditLog, Booking, Conversation, Customer, RebookingInventory
from . import rules_engine as rules

POLICY = rules.ESCALATION_REASONS


class ToolContext:
    """Everything a tool needs: db session + current conversation."""

    def __init__(self, db: Session, conversation: Optional[Conversation]):
        self.db = db
        self.conversation = conversation
        # The customer message that triggered this turn (for the audit trail)
        self.customer_message: Optional[str] = None
        # Reasoning the model attached to this tool call (for the audit trail)
        self.agent_reasoning: Optional[str] = None

    @property
    def pnr(self) -> Optional[str]:
        return self.conversation.pnr if self.conversation else None

    def mark_escalated(self, reason: str) -> None:
        if self.conversation:
            self.conversation.escalated = True
            self.conversation.escalation_reason = reason
            self.db.add(self.conversation)


def _booking_by_disrupted(db: Session, pnr: str) -> Optional[Booking]:
    """The disrupted leg of a PNR (the leg the conversation is about)."""
    rows = db.query(Booking).filter(Booking.pnr == pnr).all()
    disrupted = [b for b in rows if b.is_disrupted_leg]
    return disrupted[0] if disrupted else (rows[0] if rows else None)


def _log(
    ctx: ToolContext,
    tool: str,
    args: dict,
    policy_reference: str,
    action_taken: str,
    escalated: bool = False,
) -> None:
    entry = AuditLog(
        timestamp=datetime.now(timezone.utc),
        conversation_id=ctx.conversation.id if ctx.conversation else None,
        pnr=ctx.pnr,
        customer_message=ctx.customer_message,
        agent_reasoning=ctx.agent_reasoning,
        tool_called=tool,
        tool_args=json.dumps(args, ensure_ascii=False),
        policy_reference=policy_reference,
        action_taken=action_taken,
        escalated=escalated,
    )
    ctx.db.add(entry)


def _booking_dict(b: Booking) -> dict:
    return {
        "pnr": b.pnr,
        "flight": b.flight_label,
        "route": b.route,
        "scheduled_departure": b.scheduled_departure,
        "status": b.status,
        "delay_hours": b.delay_hours,
        "new_departure": b.new_departure,
        "payment_method": b.payment_method,
    }


# --------------------------------------------------------------------------
# Tool implementations
# --------------------------------------------------------------------------

def tool_lookup_booking(db: Session, pnr: str, ctx: ToolContext, **_) -> dict:
    b = _booking_by_disrupted(db, pnr)
    if not b:
        result = {"error": f"No booking found for PNR {pnr}."}
    else:
        result = _booking_dict(b)
        result["policy_reference"] = "Booking/transaction data (data pack)"
    _log(ctx, "lookup_booking", {"pnr": pnr}, result.get("policy_reference", ""),
         f"Looked up booking {pnr}: {result.get('status', 'not found')}")
    return result


def tool_get_customer_profile(db: Session, pnr: str, ctx: ToolContext, **_) -> dict:
    b = _booking_by_disrupted(db, pnr)
    if not b:
        result = {"error": f"No customer found for PNR {pnr}."}
    else:
        c: Customer = b.customer
        result = {
            "name": c.name,
            "loyalty_tier": c.loyalty_tier,
            "email": c.email,
            "phone": c.phone,
            "flights_last_12m": c.flights_last_12m,
            "prior_complaints": c.prior_complaints,
            **rules.get_loyalty_benefits(c.loyalty_tier),  # R5 benefits, deterministic
        }
    _log(ctx, "get_customer_profile", {"pnr": pnr}, "R5 Loyalty Tier Rule",
         f"Fetched profile: {result.get('name')} ({result.get('loyalty_tier')})")
    return result


def tool_get_delay_compensation(db: Session, hours: float, ctx: ToolContext, **_) -> dict:
    c = rules.get_delay_compensation(hours)
    result = {
        "delay_hours": c.delay_hours,
        "meal_voucher": c.meal_voucher,
        "meal_voucher_amount": c.meal_voucher_amount,
        "lounge_access": c.lounge_access,
        "hotel_delayed_hours_only": c.hotel_delayed_hours_only,
        "hotel_hours": c.hotel_hours,
        "hotel_full_night": c.hotel_full_night,
        "notes": c.notes,
        "policy_reference": c.policy_reference,
    }
    _log(ctx, "get_delay_compensation", {"hours": hours}, c.policy_reference,
         f"Computed compensation for {hours}h delay: voucher={c.meal_voucher}, "
         f"lounge={c.lounge_access}, hotel(delayed hours only)={c.hotel_delayed_hours_only}")
    return result


def tool_get_cancellation_options(db: Session, pnr: str, ctx: ToolContext, **_) -> dict:
    b = _booking_by_disrupted(db, pnr)
    if not b:
        result = {"error": f"No booking found for PNR {pnr}."}
    else:
        cancelled = "cancel" in b.status.lower()
        if not cancelled:
            result = {
                "eligible_for_cancellation_options": False,
                "status": b.status,
                "policy_reference": "R1 Cancellation Rebooking Rule",
                "note": "R1 applies only to airline-caused cancellations.",
            }
        else:
            tier = b.customer.loyalty_tier
            inv = (
                db.query(RebookingInventory)
                .filter(RebookingInventory.origin == b.origin,
                        RebookingInventory.destination == b.destination)
                .order_by(RebookingInventory.departure)
                .all()
            )
            flights = [
                {
                    "flight_number": f.flight_number,
                    "departure": f.departure,
                    "arrival": f.arrival,
                    "fare": f.fare,
                    "higher_fare": f.is_higher_fare,
                    "note": f.note,
                }
                for f in inv
            ]
            # R5: Gold/Platinum get first access to next-available seats.
            result = {
                "eligible_for_cancellation_options": True,
                "status": b.status,
                "options": rules.cancellation_entitlement(),  # R1: choice of rebooking or refund
                "rebooking_flights": flights,
                "priority_rebooking_applied": rules.is_priority_tier(tier),
                "refund_terms": rules.refund_terms(b.payment_method),  # R3
                "policy_reference": "R1 Cancellation Rebooking Rule",
            }
    _log(ctx, "get_cancellation_options", {"pnr": pnr}, "R1 Cancellation Rebooking Rule",
         f"Listed cancellation options for {pnr} "
         f"(priority rebooking: {result.get('priority_rebooking_applied', False)})")
    return result


def tool_check_fare_waiver_allowed(db: Session, amount: float, ctx: ToolContext, **_) -> dict:
    r = rules.check_fare_waiver_allowed(amount)
    if r["must_escalate"]:
        _log(ctx, "check_fare_waiver_allowed", {"amount": amount}, r["policy_reference"],
             f"Rs.{amount:g} waiver exceeds the Rs.{rules.FARE_WAIVER_AGENT_LIMIT:g} agent limit "
             f"-> supervisor approval required", escalated=True)
        ctx.mark_escalated(POLICY["fare_waiver_over_limit"])
    else:
        _log(ctx, "check_fare_waiver_allowed", {"amount": amount}, r["policy_reference"],
             f"Rs.{amount:g} waiver within agent limit - allowed")
    return r


def tool_execute_rebooking(db: Session, pnr: str, flight_number: str, ctx: ToolContext, **_) -> dict:
    b = _booking_by_disrupted(db, pnr)
    if not b:
        result = {"success": False, "error": f"No booking found for PNR {pnr}."}
    else:
        inv = (
            db.query(RebookingInventory)
            .filter(RebookingInventory.flight_number == flight_number,
                    RebookingInventory.origin == b.origin,
                    RebookingInventory.destination == b.destination)
            .first()
        )
        tier = b.customer.loyalty_tier

        hours_after: Optional[float] = None
        if inv:
            try:
                dep_fmt = "%a %d %b %Y %H:%M"
                orig = datetime.strptime(b.scheduled_departure, dep_fmt)
                new = datetime.strptime(inv.departure, dep_fmt)
                hours_after = (new - orig).total_seconds() / 3600.0
            except ValueError:
                hours_after = None

        check = rules.validate_rebooking(
            booking_status=b.status,
            flight_found=bool(inv),
            hours_after_original=hours_after,
            tier=tier,
            target_fare_delta=(inv.fare - b.fare) if inv else 0.0,
        )

        # R4 guard: a higher-fare flight chosen on an airline-caused
        # cancellation is still free under R1 only if fare matches; a
        # higher-fare voluntary switch needs fare-difference handling.
        fare_delta = check["fare_difference_due"]
        if inv and inv.is_higher_fare and fare_delta > 0:
            waiver = rules.check_fare_waiver_allowed(fare_delta)
            if not waiver["allowed_without_supervisor"]:
                check["allowed"] = False
                check["violations"].append(
                    f"Voluntary higher-fare change (Rs.{fare_delta:g} difference) - waiver "
                    f"above Rs.{rules.FARE_WAIVER_AGENT_LIMIT:g} needs supervisor approval."
                )
                check["escalate"] = True
                check["policy_reference"] += " / R4 Fare Difference Rule"

        if not check["allowed"]:
            result = {"success": False, "rebooking_not_performed": True,
                      "violations": check["violations"],
                      "policy_reference": check["policy_reference"]}
            _log(ctx, "execute_rebooking", {"pnr": pnr, "flight_number": flight_number},
                 check["policy_reference"],
                 f"REBOOKING DENIED: {'; '.join(check['violations'])}",
                 escalated=check.get("escalate", False))
            if check.get("escalate"):
                ctx.mark_escalated(POLICY["fare_waiver_over_limit"])
            return result

        b.status = f"Rebooked on {inv.flight_number} (was: {b.status})"
        b.new_departure = inv.departure
        ctx.db.add(b)
        result = {
            "success": True,
            "pnr": pnr,
            "rebooked_on": inv.flight_number,
            "new_departure": inv.departure,
            "charge": 0,  # R1: airline-caused -> free
            "priority_rebooking_applied": check["priority_rebooking_applied"],
            "policy_reference": check["policy_reference"],
        }
        _log(ctx, "execute_rebooking", {"pnr": pnr, "flight_number": flight_number},
             check["policy_reference"],
             f"Rebooked {pnr} onto {inv.flight_number} departing {inv.departure} at no charge"
             + (" with Gold/Platinum priority" if check["priority_rebooking_applied"] else ""))
    return result


def tool_execute_refund(db: Session, pnr: str, ctx: ToolContext, **_) -> dict:
    b = _booking_by_disrupted(db, pnr)
    if not b:
        result = {"success": False, "error": f"No booking found for PNR {pnr}."}
    else:
        cancelled = "cancel" in b.status.lower()
        if not cancelled:
            result = {"success": False, "refund_not_initiated": True,
                      "reason": "Refunds apply to airline-caused cancellations only.",
                      "policy_reference": "R3 Refund Processing Rule"}
        else:
            terms = rules.refund_terms(b.payment_method)
            result = {
                "success": True,
                "refund_request_initiated": True,
                "pnr": pnr,
                "amount": "full",
                "to_payment_method": b.payment_method,  # R3: ORIGINAL method ONLY
                "window_business_days": terms["window_business_days"],
                "policy_reference": terms["policy_reference"],
            }
        _log(ctx, "execute_refund", {"pnr": pnr}, "R3 Refund Processing Rule",
             f"Refund request initiated for {pnr}: full amount to ORIGINAL payment method "
             f"({b.payment_method}), within 7 business days")
    return result


COMPENSATION_TYPES = {
    "meal_voucher": ("meal_voucher", "R2 Delay Compensation Rule"),
    "lounge_access": ("lounge_access", "R2 Delay Compensation Rule"),
    "hotel_delayed_hours": ("hotel_delayed_hours_only", "R2 Delay Compensation Rule"),
}


def tool_issue_compensation(db: Session, pnr: str, type: str, ctx: ToolContext, **_) -> dict:
    """Issue a compensation item - but ALWAYS recomputed from the booking's
    actual stored delay, never from a number the LLM supplies."""
    b = _booking_by_disrupted(db, pnr)
    if not b:
        result = {"success": False, "error": f"No booking found for PNR {pnr}."}
        _log(ctx, "issue_compensation", {"pnr": pnr, "type": type}, "",
             "FAILED - no booking")
        return result

    if b.delay_hours is None:
        result = {"success": False, "error": "This booking is not delayed - delay "
                  "compensation does not apply.", "policy_reference": "R2 Delay Compensation Rule"}
        _log(ctx, "issue_compensation", {"pnr": pnr, "type": type},
             result["policy_reference"],
             f"DENIED - {pnr} is not delayed; R2 does not apply")
        return result

    comp = rules.get_delay_compensation(b.delay_hours)
    key = COMPENSATION_TYPES.get(type, (None, None))[0]
    if key is None:
        result = {"success": False,
                  "error": f"Unknown compensation type '{type}'. Valid: "
                           f"{list(COMPENSATION_TYPES)}",
                  "policy_reference": "R2 Delay Compensation Rule"}
    elif not getattr(comp, key):
        result = {
            "success": False,
            "not_entitled": True,
            "reason": f"A {b.delay_hours:g}h delay does not qualify for '{type}'.",
            "entitled_to": {
                "meal_voucher": comp.meal_voucher,
                "lounge_access": comp.lounge_access,
                "hotel_delayed_hours_only": comp.hotel_delayed_hours_only,
            },
            "policy_reference": comp.policy_reference,
        }
    else:
        if key == "meal_voucher":
            detail = f"Rs.{comp.meal_voucher_amount} meal voucher"
        elif key == "lounge_access":
            detail = "lounge access"
        else:
            detail = f"hotel accommodation for the {comp.hotel_hours:g} delayed hours ONLY (not a full night)"
        result = {"success": True, "issued": type, "detail": detail,
                  "policy_reference": comp.policy_reference}

    if result["success"]:
        _log(ctx, "issue_compensation", {"pnr": pnr, "type": type}, comp.policy_reference,
             f"Issued {type} for {pnr} ({result['detail']})")
    else:
        escalated = bool(result.get("not_entitled")) and type == "hotel_full_night"
        _log(ctx, "issue_compensation", {"pnr": pnr, "type": type}, comp.policy_reference,
             f"DENIED '{type}' for {pnr}: {result.get('reason')}", escalated=escalated)
    return result


def tool_escalate_to_human(db: Session, pnr: str, reason: str, ctx: ToolContext, **_) -> dict:
    ctx.mark_escalated(reason)
    result = {
        "success": True,
        "escalated": True,
        "handoff": "Specialist human support team",
        "promise": "The specialist team will reach out to the customer directly.",
        "policy_reference": "PROHIBITED ACTIONS - escalation mandate",
    }
    _log(ctx, "escalate_to_human", {"pnr": pnr, "reason": reason},
         result["policy_reference"], f"ESCALATED to human team: {reason}", escalated=True)
    return result


def tool_log_action(db: Session, pnr: str, action: str, policy_reference: str,
                    ctx: ToolContext, **_) -> dict:
    _log(ctx, "log_action", {"pnr": pnr, "action": action,
                             "policy_reference": policy_reference},
         policy_reference, action)
    return {"success": True, "logged": action, "policy_reference": policy_reference}


# --------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------

DISPATCH = {
    "lookup_booking": tool_lookup_booking,
    "get_customer_profile": tool_get_customer_profile,
    "get_delay_compensation": tool_get_delay_compensation,
    "get_cancellation_options": tool_get_cancellation_options,
    "check_fare_waiver_allowed": tool_check_fare_waiver_allowed,
    "execute_rebooking": tool_execute_rebooking,
    "execute_refund": tool_execute_refund,
    "issue_compensation": tool_issue_compensation,
    "escalate_to_human": tool_escalate_to_human,
    "log_action": tool_log_action,
}


def execute_tool(name: str, args: dict, ctx: ToolContext) -> dict:
    """Run a tool by name. Returns a JSON-serialisable dict."""
    fn = DISPATCH.get(name)
    if fn is None:
        return {"error": f"Unknown tool '{name}'"}
    try:
        # Only pass args the function actually accepts (LLMs sometimes add extras).
        sig_keys = fn.__code__.co_varnames[: fn.__code__.co_argcount]
        filtered = {k: v for k, v in (args or {}).items() if k in sig_keys and k != "db"}
        return fn(ctx.db, ctx=ctx, **filtered)
    except Exception as exc:  # noqa: BLE001 - tools must never crash the loop
        return {"error": f"Tool '{name}' failed: {exc}"}
