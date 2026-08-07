"""The remote-control driver must send commands a shell can actually read.

`task demo:prod:*` sends its work to the production host through PowerShell,
then ssh's argument reassembly, then the remote shell. All three own the quote
character, and the failure is silent until somebody runs the command for real:

- the permission check reached the host as an unterminated string
  (``bash: -c: ligne 1: fin de fichier (EOF) prematuree``, 2026-08-07);
- the surface check had been unparseable since the day it was written and
  nobody knew, because `verify` had never been run against the host — ``sh -n``
  refused it outright.

Two rules close the class, and both are checked here:

1. the command travels BASE64-encoded, so the ssh argument holds only
   ``[A-Za-z0-9+/=]`` and no shell on the path can misread it;
2. anything beyond a single command line lives in a shell SCRIPT that ships
   with the bundle — a file a shell can check, and that `sh -n` does check.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ROOT = repo_root_or_skip()
DRIVER = ROOT / "scripts/deploy/demo-prod.ps1"
PREPARE = ROOT / "scripts/deploy/prepare-prod.ps1"

#: Shell scripts the driver calls on the host. Each must ship with the bundle
#: and must parse — they carry the logic that cannot live in a quoted string.
SHIPPED_SCRIPTS = (
    "scripts/deploy/harden-demo-host.sh",
    "scripts/deploy/verify-demo-surface.sh",
    "scripts/deploy/preflight-demo-prod.sh",
)


def _driver() -> str:
    return DRIVER.read_text(encoding="utf-8")


#: PowerShell variables the driver interpolates. Replaced by an inert literal
#: so the extracted command parses as the shell will see it.
_INTERPOLATED = {
    "$Compose": "docker compose -f x.yml",
    "$RemoteDir": "lia",
    "$Target": "user@host",
}


def _remote_commands() -> list[str]:
    """Every command the driver sends, as a shell would receive it.

    Resolves PowerShell's backtick escapes (`` `" `` -> ``"``, `` `$ `` ->
    ``$``) because those are what the interpreter resolves before the string
    ever reaches ssh.
    """
    commands: list[str] = []
    for match in re.finditer(r'Invoke-Remote\s+"((?:[^"`]|`.)*)"', _driver()):
        command = match.group(1)
        command = command.replace('`"', '"').replace("`$", "$").replace("``", "`")
        for name, value in _INTERPOLATED.items():
            command = command.replace(name, value)
        commands.append(command)
    return commands


class TestTheCommandCannotBeMisreadOnTheWay:
    def test_it_is_base64_encoded_before_it_leaves(self) -> None:
        body = _driver()

        assert "ToBase64String" in body, (
            "interpolating a command into a quoted ssh argument makes it cross "
            "three shells that each own the quote character; encoding removes "
            "the ambiguity instead of trying to escape it"
        )
        assert "base64 -d" in body, "the host must decode what the driver encoded"

    def test_every_remote_command_parses_as_a_shell_script(self) -> None:
        """The property that matters, checked directly rather than by proxy.

        Forbidding the quote character would be a proxy: stricter than needed
        on commands that are correct, and silent about a command that balances
        its quotes and still says nonsense. So each command is extracted,
        PowerShell's escapes are resolved the way PowerShell resolves them,
        and a real shell is asked to READ it — which is exactly what nobody
        did to the surface check, unparseable from the day it was written.
        """
        if shutil.which("sh") is None:  # pragma: no cover - POSIX shell absent
            pytest.skip("no POSIX shell available to parse the commands")

        commands = _remote_commands()
        assert len(commands) >= 10, f"only {len(commands)} commands extracted — parser drift"

        broken = []
        for command in commands:
            result = subprocess.run(
                ["sh", "-n"], input=command, capture_output=True, text=True, check=False
            )
            if result.returncode != 0:
                broken.append((command[:90], result.stderr.strip()[:110]))

        assert not broken, "; ".join(f"{c!r}: {e}" for c, e in broken)


class TestTheComplexLogicLivesInFilesAShellCanCheck:
    @pytest.mark.parametrize("relative", SHIPPED_SCRIPTS)
    def test_the_script_exists(self, relative: str) -> None:
        assert (ROOT / relative).is_file(), f"{relative} is missing"

    @pytest.mark.parametrize("relative", SHIPPED_SCRIPTS)
    def test_the_driver_calls_it(self, relative: str) -> None:
        assert relative in _driver(), (
            f"{relative} ships but nothing calls it — a check nobody runs is a " "check nobody has"
        )

    @pytest.mark.parametrize("relative", SHIPPED_SCRIPTS)
    def test_the_deployment_ships_it(self, relative: str) -> None:
        name = relative.rsplit("/", 1)[1]
        assert name in PREPARE.read_text(encoding="utf-8"), (
            f"{name} is not copied into the PROD bundle, so the remote call "
            "would fail with 'no such file'"
        )

    @pytest.mark.parametrize("relative", SHIPPED_SCRIPTS)
    def test_the_script_parses(self, relative: str) -> None:
        """`sh -n` reads it without running it — exactly what nobody did."""
        if shutil.which("sh") is None:  # pragma: no cover - POSIX shell absent
            pytest.skip("no POSIX shell available to parse the script")

        result = subprocess.run(
            ["sh", "-n"],
            input=(ROOT / relative).read_text(encoding="utf-8"),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, f"{relative} does not parse: {result.stderr.strip()}"

    @pytest.mark.parametrize("relative", SHIPPED_SCRIPTS)
    def test_the_script_uses_unix_line_endings(self, relative: str) -> None:
        """CRLF makes the shebang `sh\\r`, and the host answers 'not found'.

        Measured 2026-08-07 on the API entrypoint: rewriting a `.sh` through a
        Windows text API turned every line ending, and Docker builds from the
        working tree — `.gitattributes` only normalises at commit time.
        """
        raw = (ROOT / relative).read_bytes()

        assert b"\r\n" not in raw, f"{relative} carries CRLF line endings"


class TestTheDangerousActionsAnnounceThemselves:
    def test_starting_the_instance_asks_first(self) -> None:
        taskfile = (ROOT / "Taskfile.yml").read_text(encoding="utf-8")
        block = re.search(r"^  demo:prod:up:\n(.*?)(?=^  [a-z][\w:]*:\n)", taskfile, re.M | re.S)

        assert block, "demo:prod:up disappeared"
        assert "prompt:" in block.group(1), (
            "putting an instance in front of the Internet is a decision; it "
            "must be confirmed, not typed by accident"
        )


class TestTheDeploymentScriptsAreNotSilentlyCorrupted:
    """A control byte in a path is invisible in a diff and fatal at runtime.

        Measured 2026-08-07: rewriting `prepare-prod.ps1` through a Python string
        turned ``"scripts\\deploy\verify-..."`` into a VERTICAL TAB, because
        ``
    `` is an escape and Python only warns about the ones it does not know
        (``\\d`` warned, ``
    `` did not). The deployment died on
        ``Test-Path : Caracteres non conformes dans le chemin d'acces`` — after
        copying eleven directories, so the operator had already waited.
    """

    @pytest.mark.parametrize(
        "relative",
        [
            "scripts/deploy/prepare-prod.ps1",
            "scripts/deploy/deploy-prod.ps1",
            "scripts/deploy/demo-prod.ps1",
            *SHIPPED_SCRIPTS,
        ],
    )
    def test_no_control_byte_survives_in_a_deployment_script(self, relative: str) -> None:
        raw = (ROOT / relative).read_bytes()
        allowed = {0x09, 0x0A, 0x0D}
        found = sorted({byte for byte in raw if byte < 0x20 and byte not in allowed})

        assert not found, (
            f"{relative} carries control bytes {[hex(b) for b in found]} — a "
            "backslash path went through an interpreter that reads escapes"
        )

    def test_every_shipped_script_is_actually_copied_by_the_bundle(self) -> None:
        """Declared and copied are two different things.

        `prepare-prod.ps1` throws when one is missing, but the throw only fires
        if the path it tests is the path that exists — which is exactly what a
        corrupted byte breaks.
        """
        prepare = PREPARE.read_text(encoding="utf-8")
        for relative in SHIPPED_SCRIPTS:
            name = relative.rsplit("/", 1)[1]
            expected = '"scripts' + "\\" + "deploy" + "\\" + name + '"'
            assert (
                expected in prepare
            ), f"{name} is not referenced with a clean Windows path in prepare-prod.ps1"


#: PowerShell drivers the demonstrator's production path depends on.
POWERSHELL_DRIVERS = (
    "scripts/deploy/demo-prod.ps1",
    "scripts/deploy/deploy-prod.ps1",
    "scripts/deploy/prepare-prod.ps1",
)


class TestThePowerShellDriversParse:
    """A driver that does not parse fails at the worst possible moment.

    Measured 2026-08-07: a French apostrophe inside a message string left the
    tokenizer looking for a terminator, and `task demo:prod:up` died AFTER the
    operator had confirmed putting the instance on the Internet. The same
    class had already cost a deployment eleven directories in, on a control
    byte in a path.

    `sh -n` guards the shell scripts; this is its PowerShell equivalent, and
    it runs wherever `pwsh` exists — which GitHub's runners provide, and which
    the Taskfile already assumes for linux/darwin.
    """

    @pytest.mark.parametrize("relative", POWERSHELL_DRIVERS)
    def test_the_driver_parses(self, relative: str) -> None:
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell is None:  # pragma: no cover - no PowerShell on this runner
            pytest.skip("no PowerShell available to parse the drivers")

        path = (ROOT / relative).as_posix()
        script = (
            "$errors = $null; "
            "[System.Management.Automation.Language.Parser]::ParseFile("
            f"'{path}', [ref]$null, [ref]$errors) | Out-Null; "
            "if ($errors.Count) { "
            "$errors | ForEach-Object { Write-Output $_.Message }; exit 1 } "
            "else { exit 0 }"
        )
        result = subprocess.run(
            [shell, "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, f"{relative} does not parse: " + result.stdout.strip()


class TestTheDemonstratorSecretsReachTheHostWithoutAManualStep:
    """A prerequisite you document is a prerequisite somebody forgets.

    The first design asked the operator to place `.env.demo-instance.prod` by
    hand, and `task demo:prod:up` refused on a host where it was missing
    (measured 2026-08-07, twice). The deployment sends it now — over the SSH
    channel, never through the bundle, because it carries a different set of
    credentials from the production instance.
    """

    def test_the_deployment_sends_it_and_locks_it_down(self) -> None:
        body = (ROOT / "scripts/deploy/deploy-prod.ps1").read_text(encoding="utf-8")

        assert ".env.demo-instance.prod" in body, "the deployment never sends the secrets file"
        assert "chmod 600" in body, "a file created by scp inherits the umask"
        assert "PERMS_DEMO=600" in body, (
            "the permission must be verified on the host, not assumed — an "
            "unreported chmod failure would pass as a success"
        )

    def test_it_refuses_the_development_file(self) -> None:
        """One character apart in the name, and a dead verification link."""
        for relative in ("scripts/deploy/deploy-prod.ps1", "scripts/deploy/demo-prod.ps1"):
            body = (ROOT / relative).read_text(encoding="utf-8")
            assert "localhost" in body, (
                f"{relative} must refuse a file whose URLs point at localhost: "
                "that is the development shape, and sending it breaks the link "
                "a visitor clicks"
            )

    def test_the_bundle_never_carries_it(self) -> None:
        """It travels over SSH, never inside the copied tree."""
        prepare = PREPARE.read_text(encoding="utf-8")

        assert ".env.demo-instance.prod" not in prepare, (
            "the secrets file must not enter the PROD bundle: the bundle is a "
            "directory that lingers on the workstation"
        )


class TestBothEnvFileSettingsAreCarried:
    """Two settings name the same file and they are not interchangeable.

    ``--env-file`` tells Compose where to INTERPOLATE ``${VAR}`` from.
    ``DEMO_INSTANCE_ENV_FILE`` tells the API service which file to LOAD — the
    envelope declares ``env_file: ${DEMO_INSTANCE_ENV_FILE:-.env.demo-instance}``,
    so setting only the first makes the service ask for the DEVELOPMENT file:

        env file <deploy dir>/.env.demo-instance not found

    Measured 2026-08-07, and the sting is that it happened AFTER a green
    preflight — the file that existed had been checked, the file that was
    requested had not. The preflight now renders the stack with `compose
    config`, which asks Compose the same question the start does.
    """

    def test_the_driver_sets_both(self) -> None:
        body = _driver()

        assert "--env-file .env.demo-instance.prod" in body, "interpolation source missing"
        assert "DEMO_INSTANCE_ENV_FILE=.env.demo-instance.prod" in body, (
            "without it the API service loads the development file, which does "
            "not exist on the production host"
        )

    def test_the_preflight_renders_the_stack_before_starting_it(self) -> None:
        preflight = (ROOT / "scripts/deploy/preflight-demo-prod.sh").read_text(encoding="utf-8")

        assert "compose" in preflight and "config" in preflight, (
            "the preflight must ask Compose to resolve the stack: checking the "
            "files that exist says nothing about the file the service requests"
        )
        assert "DEMO_INSTANCE_ENV_FILE" in preflight, (
            "the render must use the same two settings the start uses, or it "
            "answers a different question"
        )

    def test_the_envelope_still_defaults_to_the_development_file(self) -> None:
        """Pin the default the driver has to override.

        If the envelope ever hardcodes one file, the override becomes dead
        weight — and if it changes the variable name, the driver goes silently
        back to loading the wrong file.
        """
        envelope = (ROOT / "docker-compose.demo-instance.yml").read_text(encoding="utf-8")

        assert "${DEMO_INSTANCE_ENV_FILE:-.env.demo-instance}" in envelope


class TestTheDriverSurvivesWindowsPowerShellEncoding:
    """Non-ASCII without a BOM is read as ANSI, and the parse dies.

    Measured 2026-08-07: an em dash inside a comment made Windows PowerShell
    5.1 report ``Le jeton && n'est pas un separateur d'instruction valide`` on
    a line that contained no operator at all — the multi-byte character had
    shifted the tokenizer. The driver is now ASCII-only, which needs no BOM
    and no encoding declaration to be read the same way everywhere.
    """

    def test_the_remote_driver_is_ascii_only(self) -> None:
        raw = (ROOT / "scripts/deploy/demo-prod.ps1").read_bytes()
        offenders = sorted({byte for byte in raw if byte > 0x7F})

        assert not offenders, (
            f"demo-prod.ps1 carries non-ASCII bytes {[hex(b) for b in offenders]}: "
            "Windows PowerShell reads a BOM-less file as ANSI and the parse "
            "breaks on a line that looks innocent"
        )


class TestTheProductionStartCarriesWhatTheEnvelopeAsksFor:
    """`APPLY_SEEDS=true` without a digest is a refusal, not a seeding.

    The envelope asks for the reference bundle and the entrypoint refuses it
    when ``SEED_BUNDLE_SHA256`` is empty — fail-closed, by design. `task
    demo:up*` computes the digest for the local shape; nothing computed it for
    production, so a deployed instance would have run on the PARTIAL pricing
    catalogue, with a spend ceiling reading zero.
    """

    def test_the_driver_computes_the_seed_digest(self) -> None:
        body = _driver()

        assert "compute_seed_bundle_sha256" in body, (
            "the production start must compute the bundle digest, like the "
            "local one does — otherwise the seeds are skipped"
        )
        assert "SEED_BUNDLE_SHA256=" in body, "the digest must reach the compose command"

    def test_it_refuses_to_start_without_one(self) -> None:
        body = _driver()

        assert "digest du bundle de seeds incalculable" in body, (
            "an uncomputable digest must stop the start: a silent skip leaves "
            "the instance billing against a ceiling that cannot see it"
        )

    def test_a_failed_start_shows_the_reason(self) -> None:
        """An operator should not have to go and fetch the log."""
        body = _driver()

        assert "-Diagnose" in body, "the start step must surface the API log on failure"
        assert "logs --tail" in body, "the diagnostic must actually read the log"


class TestThePublicNameIsCheckedWhereTheBrowserActuallyGoes:
    """A perfect stack behind a name Cloudflare cannot serve is a blank page.

    Measured 2026-08-07: every gate was green -- containers healthy, tunnel
    connected, host isolation enforced, surface census correct -- and the
    demonstrator answered ``ERR_SSL_VERSION_OR_CIPHER_MISMATCH``. Nothing we
    inspected could have seen it, because the browser negotiates TLS with
    Cloudflare and never with this host.

    The cause is a rule about certificates, not about us: a zone's Universal
    SSL covers ``zone.tld`` and ``*.zone.tld``, and a TLS wildcard matches
    EXACTLY ONE label. ``demo.product.zone.tld`` sits two labels under the
    apex, so no certificate covers it and Cloudflare aborts the handshake
    (``alert 40``). Proven on the real zone: the served certificate carries
    ``DNS:zone.tld, DNS:*.zone.tld`` and nothing else.
    """

    def test_the_preflight_opens_a_real_tls_connection(self) -> None:
        preflight = (ROOT / "scripts/deploy/preflight-demo-prod.sh").read_text(encoding="utf-8")

        assert "curl -s -o /dev/null -w '%{http_code}'" in preflight, (
            "the public name must be probed, not merely parsed: this failure "
            "lives entirely upstream of this machine"
        )
        assert "ERR_SSL_VERSION_OR_CIPHER_MISMATCH" in preflight, (
            "the refusal must name what the visitor sees, or nobody connects "
            "the message to the symptom"
        )

    def test_success_is_decided_by_the_http_status_not_by_curls_exit_code(self) -> None:
        """Refusing a healthy deployment is the one direction to avoid.

        A working host answered curl exit 23 (write error) while serving HTTP
        200 during the harness run. Any status at all proves the handshake
        happened; ``000`` proves it did not.
        """
        preflight = (ROOT / "scripts/deploy/preflight-demo-prod.sh").read_text(encoding="utf-8")

        assert '[ "${code:-000}" != "000" ]' in preflight, (
            "curl exits non-zero for reasons unrelated to TLS; the HTTP status " "is the oracle"
        )

    def test_values_read_from_the_env_file_are_stripped_of_carriage_returns(self) -> None:
        """The file is authored on Windows and copied byte for byte.

        Measured 2026-08-07 on the real production file: 191 CRLF, not one
        bare LF. Docker Compose strips them -- checked inside a container, the
        variable ends at ``flash`` -- so the instance is unaffected and only a
        shell reading the file directly is caught. It cost a full round-trip
        twice over, because the carriage return breaks BOTH the check and its
        diagnosis:

        - ``https://host\r/`` is a malformed URL, so curl exits 3 and the
          public name is declared unreachable while it serves fine;
        - the CR inside the refusal sends the terminal back to column zero, so
          the message that named the host was overprinted with
          ``/. curl a echoue`` -- a diagnosis nobody can act on.
        """
        preflight = (ROOT / "scripts/deploy/preflight-demo-prod.sh").read_text(encoding="utf-8")

        for key in ("FRONTEND_URL", "APP_URL_SERVER"):
            extraction = [
                line for line in preflight.splitlines() if f"'^{key}='" in line and "cut" in line
            ]
            assert extraction, f"the {key} extraction disappeared"
            assert all(
                "tr -d" in line for line in extraction
            ), f"{key} is read without stripping the carriage return"

    def test_it_separates_the_states_an_operator_must_tell_apart(self) -> None:
        preflight = (ROOT / "scripts/deploy/preflight-demo-prod.sh").read_text(encoding="utf-8")

        # No DNS record, refused handshake, and a name that resolves but never
        # answers are three different problems with three different fixes.
        assert "ne resout pas" in preflight
        assert "refuse la poignee de main TLS" in preflight
        assert "delai depasse" in preflight


class TestTheOutermostSurfaceIsMeasuredFromTheInternet:
    """Everything green inside, a dead page outside.

    Measured 2026-08-07: containers up and healthy, ``/ready`` answering
    ``ready``, DNS correct, TLS valid, host isolation enforced, route census
    clean -- and a visitor got HTTP 503. The last hop was broken and only
    cloudflared knew::

        WRN No ingress rules were defined in provided config (if any) nor
            from the cli, cloudflared will return 503 for all incoming HTTP
            requests

    A token tunnel takes its configuration from the dashboard, never from the
    container, so no file in this repository can hold it and none can fix it.
    What the repository CAN do is refuse to report "OK" while a dead page
    faces the world.
    """

    def test_the_surface_check_asks_the_public_url(self) -> None:
        script = (ROOT / "scripts/deploy/verify-demo-surface.sh").read_text(encoding="utf-8")

        assert "FRONTEND_URL" in script, (
            "the census reads the stack from inside the ingress network; a "
            "visitor arrives through Cloudflare, and that hop is the one that "
            "was broken"
        )
        assert r"tr -d '\r'" in script, "the env file is CRLF; an unstripped value builds a bad URL"

    def test_an_empty_5xx_is_named_for_what_it_is(self) -> None:
        """Reporting "503" alone sends the reader into the application logs.

        The application was healthy. The body is empty because Cloudflare, not
        the stack, produced the response -- so the message must say where the
        configuration actually lives.
        """
        script = (ROOT / "scripts/deploy/verify-demo-surface.sh").read_text(encoding="utf-8")

        assert 'if [ "${code:-000}" = "000" ]' in script, "no DNS and no TLS is a different failure"
        assert "Public Hostname" in script, "the refusal must name where to fix it"
        assert "http://demo-instance-edge:80" in script, (
            "the origin the tunnel must be pointed at is knowable here; "
            "making the operator go and find it is how the value gets guessed"
        )


class TestStartingTheDemonstratorServesTheCodeThatWasShipped:
    """Starting is not the same as rebuilding, and the gap was invisible.

    `deploy:prod` ships the code and deliberately does NOT start the
    demonstrator (owner arbitration). Its build step lists the three production
    envelopes and not the demonstrator's, so nothing in the deployment ever
    rebuilds that image. `demo:prod:up` then started the image that already
    existed.

    Measured 2026-08-07 on the public instance: the API container had been
    recreated minutes earlier and healthy, while `/app/src/domains/users/
    service.py` inside it was dated 23 July — the fix that makes a stored
    preference survive the DTO was on the host and nowhere near the process.
    The visible symptom was a debug panel that a visitor had switched on and
    that stayed empty, with no error anywhere.

    A start that does not build is a start that serves yesterday.
    """

    def test_the_start_builds_before_it_runs(self) -> None:
        driver = _driver()
        start = [line for line in driver.splitlines() if "up -d" in line]

        assert start, "the start command disappeared"
        for line in start:
            assert "--build" in line, (
                "starting must rebuild from the shipped sources: nothing else "
                "in the pipeline ever builds the demonstrator's image"
            )


class TestTheStartDoesNotFillTheHostsDisk:
    """Building on every start is right; hoarding every layer is not.

    Adding `--build` to the start (so the demonstrator serves the code that was
    shipped, not yesterday's image) makes this driver a producer of build
    cache. Measured on the host the same day: **50.38 GB of build cache, 12.12
    GB of it reclaimable** — on a Raspberry Pi whose disk is shared with the
    production stack, its backups and its observability retention.

    So the step that creates the garbage takes it out. Bounded by age rather
    than emptied wholesale: a full prune would throw away the layers that make
    the NEXT build fast, turning every start into a cold rebuild.
    """

    def test_the_start_reclaims_stale_build_cache(self) -> None:
        driver = _driver()

        assert "builder prune" in driver, (
            "the start builds every time; without a bounded prune the cache it "
            "produces grows without limit on a shared disk"
        )

    def test_it_keeps_the_recent_layers_that_make_the_next_build_fast(self) -> None:
        driver = _driver()
        prune = next(line for line in driver.splitlines() if "builder prune" in line)

        assert "--filter" in prune and "until=" in prune, (
            "an unfiltered prune drops the warm layers too, and the next start "
            "becomes a cold rebuild on a Raspberry Pi"
        )
        assert (
            "-a" not in prune.split("prune")[1].split("--filter")[0]
        ), "`prune -a` ignores the age filter's intent and empties everything"
