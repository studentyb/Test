"""Token ledger (plan item E0-1): one row per LLM stage execution.

Rows are appended to $CMATG_LEDGER (default memory/token_ledger.jsonl). Usage is
the difference of the shared CrewAI LLM object's cumulative counters before and
after the stage, so it does not depend on what the Crew result object exposes
(streaming results carry no usage). Direct OpenAI-client calls (experience
summaries, code-context selection) are recorded by utils/chat.py with their own
stage names. Context (project, feature, task sequence number) is set by the
runner through set_context().
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

STAGES = ("plan", "mr_generate", "mr_review", "mr_fix", "design", "develop", "repair")
_CONTEXT: dict = {}


def ledger_path() -> Path:
    return Path(os.environ.get("CMATG_LEDGER") or Path(__file__).resolve().parents[1] / "memory" / "token_ledger.jsonl")


def set_context(**kwargs) -> None:
    _CONTEXT.update(kwargs)


def get_context() -> dict:
    return dict(_CONTEXT)


def llm_counters(llm) -> dict:
    try:
        s = llm.get_token_usage_summary()
        return {"prompt_tokens": int(getattr(s, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(s, "completion_tokens", 0) or 0),
                "cached_prompt_tokens": int(getattr(s, "cached_prompt_tokens", 0) or 0),
                "requests": int(getattr(s, "successful_requests", 0) or 0)}
    except Exception:
        return {}


def write_row(stage: str, prompt, completion, **extra) -> None:
    row = {"stage": stage, "prompt_tokens": prompt, "completion_tokens": completion, **extra,
           **_CONTEXT, "recorded_at": datetime.now(timezone.utc).isoformat()}
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + chr(10))


def record_delta(stage: str, llm, before: dict, started: float, result=None) -> None:
    after = llm_counters(llm)
    seconds = round(time.time() - started, 2)
    if after:
        d = {k: after.get(k, 0) - before.get(k, 0) for k in after}
        if d.get("prompt_tokens") or d.get("completion_tokens") or d.get("requests"):
            write_row(stage, d["prompt_tokens"], d["completion_tokens"],
                      cached_prompt_tokens=d["cached_prompt_tokens"], requests=d["requests"],
                      seconds=seconds)
            return
    usage = getattr(result, "token_usage", None)
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if prompt is None and completion is None:
        write_row(stage, None, None, usage_missing=True, seconds=seconds)
        return
    write_row(stage, int(prompt or 0), int(completion or 0),
              cached_prompt_tokens=int(getattr(usage, "cached_prompt_tokens", 0) or 0),
              requests=int(getattr(usage, "successful_requests", 0) or 0),
              seconds=seconds)


def record_stage_usage(stage, result=None, crew=None):  # kept for callers of the old interface
    return False
