"""
SOP Loader — reads and exposes Bloom Aesthetics Clinic SOP data.
All agent modules import from here so SOP truth lives in one place.
"""

import json
import os
from pathlib import Path


def load_sop() -> dict:
    """Load SOP JSON from disk and return as a dict."""
    sop_path = Path(__file__).parent.parent / "sop_data" / "bloom_clinic.json"
    with open(sop_path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_sop_for_prompt(sop: dict) -> str:
    """
    Render the SOP dict into a plain-text block that can be injected
    verbatim into any system prompt.
    """
    services = "\n".join(
        f"  - {s['name']}: from £{s['price_from']} — {s['description']}"
        for s in sop["services"]
    )

    hours_lines = "\n".join(
        f"  {day.capitalize()}: {time}"
        for day, time in sop["hours"].items()
    )

    booking_methods = ", ".join(sop["booking"]["methods"])

    return f"""
=== BLOOM AESTHETICS CLINIC — OFFICIAL SOP ===

Business: {sop['business']['name']}
Tagline: {sop['business']['tagline']}

OPENING HOURS:
{hours_lines}

SERVICES & PRICING:
{services}

BOOKING:
  - Book via: {booking_methods}
  - Cancellation policy: {sop['booking']['cancellation_policy']}

ESCALATION — You MUST escalate if:
  - Customer makes a complaint
  - Customer asks a medical question
  - Customer attempts to negotiate pricing
  - More than 2 questions go unanswered
  - Customer is angry or frustrated
  - Customer explicitly requests a human agent
  - Question is entirely outside the above SOP

STRICT RULE: Never invent, assume, or guess any information not listed above.
If a question cannot be answered from this SOP, say so clearly and escalate.
==============================================
""".strip()


# Convenience singleton loaded once at import time
SOP = load_sop()
SOP_TEXT = format_sop_for_prompt(SOP)
