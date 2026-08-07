"""Post-install runtime probes (ADR-215, G3/G4) — stdlib only.

Run on the disposable host AFTER ``install.sh`` reports success:

1. public login on ``/api/v1/auth/login`` with the bootstrap admin;
2. one SSE chat on ``/api/v1/agents/chat/stream`` requiring a terminal
   event (the seeded pipeline core answers through the fake provider);
3. running container `.Image` config IDs vs the manifest's per-platform
   config digests (prebuilt rows; never compared to an index digest).

Usage:
    python assert_install.py --base-url http://127.0.0.1:3000 \
        --admin-email admin@... --admin-password-env ADMIN_PASSWORD \
        [--manifest lia-self-host-manifest.json --platform linux/amd64 \
         --project lia-installer-smoke-x]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def _post_json(url: str, payload: dict, cookie: str | None = None) -> tuple[int, dict, str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if cookie:
        request.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            set_cookie = response.headers.get("Set-Cookie", "")
            return response.status, json.loads(response.read() or b"{}"), set_cookie
    except urllib.error.HTTPError as exc:
        return exc.code, {}, ""


def probe_login(base_url: str, email: str, password: str) -> str:
    status, _body, set_cookie = _post_json(
        f"{base_url}/api/v1/auth/login",
        {"email": email, "password": password},
    )
    check(status == 200, f"login expected 200, got {status}")
    cookie = set_cookie.split(";")[0] if set_cookie else ""
    check(bool(cookie), "login returned no session cookie")
    return cookie


def probe_chat_stream(base_url: str, cookie: str) -> None:
    request = urllib.request.Request(
        f"{base_url}/api/v1/agents/chat/stream",
        data=json.dumps({"message": "Say OK.", "conversation_id": None}).encode(),
        headers={"Content-Type": "application/json", "Cookie": cookie},
        method="POST",
    )
    terminal = False
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            check(response.status == 200, f"chat stream {response.status}")
            for raw_line in response:
                line = raw_line.decode("utf-8", "replace").strip()
                if line.startswith("data:") and (
                    '"type": "done"' in line
                    or '"type":"done"' in line
                    or "[DONE]" in line
                    or '"event": "end"' in line
                ):
                    terminal = True
                    break
    except Exception as exc:  # noqa: BLE001
        check(False, f"chat stream failed: {type(exc).__name__}")
        return
    check(terminal, "chat stream ended without a terminal SSE event")


def probe_image_identities(manifest_path: str, platform: str, project: str) -> None:
    manifest = json.loads(open(manifest_path, encoding="utf-8").read())
    config_by_service = {
        image["service"]: next(
            row["config_digest"]
            for row in image["platforms"]
            if row["platform"] == platform
        )
        for image in manifest["images"]
    }
    listing = subprocess.run(
        ["docker", "ps", "--filter", f"label=com.docker.compose.project={project}",
         "--format", "{{.Label \"com.docker.compose.service\"}} {{.ID}}"],
        capture_output=True, text=True, check=True,
    )
    for line in listing.stdout.strip().splitlines():
        service, container_id = line.split()
        if service not in config_by_service:
            continue
        inspected = subprocess.run(
            ["docker", "inspect", "--format", "{{.Image}}", container_id],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        check(
            inspected == config_by_service[service],
            f"{service}: running config {inspected} != manifest "
            f"{config_by_service[service]} ({platform})",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password-env", required=True)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--platform", default=None)
    parser.add_argument("--project", default=None)
    args = parser.parse_args()

    password = os.environ.get(args.admin_password_env, "")
    check(bool(password), f"missing env {args.admin_password_env}")
    if password:
        cookie = probe_login(args.base_url, args.admin_email, password)
        if cookie:
            probe_chat_stream(args.base_url, cookie)
    if args.manifest and args.platform and args.project:
        probe_image_identities(args.manifest, args.platform, args.project)

    if FAILURES:
        for failure in FAILURES:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print("assert_install: all probes green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
