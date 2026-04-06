#!/usr/bin/env bash
# =============================================================================
# Environment Check Script for the DI-AAI-FS playground
#
# Run:  bash scripts/dev/check-env.sh
#
# Checks every required tool and prints actionable install instructions
# for anything that is missing or at the wrong version.
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
WARN=0
FAIL=0

pass()  { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS + 1)); }
warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; WARN=$((WARN + 1)); }
fail()  { echo -e "  ${RED}✗${NC} $1"; FAIL=$((FAIL + 1)); }

echo ""
echo "============================================"
echo "  DI-AAI-FS  Playground Environment Check"
echo "============================================"
echo ""

# ---- Python ----
echo "Python"
if command -v python3 &>/dev/null; then
  PY_VER=$(uv run python --version 2>&1 | awk '{print $2}')
  if [[ "$PY_VER" == 3.12* ]]; then
    pass "Python $PY_VER"
  else
    warn "Python $PY_VER found — 3.12.x required"
    echo "       Install: brew install python@3.12  (macOS)"
    echo "       Or:      pyenv install 3.12"
  fi
else
  fail "Python 3 not found"
  echo "       Install: brew install python@3.12  (macOS)"
  echo "       Or:      https://www.python.org/downloads/"
fi

# ---- uv ----
echo ""
echo "uv (Python package manager)"
if command -v uv &>/dev/null; then
  UV_VER=$(uv --version 2>&1 | awk '{print $2}')
  pass "uv $UV_VER"
else
  fail "uv not found"
  echo "       Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "       Or:      brew install uv"
fi

# ---- Node.js ----
echo ""
echo "Node.js"
if command -v node &>/dev/null; then
  NODE_VER=$(node --version | tr -d 'v')
  NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
  if [[ "$NODE_MAJOR" -ge 18 && "$NODE_MAJOR" -lt 23 ]]; then
    pass "Node.js v$NODE_VER"
  else
    warn "Node.js v$NODE_VER — need >=18 <23"
    echo "       Install: nvm install 22"
    echo "       Or:      brew install node@22"
  fi
else
  fail "Node.js not found"
  echo "       Install: https://nodejs.org/ or nvm install 22"
fi

# ---- pnpm ----
echo ""
echo "pnpm"
if command -v pnpm &>/dev/null; then
  PNPM_VER=$(pnpm --version)
  PNPM_MAJOR=$(echo "$PNPM_VER" | cut -d. -f1)
  if [[ "$PNPM_MAJOR" -ge 10 ]]; then
    pass "pnpm $PNPM_VER"
  else
    warn "pnpm $PNPM_VER — need 10.x"
    echo "       Upgrade: corepack prepare pnpm@latest --activate"
  fi
else
  fail "pnpm not found"
  echo "       Install: corepack enable && corepack prepare pnpm@latest --activate"
  echo "       Or:      npm install -g pnpm"
fi

# ---- Docker ----
echo ""
echo "Docker"
if command -v docker &>/dev/null; then
  DOCKER_VER=$(docker --version | awk '{print $3}' | tr -d ',')
  pass "Docker $DOCKER_VER"
else
  fail "Docker not found"
  echo "       Install: https://docs.docker.com/get-docker/"
fi

# ---- Docker Compose ----
echo ""
echo "Docker Compose"
if docker compose version &>/dev/null 2>&1; then
  DC_VER=$(docker compose version --short 2>/dev/null || echo "unknown")
  pass "Docker Compose $DC_VER"
else
  fail "Docker Compose v2 not found"
  echo "       Docker Desktop includes Compose v2."
  echo "       Or: https://docs.docker.com/compose/install/"
fi

# ---- Git ----
echo ""
echo "Git"
if command -v git &>/dev/null; then
  GIT_VER=$(git --version | awk '{print $3}')
  pass "Git $GIT_VER"
else
  fail "Git not found"
  echo "       Install: brew install git  (macOS)"
fi

# ---- .env ----
echo ""
echo "Configuration"
if [[ -f .env ]]; then
  pass ".env file exists"
else
  warn ".env file missing — copy from .env.example"
  echo "       Run: cp .env.example .env"
fi

# ---- Summary ----
echo ""
echo "============================================"
echo -e "  ${GREEN}$PASS passed${NC}  ${YELLOW}$WARN warnings${NC}  ${RED}$FAIL failed${NC}"
echo "============================================"
echo ""

if [[ $FAIL -gt 0 ]]; then
  echo "Fix the failures above before proceeding."
  exit 1
elif [[ $WARN -gt 0 ]]; then
  echo "Warnings present — the system may still work but check versions."
  exit 0
else
  echo "All checks passed. You are ready to develop."
  exit 0
fi
