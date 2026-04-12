#!/bin/bash
# ============================================
# TeamPilot One-Click Deploy Script
# Usage: bash deploy.sh
# ============================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  TeamPilot - One-Click Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 1. Check prerequisites
echo -e "${YELLOW}[1/6] Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker not found. Installing...${NC}"
    curl -fsSL https://get.docker.com | sh
    sudo systemctl enable docker && sudo systemctl start docker
    echo -e "${GREEN}Docker installed.${NC}"
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}Docker Compose not found. Installing...${NC}"
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin
    echo -e "${GREEN}Docker Compose installed.${NC}"
fi

echo -e "${GREEN}  Docker: $(docker --version)${NC}"

# 2. Generate config if not exists
echo -e "${YELLOW}[2/6] Checking configuration...${NC}"

if [ ! -f deploy.env ]; then
    echo -e "${RED}deploy.env not found! Creating from template...${NC}"
    cp deploy.env.example deploy.env 2>/dev/null || true
fi

# Auto-generate JWT secret if still default
if grep -q "change-me-to-a-random" deploy.env 2>/dev/null; then
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
    sed -i "s/change-me-to-a-random-64-char-hex-string-in-production/$JWT_SECRET/" deploy.env
    echo -e "${GREEN}  JWT secret auto-generated.${NC}"
fi

echo -e "${GREEN}  Configuration: deploy.env${NC}"

# 3. Build and start
echo -e "${YELLOW}[3/6] Building Docker images...${NC}"

COMPOSE_CMD="docker compose"
if ! docker compose version &> /dev/null; then
    COMPOSE_CMD="docker-compose"
fi

$COMPOSE_CMD build --no-cache

echo -e "${YELLOW}[4/6] Starting services...${NC}"
$COMPOSE_CMD up -d

# 5. Wait for health
echo -e "${YELLOW}[5/6] Waiting for services to start...${NC}"

for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}  Backend is ready.${NC}"
        break
    fi
    sleep 2
    echo -n "."
done
echo ""

# 6. Create default admin
echo -e "${YELLOW}[6/6] Creating default admin user...${NC}"

# The backend auto-creates admin on first start via lifespan
sleep 2
if curl -sf http://localhost:8000/api/v1/auth/login -X POST \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' > /dev/null 2>&1; then
    echo -e "${GREEN}  Default admin created: admin / admin123${NC}"
else
    echo -e "${YELLOW}  Admin may already exist or DB is being initialized...${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  Frontend:  ${GREEN}http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost')${NC}"
echo -e "  API Docs:  ${GREEN}http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):8000/docs${NC}"
echo -e "  Login:     ${GREEN}admin / admin123${NC}"
echo ""
echo -e "${YELLOW}  Next steps:${NC}"
echo -e "  1. Change admin password after first login"
echo -e "  2. Configure AI in Settings > AI Config"
echo -e "  3. Add team members in Personnel Management"
echo ""
echo -e "  Manage: ${COMPOSE_CMD} logs -f    # View logs"
echo -e "          ${COMPOSE_CMD} down       # Stop"
echo -e "          ${COMPOSE_CMD} restart    # Restart"
echo ""
