#!/usr/bin/env bash
# Interactive, model-free WAN outage test for the two Pi-hole resolvers.
# Run this on ailab-ubuntu while the WAN is still connected.

set -uo pipefail

OFFLINE_DURATION=300
INTERVAL=5
RECOVERY_TIMEOUT=300
BASELINE_ONLY=0
OUTPUT_BASE="${PWD}/offline-test-results"
DNS_SERVERS=("192.168.50.4" "192.168.50.5")
LOCAL_DOMAINS=("musicassistant.kirelabs.org" "t3-ubuntu-ailab.kirelabs.org")
RESULT_DIR=""
CSV_FILE=""
SESSION_LOG=""
SUMMARY_FILE=""
RUN_START_ISO=""
WAN_DISCONNECTED=0
BASELINE_LOCAL_FAILURES=0
OFFLINE_LOCAL_FAILURES=0
OFFLINE_WAN_SUCCESSES=0
OFFLINE_CYCLES=0
RECOVERED=0
RECOVERY_LOCAL_FAILURES=0
IPAD_OK=0

usage() {
  cat <<'EOF'
Usage: pihole-wan-resilience-test.sh [options]

Interactive phases:
  1. Capture an online baseline and prime DNS caches.
  2. Ask you to disconnect only the WAN and press Enter.
  3. Test both Pi-holes and local services without using any LLM.
  4. Ask you to reconnect WAN and press Enter.
  5. Capture DNS/Internet recovery and filtered Pi-hole diagnostics.

Options:
  --duration SECONDS          Offline test duration (default: 300)
  --interval SECONDS          Delay between cycles (default: 5)
  --recovery-timeout SECONDS  Maximum WAN recovery wait (default: 300)
  --baseline-only             Capture and validate only the online baseline
  --output-dir DIR            Result parent (default: ./offline-test-results)
  -h, --help                  Show this help

Run from ailab-ubuntu before disconnecting WAN:
  cd /home/daniel/code/pi
  ./scripts/pihole-wan-resilience-test.sh --duration 300
EOF
}

is_positive_integer() {
  case "$1" in
    ''|*[!0-9]*|0) return 1 ;;
    *) return 0 ;;
  esac
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --duration)
      [ "$#" -ge 2 ] || { echo "Missing value for --duration" >&2; exit 2; }
      OFFLINE_DURATION="$2"; shift 2 ;;
    --interval)
      [ "$#" -ge 2 ] || { echo "Missing value for --interval" >&2; exit 2; }
      INTERVAL="$2"; shift 2 ;;
    --recovery-timeout)
      [ "$#" -ge 2 ] || { echo "Missing value for --recovery-timeout" >&2; exit 2; }
      RECOVERY_TIMEOUT="$2"; shift 2 ;;
    --baseline-only)
      BASELINE_ONLY=1; shift ;;
    --output-dir)
      [ "$#" -ge 2 ] || { echo "Missing value for --output-dir" >&2; exit 2; }
      OUTPUT_BASE="$2"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2 ;;
  esac
done

is_positive_integer "$OFFLINE_DURATION" || { echo "--duration must be a positive integer" >&2; exit 2; }
is_positive_integer "$INTERVAL" || { echo "--interval must be a positive integer" >&2; exit 2; }
is_positive_integer "$RECOVERY_TIMEOUT" || { echo "--recovery-timeout must be a positive integer" >&2; exit 2; }

for command_name in dig curl ping ssh; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Required command is missing: $command_name" >&2
    exit 1
  }
done

if [ "$BASELINE_ONLY" -eq 0 ] && [ ! -t 0 ]; then
  echo "This test is interactive and must run in a terminal." >&2
  exit 1
fi

now_iso() { date '+%Y-%m-%dT%H:%M:%S%z'; }
csv_escape() { printf '%s' "$1" | sed 's/"/""/g'; }

TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
RESULT_DIR="${OUTPUT_BASE%/}/pihole-wan-${TIMESTAMP}"
CSV_FILE="${RESULT_DIR}/probes.csv"
SESSION_LOG="${RESULT_DIR}/session.log"
SUMMARY_FILE="${RESULT_DIR}/summary.txt"
RUN_START_ISO="$(now_iso)"
mkdir -p "$RESULT_DIR" || exit 1
printf 'timestamp,phase,cycle,probe,status,detail\n' > "$CSV_FILE"
exec > >(tee -a "$SESSION_LOG") 2>&1

