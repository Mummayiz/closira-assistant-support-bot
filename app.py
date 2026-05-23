"""
Closira Assistant — CLI entry point for Bloom Aesthetics Clinic AI support.
Uses Google Gemini via the google-genai SDK.

Run:
    python app.py

Environment variables (see .env.example):
    GOOGLE_API_KEY  — required
    GEMINI_MODEL    — optional, defaults to gemini-2.0-flash
"""

import io
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import google.genai as genai

# Force UTF-8 output on Windows so box-drawing chars and symbols print correctly
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv()

from agents.faq_agent import FAQAgent
from agents.qualification_agent import QualificationAgent, LeadData
from agents.escalation_agent import EscalationAgent
from agents.summary_agent import SummaryAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("closira.app")

WELCOME_BANNER = """
+----------------------------------------------------------+
|         Bloom Aesthetics Clinic                          |
|         Powered by Closira Assistant (Gemini)            |
|                                                          |
|  Type your question or 'quit' / 'exit' to end session.  |
|  Type 'summary' to generate a session summary now.      |
+----------------------------------------------------------+
"""

GREETING = (
    "Hello and welcome to Bloom Aesthetics Clinic! "
    "I'm Closira, your virtual assistant. "
    "How can I help you today?"
)

SESSION_END = (
    "\n----------------------------------------------------------\n"
    "Thank you for contacting Bloom Aesthetics Clinic. "
    "We hope to see you soon!\n"
)

FAQ_TURNS_BEFORE_QUALIFICATION = 2


class SessionState:
    def __init__(self):
        self.history: list = []
        self.faq_turns: int = 0
        self.qualification_done: bool = False
        self.escalated: bool = False
        self.escalation_status: dict = {}
        self.lead_data: LeadData = LeadData()

    def add(self, role: str, text: str) -> None:
        self.history.append({"role": role, "content": text})

    @staticmethod
    def print_confidence(confidence: float) -> None:
        filled = int(confidence * 10)
        bar = "█" * filled + "░" * (10 - filled)
        print(f"  [Confidence: {bar} {confidence:.0%}]\n")


def print_assistant(text: str) -> None:
    print(f"\nClosira: {text}\n")


def print_system(text: str) -> None:
    print(f"\n  ⚙  {text}")


def print_escalation_notice(text: str) -> None:
    print(f"\n[ESCALATION] {text}\n")


def run_session(faq: FAQAgent, qual: QualificationAgent, esc: EscalationAgent, summ: SummaryAgent) -> None:
    state = SessionState()

    print(WELCOME_BANNER)
    print_assistant(GREETING)
    state.add("assistant", GREETING)

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not user_input:
            continue

        if user_input.lower() in {"quit", "exit", "bye", "goodbye"}:
            break

        if user_input.lower() == "summary":
            _do_summary(summ, state)
            continue

        state.add("user", user_input)

        # Escalation check every turn
        esc_result = esc.check(
            message=user_input,
            conversation_history=state.history,
            unanswered_count=faq.unanswered_count,
        )

        if esc_result.get("escalated"):
            state.escalated = True
            state.escalation_status = esc_result
            print_escalation_notice(
                f"Reason: {esc_result['reason']} | Confidence: {esc_result['confidence']:.0%}"
            )
            msg = esc.escalation_message(esc_result["reason"])
            print_assistant(msg)
            state.add("assistant", msg)
            _do_summary(summ, state)
            break

        # FAQ answer
        result = faq.answer(user_input)
        print_assistant(result["response"])
        state.add("assistant", result["response"])
        state.print_confidence(result["confidence"])
        state.faq_turns += 1

        if result.get("escalate"):
            state.escalation_status = {
                "escalated": True, "reason": "out_of_scope",
                "confidence": result["confidence"],
                "summary": "FAQ could not answer from SOP.",
            }

        # Lead qualification after N FAQ turns
        if (
            state.faq_turns >= FAQ_TURNS_BEFORE_QUALIFICATION
            and not state.qualification_done
            and not state.escalated
        ):
            print_system("Starting lead qualification...\n")
            state = _run_qualification(qual, state)

    print(SESSION_END)
    if not state.escalated:
        _do_summary(summ, state)


def _run_qualification(agent: QualificationAgent, state: SessionState) -> SessionState:
    print_system("I have a few quick questions to help us serve you better.\n")

    while not agent.is_done:
        q_msg = agent.next_message(state.history)
        print_assistant(q_msg)
        state.add("assistant", q_msg)

        if agent.is_done:
            break

        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if user_input.lower() in {"quit", "exit", "bye"}:
            break

        state.add("user", user_input)

    state.lead_data = agent.extract_lead_data(state.history)
    state.qualification_done = True
    print_system(f"Lead data collected:\n{state.lead_data.to_json()}\n")
    return state


def _do_summary(agent: SummaryAgent, state: SessionState) -> None:
    print_system("Generating session summary...\n")
    summary_md = agent.generate(
        conversation_history=state.history,
        lead_data=state.lead_data.to_dict() if state.lead_data else None,
        escalation_status=state.escalation_status or None,
    )
    print("\n" + "═" * 56)
    print(summary_md)
    print("═" * 56 + "\n")
    saved = agent.save(summary_md)
    print_system(f"Summary saved → {saved}\n")


def main() -> None:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    logger.info("Starting Closira Assistant | model=%s", model_name)

    (Path(__file__).parent / "logs").mkdir(exist_ok=True)

    faq = FAQAgent(client, model_name)
    qual = QualificationAgent(client, model_name)
    esc = EscalationAgent(client, model_name)
    summ = SummaryAgent(client, model_name)

    run_session(faq, qual, esc, summ)


if __name__ == "__main__":
    main()
