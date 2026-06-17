import json


def parse_ai_json(raw):
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)
