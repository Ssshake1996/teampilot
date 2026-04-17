#!/bin/bash
# ============================================
# TeamPilot One-Click Deploy Script
# Usage: bash deploy.sh
# ============================================

set -e
set -o pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ENV="${SCRIPT_DIR}/deploy.env"
DEPLOY_ENV_EXAMPLE="${SCRIPT_DIR}/deploy.env.example"

log_info() {
    echo -e "${GREEN}$1${NC}"
}

log_warn() {
    echo -e "${YELLOW}$1${NC}"
}

log_error() {
    echo -e "${RED}$1${NC}"
}

fail() {
    log_error "$1"
    exit 1
}

version_gte() {
    local current="$1"
    local minimum="$2"
    if command -v dpkg >/dev/null 2>&1; then
        dpkg --compare-versions "$current" ge "$minimum"
        return
    fi
    [ "$(printf '%s\n' "$minimum" "$current" | sort -V | head -n1)" = "$minimum" ]
}

check_supported_environment() {
    [ "$(uname -s)" = "Linux" ] || fail "deploy.sh only supports Linux hosts. Use Ubuntu 20.04.5+ for deployment."
    [ -f /etc/os-release ] || fail "Could not detect the Linux distribution. Use Ubuntu 20.04.5+ for deployment."

    . /etc/os-release

    [ "${ID:-}" = "ubuntu" ] || fail "Unsupported distribution: ${PRETTY_NAME:-unknown}. deploy.sh currently supports Ubuntu 20.04.5+ only."
    version_gte "${VERSION_ID:-0}" "20.04" || fail "Unsupported Ubuntu version: ${PRETTY_NAME:-unknown}. Please use Ubuntu 20.04.5 or newer."
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "$1 is required but was not found."
}

set_env_value() {
    local key="$1"
    local value="$2"
    local escaped_value
    escaped_value=$(printf '%s' "$value" | sed -e 's/[\/&]/\\&/g')
    if grep -q "^${key}=" "$DEPLOY_ENV"; then
        sed -i "s/^${key}=.*/${key}=${escaped_value}/" "$DEPLOY_ENV"
    else
        echo "${key}=${value}" >> "$DEPLOY_ENV"
    fi
}

random_hex() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 32
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c "import secrets; print(secrets.token_hex(32))"
    else
        od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
    fi
}

random_password() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 24 | tr -d '\n' | tr '/+' 'AB'
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c "import secrets, string; alphabet = string.ascii_letters + string.digits; print(''.join(secrets.choice(alphabet) for _ in range(24)))"
    else
        tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24
    fi
}

install_compose_plugin() {
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y docker-compose-plugin
        return
    fi
    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y docker-compose-plugin
        return
    fi
    if command -v yum >/dev/null 2>&1; then
        sudo yum install -y docker-compose-plugin || sudo yum install -y docker-compose
        return
    fi
    fail "Could not install Docker Compose automatically on this distribution. Please install it manually and re-run deploy.sh."
}

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  TeamPilot - One-Click Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo -e "${YELLOW}[1/6] Checking prerequisites...${NC}"
check_supported_environment
echo -e "${GREEN}  OS: Ubuntu ${VERSION_ID}${NC}"

if ! command -v docker >/dev/null 2>&1; then
    log_warn "Docker not found. Installing..."
    require_command curl
    curl -fsSL https://get.docker.com | sh
    if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl enable docker
        sudo systemctl start docker
    fi
    log_info "Docker installed."
fi

if ! command -v docker-compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
    log_warn "Docker Compose not found. Installing..."
    install_compose_plugin
fi

echo -e "${GREEN}  Docker: $(docker --version)${NC}"

echo -e "${YELLOW}[2/6] Checking configuration...${NC}"

