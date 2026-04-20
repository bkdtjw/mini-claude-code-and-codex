#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
ENV_FILE="${PROJECT_DIR}/.env"
SERVICE_NAME="${1:-${SERVICE_NAME:-agent-studio}}"
SERVICE_UNIT="${SERVICE_NAME%.service}.service"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"
require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "Please run this script as root or with sudo."
        exit 1
    fi
}
require_tools() {
    local tool
    for tool in curl docker grep sed systemctl; do
        if ! command -v "${tool}" >/dev/null 2>&1; then
            echo "Missing required command: ${tool}"
            exit 1
        fi
    done
}
require_files() {
    local file
    for file in "${COMPOSE_FILE}" "${ENV_FILE}"; do
        if [ ! -f "${file}" ]; then
            echo "Required file not found: ${file}"
            exit 1
        fi
    done
}
confirm_step() {
    local message="$1"
    echo
    echo "==> ${message}"
    read -r -p "Continue? [y/N] " reply
    case "${reply}" in
        y|Y|yes|YES)
            ;;
        *)
            echo "Aborted."
            exit 1
            ;;
    esac
}
resolve_auth_secret() {
    local secret
    secret=""
    if [ -f "${ENV_FILE}" ]; then
        secret="$(grep '^AUTH_SECRET=' "${ENV_FILE}" | head -n1 | cut -d= -f2- || true)"
    fi
    if [ -n "${secret}" ]; then
        printf '%s\n' "${secret}"
        return
    fi
    printf '%s\n' "change-me-in-production"
}
set_compose_port() {
    local source_port="$1"
    local target_port="$2"
    if grep -q "API_PORT: \"${target_port}\"" "${COMPOSE_FILE}"; then
        echo "docker-compose.yml already uses API_PORT ${target_port}."
        return
    fi
    if ! grep -q "API_PORT: \"${source_port}\"" "${COMPOSE_FILE}"; then
        echo "Unable to find API_PORT ${source_port} in ${COMPOSE_FILE}."
        exit 1
    fi
    sed -i -E "s/(API_PORT: )\"${source_port}\"/\\1\"${target_port}\"/" "${COMPOSE_FILE}"
    if ! grep -q "API_PORT: \"${target_port}\"" "${COMPOSE_FILE}"; then
        echo "Failed to update API_PORT to ${target_port}."
        exit 1
    fi
    echo "Updated docker-compose.yml API_PORT to ${target_port}."
}
expect_unreachable() {
    local url="$1"
    if curl --noproxy '*' --connect-timeout 2 --max-time 5 -fsS "${url}" >/dev/null 2>&1; then
        echo "Expected ${url} to be unavailable, but it is still responding."
        exit 1
    fi
    echo "Confirmed unavailable: ${url}"
}
wait_for_health() {
    local url="$1"
    local attempt
    for attempt in $(seq 1 "${HEALTH_TIMEOUT}"); do
        if curl --noproxy '*' --connect-timeout 2 --max-time 5 -fsS "${url}" >/dev/null 2>&1; then
            echo "Health check passed: ${url}"
            return 0
        fi
        sleep 1
    done
    echo "Timed out waiting for ${url} after ${HEALTH_TIMEOUT}s."
    echo "Rollback hint: sudo ${PROJECT_DIR}/scripts/rollback-to-systemd.sh ${SERVICE_NAME}"
    exit 1
}
ensure_docker_enabled() {
    local state
    state="$(systemctl is-enabled docker 2>/dev/null || true)"
    if [ "${state}" = "enabled" ]; then
        echo "Docker daemon is already enabled at boot."
        return
    fi
    echo "Docker daemon is not enabled at boot. Enabling it now."
    systemctl enable docker
}
verify_sessions() {
    local secret
    secret="$(resolve_auth_secret)"
    curl --noproxy '*' --connect-timeout 2 --max-time 10 -fsS \
        -H "Authorization: Bearer ${secret}" \
        http://127.0.0.1:8000/api/sessions >/dev/null
    echo "Session list check passed on 8000."
}
verify_feishu_webhook() {
    local response
    response="$(curl --noproxy '*' --connect-timeout 2 --max-time 10 -fsS \
        -H 'Content-Type: application/json' \
        -d '{}' \
        http://127.0.0.1:8000/api/feishu/event)"
    if ! printf '%s' "${response}" | grep -q '"status":"ignored"'; then
        echo "Unexpected Feishu webhook probe response: ${response}"
        exit 1
    fi
    echo "Feishu webhook reachability check passed on 8000."
}
show_runtime_summary() {
    local active_state enabled_state
    active_state="$(systemctl is-active "${SERVICE_UNIT}" 2>/dev/null || true)"
    enabled_state="$(systemctl is-enabled "${SERVICE_UNIT}" 2>/dev/null || true)"
    echo
    echo "docker compose ps"
    docker compose ps
    echo
    echo "systemctl is-active ${SERVICE_UNIT}: ${active_state}"
    echo "systemctl is-enabled ${SERVICE_UNIT}: ${enabled_state}"
    if [ "${active_state}" != "inactive" ]; then
        echo "Expected ${SERVICE_UNIT} to be inactive."
        exit 1
    fi
    if [ "${enabled_state}" != "disabled" ]; then
        echo "Expected ${SERVICE_UNIT} to be disabled."
        exit 1
    fi
    echo
    echo "docker compose logs app --tail=20"
    docker compose logs app --tail=20
}
main() {
    require_root
    require_tools
    cd "${PROJECT_DIR}"
    require_files
    echo "Project directory: ${PROJECT_DIR}"
    echo "Legacy systemd unit: ${SERVICE_UNIT}"
    echo "Compose file: ${COMPOSE_FILE}"
    echo "This script performs the Phase 3.3 cutover from systemd:8000 to Docker:8000."
    echo "Expected starting state: systemd serves 8000, Docker serves 8001."
    confirm_step "Step 1/6: stop the Docker container currently serving port 8001."
    docker compose down
    expect_unreachable "http://127.0.0.1:8001/health"
    confirm_step "Step 2/6: switch docker-compose.yml from API_PORT 8001 to 8000."
    set_compose_port "8001" "8000"
    confirm_step "Step 3/6: stop ${SERVICE_UNIT}. Downtime starts after this step."
    systemctl stop "${SERVICE_UNIT}"
    expect_unreachable "http://127.0.0.1:8000/health"
    confirm_step "Step 4/6: start the Docker container on port 8000 and wait for health."
    docker compose up -d --build
    wait_for_health "http://127.0.0.1:8000/health"
    echo "Downtime window has ended."
    confirm_step "Step 5/6: disable ${SERVICE_UNIT} so it does not reclaim port 8000 on reboot."
    systemctl disable "${SERVICE_UNIT}"
    ensure_docker_enabled
    confirm_step "Step 6/6: run post-cutover verification."
    curl --noproxy '*' --connect-timeout 2 --max-time 10 -fsS http://127.0.0.1:8000/health
    echo
    verify_sessions
    verify_feishu_webhook
    show_runtime_summary
    echo
    echo "Cutover completed successfully."
}
main "$@"
