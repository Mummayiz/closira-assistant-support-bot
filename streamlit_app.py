"""
Closira Assistant — Streamlit browser UI for Bloom Aesthetics Clinic.

Run:
    streamlit run streamlit_app.py
"""

import os
import json
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
import google.genai as genai

load_dotenv()

from agents.faq_agent import FAQAgent
from agents.qualification_agent import QualificationAgent, LeadData
from agents.escalation_agent import EscalationAgent
from agents.summary_agent import SummaryAgent

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Closira — Bloom Aesthetics Clinic",
    page_icon="🌸",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state initialisation (runs once per browser session)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helpers  (defined before init_session so they can be called inside it)
# ---------------------------------------------------------------------------

FAQ_TURNS_BEFORE_QUAL = 2


def _add_message(role: str, content: str):
    st.session_state.messages.append({"role": role, "content": content})
    if role in ("user", "assistant"):
        st.session_state.history.append({"role": role, "content": content})


def init_session():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        st.error("GOOGLE_API_KEY not set. Add it to your .env file.")
        st.stop()

    client = genai.Client(api_key=api_key)
    model  = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    st.session_state.client          = client
    st.session_state.model           = model
    st.session_state.faq_agent       = FAQAgent(client, model)
    st.session_state.qual_agent      = QualificationAgent(client, model)
    st.session_state.esc_agent       = EscalationAgent(client, model)
    st.session_state.summ_agent      = SummaryAgent(client, model)

    st.session_state.messages        = []
    st.session_state.history         = []
    st.session_state.faq_turns       = 0
    st.session_state.qual_done       = False
    st.session_state.escalated       = False
    st.session_state.escalation      = {}
    st.session_state.lead_data       = LeadData()
    st.session_state.summary_md      = None
    st.session_state.last_confidence = None
    st.session_state.qual_pending    = False
    st.session_state.initialized     = True

    greeting = (
        "Hello and welcome to Bloom Aesthetics Clinic! "
        "I'm Closira, your virtual assistant. "
        "How can I help you today?"
    )
    _add_message("assistant", greeting)


if "initialized" not in st.session_state:
    init_session()


def _process_user_message(user_input: str):
    """Core workflow: escalation → FAQ → qualification."""
    s = st.session_state

    if s.escalated:
        _add_message("system", "This session has been escalated. Please wait for a team member.")
        return

    _add_message("user", user_input)

    # ── Escalation check ────────────────────────────────────────────────
    esc = s.esc_agent.check(
        message=user_input,
        conversation_history=s.history,
        unanswered_count=s.faq_agent.unanswered_count,
    )

    if esc.get("escalated"):
        s.escalated     = True
        s.escalation    = esc
        esc_msg = s.esc_agent.escalation_message(esc["reason"])
        _add_message("assistant", esc_msg)
        _add_message("system", f"🔔 Escalated — Reason: **{esc['reason']}** | Confidence: {esc['confidence']:.0%}")
        _generate_summary()
        return

    # ── Qualification follow-up (if we're mid-qual) ──────────────────────
    if s.qual_pending and not s.qual_done:
        _continue_qualification(user_input)
        return

    # ── FAQ answer ───────────────────────────────────────────────────────
    result = s.faq_agent.answer(user_input)
    _add_message("assistant", result["response"])
    s.last_confidence = result["confidence"]
    s.faq_turns += 1

    if result.get("escalate"):
        s.escalation = {
            "escalated": True, "reason": "out_of_scope",
            "confidence": result["confidence"],
            "summary": "FAQ could not answer from SOP.",
        }

    # ── Start qualification after N FAQ turns ────────────────────────────
    if s.faq_turns >= FAQ_TURNS_BEFORE_QUAL and not s.qual_done:
        _start_qualification()


def _start_qualification():
    s = st.session_state
    _add_message("system", "Starting lead qualification — a few quick questions to help us serve you better.")
    q_msg = s.qual_agent.next_message(s.history)
    _add_message("assistant", q_msg)
    s.qual_pending = True


