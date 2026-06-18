"""LangGraph workflow: a ReAct-style budget agent over a configurable LLM.

The model is selected per-run via ``config.configurable.model``, with the
catalog of allowed model specs defined in ``models.json`` at the repo root.

Supported model spec formats (``service:model_name``):

- ``anthropic:<model>`` -> ``langchain_anthropic.ChatAnthropic`` (uses
  ``ANTHROPIC_API_KEY`` from the env).
- ``openai-compat:<model>`` -> ``langchain_openai.ChatOpenAI`` pointed at
  ``LOCAL_LLM_BASE_URL`` (default ``http://localhost:9292/v1``).

If no model is provided on a run, the catalog's ``default`` is used.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from langgraph.config import get_config
from langgraph.prebuilt import create_react_agent
from langgraph.runtime import Runtime

from agent.tools import TOOLS

_DEFAULT_BASE_URL = "http://localhost:9292/v1"
_DEFAULT_LOCAL_MODEL = "gpt-oss-20b"
_FALLBACK_DEFAULT_SPEC = "anthropic:claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a personal finance assistant.

You have tools to record, list, and summarize the user's transactions,
and to add new bank accounts and categories. All `amount` values are
positive decimals; direction comes from the transaction type ('income',
'expense', 'transfer').

Workflow for recording a transaction:
1. Extract amount, type, description, date (default today), and
   account from the user's message.
2. Call `list_categories` (filtered by the transaction's type) to see
   what already exists. Pick the best fit by name/meaning.
3. If nothing fits, propose a new category in chat and ask the user
   whether to add it. Mention that it can be either top-level OR a
   subcategory of an existing related parent (e.g. "groceries" nested
   under "food"). Once the user agrees, call `add_category`.
4. Call `record_transaction` with the chosen category. The tool will
   pause and show the user a preview for final confirmation — you do
   NOT need to ask the user to confirm in chat first. If the tool
   returns "user declined", relay that and ask what to change.

Other rules:
- ALWAYS attempt the relevant tool first. Do NOT assume an account,
  category, or transaction is missing without calling the tool. Tools
  tell you when a lookup fails.
- If `record_transaction` returns "no account with nickname X", ask
  the user whether to add it with `add_account`, and retry after they
  confirm.
- For summaries, totals are signed (expenses negative, income
  positive).
- Confirm successful writes with a short reply including the new
  row's ID and key fields. Be concise.
"""


def _models_config_path() -> Path:
    """Resolve the path to ``models.json``.

    Honors ``MODELS_CONFIG_PATH`` env var (used inside the containers,
    which mount the file at ``/app/models.json``). Falls back to a
    repo-root lookup so ``uv run`` outside docker works.
    """
    env = os.environ.get("MODELS_CONFIG_PATH")
    if env:
        return Path(env)
    # src/agent/graph.py -> repo root is parents[2]
    return Path(__file__).resolve().parents[2] / "models.json"


@lru_cache(maxsize=1)
def _default_model_spec() -> str:
    path = _models_config_path()
    try:
        data = json.loads(path.read_text())
        default = data.get("default")
        if isinstance(default, str) and default:
            return default
    except (OSError, json.JSONDecodeError):
        pass
    return _FALLBACK_DEFAULT_SPEC


# Tools-bound runnables, keyed by spec, so we don't rebuild the chat client
# (or re-bind tools) on every turn.
_MODEL_CACHE: dict[str, Runnable] = {}


def _resolve_model(spec: str) -> Runnable:
    """Instantiate (and cache) a tools-bound chat model from a spec.

    ``create_react_agent`` does NOT auto-bind tools when its ``model`` is a
    callable — the callable is contractually responsible for returning a
    runnable that already knows about the tools. We bind once per spec and
    cache the result. Without this, providers like Anthropic see no
    ``tools`` parameter and fall back to emitting tool calls as raw text
    (XML for Claude), which the ReAct loop can't dispatch.
    """
    if spec in _MODEL_CACHE:
        return _MODEL_CACHE[spec]

    if ":" not in spec:
        raise ValueError(
            f"invalid model spec {spec!r}: expected 'service:model_name'"
        )
    service, _, name = spec.partition(":")
    name = name.strip()
    if not name:
        raise ValueError(f"invalid model spec {spec!r}: missing model name")

    model: BaseChatModel
    if service == "anthropic":
        # Imported lazily so module import never triggers Anthropic SDK setup
        # when only the local backend is in use.
        from langchain_anthropic import ChatAnthropic

        model = ChatAnthropic(model=name, temperature=0)
    elif service == "openai-compat":
        model = ChatOpenAI(
            base_url=os.environ.get("LOCAL_LLM_BASE_URL", _DEFAULT_BASE_URL),
            api_key=os.environ.get("LOCAL_LLM_API_KEY", "not-needed"),
            model=name or os.environ.get("LOCAL_LLM_MODEL", _DEFAULT_LOCAL_MODEL),
            temperature=0,
        )
    else:
        raise ValueError(f"unknown model service {service!r} in spec {spec!r}")

    bound = model.bind_tools(TOOLS)
    _MODEL_CACHE[spec] = bound
    return bound


def _spec_from_config() -> str:
    """Read the per-run model spec from ``config.configurable.model``."""
    try:
        cfg = get_config()
    except RuntimeError:
        return _default_model_spec()
    configurable: dict[str, Any] = cfg.get("configurable") or {}
    spec = configurable.get("model")
    if isinstance(spec, str) and spec.strip():
        return spec.strip()
    return _default_model_spec()


def _select_model(_state: Any, _runtime: Runtime[Any]) -> Runnable:
    """Per-run model selector passed to ``create_react_agent``.

    Signature ``Callable[[StateSchema, Runtime[ContextT]], Runnable]``,
    which is what langgraph 1.2.5's ``create_react_agent`` accepts. The
    per-run model id is supplied by the caller as
    ``config.configurable.model`` and is read via ``get_config()``
    because the ``Runtime`` object does not expose ``config`` directly
    (per the langgraph docs). The returned runnable is already bound to
    ``TOOLS`` — see ``_resolve_model`` for why that's mandatory.
    """
    return _resolve_model(_spec_from_config())


graph = create_react_agent(
    _select_model,
    tools=TOOLS,
    prompt=SYSTEM_PROMPT,
    name="budget-agent",
)