on_interrupt() {
  echo
  echo "Test interrupted."
  if [ "$WAN_DISCONNECTED" -eq 1 ]; then
    echo "IMPORTANT: Reconnect the WAN cable before leaving the test."
  fi
  echo "Partial results: $RESULT_DIR"
  exit 130
}
trap on_interrupt INT TERM

record_probe() {
  local phase="$1" cycle="$2" probe="$3" status="$4" detail="$5"
  printf '"%s","%s",%s,"%s","%s","%s"\n' \
    "$(now_iso)" "$(csv_escape "$phase")" "$cycle" \
    "$(csv_escape "$probe")" "$status" "$(csv_escape "$detail")" >> "$CSV_FILE"
  printf '  %-5s %-46s %s\n' "$status" "$probe" "$detail"
}

probe_dns() {
  local phase="$1" cycle="$2" server="$3" domain="$4" rrtype="$5"
  local output rc status answers result detail
  output="$(dig +time=2 +tries=1 +noall +comments +answer @"$server" "$domain" "$rrtype" 2>&1)"; rc=$?
  status="$(printf '%s\n' "$output" | awk '/status:/{gsub(/,/,"",$6); print $6; exit}')"
  answers="$(printf '%s\n' "$output" | awk '$4 ~ /^(A|AAAA|CNAME|HTTPS|SVCB)$/ {print $4 "=" $5}' | paste -sd ';' -)"
  result=FAIL
  if [ "$rc" -eq 0 ] && [ "$status" = "NOERROR" ]; then
    if [ "$rrtype" = "A" ]; then
      printf '%s\n' "$output" | grep -q '192\.168\.50\.5' && result=OK
    else
      printf '%s\n' "$output" | grep -q 'homelab-nuc\.lan\.' && result=OK
    fi
  fi
  detail="server=$server type=$rrtype dns_status=${status:-NO_REPLY} answers=${answers:-none}"
  record_probe "$phase" "$cycle" "DNS $domain" "$result" "$detail"
  [ "$result" = "OK" ]
}

probe_external_dns() {
  local phase="$1" cycle="$2" server="$3" output rc status answers result
  output="$(dig +time=2 +tries=1 +noall +comments +answer @"$server" example.com A 2>&1)"; rc=$?
  status="$(printf '%s\n' "$output" | awk '/status:/{gsub(/,/,"",$6); print $6; exit}')"
  answers="$(printf '%s\n' "$output" | awk '$4 == "A" {print $5}' | paste -sd ';' -)"
  result=FAIL
  [ "$rc" -eq 0 ] && [ "$status" = "NOERROR" ] && [ -n "$answers" ] && result=OK
  record_probe "$phase" "$cycle" "External DNS example.com" "$result" \
    "server=$server dns_status=${status:-NO_REPLY} answers=${answers:-none} (informational during outage)"
  [ "$result" = "OK" ]
}

probe_http() {
  local phase="$1" cycle="$2" label="$3" url="$4" resolve_arg="${5:-}"
  local output rc code remote seconds result detail
  if [ -n "$resolve_arg" ]; then
    output="$(curl -ksS --connect-timeout 2 --max-time 6 --resolve "$resolve_arg" \
      -o /dev/null -w '%{http_code}|%{remote_ip}|%{time_total}' "$url" 2>/dev/null)"; rc=$?
  else
    output="$(curl -ksS --connect-timeout 2 --max-time 6 \
      -o /dev/null -w '%{http_code}|%{remote_ip}|%{time_total}' "$url" 2>/dev/null)"; rc=$?
  fi
  code="$(printf '%s' "$output" | cut -d'|' -f1)"
  remote="$(printf '%s' "$output" | cut -d'|' -f2)"
  seconds="$(printf '%s' "$output" | cut -d'|' -f3)"
  result=FAIL
  case "$code" in 2??|3??|401|403) result=OK ;; esac
  detail="HTTP ${code:-000} remote=${remote:-none} time=${seconds:-unknown} curl_rc=$rc"
  record_probe "$phase" "$cycle" "$label" "$result" "$detail"
  [ "$result" = "OK" ]
}