def _continue_qualification(user_input: str):
    s = st.session_state
    if s.qual_agent.is_done:
        s.qual_done    = True
        s.qual_pending = False
        s.lead_data    = s.qual_agent.extract_lead_data(s.history)
        _add_message("system", "Lead qualification complete.")
        return

    q_msg = s.qual_agent.next_message(s.history)
    _add_message("assistant", q_msg)

    if s.qual_agent.is_done:
        s.qual_done    = True
        s.qual_pending = False
        s.lead_data    = s.qual_agent.extract_lead_data(s.history)
        _add_message("system", "Lead qualification complete.")


def _generate_summary():
    s = st.session_state
    summary = s.summ_agent.generate(
        conversation_history=s.history,
        lead_data=s.lead_data.to_dict(),
        escalation_status=s.escalation or None,
    )
    s.summary_md = summary
    saved = s.summ_agent.save(summary)
    _add_message("system", f"Session summary generated and saved to `{saved.name}`.")


def _reset_session():
    for key in list(st.session_state.keys()):
        del st.session_state[key]


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image("https://placehold.co/300x80/f9a8d4/581c87?text=Bloom+Aesthetics&font=playfair-display", use_container_width=True)
    st.markdown("## Closira Assistant")
    st.caption(f"Model: `{st.session_state.model}`")
    st.divider()

    # Session status
    if st.session_state.escalated:
        st.error("🔔 Session Escalated")
        esc = st.session_state.escalation
        st.markdown(f"**Reason:** {esc.get('reason', '—')}")
        st.markdown(f"**Confidence:** {esc.get('confidence', 0):.0%}")
    else:
        st.success("✅ Session Active")

    # Last answer confidence
    if st.session_state.last_confidence is not None:
        st.divider()
        st.markdown("**Last Answer Confidence**")
        st.progress(st.session_state.last_confidence)
        st.caption(f"{st.session_state.last_confidence:.0%}")

    # Lead data
    st.divider()
    st.markdown("**Lead Data Collected**")
    lead = st.session_state.lead_data
    fields = {
        "Treatment": lead.treatment_interest,
        "Returning": str(lead.returning_customer) if lead.returning_customer is not None else None,
        "Preferred day": lead.preferred_day,
        "Contact": lead.preferred_contact,
    }
    any_data = False
    for label, value in fields.items():
        if value:
            st.markdown(f"- **{label}:** {value}")
            any_data = True
    if not any_data:
        st.caption("Not collected yet")

    # Stats
    st.divider()
    st.markdown("**Session Stats**")
    st.markdown(f"- Messages: **{len(st.session_state.messages)}**")
    st.markdown(f"- FAQ turns: **{st.session_state.faq_turns}**")
    st.markdown(f"- Unanswered: **{st.session_state.faq_agent.unanswered_count}**")
    st.markdown(f"- Qual done: **{'Yes' if st.session_state.qual_done else 'No'}**")

    st.divider()

    # Actions
    if st.button("📋 Generate Summary", use_container_width=True, disabled=st.session_state.summary_md is not None):
        _generate_summary()
        st.rerun()

    if st.button("🔄 New Session", use_container_width=True):
        _reset_session()
        st.rerun()

# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------

st.markdown("## 🌸 Bloom Aesthetics Clinic — AI Support")
st.caption("Powered by Closira Assistant · Gemini AI · Ask about our services, prices, or booking.")
st.divider()

# Render all messages
for msg in st.session_state.messages:
    role = msg["role"]

    if role == "system":
        st.info(msg["content"], icon="ℹ️")

    elif role == "user":
        with st.chat_message("user", avatar="🧑"):
            st.markdown(msg["content"])

    elif role == "assistant":
        with st.chat_message("assistant", avatar="🌸"):
            st.markdown(msg["content"])

# Summary panel (shown inline when generated)
if st.session_state.summary_md:
    st.divider()
    with st.expander("📋 Session Summary", expanded=True):
        st.markdown(st.session_state.summary_md)
        st.download_button(
            label="Download Summary",
            data=st.session_state.summary_md,
            file_name=f"closira_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
        )

# Chat input (disabled after escalation)
placeholder = (
    "Session escalated — please wait for our team."
    if st.session_state.escalated
    else "Type your message here…"
)

if prompt := st.chat_input(placeholder, disabled=st.session_state.escalated):
    _process_user_message(prompt)
    st.rerun()