if [ ! -f "$DEPLOY_ENV" ]; then
    [ -f "$DEPLOY_ENV_EXAMPLE" ] || fail "deploy.env is missing and deploy.env.example was not found."
    log_warn "deploy.env not found. Creating it from deploy.env.example..."
    cp "$DEPLOY_ENV_EXAMPLE" "$DEPLOY_ENV"
fi

if grep -q "^JWT_SECRET_KEY=change-me-to-a-random-64-char-hex-string-in-production$" "$DEPLOY_ENV"; then
    set_env_value "JWT_SECRET_KEY" "$(random_hex)"
    log_info "  JWT secret auto-generated."
fi

if grep -q "^AI_ENCRYPTION_KEY=change-me-to-a-random-64-char-hex-string-for-ai-secrets$" "$DEPLOY_ENV"; then
    set_env_value "AI_ENCRYPTION_KEY" "$(random_hex)"
    log_info "  AI encryption key auto-generated."
fi

if grep -q "^ADMIN_PASSWORD=change-me-to-a-random-admin-password-in-production$" "$DEPLOY_ENV"; then
    set_env_value "ADMIN_PASSWORD" "$(random_password)"
    log_info "  Admin password auto-generated."
fi

set -a
. "$DEPLOY_ENV"
set +a

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-80}"
if [ -z "${ADMIN_USERNAME:-}" ]; then
    ADMIN_USERNAME="admin"
    set_env_value "ADMIN_USERNAME" "$ADMIN_USERNAME"
fi

if [ -z "${ADMIN_PASSWORD:-}" ]; then
    ADMIN_PASSWORD="$(random_password)"
    set_env_value "ADMIN_PASSWORD" "$ADMIN_PASSWORD"
    log_info "  Admin password auto-generated because deploy.env did not provide one."
fi

echo -e "${GREEN}  Configuration: deploy.env${NC}"

echo -e "${YELLOW}[3/6] Building Docker images...${NC}"

COMPOSE_CMD=(docker compose)
if ! docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
fi

"${COMPOSE_CMD[@]}" build --no-cache

echo -e "${YELLOW}[4/6] Starting services...${NC}"
"${COMPOSE_CMD[@]}" up -d

echo -e "${YELLOW}[5/6] Waiting for services to start...${NC}"

BACKEND_HEALTH_URL="http://127.0.0.1:${BACKEND_PORT}/health"
for i in $(seq 1 30); do
    if curl -sf "$BACKEND_HEALTH_URL" >/dev/null 2>&1; then
        echo -e "${GREEN}  Backend is ready.${NC}"
        break
    fi
    sleep 2
    echo -n "."
    if [ "$i" -eq 30 ]; then
        echo ""
        "${COMPOSE_CMD[@]}" ps || true
        "${COMPOSE_CMD[@]}" logs --tail=120 backend db || true
        fail "Backend health check failed after 60 seconds. Deployment stopped."
    fi
done
echo ""

echo -e "${YELLOW}[6/6] Finalizing bootstrap credentials...${NC}"
log_info "  Bootstrap admin is managed via deploy.env."

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
SERVER_IP="${SERVER_IP:-localhost}"
echo -e "  Frontend:  ${GREEN}http://${SERVER_IP}:${FRONTEND_PORT}${NC}"
echo -e "  API Docs:  ${GREEN}http://${SERVER_IP}:${BACKEND_PORT}/docs${NC}"
echo -e "  Login:     ${GREEN}${ADMIN_USERNAME} / ${ADMIN_PASSWORD}${NC}"
echo ""
echo -e "${YELLOW}  Next steps:${NC}"
echo -e "  1. Change admin password after first login"
echo -e "  2. Update CORS_ORIGINS in deploy.env to your real domain before exposing the app"
echo -e "  3. Configure AI in Settings > AI Config"
echo ""
echo -e "  Manage: ${COMPOSE_CMD[*]} logs -f    # View logs"
echo -e "          ${COMPOSE_CMD[*]} down       # Stop"
echo -e "          ${COMPOSE_CMD[*]} restart    # Restart"
echo ""