probe_wan_ping() {
  local phase="$1" cycle="$2" result=FAIL detail="unreachable"
  if ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1; then result=OK; detail="reachable"; fi
  record_probe "$phase" "$cycle" "WAN ping 1.1.1.1" "$result" "$detail"
  [ "$result" = "OK" ]
}

probe_wan_https() {
  local phase="$1" cycle="$2" code result=FAIL
  code="$(curl -sS --connect-timeout 2 --max-time 4 -o /dev/null -w '%{http_code}' https://example.com/ 2>/dev/null || true)"
  case "$code" in 2??|3??) result=OK ;; esac
  record_probe "$phase" "$cycle" "WAN HTTPS example.com" "$result" "HTTP ${code:-000}"
  [ "$result" = "OK" ]
}

run_local_matrix() {
  local phase="$1" cycle="$2" server domain rrtype failures=0
  for server in "${DNS_SERVERS[@]}"; do
    for domain in "${LOCAL_DOMAINS[@]}"; do
      for rrtype in A AAAA HTTPS SVCB; do
        probe_dns "$phase" "$cycle" "$server" "$domain" "$rrtype" || failures=$((failures + 1))
      done
    done
    probe_external_dns "$phase" "$cycle" "$server" || true
  done
  probe_http "$phase" "$cycle" "Music Assistant normal DNS" \
    "https://musicassistant.kirelabs.org/" || failures=$((failures + 1))
  probe_http "$phase" "$cycle" "Music Assistant forced Caddy" \
    "https://musicassistant.kirelabs.org/" "musicassistant.kirelabs.org:443:192.168.50.5" || failures=$((failures + 1))
  probe_http "$phase" "$cycle" "T3 Code normal DNS" \
    "https://t3-ubuntu-ailab.kirelabs.org/.well-known/t3/environment" || failures=$((failures + 1))
  probe_http "$phase" "$cycle" "T3 Code forced Caddy" \
    "https://t3-ubuntu-ailab.kirelabs.org/.well-known/t3/environment" \
    "t3-ubuntu-ailab.kirelabs.org:443:192.168.50.5" || failures=$((failures + 1))
  return "$failures"
}

remote_pihole_snapshot() {
  local target="$1" mode="$2" since="$3"
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$target" "bash -s -- '$mode' '$since'" <<'REMOTE'
set -u
mode="$1"
since="$2"
docker_cmd() {
  if [ "$mode" = "sudo" ]; then sudo -n docker "$@"; else docker "$@"; fi
}
echo "host=$(hostname) time=$(date -Is)"
docker_cmd inspect --format 'container={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} restarts={{.RestartCount}}' pihole
docker_cmd exec pihole pihole-FTL dnsmasq-test 2>&1
echo -n 'cache_optimizer='; docker_cmd exec pihole pihole-FTL --config dns.cache.optimizer 2>&1
echo -n 'rate_limit='; docker_cmd exec pihole pihole-FTL --config dns.rateLimit 2>&1 | paste -sd ',' -
echo 'resilience_directives:'
docker_cmd exec pihole sh -c 'grep -Rhs -E "^(use-stale-cache|dns-forward-max)=" /etc/pihole/dnsmasq.conf /etc/dnsmasq.d/*.conf' 2>&1
echo 'filtered warnings since test start:'
docker_cmd logs --since "$since" pihole 2>&1 \
  | grep -Ei 'Maximum number of concurrent DNS queries|Connection error|illegal|syntax|SERVFAIL|no servers could be reached|fatal|unhealthy' \
  | tail -200 || true
REMOTE
}

collect_diagnostics() {
  local phase="$1" file
  file="${RESULT_DIR}/pihole-${phase}.log"
  echo
  echo "Collecting Pi-hole diagnostics: $phase"
  {
    echo "=== Pi-hole .5 / homelab-nuc ==="
    remote_pihole_snapshot root@192.168.50.5 direct "$RUN_START_ISO" || echo "ERROR: could not collect .5 diagnostics"
    echo
    echo "=== Pi-hole .4 / nameserver-pi ==="
    remote_pihole_snapshot daniel@192.168.50.4 sudo "$RUN_START_ISO" || echo "ERROR: could not collect .4 diagnostics"
  } > "$file" 2>&1
  grep -E '^(===|host=|container=|dnsmasq:|cache_optimizer=|rate_limit=|use-stale-cache=|dns-forward-max=|ERROR:)' "$file" || true
  echo "Diagnostic file: $file"
}

