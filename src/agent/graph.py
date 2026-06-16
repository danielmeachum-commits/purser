"""LangGraph workflow: a ReAct-style budget agent over a local LLM.

Defaults to llama-swap on http://localhost:9292/v1 serving `gpt-oss-20b`.
Override via `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_MODEL`, `LOCAL_LLM_API_KEY`.
"""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agent.tools import TOOLS

_DEFAULT_BASE_URL = "http://localhost:9292/v1"
_DEFAULT_MODEL = "gpt-oss-20b"

SYSTEM_PROMPT = """You are a personal finance assistant.

You have tools to record, list, and summarize the user's transactions,
and to add new bank accounts and categories. All `amount` values are
positive decimals; direction comes from the transaction type ('income',
'expense', 'transfer').

Rules:
- ALWAYS attempt the relevant tool first. Do NOT assume an account,
  category, or transaction is missing without calling the tool. The
  tools will tell you if a lookup failed.
- For recording: extract amount, type, description, date (default
  today), category, and account from the user's message, then call
  record_transaction. If the tool returns "no account with nickname X"
  or "no ... category named X", THEN ask the user whether to add it
  with add_account or add_category, and after they confirm, add it and
  retry record_transaction.
- For summaries, totals are signed (expenses negative, income positive).
- Confirm successful writes with a short reply including the new row's
  ID and key fields. Be concise.
"""


def _make_model() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=os.environ.get("LOCAL_LLM_BASE_URL", _DEFAULT_BASE_URL),
        api_key=os.environ.get("LOCAL_LLM_API_KEY", "not-needed"),
        model=os.environ.get("LOCAL_LLM_MODEL", _DEFAULT_MODEL),
        temperature=0,
    )


graph = create_react_agent(
    _make_model(),
    tools=TOOLS,
    prompt=SYSTEM_PROMPT,
    name="budget-agent",
)
