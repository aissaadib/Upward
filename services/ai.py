import json
import re


def parse_ai_json(raw):
    raw = raw.strip()
    
    # Try to extract JSON from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)
    else:
        # Fallback: remove any markdown code block markers
        raw = raw.replace("```json", "").replace("```", "").strip()
    
    # Try to find JSON object/array in the text
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from text that might have extra content
        json_match = re.search(r'(\{.*?\}|\[.*?\])', raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        raise