wan_is_up() {
  curl -sS --connect-timeout 2 --max-time 4 -o /dev/null https://example.com/ >/dev/null 2>&1
}

wait_for_wan_state() {
  local wanted="$1" timeout="$2" deadline now
  deadline=$(( $(date '+%s') + timeout ))
  while :; do
    if [ "$wanted" = "down" ]; then
      wan_is_up || return 0
    else
      wan_is_up && return 0
    fi
    now="$(date '+%s')"
    [ "$now" -lt "$deadline" ] || return 1
    sleep 2
  done
}

echo "Pi-hole WAN resilience test"
echo "Started:          $RUN_START_ISO"
echo "Host:             $(hostname)"
echo "Offline duration: ${OFFLINE_DURATION}s"
echo "Result directory: $RESULT_DIR"
echo "Models:           disabled (this test has no LLM dependency)"
echo

echo "=== Phase 1: online baseline ==="
probe_wan_ping baseline 0 || true
probe_wan_https baseline 0 || true
run_local_matrix baseline 0 || BASELINE_LOCAL_FAILURES=$?
collect_diagnostics baseline

if [ "$BASELINE_LOCAL_FAILURES" -ne 0 ]; then
  echo
  echo "ERROR: Baseline has $BASELINE_LOCAL_FAILURES required local failure(s)."
  echo "Fix the online baseline before disconnecting WAN."
  exit 1
fi

if ! wan_is_up; then
  echo
  echo "ERROR: WAN is not reachable during baseline. Reconnect WAN and rerun."
  exit 1
fi

if [ "$BASELINE_ONLY" -eq 1 ]; then
  echo
  echo "BASELINE: PASS"
  echo "Results saved in: $RESULT_DIR"
  exit 0
fi

cat <<'EOF'

Baseline complete.

1. Disconnect ONLY the WAN/internet cable. Keep router, LAN and Wi-Fi running.
2. Keep this terminal open.
3. Press Enter after the WAN cable is disconnected.
EOF
if ! read -r _; then
  echo "No WAN-disconnect confirmation received; aborting without starting the offline phase."
  exit 1
fi
WAN_DISCONNECTED=1

if ! wait_for_wan_state down 60; then
  echo "ERROR: WAN still appears reachable after 60 seconds."
  echo "Reconnect/check cabling, then rerun the test."
  exit 1
fi

echo
echo "=== Phase 2: offline test ==="
echo "WAN loss confirmed. During this phase, open these on the iPad:"
echo "  - https://musicassistant.kirelabs.org"
echo "  - https://t3-ubuntu-ailab.kirelabs.org"
echo

OFFLINE_START_EPOCH="$(date '+%s')"
OFFLINE_END_EPOCH=$((OFFLINE_START_EPOCH + OFFLINE_DURATION))
while [ "$(date '+%s')" -lt "$OFFLINE_END_EPOCH" ]; do
  OFFLINE_CYCLES=$((OFFLINE_CYCLES + 1))
  echo
  echo "Offline cycle $OFFLINE_CYCLES — $(now_iso)"
  if probe_wan_ping offline "$OFFLINE_CYCLES"; then OFFLINE_WAN_SUCCESSES=$((OFFLINE_WAN_SUCCESSES + 1)); fi
  if probe_wan_https offline "$OFFLINE_CYCLES"; then OFFLINE_WAN_SUCCESSES=$((OFFLINE_WAN_SUCCESSES + 1)); fi
  cycle_failures=0
  run_local_matrix offline "$OFFLINE_CYCLES" || cycle_failures=$?
  OFFLINE_LOCAL_FAILURES=$((OFFLINE_LOCAL_FAILURES + cycle_failures))
  [ "$(date '+%s')" -lt "$OFFLINE_END_EPOCH" ] || break
  sleep "$INTERVAL"
done
collect_diagnostics offline

echo
printf 'Did BOTH Music Assistant and T3 Code work on the iPad? [y/N] '
if read -r ipad_answer; then
  case "$ipad_answer" in y|Y|yes|YES|ja|JA) IPAD_OK=1 ;; esac
