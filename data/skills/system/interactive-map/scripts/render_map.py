"""Render an interactive Google Maps iframe for a given location.

Reads `{"parameters": {"location": "<string>"}}` from stdin and emits a
SkillScriptOutput JSON on stdout with a `frame.url` pointing to the Google
Maps embed for the requested location. Logs go to stderr so they do not
interfere with the JSON contract parser.

No API key is required: `https://maps.google.com/maps?q=...&output=embed`
is a public embed endpoint.
"""

from __future__ import annotations

import json
import sys
from urllib.parse import quote


def main() -> None:
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({
            "text": "Invalid input payload.",
            "error": "stdin is not valid JSON",
        }))
        return

    params = payload.get("parameters") or {}
    location = (params.get("location") or "").strip()

    if not location:
        print(json.dumps({
            "text": "No location was provided.",
            "error": "Missing 'location' parameter",
        }))
        return

    url = f"https://maps.google.com/maps?q={quote(location)}&output=embed"
    print(json.dumps({
        "text": f"Here is {location} on the map.",
        "frame": {
            "url": url,
            "title": f"Map: {location}",
            "aspect_ratio": 1.333,
        },
    }))


if __name__ == "__main__":
    main()
