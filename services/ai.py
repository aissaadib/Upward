"""AI utility functions — JSON parsing with markdown-stripping and balanced-brace fallback."""

import json
import re


def _balanced_json(text):
    """Find the first balanced JSON object {} or array [] in text."""
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start:i+1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        break
    return None


def parse_ai_json(raw):
    """
    Parse JSON from AI responses, stripping markdown code fences.
    Tries to extract JSON from ```json blocks first, then falls back to
    finding the first balanced JSON object/array in the raw text.
    """
    raw = raw.strip()

    # Try to extract JSON from markdown code blocks first
    json_match = re.search(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)
    else:
        raw = raw.replace("```json", "").replace("```", "").strip()

    # Direct parse attempt
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fallback: balanced brace/bracket scan
    found = _balanced_json(raw)
    if found is not None:
        return json.loads(found)

    raise json.JSONDecodeError("Could not extract valid JSON", raw, 0)
