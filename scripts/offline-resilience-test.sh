#!/usr/bin/env bash
# Offline resilience test for the kirelabs homelab.
#
# Run this AFTER disconnecting the WAN/internet cable:
#   ./scripts/offline-resilience-test.sh --duration 900 --interval 5
#
# The script is read-only. It does not restart, reconfigure, or control anything.
# It writes a live report plus CSV/raw logs to a timestamped result directory.
# Compatible with Bash 3.2 (including the Bash shipped with macOS).

set -u

DURATION=600
INTERVAL=5
MODEL_INTERVAL=300
MODEL_TIMEOUT=240
OUTPUT_BASE="${PWD}/offline-test-results"
GATEWAY="192.168.50.1"
DNS1="192.168.50.4"
DNS2="192.168.50.5"
HOMELAB="192.168.50.5"
AILAB="192.168.50.10"
HA_DOMAIN="homeassistant.kirelabs.org"
MA_DOMAIN="musicassistant.kirelabs.org"
LITELLM_DOMAIN="litellm.kirelabs.org"
LITELLM_URL="https://${LITELLM_DOMAIN}"
PI_AUTH_FILE="${PI_AGENT_AUTH_FILE:-${HOME}/.pi/agent/auth.json}"
PI_AUTH_PROFILE="litellm"
LITELLM_API_KEY_VALUE=""
LITELLM_KEY_SOURCE="Pi agent credential store"
SKIP_MODELS=0
CUSTOM_MODELS=0
EXTERNAL_DOMAIN="example.com"
STOP_REQUESTED=0
CYCLE=0
NEXT_MODEL_EPOCH=0

LITELLM_MODELS=(
  "Muse-Glimmer-30B-low"
  "Qwen3.8-27B-Instruct-medium"
  "home-hermes"
)

EXPECTED_LITELLM_MODELS=(
  "home-fast"
  "home-smart"
  "home-ha"
  "home-hermes"
  "home-vision"
  "home-embed"
  "Muse-Glimmer-30B-low"
  "Qwen3.8-27B-Instruct"
  "Qwen3.8-27B-Instruct-low"
  "Qwen3.8-27B-Instruct-medium"
  "Qwen3.8-27B-Instruct-nothink"
  "home-asr"
  "home-tts"
  "home-tts-design"
)

PROBE_IDS=()
PROBE_LABELS=()
PROBE_KINDS=()
OK_COUNTS=()
FAIL_COUNTS=()
SKIP_COUNTS=()
LAST_STATUS=()
MODEL_PROBE_IDS=()

usage() {
  cat <<'EOF'
Usage: offline-resilience-test.sh [options]

Options:
  --duration SECONDS   Total runtime (default: 600)
  --interval SECONDS   Delay between test cycles (default: 5)
  --model-interval SEC Run real LiteLLM model probes this often (default: 300)
  --model-timeout SEC  Timeout per model completion (default: 240)
  --pi-auth-file FILE  Pi agent credential store
                       (default: ~/.pi/agent/auth.json)
  --pi-auth-profile P  Credential profile (default: litellm)
  --litellm-model NAME Add/replace the default completion models; repeatable
  --skip-models        Skip authenticated LiteLLM catalog/completion probes
  --output-dir DIR     Parent directory for results
  -h, --help           Show this help

Example:
  ./scripts/offline-resilience-test.sh --duration 900 --interval 5

The LiteLLM access token and base URL are read from the Pi agent credential
store. The token is never logged or written to the result directory.
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
      DURATION="$2"; shift 2 ;;
    --interval)
      [ "$#" -ge 2 ] || { echo "Missing value for --interval" >&2; exit 2; }
      INTERVAL="$2"; shift 2 ;;
    --model-interval)
      [ "$#" -ge 2 ] || { echo "Missing value for --model-interval" >&2; exit 2; }
      MODEL_INTERVAL="$2"; shift 2 ;;
    --model-timeout)
      [ "$#" -ge 2 ] || { echo "Missing value for --model-timeout" >&2; exit 2; }
      MODEL_TIMEOUT="$2"; shift 2 ;;
    --pi-auth-file)
      [ "$#" -ge 2 ] || { echo "Missing value for --pi-auth-file" >&2; exit 2; }
      PI_AUTH_FILE="$2"; shift 2 ;;
    --pi-auth-profile)
      [ "$#" -ge 2 ] || { echo "Missing value for --pi-auth-profile" >&2; exit 2; }
      PI_AUTH_PROFILE="$2"; shift 2 ;;
    --litellm-model)
      [ "$#" -ge 2 ] || { echo "Missing value for --litellm-model" >&2; exit 2; }
      if [ "$CUSTOM_MODELS" -eq 0 ]; then
        LITELLM_MODELS=()
        CUSTOM_MODELS=1
      fi
      LITELLM_MODELS[${#LITELLM_MODELS[@]}]="$2"
      shift 2 ;;
    --skip-models)
      SKIP_MODELS=1; shift ;;
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

is_positive_integer "$DURATION" || { echo "--duration must be a positive integer" >&2; exit 2; }
is_positive_integer "$INTERVAL" || { echo "--interval must be a positive integer" >&2; exit 2; }
is_positive_integer "$MODEL_INTERVAL" || { echo "--model-interval must be a positive integer" >&2; exit 2; }
is_positive_integer "$MODEL_TIMEOUT" || { echo "--model-timeout must be a positive integer" >&2; exit 2; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

HAS_CURL=0; command_exists curl && HAS_CURL=1
HAS_DIG=0; command_exists dig && HAS_DIG=1
HAS_PING=0; command_exists ping && HAS_PING=1
HAS_NC=0; command_exists nc && HAS_NC=1
HAS_OPENSSL=0; command_exists openssl && HAS_OPENSSL=1
HAS_JQ=0; command_exists jq && HAS_JQ=1

if [ "$HAS_CURL" -eq 0 ] && [ "$HAS_DIG" -eq 0 ] && [ "$HAS_PING" -eq 0 ] && [ "$HAS_NC" -eq 0 ]; then
  echo "None of the required probe tools are installed (curl, dig, ping, nc)." >&2
  exit 1
fi

if [ "$SKIP_MODELS" -eq 0 ]; then
  [ "$HAS_JQ" -eq 1 ] || {
    echo "jq is required to read the Pi agent credential store (or use --skip-models)." >&2
    exit 1
  }
  [ -r "$PI_AUTH_FILE" ] || {
    echo "Pi agent credential store is not readable: $PI_AUTH_FILE" >&2
    exit 1
  }
  LITELLM_API_KEY_VALUE="$(jq -er --arg profile "$PI_AUTH_PROFILE" \
    '.[$profile].access | select(type == "string" and length > 0)' \
    "$PI_AUTH_FILE" 2>/dev/null)" || {
      echo "No access token found for Pi credential profile '$PI_AUTH_PROFILE'." >&2
      exit 1
    }
  STORE_LITELLM_URL="$(jq -er --arg profile "$PI_AUTH_PROFILE" \
    '.[$profile].baseUrl | select(type == "string" and length > 0)' \
    "$PI_AUTH_FILE" 2>/dev/null || true)"
  if [ -n "$STORE_LITELLM_URL" ]; then
    LITELLM_URL="${STORE_LITELLM_URL%/}"
    LITELLM_DOMAIN="$(printf '%s' "$LITELLM_URL" | sed -n 's#^[a-zA-Z][a-zA-Z0-9+.-]*://\([^/:]*\).*#\1#p')"
  fi
  [ -n "$LITELLM_DOMAIN" ] || {
    echo "Could not determine LiteLLM hostname from Pi credential store." >&2
    exit 1
  }
fi

case "$(uname -s 2>/dev/null || echo unknown)" in
  Darwin) PING_WAIT=2000 ;;
  *) PING_WAIT=2 ;;
