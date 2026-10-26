"""Create or remove the repository's isolated native/optimized World proof host.

Requires the repository's API/web development images (``docker compose -f
docker-compose.dev.yml build api web``). No development volume, environment
file, account or network is reused. All data is disposable; no provider can be
reached from the internal Docker network.
"""

import argparse
import base64
import json
import secrets
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
LABEL = "world-proof"
NETWORK = "lia-world-qa"
ACCESS_NETWORK = "lia-world-qa-access"
NAMES = {part: f"lia-world-qa-{part}" for part in ("web", "api", "redis", "postgres")}


def docker(*args: str) -> str:
    """Run Docker without a shell; return stdout and keep command failures visible."""
    result = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        result.check_returncode()
    return result.stdout.strip()


def exists(kind: str, name: str) -> bool:
    """Check inventory without treating a broken Docker daemon as an absent resource."""
    return (
        name
        in docker(
            kind,
            "ls",
            "--format",
            "{{.Name}}" if kind == "network" else "{{.Names}}",
            *(["-a"] if kind == "container" else []),
        ).splitlines()
    )


def require_owned(name: str, kind: str = "container") -> None:
    """Refuse to operate on a name without this proof's ownership label."""
    metadata = json.loads(docker(kind, "inspect", name))[0]
    labels = (
        metadata.get("Config", {}).get("Labels", {})
        if kind == "container"
        else metadata.get("Labels", {})
    )
    if (labels or {}).get("lia.task") != LABEL:
        raise RuntimeError(f"Refusing {name}: ownership label differs")


def remove_owned(name: str, kind: str = "container") -> None:
    """Delete only an explicitly labelled proof resource; refuse a name collision."""
    require_owned(name, kind)
    docker(kind, "rm", *(["-f", "-v"] if kind == "container" else []), name)


def proof_environment() -> dict[str, str]:
    """Generate fresh inert credentials; never read the caller's application environment."""
    password = secrets.token_hex(24)
    return {
        "ENVIRONMENT": "development",
        "DATABASE_URL": f"postgresql+asyncpg://world:{password}@world-proof-postgres:5432/world_qualification",
        "REDIS_URL": f"redis://:{password}@world-proof-redis:6379/0",
        "POSTGRES_USER": "world",
        "POSTGRES_PASSWORD": password,
        "POSTGRES_DB": "world_qualification",
        "PROOF_REDIS_PASSWORD": password,
        "SECRET_KEY": secrets.token_hex(32),
        "FERNET_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
        "WORLD_NAMESPACE": "world-qualification-proof",
        "WORLD_ENABLED": "true",
        "PEERS_ENABLED": "true",
        "SESSION_COOKIE_SECURE": "false",
        "LANGFUSE_ENABLED": "false",
        "OTEL_ENABLED": "false",
        "TURNSTILE_ENABLED": "false",
    }


def snapshot(root: Path, paths: list[Path], target: Path) -> None:
    """Archive only listed source files inside root; reject escapes and omit env files."""
    root = root.resolve()
    with tarfile.open(target, "w") as archive:
        for relative in paths:
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Proof source is outside the repository")
            if any(
                part.startswith(".env") or part in {"node_modules", "__pycache__", ".git"}
                for part in relative.parts
            ):
                continue
            if path.is_file():
                archive.add(path, arcname=relative.as_posix(), recursive=False)


