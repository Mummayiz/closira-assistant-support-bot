"""
FAQ Agent — answers customer questions strictly from the Bloom Aesthetics SOP.
Uses google-genai SDK (google.genai).
"""

import json
import logging
import re
from typing import Optional

import google.genai as genai
from google.genai import types

from utils.prompts import FAQ_SYSTEM_PROMPT, FAQ_CLASSIFICATION_PROMPT

logger = logging.getLogger(__name__)

_OUT_OF_SCOPE_TOPICS = frozenset([
    "laser", "chemical peel", "microneedling", "hifu", "prp",
    "surgery", "thread lift", "iv drip", "teeth whitening",
])


def _parse_json(text: str) -> Optional[dict]:
    # Strip markdown fences
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()
    # Try full parse first
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    # Extract first {...} block in case model added surrounding text
    match = re.search(r"\{[^{}]+\}", clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    logger.warning("JSON parse failed: %s", clean[:200])
    return None


class FAQAgent:
    """Two-step FAQ: classify → answer. SOP grounded via system instruction."""

    def __init__(self, client: genai.Client, model_name: str):
        self.client = client
        self.model_name = model_name
        self.unanswered_count = 0
        # Maintain conversation history manually for context
        self._history: list[types.Content] = []

    def answer(self, message: str) -> dict:
        if self._is_obviously_out_of_scope(message):
            self.unanswered_count += 1
            return self._out_of_scope_result("out_of_scope", 0.95)

        classification = self._classify(message)
        answerable = classification.get("answerable", True)
        topic = classification.get("topic", "unknown")
        confidence = float(classification.get("confidence", 0.5))

        if not answerable or confidence < 0.45:
            self.unanswered_count += 1
            return self._out_of_scope_result(topic, confidence)

        try:
            # Add user message to history
            self._history.append(types.Content(
                role="user",
                parts=[types.Part(text=message)]
            ))
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=self._history,
                config=types.GenerateContentConfig(
                    system_instruction=FAQ_SYSTEM_PROMPT,
                    max_output_tokens=400,
                )
            )
            answer_text = response.text.strip()
            # Add assistant reply to history
            self._history.append(types.Content(
                role="model",
                parts=[types.Part(text=answer_text)]
            ))
        except Exception as exc:
            logger.error("Answer generation failed: %s", exc)
            answer_text = (
                "I'm experiencing a technical issue right now. "
                "Please try again or contact us directly via WhatsApp."
            )

        return {
            "response": answer_text,
            "answerable": True,
            "topic": topic,
            "confidence": confidence,
            "escalate": False,
            "unanswered_count": self.unanswered_count,
        }

    def _classify(self, message: str) -> dict:
        prompt = FAQ_CLASSIFICATION_PROMPT.format(message=message)
        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=150),
            )
            return _parse_json(resp.text) or {"answerable": True, "topic": "unknown", "confidence": 0.5}
        except Exception as exc:
            logger.error("Classification failed: %s", exc)
            return {"answerable": True, "topic": "unknown", "confidence": 0.5}

    def _is_obviously_out_of_scope(self, message: str) -> bool:
        return any(kw in message.lower() for kw in _OUT_OF_SCOPE_TOPICS)

    @staticmethod
    def _out_of_scope_result(topic: str, confidence: float) -> dict:
        return {
            "response": (
                "I'm sorry, I don't have information about that in our current records. "
                "Let me connect you with a member of our team who can help."
            ),
            "answerable": False,
            "topic": topic,
            "confidence": confidence,
            "escalate": True,
            "unanswered_count": 0,
        }

    def reset(self) -> None:
        self.unanswered_count = 0
        self._history = []