esac

TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
RESULT_DIR="${OUTPUT_BASE%/}/${TIMESTAMP}"
CSV_FILE="${RESULT_DIR}/results.csv"
RAW_FILE="${RESULT_DIR}/raw.log"
SUMMARY_FILE="${RESULT_DIR}/summary.txt"
mkdir -p "$RESULT_DIR" || exit 1

cleanup_temp_files() {
  rm -f \
    "${RESULT_DIR}/http-body.tmp" \
    "${RESULT_DIR}/llamaswap-running.tmp" \
    "${RESULT_DIR}/litellm-models.tmp" \
    "${RESULT_DIR}/litellm-completion.tmp"
}
trap cleanup_temp_files EXIT

csv_escape() {
  printf '%s' "$1" | sed 's/"/""/g'
}

now_iso() { date '+%Y-%m-%dT%H:%M:%S%z'; }

add_probe() {
  PROBE_IDS[${#PROBE_IDS[@]}]="$1"
  PROBE_LABELS[${#PROBE_LABELS[@]}]="$2"
  PROBE_KINDS[${#PROBE_KINDS[@]}]="$3"
  OK_COUNTS[${#OK_COUNTS[@]}]=0
  FAIL_COUNTS[${#FAIL_COUNTS[@]}]=0
  SKIP_COUNTS[${#SKIP_COUNTS[@]}]=0
  LAST_STATUS[${#LAST_STATUS[@]}]="SKIP"
}

find_probe_index() {
  local wanted="$1" i=0
  while [ "$i" -lt "${#PROBE_IDS[@]}" ]; do
    if [ "${PROBE_IDS[$i]}" = "$wanted" ]; then
      printf '%s' "$i"
      return 0
    fi
    i=$((i + 1))
  done
  return 1
}

add_probe gateway_ping       "Gateway 192.168.50.1"                    "local_gateway"
add_probe dns1_ha            "DNS .4: Home Assistant"                   "local_dns"
add_probe dns1_ma            "DNS .4: Music Assistant"                  "local_dns"
add_probe dns1_litellm       "DNS .4: LiteLLM"                          "local_dns"
add_probe dns1_llamaswap     "DNS .4: LlamaSwap"                        "local_dns"
add_probe dns1_hermes        "DNS .4: Local Hermes"                     "local_dns"
add_probe dns1_external      "DNS .4: external domain"                  "wan_dns"
add_probe dns2_ha            "DNS .5: Home Assistant"                   "local_dns"
add_probe dns2_ma            "DNS .5: Music Assistant"                  "local_dns"
add_probe dns2_litellm       "DNS .5: LiteLLM"                          "local_dns"
add_probe dns2_llamaswap     "DNS .5: LlamaSwap"                        "local_dns"
add_probe dns2_hermes        "DNS .5: Local Hermes"                     "local_dns"
add_probe dns2_external      "DNS .5: external domain"                  "wan_dns"
add_probe caddy_tls          "Caddy HTTPS/TLS forced to .5"             "local_proxy"
add_probe ha_direct          "Home Assistant direct :8123"              "local_backend"
add_probe ha_domain          "Home Assistant via domain"                "local_domain"
add_probe ha_forced          "Home Assistant domain forced to .5"       "local_proxy"
add_probe ma_direct          "Music Assistant direct :8095"             "local_backend"
add_probe ma_domain          "Music Assistant via domain"               "local_domain"
add_probe ma_forced          "Music Assistant domain forced to .5"      "local_proxy"
add_probe ma_websocket       "Music Assistant /ws endpoint"             "local_websocket"
add_probe homepage_domain    "Homepage via domain"                      "local_service"
add_probe pocket_id_domain   "Pocket ID via domain"                     "local_service"
add_probe z2m_domain         "Zigbee2MQTT via domain"                   "local_service"
add_probe evcc_domain        "evcc via domain"                          "local_service"
add_probe immich_domain      "Immich via domain"                        "local_service"
add_probe jellyfin_domain    "Jellyfin via domain"                      "local_service"
add_probe seerr_domain       "Seerr via domain"                         "local_service"
add_probe pihole1_domain     "Pi-hole homelab UI via domain"            "local_service"
add_probe pihole2_domain     "Pi-hole nameserver UI via domain"         "local_service"
add_probe litellm_direct     "LiteLLM direct :4000 readiness"            "local_ai_backend"
add_probe litellm_domain     "LiteLLM domain readiness"                 "local_ai_domain"
add_probe litellm_forced     "LiteLLM forced to Caddy .5"               "local_ai_proxy"
add_probe llamaswap_direct   "LlamaSwap direct :9292 running"            "local_ai_backend"
add_probe llamaswap_domain   "LlamaSwap domain /running"                "local_ai_domain"
add_probe llamaswap_forced   "LlamaSwap forced to Caddy .5"             "local_ai_proxy"
add_probe llamaswap_qwen     "LlamaSwap Qwen backend ready"             "local_ai_runtime"
add_probe llamaswap_embed    "LlamaSwap embedding ready"                "local_ai_runtime"
add_probe llamaswap_asr      "LlamaSwap ASR ready"                      "local_ai_runtime"
add_probe llamaswap_tts      "LlamaSwap TTS ready"                      "local_ai_runtime"
add_probe hermes_api         "Local Hermes API /health"                 "local_agent"
add_probe hermes_domain      "Local Hermes dashboard via domain"        "local_agent"
add_probe hermes_forced      "Local Hermes forced to Caddy .5"          "local_agent"
add_probe t3_direct          "T3 Code direct :8093 environment"          "local_agent"
add_probe t3_domain          "T3 Code via domain"                       "local_agent"
add_probe mqtt_tcp           "Mosquitto 192.168.50.5:1883"              "local_service_tcp"
add_probe smb_tcp            "SMB 192.168.50.5:445"                     "local_service_tcp"
add_probe tapo_tcp           "Tapo camera 192.168.50.70:443"             "optional_iot"
add_probe nesthub_tcp        "Nest Hub 192.168.50.182:8009"              "optional_iot"
add_probe bathroom_cast_tcp  "Bathroom Cast 192.168.50.215:8009"        "optional_iot"
add_probe bedroom_cast_tcp   "Bedroom Cast 192.168.50.219:8009"         "optional_iot"
add_probe wan_ping           "WAN IP 1.1.1.1"                            "wan"
add_probe wan_https          "WAN HTTPS example.com"                    "wan"

if [ "$SKIP_MODELS" -eq 0 ]; then
  add_probe litellm_catalog  "Pi agent LiteLLM local model catalog"      "local_ai_auth"
  model_index=0
  while [ "$model_index" -lt "${#LITELLM_MODELS[@]}" ]; do
    model_probe_id="litellm_model_$((model_index + 1))"
    MODEL_PROBE_IDS[${#MODEL_PROBE_IDS[@]}]="$model_probe_id"
    add_probe "$model_probe_id" "LiteLLM completion: ${LITELLM_MODELS[$model_index]}" "local_ai_completion"
    model_index=$((model_index + 1))
  done
fi

printf 'timestamp,cycle,probe_id,label,kind,status,latency_ms,detail\n' > "$CSV_FILE"
{
  echo "Offline resilience test started: $(now_iso)"
  echo "Duration: ${DURATION}s; interval: ${INTERVAL}s"
  echo "Host: $(hostname 2>/dev/null || echo unknown)"
  echo "Tools: curl=$HAS_CURL dig=$HAS_DIG ping=$HAS_PING nc=$HAS_NC openssl=$HAS_OPENSSL jq=$HAS_JQ"
  if [ "$SKIP_MODELS" -eq 0 ]; then
    echo "LiteLLM credentials: ${LITELLM_KEY_SOURCE} profile=${PI_AUTH_PROFILE}"
    echo "LiteLLM URL: $LITELLM_URL"
    echo "Model interval: ${MODEL_INTERVAL}s; timeout per completion: ${MODEL_TIMEOUT}s"
    printf 'Completion models:'
    printf ' %s' "${LITELLM_MODELS[@]}"
    echo
  else
    echo "LiteLLM model probes: skipped by request"
  fi
  echo "Result directory: $RESULT_DIR"
  echo
} | tee -a "$RAW_FILE"

RESULT_STATUS="SKIP"
RESULT_LATENCY="-"
RESULT_DETAIL="not run"

set_result() {
  RESULT_STATUS="$1"
  RESULT_LATENCY="$2"
  RESULT_DETAIL="$3"
}

probe_ping() {
  local host="$1" output rc latency
  if [ "$HAS_PING" -eq 0 ]; then set_result "SKIP" "-" "ping not installed"; return; fi
  output="$(ping -c 1 -W "$PING_WAIT" "$host" 2>&1)"; rc=$?
  printf '[%s] ping %s\n%s\n\n' "$(now_iso)" "$host" "$output" >> "$RAW_FILE"
  latency="$(printf '%s\n' "$output" | sed -n 's/.*time[=<]\{0,1\}\([0-9.]*\) *ms.*/\1/p' | head -1)"
  [ -n "$latency" ] || latency="-"
  if [ "$rc" -eq 0 ]; then set_result "OK" "$latency" "reachable"; else set_result "FAIL" "$latency" "unreachable"; fi
}

probe_dns() {
  local server="$1" domain="$2" expected="$3" output rc answer latency
  if [ "$HAS_DIG" -eq 0 ]; then set_result "SKIP" "-" "dig not installed"; return; fi
  output="$(dig +time=2 +tries=1 +noall +answer +stats @"$server" "$domain" A 2>&1)"; rc=$?
  printf '[%s] dig @%s %s A\n%s\n\n' "$(now_iso)" "$server" "$domain" "$output" >> "$RAW_FILE"
  answer="$(printf '%s\n' "$output" | awk '$4 == "A" {print $5}' | paste -sd ';' -)"
  latency="$(printf '%s\n' "$output" | sed -n 's/^;; Query time: \([0-9][0-9]*\) msec$/\1/p' | head -1)"
  [ -n "$latency" ] || latency="-"
  if [ "$rc" -ne 0 ]; then
    set_result "FAIL" "$latency" "query failed"
  elif [ -z "$answer" ]; then
    set_result "FAIL" "$latency" "no A answer"
  elif [ -n "$expected" ] && ! printf '%s' "$answer" | grep -q "$expected"; then
    set_result "FAIL" "$latency" "unexpected: $answer"
  else
    set_result "OK" "$latency" "$answer"
  fi
}

probe_http() {
  local url="$1" resolve_arg="${2:-}" output rc code remote seconds latency detail
  if [ "$HAS_CURL" -eq 0 ]; then set_result "SKIP" "-" "curl not installed"; return; fi
  if [ -n "$resolve_arg" ]; then
    output="$(curl -sS -k -o /dev/null --connect-timeout 2 --max-time 4 --resolve "$resolve_arg" -w '%{http_code}|%{remote_ip}|%{time_total}' "$url" 2>>"$RAW_FILE")"; rc=$?
  else
    output="$(curl -sS -k -o /dev/null --connect-timeout 2 --max-time 4 -w '%{http_code}|%{remote_ip}|%{time_total}' "$url" 2>>"$RAW_FILE")"; rc=$?
  fi
  code="$(printf '%s' "$output" | cut -d'|' -f1)"
  remote="$(printf '%s' "$output" | cut -d'|' -f2)"
  seconds="$(printf '%s' "$output" | cut -d'|' -f3)"
  latency="$(awk -v s="$seconds" 'BEGIN {if (s ~ /^[0-9.]+$/) printf "%.0f", s*1000; else print "-"}')"
  detail="HTTP ${code:-000} remote=${remote:-none} curl_rc=$rc"
  printf '[%s] curl %s resolve=%s -> %s\n' "$(now_iso)" "$url" "${resolve_arg:-normal}" "$detail" >> "$RAW_FILE"
  case "$code" in
    2??|3??|401|403) set_result "OK" "$latency" "$detail" ;;
    *) set_result "FAIL" "$latency" "$detail" ;;
  esac
}

probe_http_keyword() {
  local url="$1" resolve_arg="$2" keyword="$3" body_file output rc code remote seconds latency detail
  if [ "$HAS_CURL" -eq 0 ]; then set_result "SKIP" "-" "curl not installed"; return; fi
  body_file="${RESULT_DIR}/http-body.tmp"
  if [ -n "$resolve_arg" ]; then
    output="$(curl -sS -k -o "$body_file" --connect-timeout 2 --max-time 8 \
      --resolve "$resolve_arg" -w '%{http_code}|%{remote_ip}|%{time_total}' \
      "$url" 2>>"$RAW_FILE")"; rc=$?
  else
    output="$(curl -sS -k -o "$body_file" --connect-timeout 2 --max-time 8 \
      -w '%{http_code}|%{remote_ip}|%{time_total}' "$url" 2>>"$RAW_FILE")"; rc=$?
  fi
  code="$(printf '%s' "$output" | cut -d'|' -f1)"
  remote="$(printf '%s' "$output" | cut -d'|' -f2)"
  seconds="$(printf '%s' "$output" | cut -d'|' -f3)"
  latency="$(awk -v s="$seconds" 'BEGIN {if (s ~ /^[0-9.]+$/) printf "%.0f", s*1000; else print "-"}')"
  detail="HTTP ${code:-000} remote=${remote:-none} keyword=$keyword curl_rc=$rc"
  printf '[%s] curl-keyword %s resolve=%s -> %s\n' \
    "$(now_iso)" "$url" "${resolve_arg:-normal}" "$detail" >> "$RAW_FILE"
  if [ "$rc" -eq 0 ] && printf '%s' "$code" | grep -Eq '^2[0-9][0-9]$' \
    && grep -Fq "$keyword" "$body_file" 2>/dev/null; then
    set_result "OK" "$latency" "$detail"
  else
    set_result "FAIL" "$latency" "$detail"
  fi
}

probe_llamaswap_model() {
  local model="$1" body_file output rc code seconds latency detail ready
  if [ "$HAS_CURL" -eq 0 ]; then set_result "SKIP" "-" "curl not installed"; return; fi
  body_file="${RESULT_DIR}/llamaswap-running.tmp"
  output="$(curl -sS -o "$body_file" --connect-timeout 2 --max-time 8 \
    -w '%{http_code}|%{time_total}' "http://${AILAB}:9292/running" 2>>"$RAW_FILE")"; rc=$?
  code="$(printf '%s' "$output" | cut -d'|' -f1)"
  seconds="$(printf '%s' "$output" | cut -d'|' -f2)"
  latency="$(awk -v s="$seconds" 'BEGIN {if (s ~ /^[0-9.]+$/) printf "%.0f", s*1000; else print "-"}')"
  ready=0
  if [ "$rc" -eq 0 ] && [ "$code" = "200" ]; then
    if [ "$HAS_JQ" -eq 1 ]; then
      jq -e --arg model "$model" \
        'any(.running[]?; .model == $model and .state == "ready")' \
        "$body_file" >/dev/null 2>&1 && ready=1
    elif grep -Fq "\"model\":\"$model\"" "$body_file" \
      && grep -Fq '"state":"ready"' "$body_file"; then
      ready=1
    fi
  fi
  detail="HTTP ${code:-000} model=$model state=$([ "$ready" -eq 1 ] && echo ready || echo unavailable) curl_rc=$rc"
  printf '[%s] llamaswap-running model=%s -> %s\n' "$(now_iso)" "$model" "$detail" >> "$RAW_FILE"
  if [ "$ready" -eq 1 ]; then set_result "OK" "$latency" "$detail"; else set_result "FAIL" "$latency" "$detail"; fi
}

probe_litellm_catalog() {
  local body_file output rc code seconds latency missing model detail
  if [ "$HAS_CURL" -eq 0 ] || [ "$HAS_JQ" -eq 0 ]; then
    set_result "SKIP" "-" "curl or jq not installed"
    return
  fi
  body_file="${RESULT_DIR}/litellm-models.tmp"
  output="$(printf 'header = "Authorization: Bearer %s"\n' "$LITELLM_API_KEY_VALUE" | \
    curl -sS -k --config - -o "$body_file" --connect-timeout 3 --max-time 15 \
      -w '%{http_code}|%{time_total}' "${LITELLM_URL}/v1/models" 2>>"$RAW_FILE")"; rc=$?
  code="$(printf '%s' "$output" | cut -d'|' -f1)"
  seconds="$(printf '%s' "$output" | cut -d'|' -f2)"
  latency="$(awk -v s="$seconds" 'BEGIN {if (s ~ /^[0-9.]+$/) printf "%.0f", s*1000; else print "-"}')"
  missing=""
  if [ "$rc" -eq 0 ] && [ "$code" = "200" ]; then
    for model in "${EXPECTED_LITELLM_MODELS[@]}"; do
      if ! jq -e --arg model "$model" 'any(.data[]?; .id == $model)' "$body_file" >/dev/null 2>&1; then
        missing="${missing}${missing:+;}${model}"
      fi
    done
  else
    missing="catalog request failed"
  fi
  if [ -z "$missing" ]; then
    detail="HTTP 200 all ${#EXPECTED_LITELLM_MODELS[@]} expected local routes visible"
    set_result "OK" "$latency" "$detail"
  else
    detail="HTTP ${code:-000} missing=${missing} curl_rc=$rc"
    set_result "FAIL" "$latency" "$detail"
  fi
  printf '[%s] litellm-catalog -> %s\n' "$(now_iso)" "$detail" >> "$RAW_FILE"
}

probe_litellm_completion() {
  local model="$1" marker="$2" body_file payload output rc code seconds latency response_model text_length error_detail detail
  if [ "$HAS_CURL" -eq 0 ] || [ "$HAS_JQ" -eq 0 ]; then
    set_result "SKIP" "-" "curl or jq not installed"
    return
  fi
  body_file="${RESULT_DIR}/litellm-completion.tmp"
  payload="$(jq -cn --arg model "$model" --arg marker "$marker" \
    '{model:$model,messages:[{role:"user",content:("Reply with exactly " + $marker + " and nothing else.")}],max_tokens:128,temperature:0,stream:false}')"
  output="$(printf 'header = "Authorization: Bearer %s"\n' "$LITELLM_API_KEY_VALUE" | \
    curl -sS -k --config - -o "$body_file" --connect-timeout 3 --max-time "$MODEL_TIMEOUT" \
      -H 'Content-Type: application/json' --data-binary "$payload" \
      -w '%{http_code}|%{time_total}' "${LITELLM_URL}/v1/chat/completions" 2>>"$RAW_FILE")"; rc=$?
  code="$(printf '%s' "$output" | cut -d'|' -f1)"
  seconds="$(printf '%s' "$output" | cut -d'|' -f2)"
  latency="$(awk -v s="$seconds" 'BEGIN {if (s ~ /^[0-9.]+$/) printf "%.0f", s*1000; else print "-"}')"
  response_model="$(jq -r '.model // "unknown"' "$body_file" 2>/dev/null || echo unknown)"
  text_length="$(jq -r '[.choices[0].message.content, .choices[0].message.reasoning_content] | map(select(type == "string")) | join("") | length' "$body_file" 2>/dev/null || echo 0)"
  detail="HTTP ${code:-000} requested=$model response=$response_model output_chars=$text_length curl_rc=$rc"
  if [ "$rc" -ne 0 ] || [ "$code" != "200" ]; then
    error_detail="$(jq -r '.error.message // .error.type // .detail // empty' "$body_file" 2>/dev/null \
      | tr '\r\n' ' ' | cut -c 1-180)"
    [ -z "$error_detail" ] || detail="${detail} error=${error_detail}"
  fi
  printf '[%s] litellm-completion model=%s -> %s\n' "$(now_iso)" "$model" "$detail" >> "$RAW_FILE"
  if [ "$rc" -eq 0 ] && [ "$code" = "200" ] \
    && jq -e --arg marker "$marker" \
      '([.choices[0].message.content, .choices[0].message.reasoning_content] | map(select(type == "string")) | join(" ")) | contains($marker)' \
      "$body_file" >/dev/null 2>&1; then
    set_result "OK" "$latency" "$detail"
  else
    set_result "FAIL" "$latency" "$detail"
  fi
}

probe_websocket() {
  local url="$1" resolve_arg="$2" output rc code remote seconds latency detail
  if [ "$HAS_CURL" -eq 0 ]; then set_result "SKIP" "-" "curl not installed"; return; fi
  output="$(curl --http1.1 -sS -k -o /dev/null --connect-timeout 2 --max-time 3 \
    --resolve "$resolve_arg" \
    -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
    -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
    -w '%{http_code}|%{remote_ip}|%{time_total}' "$url" 2>>"$RAW_FILE")"; rc=$?
  code="$(printf '%s' "$output" | cut -d'|' -f1)"
  remote="$(printf '%s' "$output" | cut -d'|' -f2)"
  seconds="$(printf '%s' "$output" | cut -d'|' -f3)"
  latency="$(awk -v s="$seconds" 'BEGIN {if (s ~ /^[0-9.]+$/) printf "%.0f", s*1000; else print "-"}')"
  detail="HTTP ${code:-000} remote=${remote:-none} curl_rc=$rc"
  printf '[%s] websocket %s -> %s\n' "$(now_iso)" "$url" "$detail" >> "$RAW_FILE"
  case "$code" in
    101|400|401|403|426) set_result "OK" "$latency" "$detail" ;;
    *) set_result "FAIL" "$latency" "$detail" ;;
  esac
}

probe_tcp() {
  local host="$1" port="$2" output rc
  if [ "$HAS_NC" -eq 0 ]; then set_result "SKIP" "-" "nc not installed"; return; fi
  output="$(nc -z -w 2 "$host" "$port" 2>&1)"; rc=$?
  printf '[%s] nc %s %s\n%s\n\n' "$(now_iso)" "$host" "$port" "$output" >> "$RAW_FILE"
  if [ "$rc" -eq 0 ]; then set_result "OK" "-" "TCP open"; else set_result "FAIL" "-" "TCP unavailable"; fi
}

record_result() {
  local id="$1" index label kind escaped_label escaped_detail ts
  index="$(find_probe_index "$id")" || return 1
  label="${PROBE_LABELS[$index]}"
  kind="${PROBE_KINDS[$index]}"
  LAST_STATUS[$index]="$RESULT_STATUS"
  case "$RESULT_STATUS" in
    OK) OK_COUNTS[$index]=$((OK_COUNTS[$index] + 1)) ;;
    FAIL) FAIL_COUNTS[$index]=$((FAIL_COUNTS[$index] + 1)) ;;
    *) SKIP_COUNTS[$index]=$((SKIP_COUNTS[$index] + 1)) ;;
  esac
  ts="$(now_iso)"
  escaped_label="$(csv_escape "$label")"
  escaped_detail="$(csv_escape "$RESULT_DETAIL")"
  printf '  %-5s %-39s %8s ms  %s\n' "$RESULT_STATUS" "$label" "$RESULT_LATENCY" "$RESULT_DETAIL"
  printf '"%s",%s,"%s","%s","%s","%s","%s","%s"\n' \
    "$ts" "$CYCLE" "$id" "$escaped_label" "$kind" "$RESULT_STATUS" "$RESULT_LATENCY" "$escaped_detail" >> "$CSV_FILE"
}

run_probe() {
  local id="$1" type="$2"; shift 2
  set_result "SKIP" "-" "not executed"
  case "$type" in
    ping) probe_ping "$@" ;;
    dns) probe_dns "$@" ;;
    http) probe_http "$@" ;;
    http_keyword) probe_http_keyword "$@" ;;
    llamaswap_model) probe_llamaswap_model "$@" ;;
    litellm_catalog) probe_litellm_catalog "$@" ;;
    litellm_completion) probe_litellm_completion "$@" ;;
    websocket) probe_websocket "$@" ;;
    tcp) probe_tcp "$@" ;;
  esac
  record_result "$id"
}

