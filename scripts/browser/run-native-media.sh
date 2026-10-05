#!/usr/bin/env bash
# Native audio and hermetic STUN for the engine-diverse Playwright matrix.
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo 'usage: run-native-media.sh <command> [arguments...]' >&2
  exit 2
fi
if ! command -v pulseaudio >/dev/null || ! command -v turnserver >/dev/null; then
  if [[ -f /.dockerenv && $(id -u) -eq 0 ]]; then
    apt-get update -qq
    apt-get install -y --no-install-recommends pulseaudio coturn
  else
    echo 'The native-media matrix requires pulseaudio and coturn (provided in the test container).' >&2
    exit 2
  fi
fi

media_dir=$(mktemp -d /tmp/lia-e2e-media.XXXXXX)
browser_scripts=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
media_ip=$(hostname -I | awk '{print $1}')
if [[ -z "$media_ip" || "$media_ip" == 127.* ]]; then
  echo 'Native WebRTC needs a non-loopback interface for its local STUN candidates.' >&2
  exit 2
fi
pulse_pid=''
stun_pid=''
bus_pid=''
cleanup() {
  result=$?
  trap - EXIT
  [[ -z "$stun_pid" ]] || kill "$stun_pid" 2>/dev/null || true
  [[ -z "$pulse_pid" ]] || kill "$pulse_pid" 2>/dev/null || true
  [[ -z "$bus_pid" ]] || kill "$bus_pid" 2>/dev/null || true
  wait 2>/dev/null || true
  case "$media_dir" in /tmp/lia-e2e-media.*) rm -rf -- "$media_dir" ;; esac
  exit "$result"
}
trap cleanup EXIT

# No physical device is needed: real browser audio still runs through a native sink.
mkdir "$media_dir/runtime"
mkdir "$media_dir/config"
chmod 700 "$media_dir/runtime"
pulse_command=(pulseaudio --daemonize=no --exit-idle-time=-1 --log-level=error -n
  -L "module-native-protocol-unix socket=$media_dir/pulse.socket auth-anonymous=1"
  -L 'module-null-sink sink_name=lia_e2e')
if [[ $(id -u) -eq 0 ]]; then
  if [[ -f /.dockerenv && ! -S /run/dbus/system_bus_socket ]]; then
    mkdir -p /run/dbus
    bus_pid=$(dbus-daemon --system --fork --nopidfile --print-pid)
  fi
  chown -R pulse:pulse "$media_dir"
  runuser -u pulse -- env XDG_RUNTIME_DIR="$media_dir/runtime" XDG_CONFIG_HOME="$media_dir/config" "${pulse_command[@]}" >"$media_dir/pulse.log" 2>&1 &
else
  XDG_RUNTIME_DIR="$media_dir/runtime" XDG_CONFIG_HOME="$media_dir/config" "${pulse_command[@]}" >"$media_dir/pulse.log" 2>&1 &
fi
pulse_pid=$!
export PULSE_SERVER="unix:$media_dir/pulse.socket"
for attempt in {1..30}; do
  if pactl info >/dev/null 2>&1; then break; fi
  sleep 0.1
done
if ! pactl info >/dev/null 2>&1; then
  cat "$media_dir/pulse.log" >&2
  exit 1
fi

# STUN only: no relay or outside service. WebKit rejects loopback candidates.
turnserver -n --stun-only --relay-threads=0 --no-tls --no-dtls --no-cli --listening-ip="$media_ip" \
  --listening-port=3478 --log-file=stdout --pidfile="$media_dir/stun.pid" >"$media_dir/stun.log" 2>&1 &
stun_pid=$!
export SIMLI_TEST_ICE_URL="stun:$media_ip:3478"
for attempt in {1..30}; do
  if node "$browser_scripts/stun-ready.mjs" "$media_ip" 3478; then break; fi
  sleep 0.1
done
if ! kill -0 "$stun_pid" 2>/dev/null || ! node "$browser_scripts/stun-ready.mjs" "$media_ip" 3478; then
  cat "$media_dir/stun.log" >&2
  exit 1
fi
echo 'Native-media matrix ready: virtual audio sink and local STUN.'
"$@"