def source_files() -> list[Path]:
    """Read the current tracked and nonignored source inventory, including unstaged fixes."""
    output = subprocess.run(
        ["git", "ls-files", "-z", "-c", "-o", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return [Path(value.decode("utf-8")) for value in output.split(b"\0") if value]


def wait_postgres() -> None:
    """Wait for the owned SQL service without retrying a business operation."""
    for _ in range(60):
        try:
            docker(
                "exec",
                NAMES["postgres"],
                "pg_isready",
                "-U",
                "world",
                "-d",
                "world_qualification",
            )
            return
        except subprocess.CalledProcessError:
            time.sleep(1)
    raise RuntimeError("Proof PostgreSQL did not become ready")


def wait_web(origin: str) -> None:
    """Wait for build, web and inert API readiness without making an authenticated call."""
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{origin}/api/v1/world-proof/me", timeout=2) as response:
                response.read()
        except HTTPError as error:
            ready = error.code == 401
            error.close()
            if ready:
                return
        except URLError, TimeoutError, ConnectionError:
            pass
        time.sleep(1)
    raise RuntimeError("Proof web/API did not become ready; inspect the labelled container logs")


def start(mode: str, port: int, api_image: str, web_image: str) -> None:
    """Snapshot current code and start isolated SQL, Redis, inert API and native web."""
    if any(exists("container", name) for name in NAMES.values()) or any(
        exists("network", name) for name in (NETWORK, ACCESS_NETWORK)
    ):
        raise RuntimeError("Proof resources already exist; run stop before a fresh start")
    for image in (api_image, web_image):
        docker("image", "inspect", image)
    services = json.loads(
        docker(
            "compose",
            "-f",
            str(ROOT / "infrastructure/docker/compose.services.yml"),
            "config",
            "--format",
            "json",
        )
    )["services"]
    work = ROOT / ".tmp/world-proof"
    work.mkdir(parents=True, exist_ok=True)
    environment = proof_environment()
    origin = f"http://127.0.0.1:{port}"
    environment["CORS_ORIGINS"] = origin
    environment["FRONTEND_URL"] = origin
    env_file = work / "runtime.env"
    env_file.write_text(
        "".join(f"{key}={value}\n" for key, value in environment.items()),
        encoding="utf-8",
    )
    common = [
        "--network",
        NETWORK,
        "--label",
        f"lia.task={LABEL}",
        "--security-opt",
        "no-new-privileges:true",
    ]
    try:
        docker("network", "create", "--internal", "--label", f"lia.task={LABEL}", NETWORK)
        docker("network", "create", "--label", f"lia.task={LABEL}", ACCESS_NETWORK)
        docker(
            "run",
            "-d",
            "--name",
            NAMES["postgres"],
            *common,
            "--network-alias",
            "world-proof-postgres",
            "--env-file",
            str(env_file),
            "--tmpfs",
            "/var/lib/postgresql/data",
            services["postgres-base"]["image"],
        )
        docker(
            "run",
            "-d",
            "--name",
            NAMES["redis"],
            *common,
            "--network-alias",
            "world-proof-redis",
            "--env-file",
            str(env_file),
            services["redis-base"]["image"],
            "sh",
            "-c",
            'exec redis-server --requirepass "$PROOF_REDIS_PASSWORD" --save "" --appendonly no',
        )
        wait_postgres()
        docker(
            "cp",
            str(ROOT / "infrastructure/docker/postgres-init.sql"),
            f"{NAMES['postgres']}:/tmp/init.sql",
        )
        docker(
            "exec",
            NAMES["postgres"],
            "psql",
            "-U",
            "world",
            "-d",
            "world_qualification",
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            "/tmp/init.sql",
        )
        docker("exec", NAMES["postgres"], "createdb", "-U", "world", "world_test")
        docker(
            "run",
            "-d",
            "--name",
            NAMES["api"],
            *common,
            "--network-alias",
            "world-proof-api",
            "--env-file",
            str(env_file),
            "--entrypoint",
            "sleep",
            api_image,
            "infinity",
        )
        files = source_files()
        api_files = [
            path.relative_to("apps/api")
            for path in files
            if path.parts[:3]
            in [("apps", "api", part) for part in ("src", "alembic", "locales", "config", "tests")]
            or path.as_posix() in {"apps/api/alembic.ini", "apps/api/pyproject.toml"}
        ]
        archive = work / "api.tar"
        snapshot(ROOT / "apps/api", api_files, archive)
        docker("cp", str(archive), f"{NAMES['api']}:/tmp/source.tar")
        docker(
            "cp",
            str(ROOT / "scripts/world-proof-app.py"),
            f"{NAMES['api']}:/app/world_proof.py",
        )
        docker(
            "exec",
            NAMES["api"],
            "sh",
            "-c",
            "rm -rf /app/src /app/alembic /app/locales /app/config /app/tests; rm -f /app/.env /app/.env.test; tar -xf /tmp/source.tar -C /app; rm /tmp/source.tar",
        )
        print("Migrating the disposable proof database…", flush=True)
        docker("exec", NAMES["api"], "alembic", "upgrade", "head")
        docker(
            "exec",
            "-d",
            NAMES["api"],
            "sh",
            "-c",
            "exec uvicorn world_proof:app --host 0.0.0.0 --port 8000 --ws websockets-sansio >/tmp/world-api.log 2>&1",
        )
        docker(
            "run",
            "-d",
            "--name",
            NAMES["web"],
            "--network",
            ACCESS_NETWORK,
            "--label",
            f"lia.task={LABEL}",
            "--security-opt",
            "no-new-privileges:true",
            "-p",
            f"127.0.0.1:{port}:3000",
            "--entrypoint",
            "sleep",
            web_image,
            "infinity",
        )
        docker("network", "connect", NETWORK, NAMES["web"])
        archive = work / "web.tar"
        snapshot(ROOT, [path for path in files if path.parts[:2] == ("apps", "web")], archive)
        docker("cp", str(archive), f"{NAMES['web']}:/tmp/source.tar")
        docker(
            "exec",
            NAMES["web"],
            "sh",
            "-c",
            "rm -rf /monorepo/apps/web/src /monorepo/apps/web/public /monorepo/apps/web/locales /monorepo/apps/web/e2e; tar -xf /tmp/source.tar -C /monorepo; rm /tmp/source.tar",
        )
        command = "node scripts/copy-ort-runtime.mjs && node node_modules/next/dist/bin/next dev --webpack --hostname 0.0.0.0 --port 3000"
        if mode == "production":
            command = "node scripts/copy-ort-runtime.mjs && node node_modules/next/dist/bin/next build --webpack && cp -a public .next-world/standalone/apps/web/ && cp -a .next-world/static .next-world/standalone/apps/web/.next-world/ && HOSTNAME=0.0.0.0 PORT=3000 NODE_OPTIONS=--max-old-space-size=512 exec node .next-world/standalone/apps/web/server.js"
        docker(
            "exec",
            "-d",
            "-w",
            "/monorepo/apps/web",
            "-e",
            f"NODE_ENV={'production' if mode == 'production' else 'development'}",
            "-e",
            "NEXT_DIST_DIR=.next-world",
            "-e",
            "NEXT_PUBLIC_API_URL=",
            "-e",
            "API_URL_SERVER=http://world-proof-api:8000",
            "-e",
            "WORLD_PROOF_PREVIEW=true",
            "-e",
            "WORLD_PROOF_TRANSLATION_FIXTURE=true",
            "-e",
            "NEXT_TELEMETRY_DISABLED=1",
            "-e",
            "NODE_OPTIONS=--max-old-space-size=6144",
            NAMES["web"],
            "sh",
            "-c",
            f"{{ {command}; }} >/tmp/world-next.log 2>&1",
        )
        print(
            f"Waiting for proof build/readiness ({mode}). Logs: docker exec {NAMES['web']} cat /tmp/world-next.log",
            flush=True,
        )
        wait_web(origin)
        print(f"Proof ready: {origin} ({mode}).", flush=True)
        print(
            f"Run the matching E2E task with E2E_WORLD_NATIVE_URL={origin} and E2E_WORLD_NATIVE_OPTIMIZED={'1' if mode == 'production' else '0'}."
        )
    finally:
        env_file.unlink(missing_ok=True)
        for name in ("api.tar", "web.tar"):
            (work / name).unlink(missing_ok=True)


def stop() -> None:
    """Remove this proof's labelled containers and network, including disposable data."""
    for name in NAMES.values():
        if exists("container", name):
            remove_owned(name)
    for name in (NETWORK, ACCESS_NETWORK):
        if exists("network", name):
            remove_owned(name, "network")


def integration() -> None:
    """Run World integration against the proof's separate world_test database and Redis 15."""
    for part in ("api", "postgres", "redis"):
        require_owned(NAMES[part])
    code = (
        "import os,subprocess,sys; "
        "os.environ['TEST_DATABASE_URL']=os.environ['DATABASE_URL'].replace('/world_qualification','/world_test'); "
        "os.environ['TEST_REDIS_URL']=os.environ['REDIS_URL'].removesuffix('/0')+'/15'; "
        "os.environ['LIA_REQUIRE_DB']='1'; "
        "sys.exit(subprocess.call([sys.executable,'-m','pytest','tests/integration/world','--no-cov','-q','-o','addopts=']))"
    )
    print(docker("exec", NAMES["api"], "python", "-c", code))


def main() -> None:
    """Dispatch the explicit local lifecycle command; no resource is created on import."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status", "test"))
    parser.add_argument("--mode", choices=("development", "production"), default="development")
    parser.add_argument("--port", type=int, default=3012)
    parser.add_argument("--api-image", default="lia-api-dev:latest")
    parser.add_argument("--web-image", default="lia-web-dev:latest")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    if args.action == "start":
        start(args.mode, args.port, args.api_image, args.web_image)
    elif args.action == "stop":
        stop()
    elif args.action == "test":
        integration()
    else:
        print(
            docker(
                "ps",
                "-a",
                "--filter",
                f"label=lia.task={LABEL}",
                "--format",
                "{{.Names}} {{.Status}} {{.Ports}}",
            )
        )


if __name__ == "__main__":
    main()