else
  echo
  echo "No iPad result received."
fi

cat <<'EOF'

Offline phase complete.

1. Reconnect the WAN/internet cable.
2. Press Enter after the cable is connected.
EOF
if ! read -r _; then
  echo "No WAN-reconnect confirmation received."
  echo "IMPORTANT: Reconnect the WAN cable before leaving the test."
  exit 1
fi
WAN_DISCONNECTED=0

echo
echo "=== Phase 3: WAN recovery ==="
if wait_for_wan_state up "$RECOVERY_TIMEOUT"; then
  RECOVERED=1
  echo "WAN HTTPS recovered."
else
  echo "WAN did not recover within ${RECOVERY_TIMEOUT}s."
fi
probe_wan_ping recovery 0 || true
probe_wan_https recovery 0 || true
run_local_matrix recovery 0 || RECOVERY_LOCAL_FAILURES=$?
collect_diagnostics recovery

MAX_CONCURRENT_WARNINGS="$(grep -hi 'Maximum number of concurrent DNS queries' \
  "${RESULT_DIR}/pihole-recovery.log" 2>/dev/null | wc -l | tr -d '[:space:]')"
CONFIG_ERRORS="$(grep -hEi 'illegal repeated keyword|syntax check failed|fatal|unhealthy' \
  "${RESULT_DIR}/pihole-recovery.log" 2>/dev/null | wc -l | tr -d '[:space:]')"

OFFLINE_STATUS=PASS
[ "$OFFLINE_CYCLES" -gt 0 ] || OFFLINE_STATUS=FAIL
[ "$OFFLINE_LOCAL_FAILURES" -eq 0 ] || OFFLINE_STATUS=FAIL
[ "$OFFLINE_WAN_SUCCESSES" -eq 0 ] || OFFLINE_STATUS=FAIL
[ "$MAX_CONCURRENT_WARNINGS" -eq 0 ] || OFFLINE_STATUS=FAIL
[ "$CONFIG_ERRORS" -eq 0 ] || OFFLINE_STATUS=FAIL
[ "$IPAD_OK" -eq 1 ] || OFFLINE_STATUS=FAIL

RECOVERY_STATUS=PASS
[ "$RECOVERED" -eq 1 ] || RECOVERY_STATUS=FAIL
[ "$RECOVERY_LOCAL_FAILURES" -eq 0 ] || RECOVERY_STATUS=FAIL

OVERALL=PASS
[ "$OFFLINE_STATUS" = "PASS" ] || OVERALL=FAIL
[ "$RECOVERY_STATUS" = "PASS" ] || OVERALL=FAIL

{
  echo "Pi-hole WAN resilience summary"
  echo "Started:                         $RUN_START_ISO"
  echo "Finished:                        $(now_iso)"
  echo "Offline cycles:                  $OFFLINE_CYCLES"
  echo "Offline required-local failures: $OFFLINE_LOCAL_FAILURES"
  echo "Unexpected offline WAN successes:$OFFLINE_WAN_SUCCESSES"
  echo "Max-concurrent DNS warnings:     $MAX_CONCURRENT_WARNINGS"
  echo "Configuration errors:            $CONFIG_ERRORS"
  echo "iPad services passed:            $IPAD_OK"
  echo "WAN recovered:                   $RECOVERED"
  echo "Recovery local failures:         $RECOVERY_LOCAL_FAILURES"
  echo
  echo "OFFLINE:  $OFFLINE_STATUS"
  echo "RECOVERY: $RECOVERY_STATUS"
  echo "OVERALL:  $OVERALL"
  echo
  echo "Files:"
  echo "  Probe CSV:          $CSV_FILE"
  echo "  Session log:        $SESSION_LOG"
  echo "  Baseline Pi-hole:   ${RESULT_DIR}/pihole-baseline.log"
  echo "  Offline Pi-hole:    ${RESULT_DIR}/pihole-offline.log"
  echo "  Recovery Pi-hole:   ${RESULT_DIR}/pihole-recovery.log"
} > "$SUMMARY_FILE"

cat "$SUMMARY_FILE"
echo
echo "Results saved in: $RESULT_DIR"

[ "$OVERALL" = "PASS" ]
