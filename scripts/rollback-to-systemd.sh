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
    exit 1
}

show_runtime_summary() {
    echo
    echo "docker compose ps"
    docker compose ps

    echo
    echo "systemctl is-active ${SERVICE_UNIT}: $(systemctl is-active "${SERVICE_UNIT}" 2>/dev/null || true)"
    echo "systemctl is-enabled ${SERVICE_UNIT}: $(systemctl is-enabled "${SERVICE_UNIT}" 2>/dev/null || true)"
}

main() {
    require_root
    require_tools
    cd "${PROJECT_DIR}"
    require_files

    echo "Project directory: ${PROJECT_DIR}"
    echo "Legacy systemd unit: ${SERVICE_UNIT}"
    echo "This script rolls back Phase 3.3 and returns traffic to systemd on port 8000."

    confirm_step "Step 1/5: stop the Docker container."
    docker compose down

    confirm_step "Step 2/5: switch docker-compose.yml from API_PORT 8000 back to 8001."
    set_compose_port "8000" "8001"

    confirm_step "Step 3/5: start ${SERVICE_UNIT} on port 8000."
    systemctl start "${SERVICE_UNIT}"

    confirm_step "Step 4/5: enable ${SERVICE_UNIT} at boot."
    systemctl enable "${SERVICE_UNIT}"

    confirm_step "Step 5/5: verify 8000 health on the restored systemd service."
    wait_for_health "http://127.0.0.1:8000/health"
    show_runtime_summary

    echo
    echo "Rollback completed successfully."
}

main "$@"
