"""
Escalation Agent — rule-based + LLM escalation detection using google-genai.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import google.genai as genai
from google.genai import types

from utils.prompts import ESCALATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_COMPLAINT_KEYWORDS = [
    "complaint", "complain", "unhappy", "disappointed", "terrible",
    "awful", "unacceptable", "ridiculous", "worst", "never coming back", "sue",
]
_MEDICAL_KEYWORDS = [
    "allergy", "allergic", "medication", "pregnant", "pregnancy",
    "breastfeed", "blood thinner", "side effect", "contraindication",
    "medical condition", "doctor", "gp", "infection", "reaction",
]
_NEGOTIATION_KEYWORDS = [
    "discount", "cheaper", "lower the price", "price match", "negotiate",
    "can you do it for", "best price", "any deals", "reduce the cost", "too expensive",
]
_HUMAN_KEYWORDS = [
    "speak to a human", "talk to someone", "real person", "human agent",
    "speak to a person", "call me", "manager", "supervisor", "transfer me",
]
_ANGER_KEYWORDS = [
    "furious", "outraged", "livid", "so angry", "pissed off", "fed up",
    "this is a joke", "incompetent", "useless", "absolutely furious",
]


def _rule_check(message: str) -> Optional[dict]:
    msg = message.lower()
    checks = [
        (_COMPLAINT_KEYWORDS, "complaint", 0.85),
        (_MEDICAL_KEYWORDS, "medical_question", 0.90),
        (_NEGOTIATION_KEYWORDS, "pricing_negotiation", 0.85),
        (_HUMAN_KEYWORDS, "human_requested", 0.95),
        (_ANGER_KEYWORDS, "angry_customer", 0.80),
    ]
    for keywords, reason, confidence in checks:
        if any(kw in msg for kw in keywords):
            return {"escalated": True, "reason": reason, "confidence": confidence,
                    "summary": f"Rule match: {reason}."}
    return None


def _log_escalation(result: dict, message: str) -> None:
    log_path = Path(__file__).parent.parent / "logs" / "escalation_logs.json"
    log_path.parent.mkdir(exist_ok=True)
    log_data = []
    if log_path.exists() and log_path.stat().st_size > 2:
        with open(log_path, "r", encoding="utf-8") as f:
            log_data = json.load(f)
    log_data.append({"timestamp": datetime.now().isoformat(), "trigger_message": message[:300], **result})
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)


class EscalationAgent:
    def __init__(self, client: genai.Client, model_name: str):
        self.client = client
        self.model_name = model_name

    def check(self, message: str, conversation_history: list, unanswered_count: int = 0) -> dict:
        if unanswered_count > 2:
            result = {"escalated": True, "reason": "out_of_scope", "confidence": 1.0,
                      "summary": f"{unanswered_count} questions unanswered."}
            _log_escalation(result, message)
            return result

        result = _rule_check(message)
        if result:
            _log_escalation(result, message)
            return result

        result = self._llm_check(message, conversation_history)
        if result.get("escalated"):
            _log_escalation(result, message)
        return result

    def _llm_check(self, message: str, conversation_history: list) -> dict:
        history_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in conversation_history[-6:]
        )
        prompt = f"Recent conversation:\n{history_text}\n\nLatest message: {message}"
        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=ESCALATION_SYSTEM_PROMPT,
                    max_output_tokens=200,
                ),
            )
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.text.strip(), flags=re.MULTILINE).strip()
            return json.loads(raw)
        except Exception as exc:
            logger.warning("LLM escalation check failed: %s", exc)
            return {"escalated": False, "reason": "none", "confidence": 0.5, "summary": "Check failed."}

    def escalation_message(self, reason: str) -> str:
        base = (
            "I'd like to make sure you receive the best possible support. "
            "I'm connecting you with a member of the Bloom Aesthetics Clinic team right now. "
        )
        addenda = {
            "medical_question": "For medical questions, one of our qualified practitioners will advise you directly.",
            "complaint": "I'm sorry to hear you've had a frustrating experience. Our team will be in touch as soon as possible.",
            "pricing_negotiation": "A team member will be able to discuss your options in more detail.",
            "angry_customer": "I'm sorry you feel this way — a member of our team will reach out to resolve this promptly.",
            "human_requested": "Of course — someone from the clinic will be with you shortly.",
            "out_of_scope": "I don't have enough information to help fully, so a team member will follow up with you.",
        }
        return base + addenda.get(reason, "Our team will be in touch shortly.")
