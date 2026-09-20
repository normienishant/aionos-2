"""Deterministic safety guard (runs BEFORE and AFTER the LLM, every turn).

The brief says threats of legal action or formal complaints must be escalated
IMMEDIATELY - so we do not rely on the LLM noticing: a keyword detector flags
it deterministically, the agent loop is told it MUST call escalate_to_human,
and if the model still fails to, the guard escalates server-side itself.
"""
import re

LEGAL_THREAT_PATTERNS = [
    r"\blegal action\b",
    r"\blawyer\b",
    r"\bsue\b",
    r"\blawsuit\b",
    r"\bconsumer (court|forum|comission|commission)\b",
    r"\bformal complaint\b",
    r"\bwrite to (the )?(dgca|ministry|consumer)\b",
    r"\btribunal\b",
]

INJECTION_PATTERNS = [
    r"ignore (all |your )?(previous |prior )?instructions",
    r"you are now (an?|the) .*(without|no) (rules|restrictions)",
    r"pretend (you are|to be) (a|an) (human|agent) without (any )?polic",
    r"developer mode",
]


def _scan(text: str, patterns: list[str]) -> bool:
    lowered = (text or "").lower()
    return any(re.search(p, lowered) for p in patterns)


def detect_legal_threat(text: str) -> bool:
    return _scan(text, LEGAL_THREAT_PATTERNS)


def detect_injection(text: str) -> bool:
    return _scan(text, INJECTION_PATTERNS)
