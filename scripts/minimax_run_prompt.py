#!/usr/bin/env python3
"""Run a codex-style prompt file through minimax-m2.7 chat completion API.

Minimax doesn't have CLI file-edit tools, so we ask minimax to output a
structured yaml patch in its response. Caller parses the response and
applies the patch to the target overlay yaml via ``apply_yaml_patch.py``.

Usage::

    python scripts/minimax_run_prompt.py /tmp/prompt.md \
        --out /tmp/minimax_response_000063.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

MINIMAX_API_BASE = "https://api.minimaxi.com/v1"
MINIMAX_MODEL = "MiniMax-M2"   # Smoke-tested model name. Override via --model.

SYSTEM_PROMPT = """\
你是一个数据分析助手。任务：按 user prompt 给的 schema 严格填充 stock_overlay yaml 字段。
约束：
- 只用 prompt 里 inline 的 SQLite facts + 行业框架知识
- 禁止访问任何外部 URL（即使你认为知道 URL）
- 输出格式：纯 yaml patch，开头一行 `# YAML_PATCH_START`，结尾一行 `# YAML_PATCH_END`
- patch 内容：`nodes:` 列表，每个 node 含 `dp_id` / `data_status` / `value` / `confidence` /
  `evidence_sources` / `source_fingerprint_at_fill` / `last_filled_period` / `last_event_id` /
  `last_updated` / `missing_reason`(若不填) / `evidence_quality`
- 不要解释，不要 markdown，只输出 # YAML_PATCH_START ... # YAML_PATCH_END 包裹的 yaml
- web_analysis tier 字段：若 prompt 允许 web evidence 也禁止访问外部，按 closed-loop 处理
  （或返回 data_status: Unknown + missing_reason: "web access disabled in A/B test"）
"""


def call_minimax(prompt_text: str, model: str = MINIMAX_MODEL,
                 timeout: int = 240) -> dict:
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY not set in env")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
        ],
        "temperature": 0.2,
        "max_tokens": 16000,
    }
    url = f"{MINIMAX_API_BASE}/text/chatcompletion_v2"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"minimax HTTP {e.code}: {body[:500]}")


def extract_yaml_patch(response_text: str) -> str | None:
    """Extract content between # YAML_PATCH_START and # YAML_PATCH_END."""
    m = re.search(
        r"#\s*YAML_PATCH_START\s*\n(.*?)\n#\s*YAML_PATCH_END",
        response_text, flags=re.DOTALL,
    )
    if m:
        return m.group(1)
    # Fallback: try fenced code block ```yaml ... ```
    m2 = re.search(
        r"```(?:yaml|yml)?\s*\n(.*?)\n```",
        response_text, flags=re.DOTALL,
    )
    if m2 and "nodes:" in m2.group(1):
        return m2.group(1)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt_file")
    parser.add_argument("--out", required=True,
                        help="Path to write minimax raw response")
    parser.add_argument("--model", default=MINIMAX_MODEL)
    args = parser.parse_args()

    prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")

    try:
        resp = call_minimax(prompt_text, model=args.model)
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        Path(args.out).write_text(f"ERROR: {e}\n", encoding="utf-8")
        return 1

    # Extract text content from minimax response
    content = ""
    choices = resp.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""

    usage = resp.get("usage") or {}
    full_log = json.dumps(resp, ensure_ascii=False, indent=2)
    Path(args.out).write_text(
        f"=== minimax response (raw) ===\n{full_log}\n\n=== content ===\n{content}\n",
        encoding="utf-8",
    )
    print(
        f"usage: prompt={usage.get('prompt_tokens', '?')} "
        f"completion={usage.get('completion_tokens', '?')} "
        f"total={usage.get('total_tokens', '?')}",
        file=sys.stderr,
    )

    patch = extract_yaml_patch(content)
    if patch is None:
        print(
            f"WARN: no YAML_PATCH_START block in minimax response "
            f"(saved to {args.out})",
            file=sys.stderr,
        )
        return 2

    patch_path = Path(args.out).with_suffix(".patch.yaml")
    patch_path.write_text(patch, encoding="utf-8")
    print(f"wrote response->{args.out}, patch->{patch_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