on_interrupt() {
  STOP_REQUESTED=1
  echo
  echo "Interrupt received; finishing current probe and writing summary..."
}
trap on_interrupt INT TERM

START_EPOCH="$(date '+%s')"
START_ISO="$(now_iso)"
END_EPOCH=$((START_EPOCH + DURATION))

while [ "$(date '+%s')" -lt "$END_EPOCH" ] && [ "$STOP_REQUESTED" -eq 0 ]; do
  CYCLE=$((CYCLE + 1))
  echo
  echo "Cycle $CYCLE — $(now_iso)"
  echo "  STATE LABEL                                    LATENCY     DETAIL"

  run_probe gateway_ping      ping "$GATEWAY"
  run_probe dns1_ha           dns "$DNS1" "$HA_DOMAIN" "$HOMELAB"
  run_probe dns1_ma           dns "$DNS1" "$MA_DOMAIN" "$HOMELAB"
  run_probe dns1_litellm      dns "$DNS1" "$LITELLM_DOMAIN" "$HOMELAB"
  run_probe dns1_llamaswap    dns "$DNS1" "llama-swap.kirelabs.org" "$HOMELAB"
  run_probe dns1_hermes       dns "$DNS1" "hermes-local.kirelabs.org" "$HOMELAB"
  run_probe dns1_external     dns "$DNS1" "$EXTERNAL_DOMAIN" ""
  run_probe dns2_ha           dns "$DNS2" "$HA_DOMAIN" "$HOMELAB"
  run_probe dns2_ma           dns "$DNS2" "$MA_DOMAIN" "$HOMELAB"
  run_probe dns2_litellm      dns "$DNS2" "$LITELLM_DOMAIN" "$HOMELAB"
  run_probe dns2_llamaswap    dns "$DNS2" "llama-swap.kirelabs.org" "$HOMELAB"
  run_probe dns2_hermes       dns "$DNS2" "hermes-local.kirelabs.org" "$HOMELAB"
  run_probe dns2_external     dns "$DNS2" "$EXTERNAL_DOMAIN" ""
  run_probe caddy_tls         http "https://${HA_DOMAIN}/" "${HA_DOMAIN}:443:${HOMELAB}"
  run_probe ha_direct         http "http://${HOMELAB}:8123/" ""
  run_probe ha_domain         http "https://${HA_DOMAIN}/" ""
  run_probe ha_forced         http "https://${HA_DOMAIN}/" "${HA_DOMAIN}:443:${HOMELAB}"
  run_probe ma_direct         http_keyword "http://${HOMELAB}:8095/info" "" '"status": "running"'
  run_probe ma_domain         http "https://${MA_DOMAIN}/" ""
  run_probe ma_forced         http "https://${MA_DOMAIN}/" "${MA_DOMAIN}:443:${HOMELAB}"
  run_probe ma_websocket      websocket "https://${MA_DOMAIN}/ws" "${MA_DOMAIN}:443:${HOMELAB}"
  run_probe homepage_domain   http "https://homepage.kirelabs.org/" ""
  run_probe pocket_id_domain  http "https://id.kirelabs.org/" ""
  run_probe z2m_domain        http "https://z2m.kirelabs.org/" ""
  run_probe evcc_domain       http "https://evcc.kirelabs.org/" ""
  run_probe immich_domain     http "https://immich.kirelabs.org/" ""
  run_probe jellyfin_domain   http "https://jellyfin.kirelabs.org/" ""
  run_probe seerr_domain      http "https://seerr.kirelabs.org/" ""
  run_probe pihole1_domain    http "https://pihole-homelab.kirelabs.org/admin/" ""
  run_probe pihole2_domain    http "https://pihole-nameserver.kirelabs.org/admin/" ""
  run_probe litellm_direct    http_keyword "http://${HOMELAB}:4000/health/readiness" "" '"db":"connected"'
  run_probe litellm_domain    http_keyword "${LITELLM_URL}/health/readiness" "" '"db":"connected"'
  run_probe litellm_forced    http_keyword "${LITELLM_URL}/health/readiness" "${LITELLM_DOMAIN}:443:${HOMELAB}" '"db":"connected"'
  run_probe llamaswap_direct  http_keyword "http://${AILAB}:9292/running" "" '"state":"ready"'
  run_probe llamaswap_domain  http_keyword "https://llama-swap.kirelabs.org/running" "" '"state":"ready"'
  run_probe llamaswap_forced  http_keyword "https://llama-swap.kirelabs.org/running" "llama-swap.kirelabs.org:443:${HOMELAB}" '"state":"ready"'
  run_probe llamaswap_qwen    llamaswap_model "Qwen3.8-27B-Instruct-AutoRound-vLLM"
  run_probe llamaswap_embed   llamaswap_model "qwen3-embedding"
  run_probe llamaswap_asr     llamaswap_model "whisper-large-v3-turbo-q8-crispasr"
  run_probe llamaswap_tts     llamaswap_model "qwen3-tts"
  run_probe hermes_api        http_keyword "http://127.0.0.1:8642/health" "" '"status": "ok"'
  run_probe hermes_domain     http "https://hermes-local.kirelabs.org/" ""
  run_probe hermes_forced     http "https://hermes-local.kirelabs.org/" "hermes-local.kirelabs.org:443:${HOMELAB}"
  run_probe t3_direct         http "http://${AILAB}:8093/.well-known/t3/environment" ""
  run_probe t3_domain         http "https://t3-ubuntu-ailab.kirelabs.org/.well-known/t3/environment" ""
  run_probe mqtt_tcp          tcp "$HOMELAB" "1883"
  run_probe smb_tcp           tcp "$HOMELAB" "445"
  run_probe tapo_tcp          tcp "192.168.50.70" "443"
  run_probe nesthub_tcp       tcp "192.168.50.182" "8009"
  run_probe bathroom_cast_tcp tcp "192.168.50.215" "8009"
  run_probe bedroom_cast_tcp  tcp "192.168.50.219" "8009"
  run_probe wan_ping          ping "1.1.1.1"
  run_probe wan_https         http "https://${EXTERNAL_DOMAIN}/" ""

  NOW_EPOCH="$(date '+%s')"
  if [ "$SKIP_MODELS" -eq 0 ] && [ "$NOW_EPOCH" -ge "$NEXT_MODEL_EPOCH" ]; then
    run_probe litellm_catalog litellm_catalog
    model_index=0
    while [ "$model_index" -lt "${#LITELLM_MODELS[@]}" ]; do
      model_probe_id="${MODEL_PROBE_IDS[$model_index]}"
      model_marker="OFFLINE_LITELLM_${CYCLE}_$((model_index + 1))_OK"
      run_probe "$model_probe_id" litellm_completion "${LITELLM_MODELS[$model_index]}" "$model_marker"
      model_index=$((model_index + 1))
    done
    NEXT_MODEL_EPOCH=$((NOW_EPOCH + MODEL_INTERVAL))
  fi

  [ "$STOP_REQUESTED" -eq 0 ] || break
  NOW_EPOCH="$(date '+%s')"
  [ "$NOW_EPOCH" -lt "$END_EPOCH" ] || break
  sleep "$INTERVAL"
