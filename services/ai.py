"""AI utility functions — JSON parsing with markdown-stripping and regex fallback."""

import json
import re

 #brrrrrrrrrrrrrr
def parse_ai_json(raw):
    """
    Parse JSON from AI responses, stripping markdown code fences.
    Tries to extract JSON from ```json blocks first, then falls back to
    finding the first JSON object/array in the raw text.
    """
    raw = raw.strip()
    
    # Try to extract JSON from markdown code blocks first
    json_match = re.search(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)
    else:
        # Fallback: remove any markdown code block markers
        raw = raw.replace("```json", "").replace("```", "").strip()
    
    # Attempt to parse; if that fails, search for first JSON-like substring
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        json_match = re.search(r'(\{.*?\}|\[.*?\])', raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        raise
