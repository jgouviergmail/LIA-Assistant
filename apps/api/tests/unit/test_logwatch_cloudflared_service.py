"""The daily report's tunnel section counts what the tunnel actually logs.

Measured on production, 2026-10-18: the previous script printed « 1 023 erreurs
reelles », « 697 requetes traitees » and « 0 connexion enregistree » for a day
the tunnel served 19 795 requests over 4 connections. It counted LINES (every
failed request writes two), its noise filter targeted the QUIC messages of a
tunnel that had run HTTP/2 for two months, « requests » matched the failure
lines themselves, and the registration pattern had its words in the wrong
order. These tests pin the line shapes cloudflared 2026.8 writes and the
counter arithmetic the section reports.

The journal reaches the section the way it now reads it — its own
``journalctl --output=short-iso`` over the report window — and not through a
logwatch logfile group: there, ``*ApplyStdDate`` rewrote every line to a syslog
date without a year, so one outage of three minutes printed 27 periods, and a
day the journal stayed empty dropped the whole section, « Service : failed »
included.
"""

from __future__ import annotations

import http.server
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
LOGWATCH = REPO_ROOT / "infrastructure" / "logwatch"
SCRIPT = LOGWATCH / "scripts" / "services" / "cloudflared"


def _load() -> ModuleType:
    """Load the extensionless service script as a module, writing no bytecode.

    Registered in ``sys.modules`` before it runs: ``dataclasses`` resolves the
    string annotations of ``from __future__ import annotations`` through it.
    The deployment copies the script's directory onto the host, and the
    ``__pycache__`` an import left there stopped it at step 4/7 — ``cp``
    refuses a directory and ``set -e`` ends ``deploy.sh``.
    """
    loader = importlib.machinery.SourceFileLoader("logwatch_cloudflared", str(SCRIPT))
    spec = importlib.util.spec_from_loader("logwatch_cloudflared", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


CF = _load()

#: The report day the fixtures fall in (local time is UTC+2 on 2026-10-17).
DAY = "2026-10-17"
_LOCAL_OFFSET = timedelta(hours=2)


def _line(local_time: str, message: str, *, pid: int = 812) -> str:
    """One journal line exactly as ``journalctl --output=short-iso`` prints it.

    The journal's own stamp is local with its offset (systemd 255, measured);
    cloudflared's message carries its own UTC stamp before the level.
    """
    local = datetime.fromisoformat(f"{DAY}T{local_time}")
    utc = (local - _LOCAL_OFFSET).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{DAY}T{local_time}+02:00 host cloudflared[{pid}]: {utc} {message}"


CANCELLED = _line(
    "10:00:01",
    'ERR  error="Failed to proxy HTTP: Incoming request ended abruptly: context canceled" '
    "connIndex=1 event=1 ingressRule=1 originService=http://localhost:8000",
)
CANCELLED_TWIN = _line(
    "10:00:01",
    'ERR failed to serve incoming request error="Incoming request ended abruptly: '
    'context canceled" connIndex=1 event=1',
)


def _origin_down(local_time: str, port: int = 3000) -> str:
    return _line(
        local_time,
        'ERR  error="Unable to reach the origin service. The service may be down or it may '
        "not be responding to traffic from cloudflared: dial tcp [::1]:"
        f'{port}: connect: connection refused" connIndex=0 event=1 ingressRule=0 '
        f"originService=http://localhost:{port}",
    )


JOURNAL = [
    _line(
        "02:14:30",
        'WRN Serve tunnel error error="connection with edge closed" connIndex=3 event=0 '
        "ip=192.0.2.1",
    ),
    _line("02:14:32", 'WRN Connection terminated error="connection with edge closed" connIndex=3'),
    _line(
        "02:14:47",
        "INF Registered tunnel connection connIndex=3 connection=x event=0 ip=192.0.2.1 "
        "location=test1 protocol=http2",
    ),
    CANCELLED,
    CANCELLED_TWIN,
    _line(
        "11:00:00",
        'ERR  error="context canceled" connIndex=0 event=1 ingressRule=1 '
        "originService=http://localhost:8000",
    ),
    _line("11:00:00", 'ERR failed to serve incoming request error="context canceled" connIndex=0'),
    _line("13:13:17", "INF Initiating graceful shutdown due to signal terminated ..."),
    _line("13:13:17", "INF Unregistered tunnel connection connIndex=1"),
    _line("13:13:17", "ERR Connection terminated connIndex=1"),
    "-- Boot 0c5e3b51a1f04a3f9d3b5f0e9b5c2f11 --",
    _line("13:16:19", "INF Starting tunnel tunnelID=test-tunnel", pid=913),
    _line("13:16:19", "INF Starting metrics server on 127.0.0.1:20241/metrics", pid=913),
    _origin_down("13:16:30"),
    _origin_down("13:16:31"),
    _origin_down("13:17:05", port=8000),
    _origin_down("19:19:10", port=8000),
    _line(
        "21:00:00",
        'ERR  error="Failed to proxy HTTP: unexpected EOF" connIndex=2 event=1 ingressRule=1 '
        "originService=http://localhost:8000",
    ),
    _line("21:00:00", 'ERR failed to serve incoming request error="unexpected EOF" connIndex=2'),
]

METRICS = """# HELP cloudflared_tunnel_total_requests Amount of requests proxied
# TYPE cloudflared_tunnel_total_requests counter
cloudflared_tunnel_total_requests 19795
cloudflared_tunnel_request_errors 368
cloudflared_tunnel_ha_connections 4
cloudflared_tunnel_response_by_code{status_code="200"} 12570
cloudflared_tunnel_response_by_code{status_code="404"} 1930
cloudflared_tunnel_response_by_code{status_code="429"} 2444
cloudflared_tunnel_response_by_code{status_code="500"} 132
cloudflared_tunnel_concurrent_requests_per_tunnel 2
process_start_time_seconds 1.79223577926e+09
go_goroutines 42
"""

#: The report window the fixtures fall in, as the cron's ``--range yesterday`` names it.
WINDOW = CF.report_window("yesterday", datetime(2026, 10, 18, 4, 25, tzinfo=UTC).astimezone())


def _journal_runner(lines: list[str], extra: bytes = b"") -> Callable[[list[str]], bytes]:
    """A journalctl that answers ``lines`` for the tunnel's command, and only for it."""

    def run(command: list[str]) -> bytes:
        assert command == CF.journal_command(WINDOW)
        return "\n".join(lines).encode("utf-8") + b"\n" + extra

    return run


def _no_counters(url: str) -> str:
    raise OSError("refused")


def _report(lines: list[str], *, service: tuple[str, str] = ("active", "Sat 2026-10-17")) -> str:
    return "\n".join(
        CF.build_report(
            WINDOW,
            {"LOGWATCH_DETAIL_LEVEL": "10"},
            run=_journal_runner(lines),
            fetch=_no_counters,
            service=service,
            now=1000.0,
        )
    )


def test_loading_the_script_writes_no_bytecode_beside_it() -> None:
    """`deploy.sh` copies this directory onto the host: a ``__pycache__`` there
    made `cp` exit 1 and `set -e` stop the deployment at step 4/7."""
    assert not (SCRIPT.parent / "__pycache__").exists()


class TestTheSectionReadsTheJournalItself:
    def test_logwatch_runs_it_without_input_whatever_the_journal_holds(self) -> None:
        """A service fed by a logfile group is skipped on a day its journal is
        empty — and the tunnel section, « Service : failed » included, with it."""
        conf = (LOGWATCH / "conf" / "services" / "cloudflared.conf").read_text(encoding="utf-8")
        logfiles = [
            line.split("=", 1)[1].strip()
            for line in conf.splitlines()
            if line.strip().startswith("LogFile")
        ]

        assert logfiles == ["none"]
        assert not (LOGWATCH / "conf" / "logfiles" / "cloudflared.conf").exists()

    def test_the_window_is_read_in_epochs_from_the_tunnel_unit(self) -> None:
        """`--since=@N --until=@M` and the short-iso output, as systemd 255 accepts them."""
        assert CF.journal_command(WINDOW) == [
            "journalctl",
            "--no-pager",
            "--output=short-iso",
            "--unit=cloudflared.service",
            f"--since=@{int(WINDOW.start)}",
            f"--until=@{int(WINDOW.end)}",
        ]
        assert WINDOW.end - WINDOW.start == 24 * 3600

    def test_a_today_run_keeps_the_lines_of_its_own_last_second(self) -> None:
        """Truncated, ``--until=@int(now)`` dropped what was logged in the second
        the report started (measured against journalctl 255)."""
        command = CF.journal_command(CF.Window(100.2, 200.4, "x"))

        assert command[-2:] == ["--since=@100", "--until=@201"]

    def test_a_journalctl_line_is_keyed_by_its_minute(self) -> None:
        lines = CF.read_journal(WINDOW, _journal_runner(JOURNAL, extra=b"\xff\xfe not utf-8\n"))

        assert lines[0] == JOURNAL[0]
        assert CF._local_minute(lines[0]) == "2026-10-17 02:14"
        assert lines[-1] == "�� not utf-8"

    def test_the_syslog_shape_applystddate_wrote_is_never_keyed_by_the_second(self) -> None:
        assert CF._local_minute("Oct 17 13:16:30 host cloudflared[812]: ERR x") == "?"

    def test_an_unreadable_journal_is_named_never_read_as_a_quiet_day(self) -> None:
        def missing(command: list[str]) -> bytes:
            raise CF.JournalUnavailable("FileNotFoundError")

        text = "\n".join(
            CF.build_report(
                WINDOW,
                {},
                run=missing,
                fetch=_no_counters,
                service=("active", "Sat 2026-10-17"),
                now=1000.0,
            )
        )

        assert text.count("*** JOURNAL DU TUNNEL ILLISIBLE (FileNotFoundError)") == 2
        assert "Total" not in text
        assert "Coupures cote edge" not in text

    def test_a_failed_journalctl_is_named_by_its_first_error_line(self) -> None:
        failing = [
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('No journal files\\nx'); sys.exit(1)",
        ]

        with pytest.raises(CF.JournalUnavailable, match="^No journal files$"):
            CF._run_command(failing)

    def test_a_dead_day_still_reports_a_failed_service(self) -> None:
        text = _report(["-- No entries --"], service=("failed", ""))

        assert "Service              : failed  *** ATTENTION ***" in text
        assert "Total                         : 0" in text
        assert f"Periode                       : {WINDOW.label}" in text


class TestEveryFailedRequestIsCountedOnce:
    def test_the_two_lines_of_one_failure_count_as_one(self) -> None:
        summary = CF.parse_journal([CANCELLED, CANCELLED_TWIN])

        assert sum(summary.failures.values()) == 1

    def test_failures_are_split_by_the_side_they_belong_to(self) -> None:
        summary = CF.parse_journal(JOURNAL)

        assert summary.failures == Counter({"client": 2, "origin": 4, "other": 1})
        assert summary.by_origin == Counter(
            {"http://localhost:8000": 5, "http://localhost:3000": 2}
        )
        assert summary.other_errors == Counter({"unexpected EOF": 1})

    @pytest.mark.parametrize(
        ("error", "category"),
        [
            ("Failed to proxy HTTP: Incoming request ended abruptly: context canceled", "client"),
            ("Failed to proxy HTTP: context canceled", "client"),
            ("context canceled", "client"),
            ("Unable to reach the origin service. The service may be down", "origin"),
            ("Failed to proxy HTTP: unexpected EOF", "other"),
            ("http2: stream closed", "other"),
        ],
    )
    def test_each_error_text_has_one_category(self, error: str, category: str) -> None:
        assert CF.classify_error(error) == category


class TestTheTunnelEventsAreTheOnesCloudflaredWrites:
    def test_registrations_drops_stops_and_starts(self) -> None:
        summary = CF.parse_journal(JOURNAL)

        assert summary.registrations == 1
        assert summary.edge_drops == ["2026-10-17 02:14"]
        assert summary.graceful_stops == ["2026-10-17 13:13"]
        assert summary.starts == ["2026-10-17 13:16"]
        assert summary.metrics_address == "127.0.0.1:20241"

    def test_an_outage_is_one_period_however_many_minutes_it_spans(self) -> None:
        summary = CF.parse_journal(JOURNAL)

        assert CF.outage_periods(summary.origin_down_minutes) == [
            ("2026-10-17 13:16", "2026-10-17 13:17", 3),
            ("2026-10-17 19:19", "2026-10-17 19:19", 1),
        ]

    def test_a_three_minute_outage_prints_one_period(self) -> None:
        """Production 2026-10-17: 27 lines for one outage, one per second."""
        outage = [
            _origin_down(f"13:{minute:02d}:{second:02d}")
            for minute in (16, 17, 18)
            for second in range(0, 60, 7)
        ]

        text = _report(outage)

        assert "    2026-10-17 13:16 -> 13:18 : 27" in text
        assert text.count("2026-10-17 13:1") == 1

    def test_a_flapping_day_lists_ten_periods_and_counts_the_rest(self) -> None:
        flapping = [_origin_down(f"{hour:02d}:00:00") for hour in range(15)]

        lines = CF.render_failures(CF.parse_journal(flapping), 10, WINDOW)

        periods = [line for line in lines if line.startswith("    2026-10-17 ")]
        assert len(periods) == CF.EVENTS_SHOWN
        assert "    ... et 5 autre(s)" in lines

    def test_starts_stops_and_edge_drops_are_capped_too(self) -> None:
        restarts: list[str] = []
        for hour in range(12):
            restarts.append(_line(f"{hour:02d}:00:00", "INF Starting tunnel tunnelID=t"))
            restarts.append(_line(f"{hour:02d}:30:00", "INF Initiating graceful shutdown ..."))
            restarts.append(_line(f"{hour:02d}:40:00", "WRN Serve tunnel error error=x"))

        lines = CF.render_tunnel(CF.parse_journal(restarts), ("active", "now"), 10)

        assert sum(line.startswith("    demarrage : ") for line in lines) == CF.EVENTS_SHOWN
        assert sum(line.startswith("    arret programme : ") for line in lines) == CF.EVENTS_SHOWN
        assert lines.count("    ... et 2 autre(s)") == 3
        assert "  Demarrages           : 12" in lines


class TestTheCountersComeFromTheTunnel:
    def test_the_exposition_is_parsed_with_its_labels(self) -> None:
        samples = CF.parse_metrics(METRICS)

        assert samples["cloudflared_tunnel_total_requests"] == 19795
        assert samples['cloudflared_tunnel_response_by_code{status_code="429"}'] == 2444
        assert samples["process_start_time_seconds"] == pytest.approx(1792235779.26)

    def test_an_endpoint_that_is_not_cloudflared_is_skipped(self) -> None:
        def fetch(url: str) -> str:
            if url.endswith(":20241/metrics"):
                raise OSError("refused")
            if url.endswith(":20242/metrics"):
                return "go_goroutines 3\n"
            return METRICS

        reading = CF.read_counters(
            [f"http://127.0.0.1:{port}/metrics" for port in (20241, 20242, 20243)], fetch, 1000.0
        )

        assert reading is not None
        assert reading.counters["cloudflared_tunnel_total_requests"] == 19795
        assert "go_goroutines" not in reading.counters
        assert "cloudflared_tunnel_concurrent_requests_per_tunnel" not in reading.counters

    def test_a_listener_that_speaks_no_http_does_not_stop_the_search(
        self, banner_server: str, metrics_server: str
    ) -> None:
        """A banner is no HTTP status line: urllib raises ``BadStatusLine``,
        which is no ``OSError`` — it used to escape ``main()``."""
        reading = CF.read_counters([banner_server, metrics_server], CF._http_get, 1.0)

        assert reading is not None
        assert reading.counters["cloudflared_tunnel_total_requests"] == 19795
        assert CF.read_counters([banner_server], CF._http_get, 1.0) is None

    def test_a_malformed_override_does_not_stop_the_search(self) -> None:
        def fetch(url: str) -> str:
            if not url.startswith("http"):
                raise ValueError("unknown url type")
            return METRICS

        assert CF.read_counters(["not-a-url", "http://127.0.0.1:20241/metrics"], fetch, 1.0)

    def test_no_endpoint_reads_as_none(self) -> None:
        assert CF.read_counters(["http://127.0.0.1:20241/metrics"], _no_counters, 1.0) is None

    def test_an_operator_override_is_the_only_address_tried(self) -> None:
        summary = CF.parse_journal(JOURNAL)

        candidates = CF.metrics_candidates(
            summary, {"LIA_CLOUDFLARED_METRICS_URL": "http://127.0.0.1:20300/metrics"}
        )

        assert candidates == ["http://127.0.0.1:20300/metrics"]

    def test_the_announced_address_comes_before_the_default_ports(self) -> None:
        candidates = CF.metrics_candidates(CF.parse_journal(JOURNAL), {})

        assert candidates[0] == "http://127.0.0.1:20241/metrics"
        assert candidates[1:] == [
            f"http://127.0.0.1:{port}/metrics" for port in (20242, 20243, 20244, 20245)
        ]


def _reading(taken_at: float, start: float, total: float, code_429: float) -> object:
    return CF.Reading(
        taken_at=taken_at,
        process_start=start,
        counters={
            "cloudflared_tunnel_total_requests": total,
            "cloudflared_tunnel_ha_connections": 4.0,
            'cloudflared_tunnel_response_by_code{status_code="429"}': code_429,
        },
    )


class TestTheWindowIsStatedNotAssumed:
    def test_without_a_previous_reading_the_totals_since_start_are_said_so(self) -> None:
        window = CF.counters_window(_reading(500.0, 100.0, 10.0, 1.0), None)

        assert window.kind == "since_start"
        assert window.start == 100.0

    def test_the_same_process_yields_the_difference(self) -> None:
        window = CF.counters_window(
            _reading(900.0, 100.0, 30.0, 5.0), _reading(500.0, 100.0, 10.0, 1.0)
        )

        assert window.kind == "delta"
        assert (window.start, window.end) == (500.0, 900.0)
        assert window.values["cloudflared_tunnel_total_requests"] == 20.0
        assert window.values['cloudflared_tunnel_response_by_code{status_code="429"}'] == 4.0
        assert window.values["cloudflared_tunnel_ha_connections"] == 4.0

    def test_a_restarted_process_is_never_subtracted(self) -> None:
        window = CF.counters_window(
            _reading(900.0, 700.0, 3.0, 0.0), _reading(500.0, 100.0, 10.0, 1.0)
        )

        assert window.kind == "since_restart"
        assert window.values["cloudflared_tunnel_total_requests"] == 3.0

    def test_a_counter_that_went_down_is_a_restart_too(self) -> None:
        window = CF.counters_window(
            _reading(900.0, 100.0, 3.0, 0.0), _reading(500.0, 100.0, 10.0, 1.0)
        )

        assert window.kind == "since_restart"

    def test_the_reading_survives_a_round_trip_and_garbage_reads_as_none(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "state" / CF.STATE_FILE_NAME
        reading = _reading(500.0, 100.0, 10.0, 1.0)

        CF.save_reading(path, reading)

        assert CF.load_reading(path) == reading
        path.write_text("{not json", encoding="utf-8")
        assert CF.load_reading(path) is None
        assert CF.load_reading(tmp_path / "absent.json") is None

    def test_yesterday_today_and_anything_else(self) -> None:
        now = datetime(2026, 10, 18, 4, 25, tzinfo=UTC).astimezone()

        today = CF.report_window("Today", now)
        other = CF.report_window("all", now)

        assert today.start == WINDOW.end and today.end == now.timestamp()
        assert other.end - other.start == 24 * 3600
        assert other.label.startswith("dernieres 24 h")


class TestTheSectionSaysWhatMatters:
    def test_server_errors_are_flagged_and_throttling_is_named(self) -> None:
        reading = CF.read_counters(["http://x/metrics"], lambda url: METRICS, 1000.0)
        lines = "\n".join(CF.render_counters(CF.counters_window(reading, None)))

        assert "Requetes             : 19795" in lines
        assert "Reponses 5xx         : 132  *** A VERIFIER ***" in lines
        assert "Reponses 429         : 2444" in lines
        assert "Autres reponses 4xx  : 1930" in lines
        assert "depuis le demarrage du tunnel" in lines

    def test_unreachable_counters_are_said_so(self) -> None:
        assert any("indisponibles" in line for line in CF.render_counters(None))

    def test_an_origin_outage_is_flagged_and_client_cancels_are_not(self) -> None:
        text = _report(JOURNAL)

        assert "Total                         : 7" in text
        assert "Origine injoignable           : 4  *** A VERIFIER ***" in text
        assert "Interrompues (client parti)   : 2  (normal" in text
        assert "2026-10-17 13:16 -> 13:17 : 3" in text
        assert "Compteurs indisponibles" in text

    def test_an_edge_drop_is_flagged(self) -> None:
        lines = "\n".join(
            CF.render_tunnel(CF.parse_journal(JOURNAL), ("active", "Sat 2026-10-17"), 10)
        )

        assert "COUPURES COTE EDGE   : 1  *** A SURVEILLER ***" in lines


def _hermetic_env(tmp_path: Path, overrides: dict[str, str]) -> dict[str, str]:
    """The environment of a run whose ``PATH`` holds no ``journalctl`` nor ``systemctl``.

    The same on every platform: the run never reads the host's journal, and a
    journal it cannot read must be NAMED.
    """
    empty_path = tmp_path / "no-commands"
    empty_path.mkdir(exist_ok=True)
    environment = {k: v for k, v in os.environ.items() if k != "LIA_REPORT_STATE_DIR"}
    return {**environment, "LOGWATCH_DETAIL_LEVEL": "10", "PATH": str(empty_path), **overrides}


def _run_script(
    env_overrides: dict[str, str], tmp_path: Path, cwd: Path | None = None
) -> subprocess.CompletedProcess[bytes]:
    """Run the script the way logwatch does: no input, its own commands."""
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env=_hermetic_env(tmp_path, env_overrides),
        timeout=60,
        check=False,
        cwd=cwd,
    )


@pytest.fixture
def metrics_server() -> Iterator[str]:
    """A loopback endpoint serving the tunnel's exposition."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - the stdlib's name
            body = METRICS.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return None

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/metrics"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def banner_server() -> Iterator[str]:
    """A loopback listener that answers a banner instead of HTTP (an SSH server, say)."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(5)
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            with connection:
                connection.settimeout(5)
                try:
                    connection.recv(4096)
                    connection.sendall(b"SSH-2.0-OpenSSH_9.2p1\r\n")
                except OSError:
                    continue

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}/metrics"
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=5)