done

rate_for() {
  local ok="$1" fail="$2" skip="$3" total
  total=$((ok + fail))
  if [ "$total" -eq 0 ]; then printf 'n/a'; else awk -v o="$ok" -v t="$total" 'BEGIN {printf "%.1f%%", (o*100)/t}'; fi
}

fail_count_for_id() {
  local idx
  idx="$(find_probe_index "$1")" || { echo 0; return; }
  echo "${FAIL_COUNTS[$idx]}"
}

ok_count_for_id() {
  local idx
  idx="$(find_probe_index "$1")" || { echo 0; return; }
  echo "${OK_COUNTS[$idx]}"
}

sum_fail_counts() {
  local total=0 id
  for id in "$@"; do total=$((total + $(fail_count_for_id "$id"))); done
  echo "$total"
}

sum_ok_counts() {
  local total=0 id
  for id in "$@"; do total=$((total + $(ok_count_for_id "$id"))); done
  echo "$total"
}

{
  echo "Offline resilience test summary"
  echo "Started:  $START_ISO"
  echo "Finished: $(now_iso)"
  echo "Cycles:   $CYCLE"
  echo
  printf '%-24s %-42s %6s %6s %6s %10s\n' "PROBE" "LABEL" "OK" "FAIL" "SKIP" "OK RATE"
  i=0
  while [ "$i" -lt "${#PROBE_IDS[@]}" ]; do
    printf '%-24s %-42s %6s %6s %6s %10s\n' \
      "${PROBE_IDS[$i]}" "${PROBE_LABELS[$i]}" \
      "${OK_COUNTS[$i]}" "${FAIL_COUNTS[$i]}" "${SKIP_COUNTS[$i]}" \
      "$(rate_for "${OK_COUNTS[$i]}" "${FAIL_COUNTS[$i]}" "${SKIP_COUNTS[$i]}")"
    i=$((i + 1))
  done
  echo
  echo "Interpretation"
  echo "--------------"

  WAN_FAILS="$(sum_fail_counts wan_ping wan_https)"
  WAN_OKS="$(sum_ok_counts wan_ping wan_https)"
  LOCAL_DNS_FAILS="$(sum_fail_counts \
    dns1_ha dns1_ma dns1_litellm dns1_llamaswap dns1_hermes \
    dns2_ha dns2_ma dns2_litellm dns2_llamaswap dns2_hermes)"
  FORCED_OK="$(sum_ok_counts ha_forced ma_forced litellm_forced llamaswap_forced hermes_forced)"
  DOMAIN_FAILS="$(sum_fail_counts \
    ha_domain ma_domain litellm_domain llamaswap_domain hermes_domain t3_domain)"
  BACKEND_FAILS="$(sum_fail_counts \
    ha_direct ma_direct litellm_direct llamaswap_direct hermes_api t3_direct)"
  SERVICE_FAILS="$(sum_fail_counts \
    homepage_domain pocket_id_domain z2m_domain evcc_domain immich_domain \
    jellyfin_domain seerr_domain pihole1_domain pihole2_domain mqtt_tcp smb_tcp)"
  AI_RUNTIME_FAILS="$(sum_fail_counts \
    llamaswap_qwen llamaswap_embed llamaswap_asr llamaswap_tts)"
  IOT_FAILS="$(sum_fail_counts tapo_tcp nesthub_tcp bathroom_cast_tcp bedroom_cast_tcp)"
  GATEWAY_FAILS="$(fail_count_for_id gateway_ping)"
  MODEL_FAILS=0
  MODEL_MISSING=0
  if [ "$SKIP_MODELS" -eq 0 ]; then
    MODEL_FAILS="$(fail_count_for_id litellm_catalog)"
    [ "$(ok_count_for_id litellm_catalog)" -gt 0 ] || MODEL_MISSING=$((MODEL_MISSING + 1))
    for model_probe_id in "${MODEL_PROBE_IDS[@]}"; do
      MODEL_FAILS=$((MODEL_FAILS + $(fail_count_for_id "$model_probe_id")))
      [ "$(ok_count_for_id "$model_probe_id")" -gt 0 ] || MODEL_MISSING=$((MODEL_MISSING + 1))
    done
  fi
  # Consumer devices may be asleep or powered off even on a healthy LAN. Keep
  # their results as diagnostic evidence without making them acceptance gates.
  LOCAL_FAILURES=$((LOCAL_DNS_FAILS + DOMAIN_FAILS + BACKEND_FAILS + SERVICE_FAILS + AI_RUNTIME_FAILS + MODEL_FAILS + MODEL_MISSING + GATEWAY_FAILS))

  if [ "$WAN_FAILS" -gt 0 ] && [ "$WAN_OKS" -eq 0 ] && [ "$LOCAL_FAILURES" -eq 0 ]; then
    echo "- Expected resilient state: WAN stayed offline while all tested local paths and runtimes remained available."
  fi
  if [ "$LOCAL_DNS_FAILS" -gt 0 ] && [ "$FORCED_OK" -gt 0 ]; then
    echo "- Local DNS problem: forced Caddy/backend access worked while local service-name resolution failed."
  fi
  if [ "$DOMAIN_FAILS" -gt 0 ] && [ "$FORCED_OK" -gt 0 ]; then
    echo "- Normal domain path failed but --resolve worked: investigate client DNS, DoH/Private DNS, or resolver selection."
  fi
  if [ "$BACKEND_FAILS" -gt 0 ]; then
    echo "- One or more direct local backends failed; this is not a DNS-only problem."
  fi
  if [ "$SERVICE_FAILS" -gt 0 ]; then
    echo "- One or more additional local services failed through their normal LAN domain or TCP endpoint."
  fi
  if [ "$AI_RUNTIME_FAILS" -gt 0 ]; then
    echo "- One or more persistent Ailab runtimes (Qwen, embedding, ASR, TTS) were not ready."
  fi
  if [ "$MODEL_FAILS" -gt 0 ] || [ "$MODEL_MISSING" -gt 0 ]; then
    echo "- Pi-agent LiteLLM catalog or real local model completions failed."
  fi
  if [ "$IOT_FAILS" -gt 0 ]; then
    echo "- Optional IoT/Cast probes failed. These devices may be asleep/off; inspect them if WLAN resilience is part of this run."
  fi
  if [ "$GATEWAY_FAILS" -gt 0 ] && [ "$IOT_FAILS" -gt 0 ]; then
    echo "- Gateway and local devices failed together: strong indication of router/LAN/WLAN disruption, not merely WAN loss."
  fi
  if [ "$WAN_OKS" -gt 0 ] || [ "$WAN_FAILS" -eq 0 ]; then
    echo "- WAN was reachable during the run; this is not a valid cable-disconnected acceptance test."
  fi
  echo "- External DNS/HTTPS failures are expected after disconnecting WAN and do not count as a local resilience failure."
  echo
  if [ "$WAN_FAILS" -gt 0 ] && [ "$WAN_OKS" -eq 0 ] && [ "$LOCAL_FAILURES" -eq 0 ]; then
    OVERALL_STATUS="PASS"
    echo "OVERALL: PASS — confirmed offline and all required local probes passed."
  else
    OVERALL_STATUS="FAIL"
    echo "OVERALL: FAIL — see failed probes and interpretation above."
  fi
  echo
  echo "Files"
  echo "-----"
  echo "CSV:     $CSV_FILE"
  echo "Raw log: $RAW_FILE"
} > "$SUMMARY_FILE"

cat "$SUMMARY_FILE"
echo
echo "Results saved in: $RESULT_DIR"

if [ "$STOP_REQUESTED" -ne 0 ]; then exit 130; fi
[ "$OVERALL_STATUS" = "PASS" ]
