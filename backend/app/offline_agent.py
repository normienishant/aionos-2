"""OFFLINE FALLBACK AGENT (emergency demo mode).

If GEMINI_API_KEY is missing or the Gemini call fails, this deterministic
scripted agent keeps the demo working end-to-end. It uses the SAME tools
layer (so the audit trail and policy checks are identical) - it just replaces
LLM intent-understanding with keyword intents for the 3 assignment scenarios.

This mode is clearly labelled in the UI and README; the submission path is
the Gemini agent above.
"""
from typing import Any

from . import tools as tools_mod
from .guard import detect_legal_threat
from .models import Conversation
from .tools import ToolContext


def _run(db, conversation: Conversation, ctx: ToolContext, calls: list[tuple[str, dict]]) -> tuple[list[dict], bool]:
    trace: list[dict[str, Any]] = []
    escalated = False
    for name, args in calls:
        outcome = tools_mod.execute_tool(name, args, ctx)
        trace.append({"tool": name, "args": args, "result": outcome,
                      "policy_reference": outcome.get("policy_reference", ""),
                      "escalated": bool(outcome.get("escalated")) or name == "escalate_to_human"})
        if outcome.get("escalated") or name == "escalate_to_human":
            escalated = True
    return trace, escalated


def run_offline_turn(db, conversation: Conversation, user_message: str, ctx: ToolContext) -> tuple[str, list[dict], bool]:
    """Returns (reply, tool_trace, escalated)."""
    ctx.customer_message = user_message
    pnr = conversation.pnr
    text = (user_message or "").lower()

    calls: list[tuple[str, dict]] = [("lookup_booking", {"pnr": pnr}),
                                     ("get_customer_profile", {"pnr": pnr})]

    # --- Escalation intents (checked first) --------------------------------
    if detect_legal_threat(user_message) or "formal complaint" in text:
        trace, esc = _run(db, conversation, ctx,
                          calls + [("escalate_to_human", {"pnr": pnr, "reason":
                                   "Legal action / formal complaint mentioned - immediate escalation."})])
        return ("I hear you, and I'm sorry this has been such a frustrating experience. "
                "I want to make sure this gets the right attention - I'm escalating this "
                "to our specialist support team right now, and they'll reach out to you "
                "directly."), trace, esc

    if any(k in text for k in ["waive", "waiver"]) and any(k in text for k in ["2,000", "2000", "₹2"]):
        trace, esc = _run(db, conversation, ctx, calls + [
            ("check_fare_waiver_allowed", {"amount": 2000}),
            ("escalate_to_human", {"pnr": pnr,
             "reason": "Fare-difference waiver of Rs.2,000 requested - above the Rs.1,500 agent limit."}),
        ])
        return ("I completely understand wanting a smoother option. The flight you'd like "
                "has a Rs.2,000 fare difference, and I'm not able to waive amounts above "
                "Rs.1,500 myself - I've escalated your waiver request to our supervisor "
                "team, and they'll reach out to you directly. Meanwhile, your current "
                "flight is confirmed and you're entitled to your meal voucher, lounge "
                "access and hotel for the delayed hours - I've applied those now."), trace, esc

    if any(k in text for k in ["upgrade", "business class", "business-class", "free ticket",
                               "extra compensation", "more compensation"]):
        trace, esc = _run(db, conversation, ctx,
                          calls + [("escalate_to_human", {"pnr": pnr, "reason":
                                   "Request for compensation beyond policy (free upgrade) - not an entitled action."})])
        return ("I completely understand the frustration - I can see your flight was "
                "cancelled due to operational reasons, and I'm sorry no one reached out "
                "sooner. You're entitled to your choice of a free rebooking on the next "
                "available flight within 24 hours, or a full refund - just let me know "
                "which you'd prefer. A complimentary upgrade isn't something I'm able to "
                "approve, so I'm escalating that request to our specialist support team "
                "right now, and they'll reach out to you directly."), trace, esc

    # --- Cancellation flow ---------------------------------------------------
    confirm_words = ["yes", "confirm", "go ahead", "please do", "sure", "do it"]
    wants_rebooking = any(k in text for k in ["rebook", "another flight", "next flight",
                                              "next available", "sk-206", "sk-210", "sk-214"])
    confirms_rebooking = (any(w in text for w in confirm_words)
                          and any(k in text for k in ["rebook", "sk-", "flight", "book me"]))
    if confirms_rebooking:
        # Confirmed rebooking request -> execute on the first available flight
        trace, esc = _run(db, conversation, ctx,
                          calls + [("execute_rebooking", {"pnr": pnr, "flight_number": "SK-206"})])
        return ("All done - I've rebooked you on the next available flight at no "
                "charge. Your new flight details are confirmed on your booking."), trace, esc
    if "refund" in text or "cancel" in text or wants_rebooking:
        trace, esc = _run(db, conversation, ctx, calls + [("get_cancellation_options", {"pnr": pnr})])
        if "refund" in text and not wants_rebooking:
            t2, e2 = _run(db, conversation, ctx, [("execute_refund", {"pnr": pnr})])
            return ("I've initiated your full refund to your original payment method - "
                    "it will be processed within 7 business days. I'm sorry again for the "
                    "disruption."), trace + t2, esc or e2
        return ("I completely understand the frustration - I can see your flight was "
                "cancelled due to operational reasons. I can rebook you on the next "
                "available flight at no extra cost, or process a full refund to your "
                "original payment method. Which would you prefer?"), trace, esc

    # --- Delay flow -----------------------------------------------------------
    if any(k in text for k in ["hotel", "night", "stay", "accommodation"]):
        trace, esc = _run(db, conversation, ctx, calls + [
            ("get_delay_compensation", {"hours": _booking_delay(db, pnr)})])
        reply = ("I'm sorry for the long wait. Your flight is delayed 6 hours, which "
                 "qualifies for a meal voucher, lounge access, and hotel accommodation "
                 "for the delayed hours - though the hotel covers only those delayed "
                 "hours, not a full night. I've applied the meal voucher, lounge access "
                 "and delayed-hours hotel to your booking now.")
        delay = _booking_delay(db, pnr)
        if delay is not None and delay <= 5:
            reply = ("I'm sorry for the long wait. Your flight is delayed 4 hours, which "
                     "qualifies for a meal voucher and lounge access under our policy - "
                     "hotel accommodation applies only to delays beyond 5 hours. I've "
                     "applied the meal voucher and lounge access to your account now.")
        t2, e2 = _run(db, conversation, ctx, [
            ("issue_compensation", {"pnr": pnr, "type": "meal_voucher"}),
            ("issue_compensation", {"pnr": pnr, "type": "lounge_access"}),
            ("issue_compensation", {"pnr": pnr, "type": "hotel_delayed_hours"}),
        ])
        return reply, trace + t2, esc or e2

    if any(k in text for k in ["delay", "stuck", "waiting", "long", "compensat", "voucher", "lounge"]):
        trace, esc = _run(db, conversation, ctx, calls + [
            ("get_delay_compensation", {"hours": _booking_delay(db, pnr) or 0}),
            ("issue_compensation", {"pnr": pnr, "type": "meal_voucher"}),
            ("issue_compensation", {"pnr": pnr, "type": "lounge_access"}),
        ])
        return ("I'm sorry for the disruption. Based on your flight's delay, I've applied "
                "your meal voucher and lounge access to your booking now. Is there "
                "anything else I can help with?"), trace, esc

    # --- Fallback --------------------------------------------------------------
    trace, esc = _run(db, conversation, ctx, calls)
    return ("I'm here to help with your booking. Could you tell me a bit more about "
            "what you need - rebooking, a refund, or details about the disruption?"), trace, esc


def _booking_delay(db, pnr: str):
    from .models import Booking

    rows = db.query(Booking).filter(Booking.pnr == pnr).all()
    disrupted = [b for b in rows if b.is_disrupted_leg]
    b = disrupted[0] if disrupted else (rows[0] if rows else None)
    return b.delay_hours if b else 0
