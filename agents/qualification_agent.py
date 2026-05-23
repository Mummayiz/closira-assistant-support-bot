"""
Qualification Agent — collects structured lead data using google-genai.
"""

import json
import logging
import re
from dataclasses import dataclass, asdict
from typing import Optional

import google.genai as genai
from google.genai import types

from utils.prompts import QUALIFICATION_SYSTEM_PROMPT, QUALIFICATION_EXTRACT_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class LeadData:
    treatment_interest: Optional[str] = None
    returning_customer: Optional[bool] = None
    preferred_day: Optional[str] = None
    preferred_contact: Optional[str] = None
    additional_notes: Optional[str] = None

    def is_complete(self) -> bool:
        return all([
            self.treatment_interest is not None,
            self.returning_customer is not None,
            self.preferred_day is not None,
            self.preferred_contact is not None,
        ])

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class QualificationAgent:
    QUESTIONS = [
        "Which treatment are you most interested in? We offer Botox (from £200), Fillers (from £250), or a free initial Consultation.",
        "Have you visited Bloom Aesthetics Clinic before?",
        "Which day or time of week would work best for you?",
        "What is your preferred way to get in touch — WhatsApp or our website?",
    ]

    def __init__(self, client: genai.Client, model_name: str):
        self.client = client
        self.model_name = model_name
        self.lead_data = LeadData()
        self._done = False
        self._history: list[types.Content] = []

    @property
    def is_done(self) -> bool:
        return self._done

    def next_message(self, conversation_history: list) -> str:
        if self._done:
            return "Thank you — I have all the information I need. We look forward to seeing you!"

        self._try_update_from_history(conversation_history)

        if self.lead_data.is_complete():
            self._done = True
            return "Wonderful — I have all the details I need. A member of our team will be in touch to confirm your booking."

        question = self._next_unanswered_question()
        if question is None:
            self._done = True
            return "Brilliant, thank you! We have everything we need and will be in touch shortly."

        return self._rephrase(question)

    def extract_lead_data(self, conversation_history: list) -> LeadData:
        history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in conversation_history)
        prompt = QUALIFICATION_EXTRACT_PROMPT.format(conversation=history_text)
        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=300),
            )
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.text.strip(), flags=re.MULTILINE).strip()
            data = json.loads(raw)
            self.lead_data.treatment_interest = data.get("treatment_interest")
            self.lead_data.returning_customer = data.get("returning_customer")
            self.lead_data.preferred_day = data.get("preferred_day")
            self.lead_data.preferred_contact = data.get("preferred_contact")
            self.lead_data.additional_notes = data.get("additional_notes")
        except Exception as exc:
            logger.error("Lead extraction failed: %s", exc)
        return self.lead_data

    def _next_unanswered_question(self) -> Optional[str]:
        slots = [
            (self.lead_data.treatment_interest, self.QUESTIONS[0]),
            (self.lead_data.returning_customer, self.QUESTIONS[1]),
            (self.lead_data.preferred_day, self.QUESTIONS[2]),
            (self.lead_data.preferred_contact, self.QUESTIONS[3]),
        ]
        for value, question in slots:
            if value is None:
                return question
        return None

    def _rephrase(self, base_question: str) -> str:
        try:
            prompt = (
                f"Ask the customer the following question naturally in one or two friendly sentences. "
                f"Do not add extra questions. Question: {base_question}"
            )
            self._history.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=self._history,
                config=types.GenerateContentConfig(
                    system_instruction=QUALIFICATION_SYSTEM_PROMPT,
                    max_output_tokens=150,
                ),
            )
            reply = resp.text.strip()
            self._history.append(types.Content(role="model", parts=[types.Part(text=reply)]))
            return reply
        except Exception as exc:
            logger.warning("Rephrasing failed: %s", exc)
            return base_question

    def _try_update_from_history(self, conversation_history: list) -> None:
        if len(conversation_history) >= 3:
            self.extract_lead_data(conversation_history)
