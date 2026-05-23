"""
Summary Agent — generates a structured end-of-session report using google-genai.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import google.genai as genai
from google.genai import types

from utils.prompts import SUMMARY_SYSTEM_PROMPT, SUMMARY_GENERATION_PROMPT

logger = logging.getLogger(__name__)


class SummaryAgent:
    def __init__(self, client: genai.Client, model_name: str):
        self.client = client
        self.model_name = model_name

    def generate(
        self,
        conversation_history: list,
        lead_data: Optional[dict] = None,
        escalation_status: Optional[dict] = None,
    ) -> str:
        history_text = "\n".join(
            f"**{m['role'].upper()}:** {m['content']}" for m in conversation_history
        )
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prompt = SUMMARY_GENERATION_PROMPT.format(
            conversation=history_text,
            lead_data=json.dumps(lead_data or {}, indent=2),
            escalation_status=json.dumps(escalation_status or {"escalated": False, "reason": "none"}, indent=2),
            timestamp=timestamp,
        )
        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SUMMARY_SYSTEM_PROMPT,
                    max_output_tokens=800,
                ),
            )
            return resp.text.strip()
        except Exception as exc:
            logger.error("Summary generation failed: %s", exc)
            return self._fallback_summary(lead_data, escalation_status, timestamp)

    def save(self, summary: str, filename: Optional[str] = None) -> Path:
        transcripts_dir = Path(__file__).parent.parent / "transcripts"
        transcripts_dir.mkdir(exist_ok=True)
        if filename is None:
            filename = f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        out_path = transcripts_dir / filename
        out_path.write_text(summary, encoding="utf-8")
        return out_path

    @staticmethod
    def _fallback_summary(lead_data, escalation_status, timestamp) -> str:
        escalated = (escalation_status or {}).get("escalated", False)
        reason = (escalation_status or {}).get("reason", "n/a")
        lead_section = "\n".join(
            f"- **{k}:** {v}" for k, v in (lead_data or {}).items() if v is not None
        ) or "— No lead data collected —"
        return f"""## Session Summary — Bloom Aesthetics Clinic

**Date/Time:** {timestamp}

### Key Details Collected
{lead_section}

### Escalation Status
- Escalated: {"Yes" if escalated else "No"}
- Reason: {reason}

### Recommended Next Action
{"Human agent follow-up required." if escalated else "No immediate action required."}
"""
