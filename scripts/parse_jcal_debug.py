from __future__ import annotations

import ast
import json
import re
import sys
from typing import Any

ISO_RE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:\d{2})"


def parse_log(text: str) -> dict[str, Any]:
    spans2_len = _find_first_int(text, [r"spans2_len\s*[:=]\s*(\d+)", r"spans2\s*len\s*[:=]\s*(\d+)"])
    spans2_offset = _find_first_int(
        text,
        [r"spans2_offset\s*[:=]\s*(-?\d+)", r"spans2\s*offset\s*[:=]\s*(-?\d+)"],
    )
    zeros_pos = _find_first_list(text, [r"zeros(?:\s*\(pos\))?\s*[:=]\s*(\[[^\]]*\])"])
    zeros_abs = _find_first_list(text, [r"zeros\s*\(abs\)\s*[:=]\s*(\[[^\]]*\])"])
    no_zh_pos = _find_first_list(text, [r"no_zh(?:\s*\(pos\))?\s*[:=]\s*(\[[^\]]*\])"])
    no_zh_abs = _find_first_list(text, [r"no_zh\s*\(abs\)\s*[:=]\s*(\[[^\]]*\])"])

    if zeros_abs is None and zeros_pos is not None and spans2_offset is not None:
        zeros_abs = [spans2_offset + x for x in zeros_pos]
    if no_zh_abs is None and no_zh_pos is not None and spans2_offset is not None:
        no_zh_abs = [spans2_offset + x for x in no_zh_pos]

    spans = _parse_span_blocks(text)
    term_events = _parse_term_events(text)
    for event in term_events:
        idx = event.get("span_index")
        if idx is None:
            continue
        spans.setdefault(
            idx,
            {
                "span_index": idx,
                "start_utc": None,
                "end_utc": None,
                "principal_terms": [],
            },
        )["principal_terms"].append(
            {
                "deg": event.get("deg"),
                "utc": event.get("utc"),
                "jst_date": event.get("jst_date"),
            }
        )

    for item in spans.values():
        item["principal_terms"].sort(key=lambda x: (str(x.get("utc")), int(x.get("deg") or -1)))

    anchor_span_indices = sorted(
        idx
        for idx, item in spans.items()
        if any(term.get("deg") == 270 for term in item.get("principal_terms", []))
    )

    return {
        "spans2_len": spans2_len,
        "spans2_offset": spans2_offset,
        "zeros": {
            "pos": zeros_pos,
            "abs": zeros_abs,
        },
        "no_zh": {
            "pos": no_zh_pos,
            "abs": no_zh_abs,
        },
        "anchor_deg_270_span_indices": anchor_span_indices,
        "spans": [spans[k] for k in sorted(spans.keys())],
    }


def _find_first_int(text: str, patterns: list[str]) -> int | None:
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None
    return None


def _find_first_list(text: str, patterns: list[str]) -> list[int] | None:
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        try:
            parsed = ast.literal_eval(m.group(1))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(parsed, list):
            out: list[int] = []
            for x in parsed:
                try:
                    out.append(int(x))
                except (TypeError, ValueError):
                    pass
            return out
    return None


def _parse_span_blocks(text: str) -> dict[int, dict[str, Any]]:
    spans: dict[int, dict[str, Any]] = {}
    patterns = [
        rf"span(?:#|\[)?\s*(\d+)\]?[^\\n]*start(?:_utc)?\s*[:=]\s*({ISO_RE})[^\\n]*end(?:_utc)?\s*[:=]\s*({ISO_RE})",
        rf"'index'\s*:\s*(\d+)[^\\n]*'start_utc'\s*:\s*'({ISO_RE})'[^\\n]*'end_utc'\s*:\s*'({ISO_RE})'",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            idx = int(m.group(1))
            spans[idx] = {
                "span_index": idx,
                "start_utc": m.group(2),
                "end_utc": m.group(3),
                "principal_terms": [],
            }
    return spans


def _parse_term_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    patterns = [
        rf"span(?:#|\[)?\s*(\d+)\]?[^\\n]*deg\s*[:=]\s*(\d+)[^\\n]*utc\s*[:=]\s*({ISO_RE})(?:[^\\n]*jst_date\s*[:=]\s*(\d{{4}}-\d{{2}}-\d{{2}}))?",
        rf"deg\s*[:=]\s*(\d+)[^\\n]*utc\s*[:=]\s*({ISO_RE})[^\\n]*span(?:#|\[)?\s*(\d+)\]?(?:[^\\n]*jst_date\s*[:=]\s*(\d{{4}}-\d{{2}}-\d{{2}}))?",
        rf"'deg'\s*:\s*(\d+)[^\\n]*'utc'\s*:\s*'({ISO_RE})'[^\\n]*'local_date'\s*:\s*'(\d{{4}}-\d{{2}}-\d{{2}})'[^\\n]*span(?:_index)?\s*[:=]\s*(\d+)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            groups = m.groups()
            if pat.startswith("span"):
                span_idx, deg, utc, jst_date = groups
            elif pat.startswith("deg"):
                deg, utc, span_idx, jst_date = groups
            else:
                deg, utc, jst_date, span_idx = groups
            events.append(
                {
                    "span_index": _to_int(span_idx),
                    "deg": _to_int(deg),
                    "utc": utc,
                    "jst_date": jst_date,
                }
            )
    dedup: dict[tuple[Any, ...], dict[str, Any]] = {}
    for e in events:
        key = (e.get("span_index"), e.get("deg"), e.get("utc"), e.get("jst_date"))
        dedup[key] = e
    return list(dedup.values())


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python scripts/parse_jcal_debug.py <log_path>", file=sys.stderr)
        return 2
    path = argv[1]
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    payload = parse_log(text)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
