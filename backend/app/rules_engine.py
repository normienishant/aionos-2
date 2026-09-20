"""DETERMINISTIC RULES ENGINE.

Encodes the 5 service rules from the data pack as pure, testable functions.
The LLM NEVER computes compensation amounts or entitlements itself - it calls
these functions as tools, so every decision is consistent and auditable.

Rule index (policy_reference strings used throughout the audit log):
  R1 Cancellation Rebooking Rule
  R2 Delay Compensation Rule
  R3 Refund Processing Rule
  R4 Fare Difference Rule
  R5 Loyalty Tier Rule
"""
from dataclasses import dataclass, field
from typing import Optional

# --- Rule constants (from the data pack - verbatim) -------------------------
MEAL_VOUCHER_AMOUNT = 500          # R2: under 3h -> Rs.500 meal voucher
LOUNGE_THRESHOLD_H = 3             # R2: more than 3h -> + lounge access
HOTEL_THRESHOLD_H = 5              # R2: more than 5h -> + hotel (delayed hours only)
FARE_WAIVER_AGENT_LIMIT = 1500     # R4: agents cannot waive above Rs.1,500
REFUND_WINDOW_BUSINESS_DAYS = 7    # R3: refunds within 7 business days
PRIORITY_TIERS = ("Gold", "Platinum")  # R5: priority rebooking tiers

# Escalation triggers (PROHIBITED ACTIONS list)
ESCALATION_REASONS = {
    "over_policy_compensation": "Compensation beyond stated policy amounts",
    "fare_waiver_over_limit": "Fare difference waiver above Rs.1,500",
    "non_airline_exception": "Exception for non-airline-caused disruption",
    "legal_or_formal_complaint": "Threat of legal action or formal complaint",
    "refund_different_method": "Refund to a payment method other than the original",
}


@dataclass
class Compensation:
    """Result bundle returned by get_delay_compensation."""

    delay_hours: float
    meal_voucher: bool = False
    meal_voucher_amount: int = 0
    lounge_access: bool = False
    hotel_delayed_hours_only: bool = False
    hotel_hours: float = 0.0
    hotel_full_night: bool = False  # ALWAYS False - policy covers delayed hours only
    policy_reference: str = "R2 Delay Compensation Rule"
    notes: list[str] = field(default_factory=list)


def get_delay_compensation(hours: float) -> Compensation:
    """R2 Delay Compensation Rule (deterministic).

    - under 3h        : Rs.500 meal voucher
    - more than 3h    : meal voucher + lounge access
    - more than 5h    : meal voucher + lounge + hotel for the DELAYED HOURS ONLY
    Exactly 3h counts as "not more than 3" (voucher only); exactly 5h counts as
    "not more than 5" (voucher + lounge). Stated in README assumptions.
    """
    h = float(hours)
    c = Compensation(delay_hours=h)
    c.meal_voucher = True  # every delayed customer gets the voucher
    c.meal_voucher_amount = MEAL_VOUCHER_AMOUNT
    if h > LOUNGE_THRESHOLD_H:
        c.lounge_access = True
    if h > HOTEL_THRESHOLD_H:
        c.hotel_delayed_hours_only = True
        c.hotel_hours = h
        c.notes.append(
            f"Hotel covers ONLY the {h:g} delayed hours - NOT a full night's stay."
        )
    return c


def check_fare_waiver_allowed(amount: float) -> dict:
    """R4 Fare Difference Rule (deterministic).

    Agents may waive fare differences up to and including Rs.1,500.
    Above Rs.1,500 requires supervisor approval -> escalate.
    """
    amt = float(amount)
    allowed = amt <= FARE_WAIVER_AGENT_LIMIT
    return {
        "amount": amt,
        "agent_waiver_limit": FARE_WAIVER_AGENT_LIMIT,
        "allowed_without_supervisor": allowed,
        "requires_supervisor_approval": not allowed,
        "must_escalate": not allowed,
        "policy_reference": "R4 Fare Difference Rule",
    }


def get_loyalty_benefits(tier: str) -> dict:
    """R5 Loyalty Tier Rule (deterministic). Gold/Platinum: priority rebooking,
    NO additional compensation beyond standard policy."""
    tier = (tier or "").strip().title()
    priority = tier in PRIORITY_TIERS
    return {
        "tier": tier,
        "priority_rebooking": priority,
        "additional_compensation_beyond_policy": False,  # R5: never
        "policy_reference": "R5 Loyalty Tier Rule",
    }


def is_priority_tier(tier: str) -> bool:
    return (tier or "").strip().title() in PRIORITY_TIERS


def refund_terms(original_payment_method: str) -> dict:
    """R3 Refund Processing Rule (deterministic).

    Airline-caused cancellations: full refund within 7 business days to the
    ORIGINAL payment method ONLY. Any other method -> escalate, do not process.
    """
    return {
        "full_refund": True,
        "window_business_days": REFUND_WINDOW_BUSINESS_DAYS,
        "allowed_payment_methods": [original_payment_method],
        "other_methods_allowed": False,
        "policy_reference": "R3 Refund Processing Rule",
    }


def check_refund_method_allowed(requested_method: str, original_payment_method: str) -> dict:
    """Deterministic check for R3: refunds go to the ORIGINAL method only."""
    ok = (requested_method or "").strip().lower() == (original_payment_method or "").strip().lower()
    return {
        "requested_method": requested_method,
        "original_payment_method": original_payment_method,
        "allowed": ok,
        "must_escalate_if_different": not ok,
        "policy_reference": "R3 Refund Processing Rule",
    }


def cancellation_entitlement() -> dict:
    """R1 Cancellation Rebooking Rule (deterministic).

    Airline-caused cancellation -> customer's CHOICE of:
      a) free rebooking on next available flight within 24 hours, or
      b) full refund.
    """
    return {
        "options": ["free_rebooking_within_24h", "full_refund"],
        "customer_choice_required": True,
        "rebooking_charge": 0,
        "rebooking_window_hours": 24,
        "policy_reference": "R1 Cancellation Rebooking Rule",
    }


def validate_rebooking(
    booking_status: str,
    flight_found: bool,
    hours_after_original: Optional[float],
    tier: str,
    target_fare_delta: float = 0.0,
) -> dict:
    """Deterministic pre-check used by execute_rebooking.

    - Only airline-caused cancellations qualify (R1).
    - New flight must depart within 24h of the original (R1).
    - Gold/Platinum get priority access to seats (R5) - flag passed through.
    - A higher-fare target on a NON-airline-caused change triggers R4 fare
      difference handling.
    """
    reasons: list[str] = []
    ok = True

    cancelled = "cancel" in (booking_status or "").lower()
    if not cancelled:
        ok = False
        reasons.append("Booking is not cancelled - free rebooking does not apply (R1).")

    if not flight_found:
        ok = False
        reasons.append("Requested flight not found in inventory for this route.")

    if hours_after_original is not None and hours_after_original > 24:
        ok = False
        reasons.append("Requested flight departs more than 24h after original - outside R1 window.")

    return {
        "allowed": ok,
        "violations": reasons,
        "priority_rebooking_applied": is_priority_tier(tier),
        "fare_difference_due": max(0.0, float(target_fare_delta)),
        "policy_reference": "R1 Cancellation Rebooking Rule / R5 Loyalty Tier Rule",
    }


def classify_disruption(status: str) -> str:
    """Map a booking status to a disruption class used by the agent prompt."""
    s = (status or "").lower()
    if "cancel" in s:
        return "cancelled"
    if "delay" in s:
        return "delayed"
    return "unaffected"