class TestTheScriptRunsAsLogwatchRunsIt:
    def test_unreachable_counters_degrade_and_nothing_is_kept(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        done = _run_script(
            {
                "LIA_REPORT_STATE_DIR": str(state),
                "LIA_CLOUDFLARED_METRICS_URL": "http://127.0.0.1:9/metrics",
            },
            tmp_path,
        )

        assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
        output = done.stdout.decode("utf-8")
        assert "*** JOURNAL DU TUNNEL ILLISIBLE (FileNotFoundError)" in output
        assert "Service              : inconnu  *** ATTENTION ***" in output
        assert "Compteurs indisponibles" in output
        assert not (state / CF.STATE_FILE_NAME).exists()

    def test_the_daily_run_keeps_its_reading_for_the_next_day(
        self, tmp_path: Path, metrics_server: str
    ) -> None:
        state = tmp_path / "state"
        env = {"LIA_REPORT_STATE_DIR": str(state), "LIA_CLOUDFLARED_METRICS_URL": metrics_server}

        first = _run_script(env, tmp_path)
        second = _run_script(env, tmp_path)

        assert first.returncode == 0 and second.returncode == 0
        assert "depuis le demarrage du tunnel" in first.stdout.decode("utf-8")
        kept = json.loads((state / CF.STATE_FILE_NAME).read_text(encoding="utf-8"))
        assert kept["counters"]["cloudflared_tunnel_total_requests"] == 19795
        # Same process, same counters: the second report covers the gap between
        # the two runs and found no new request in it.
        assert "Requetes             : 0" in second.stdout.decode("utf-8")

    def test_a_manual_run_keeps_nothing(self, tmp_path: Path, metrics_server: str) -> None:
        workdir = tmp_path / "cwd"
        workdir.mkdir()

        done = _run_script({"LIA_CLOUDFLARED_METRICS_URL": metrics_server}, tmp_path, cwd=workdir)

        assert done.returncode == 0
        assert "depuis le demarrage du tunnel" in done.stdout.decode("utf-8")
        assert list(workdir.iterdir()) == []
