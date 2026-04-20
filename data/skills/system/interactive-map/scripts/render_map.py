"""Render an interactive Google Maps iframe for a given location.

Reads `{"parameters": {"location": "<string>"}}` from stdin and emits a
SkillScriptOutput JSON on stdout with a `frame.url` pointing to the Google
Maps embed for the requested location. Logs go to stderr so they do not
interfere with the JSON contract parser.

No API key is required: the embed endpoint below is the redirect target of
the legacy `maps.google.com/maps?q=...&output=embed` URL. The redirect
itself carries `X-Frame-Options: SAMEORIGIN`, which Chrome enforces on
every hop of an iframe navigation — so we skip the 301 and hit the final
URL directly. The `pb` payload is a minimal protobuf string (`!1m2!2m1!1s`
= one string field containing the query).
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

    url = f"https://www.google.com/maps/embed?origin=mfe&pb=!1m2!2m1!1s{quote(location)}"
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
