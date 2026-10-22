# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""What a plugin attaches, as it answers GET <url>/attached (decision 0025):
checked and trimmed here, so one plugin can't flood the BFF's poll or the HMI.

    {"items": [{"kind", "label", "address", "state", "detail", "live": [...]}]}

`live` blocks are {"type": "text", "lines"}, {"type": "indicators", "items":
[{"name", "on", "color"}]} or {"type": "values", "items": [{"label", "value",
"unit"}]}. Too many items, blocks, lines or characters are cut; an item
without a label or with an unknown kind or state, and a block of an unknown
type, are dropped. Everything is kept as plain text.
"""

from __future__ import annotations

from typing import Any

KINDS = ("io", "ied", "display", "other")
STATES = ("ok", "degraded", "down", "unknown")
COLORS = ("green", "red", "yellow", "blue", "white")

MAX_ITEMS = 4
MAX_BLOCKS = 4
MAX_LINES = 8
MAX_LINE_CHARS = 24
MAX_INDICATORS = 8
MAX_VALUES = 6
# label, address, detail, a value's label, unit or text value.
MAX_TEXT = 80


class AttachedError(Exception):
    """The answer isn't {"items": [...]}."""


def _text(value: Any, limit: int = MAX_TEXT) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    return str(value)[:limit]


def _text_block(block: dict) -> dict | None:
    lines = block.get("lines")
    if not isinstance(lines, list):
        return None
    return {
        "type": "text",
        "lines": [_text(line, MAX_LINE_CHARS) or "" for line in lines[:MAX_LINES]],
    }


def _indicators_block(block: dict) -> dict | None:
    items = block.get("items")
    if not isinstance(items, list):
        return None
    indicators = []
    for item in items:
        if not isinstance(item, dict) or _text(item.get("name")) is None:
            continue
        color = item.get("color")
        indicators.append(
            {
                "name": _text(item["name"]),
                "on": bool(item.get("on")),
                "color": color if color in COLORS else "white",
            }
        )
    return {"type": "indicators", "items": indicators[:MAX_INDICATORS]}


def _values_block(block: dict) -> dict | None:
    items = block.get("items")
    if not isinstance(items, list):
        return None
    values = []
    for item in items:
        if not isinstance(item, dict) or _text(item.get("label")) is None:
            continue
        value = item.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            value = _text(value)
        values.append(
            {
                "label": _text(item["label"]),
                "value": value,
                "unit": _text(item.get("unit")),
            }
        )
    return {"type": "values", "items": values[:MAX_VALUES]}


BLOCKS = {
    "text": _text_block,
    "indicators": _indicators_block,
    "values": _values_block,
}


def _item(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    label = _text(item.get("label"))
    if not label or item.get("kind") not in KINDS:
        return None
    state = item.get("state", "unknown")
    if state not in STATES:
        return None
    live = []
    for block in item.get("live") or []:
        check = BLOCKS.get(block.get("type")) if isinstance(block, dict) else None
        checked = check(block) if check else None
        if checked is not None:
            live.append(checked)
    return {
        "kind": item["kind"],
        "label": label,
        "address": _text(item.get("address")),
        "state": state,
        "detail": _text(item.get("detail")),
        "live": live[:MAX_BLOCKS],
    }


def check(data: Any) -> list[dict]:
    """The items of a plugin's GET <url>/attached answer, checked and trimmed."""
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise AttachedError(
            f'answered {str(data)[:MAX_TEXT]!r}, not {{"items": [...]}}'
        )
    items = [checked for checked in map(_item, data["items"]) if checked is not None]
    return items[:MAX_ITEMS]
