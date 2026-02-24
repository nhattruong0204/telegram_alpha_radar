# VPS Bot Deployment — Lessons Learned & Best Practices

> A battle-tested guide for deploying Telegram bots (or any Docker-based service) to a VPS.
> Written from real deployment experience. Use this to deploy for yourself or your clients.

---

## Table of Contents

1. [Pre-Deployment Checklist](#1-pre-deployment-checklist)
2. [VPS Initial Setup](#2-vps-initial-setup)
3. [SSH Key Setup](#3-ssh-key-setup)
4. [Docker Installation](#4-docker-installation)
5. [Project Structure](#5-project-structure)
6. [Deployment Commands](#6-deployment-commands)
7. [Managing Multiple Bots](#7-managing-multiple-bots-on-one-vps)
8. [Debugging & Troubleshooting](#8-debugging--troubleshooting)
9. [Monitoring & Health Checks](#9-monitoring--health-checks)
10. [Security Best Practices](#10-security-best-practices)
11. [Quick Reference Commands](#11-quick-reference--one-liners)
12. [Client Deployment Template](#12-client-deployment-template)

---

## 1. Pre-Deployment Checklist

Before touching the VPS, make sure you have:

- [ ] SSH key pair generated locally
- [ ] VPS IP address and root access
- [ ] Project code with a working `Dockerfile`
- [ ] `docker-compose.yml` configured
- [ ] `.env` file with all secrets filled in
- [ ] All API keys/tokens ready (Telegram bot token, DB passwords, etc.)
- [ ] Tested locally with `docker compose up` first

---

## 2. VPS Initial Setup

### First login and system update

```bash
# SSH into VPS
ssh -i ~/.ssh/YOUR_KEY root@YOUR_VPS_IP

# Update system
apt update && apt upgrade -y

# Install essential tools
apt install -y curl wget git htop net-tools
```

### Check system resources

```bash
# Check CPU, RAM, disk
echo "=== CPU ===" && nproc && echo "=== RAM ===" && free -h && echo "=== DISK ===" && df -h /
```

### Set timezone (optional but recommended)

```bash
timedatectl set-timezone UTC
```

---

## 3. SSH Key Setup

### Generate SSH key (on your local machine)

```bash
# Generate a new key pair
ssh-keygen -t ed25519 -f ~/.ssh/my_vps_key -C "my-vps-key"

# Copy public key to VPS
ssh-copy-id -i ~/.ssh/my_vps_key.pub root@YOUR_VPS_IP
```

### Test connection

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "echo 'Connected successfully'"
```

### SSH config shortcut (add to `~/.ssh/config`)

```
Host myvps
    HostName YOUR_VPS_IP
    User root
    IdentityFile ~/.ssh/my_vps_key
    ConnectTimeout 10
```

Now you can just: `ssh myvps`

---

## 4. Docker Installation

### Install Docker + Docker Compose (single command)

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP 'curl -fsSL https://get.docker.com | sh && docker --version && docker compose version'
```

### Verify Docker is running

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "systemctl status docker --no-pager"
```

---

## 5. Project Structure

### Recommended layout for any bot project

```
my-bot/
├── docker-compose.yml      # Container orchestration
├── Dockerfile              # Build instructions
├── .env                    # Secrets (NEVER commit to git)
├── .env.example            # Template for clients
├── requirements.txt        # Python dependencies
├── schema.sql              # DB init script (if using PostgreSQL)
├── sessions/               # Persistent session data (volume-mounted)
└── src/                    # Application source code
    └── ...
```

### docker-compose.yml template

```yaml
version: "3.8"

services:
  db:
    image: postgres:16-alpine
    container_name: mybot-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    volumes:
      - mybot_pgdata:/var/lib/postgresql/data
      - ./schema.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - mybot-network

  app:
    build: .
    container_name: mybot-app
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    env_file:
      - .env
    volumes:
      - ./sessions:/app/sessions
    ports:
      - "${HEALTH_PORT:-8080}:8080"
    networks:
      - mybot-network

volumes:
  mybot_pgdata:

networks:
  mybot-network:
    name: mybot-network
```

### Key rules:
- **Unique container names** — prevents conflicts with other bots
- **Unique network names** — isolates each bot's internal traffic
- **Unique volume names** — each bot gets its own persistent data
- **Unique port mappings** — no two bots on the same host port

---

## 6. Deployment Commands

### The single deployment command (memorize this)

```bash
# Sync code + rebuild + restart — all in one
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='sessions/' \
  -e "ssh -i ~/.ssh/my_vps_key" \
  ./my-bot/ root@YOUR_VPS_IP:/opt/my-bot/ \
  && ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP \
  "cd /opt/my-bot && docker compose up -d --build && sleep 5 && docker compose logs --tail 20"
```

### Breaking it down step by step:

#### Step 1: Create project directory on VPS

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "mkdir -p /opt/my-bot/sessions && chmod 777 /opt/my-bot/sessions"
```

#### Step 2: Copy files to VPS

```bash
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='sessions/' \
  -e "ssh -i ~/.ssh/my_vps_key" \
  ./ root@YOUR_VPS_IP:/opt/my-bot/
```

#### Step 3: Build Docker images

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose build"
```

#### Step 4: Start services

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose up -d"
```

#### Step 5: Verify

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose ps && docker compose logs --tail 20"
```

### Interactive session (for Telegram auth, first-time setup)

```bash
# Start only the database first
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose up -d db && sleep 5"

# Run app interactively (enter verification codes here)
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose run --rm -it app"

# After session created, start everything in background
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose up -d"
```

### Update only .env (no rebuild needed)

```bash
scp -i ~/.ssh/my_vps_key .env root@YOUR_VPS_IP:/opt/my-bot/.env \
  && ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose up -d app"
```

### Update code + rebuild

```bash
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='sessions/' \
  -e "ssh -i ~/.ssh/my_vps_key" ./ root@YOUR_VPS_IP:/opt/my-bot/ \
  && ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP \
  "cd /opt/my-bot && docker compose up -d --build app && sleep 5 && docker compose logs app --tail 20"
```

---

## 7. Managing Multiple Bots on One VPS

### The golden rule: **ISOLATION**

Each bot must have:
| Resource | Example Bot A | Example Bot B |
|----------|---------------|---------------|
| Directory | `/opt/bot-a/` | `/opt/bot-b/` |
| Container prefix | `bot-a-app` | `bot-b-app` |
| Network | `bot-a-network` | `bot-b-network` |
| DB volume | `bot-a_pgdata` | `bot-b_pgdata` |
| Health port | `8080` | `8081` |
| Metrics port | `9090` | `9091` |

### List all running bots

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
```

### Restart one bot without affecting others

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/bot-a && docker compose restart app"
```

### Check resource usage per container

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'"
```

---

## 8. Debugging & Troubleshooting

### The 5 commands you need (in order of usefulness)

#### 1. Check if containers are running

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose ps"
```

#### 2. View recent logs

```bash
# Last 50 lines
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose logs --tail 50"

# Follow logs in real-time
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose logs -f app"

# Logs from last 10 minutes only
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose logs --since 10m app"
```

#### 3. Check why a container crashed

```bash
# Shows exit code and error
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "docker inspect --format='{{.State.ExitCode}} {{.State.Error}}' mybot-app"

# Show last restart logs
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose logs app --tail 100 | head -50"
```

#### 4. Shell into a running container

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "docker exec -it mybot-app /bin/bash"

# If bash not available (alpine images):
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "docker exec -it mybot-app /bin/sh"
```

#### 5. Check what ports are in use

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "ss -tlnp | grep -E ':(8080|8081|9090|9091|5432|3000)'"
```

### Common problems and fixes

| Problem | Symptom | Fix |
|---------|---------|-----|
| Container keeps restarting | `Restarting (1)` in `docker ps` | Check logs: `docker compose logs app --tail 100` |
| Port conflict | `bind: address already in use` | Change port mapping in `docker-compose.yml` |
| Permission denied | `sqlite3.OperationalError: unable to open database file` | `chmod 777 /opt/my-bot/sessions` |
| Out of disk space | Build fails or container won't start | `docker system prune -af` (⚠️ removes unused images) |
| DB not ready | `connection refused` on startup | Add `depends_on` with `condition: service_healthy` |
| Environment variable missing | `KeyError` or empty config | Check `.env` file exists and is mounted |
| Can't send Telegram message | `chat not found` | User must `/start` the bot first |

### Nuclear option: full reset of one bot

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "cd /opt/my-bot && docker compose down -v && docker compose up -d --build"
```

⚠️ `-v` deletes volumes (database data). Only use if you want a fresh start.

---

## 9. Monitoring & Health Checks

### Quick health check

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP "curl -s http://localhost:8080/health | python3 -m json.tool"
```

### VPS system health

```bash
# All-in-one system check
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP '
echo "=== UPTIME ===" && uptime
echo "=== MEMORY ===" && free -h
echo "=== DISK ===" && df -h /
echo "=== DOCKER ===" && docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo "=== TOP CPU ===" && docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | head -10
'
```

### Set up log rotation (prevent disk full)

```bash
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP 'cat > /etc/docker/daemon.json << EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl restart docker'
```

---

## 10. Security Best Practices

### Never do these:
- ❌ Commit `.env` files to git
- ❌ Use default passwords
- ❌ Run with `chmod 777` on everything
- ❌ Expose database ports to the internet
- ❌ Store API keys in Dockerfile or docker-compose.yml

### Always do these:
- ✅ Use `.env` files for all secrets
- ✅ Generate random passwords: `openssl rand -base64 24`
- ✅ Keep DB ports internal (no `ports:` mapping for postgres)
- ✅ Use `restart: unless-stopped` for auto-recovery
- ✅ Use health checks in docker-compose
- ✅ Set up Docker log rotation
- ✅ Back up volumes before major changes

### Backup database

```bash
# Dump database
ssh -i ~/.ssh/my_vps_key root@YOUR_VPS_IP \
  "docker exec mybot-postgres pg_dump -U radar alpha_radar > /opt/my-bot/backup_$(date +%Y%m%d).sql"

# Download backup locally
scp -i ~/.ssh/my_vps_key root@YOUR_VPS_IP:/opt/my-bot/backup_*.sql ./backups/
```

---

## 11. Quick Reference — One-Liners

Copy-paste these. Replace `MY_KEY`, `VPS_IP`, and `my-bot` with your values.

```bash
# === CONNECTION ===
alias vps='ssh -i ~/.ssh/MY_KEY root@VPS_IP'

# === DEPLOY (the money command) ===
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='sessions/' -e "ssh -i ~/.ssh/MY_KEY" ./ root@VPS_IP:/opt/my-bot/ && ssh -i ~/.ssh/MY_KEY root@VPS_IP "cd /opt/my-bot && docker compose up -d --build && sleep 5 && docker compose logs --tail 20"

# === LOGS ===
ssh -i ~/.ssh/MY_KEY root@VPS_IP "cd /opt/my-bot && docker compose logs -f app"

# === STATUS ===
ssh -i ~/.ssh/MY_KEY root@VPS_IP "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

# === RESTART ===
ssh -i ~/.ssh/MY_KEY root@VPS_IP "cd /opt/my-bot && docker compose restart app"

# === STOP ===
ssh -i ~/.ssh/MY_KEY root@VPS_IP "cd /opt/my-bot && docker compose stop"

# === HEALTH ===
ssh -i ~/.ssh/MY_KEY root@VPS_IP "curl -s http://localhost:8080/health"

# === DISK CLEANUP ===
ssh -i ~/.ssh/MY_KEY root@VPS_IP "docker system prune -f && docker image prune -f"

# === UPDATE .ENV ONLY ===
scp -i ~/.ssh/MY_KEY .env root@VPS_IP:/opt/my-bot/.env && ssh -i ~/.ssh/MY_KEY root@VPS_IP "cd /opt/my-bot && docker compose up -d"
```

---

## 12. Client Deployment Template

### What to send your Upwork client

When a client hires you to deploy their bot, follow this checklist:

#### Before starting:
1. Get VPS credentials (IP + SSH key or password)
2. Get all API keys/tokens from client
3. Review client's code and Dockerfile
4. Estimate deployment time (usually 1-2 hours for standard bots)

#### Deployment steps:
1. SSH into VPS, update system, install Docker
2. Create project directory: `/opt/client-bot/`
3. Upload code via `rsync`
4. Create `.env` from `.env.example`, fill in client's credentials
5. Build and start with `docker compose up -d --build`
6. Run interactive session if needed (Telegram auth)
7. Verify health check and logs
8. Set up Docker log rotation
9. Test the bot functionality end-to-end

#### Deliverables to client:
- [ ] Bot running and verified on VPS
- [ ] Health check URL working
- [ ] `.env.example` documented
- [ ] These 5 maintenance commands:

```
# Check status
ssh root@VPS_IP "cd /opt/client-bot && docker compose ps"

# View logs
ssh root@VPS_IP "cd /opt/client-bot && docker compose logs --tail 50"

# Restart bot
ssh root@VPS_IP "cd /opt/client-bot && docker compose restart"

# Stop bot
ssh root@VPS_IP "cd /opt/client-bot && docker compose stop"

# Start bot
ssh root@VPS_IP "cd /opt/client-bot && docker compose up -d"
```

#### Pricing guide (as of 2026):
| Service | Suggested Price |
|---------|----------------|
| Simple bot deployment (1 container) | $50-100 |
| Bot + database deployment | $100-200 |
| Multi-service deployment | $200-400 |
| Ongoing maintenance (monthly) | $50-100/mo |
| Emergency fix / debugging | $50-100/hr |

---

## Appendix: Real Deployment Log

This is exactly what we did to deploy Alpha Radar:

```bash
# 1. Found SSH key
ls ~/.ssh/lightnode_vps

# 2. Checked existing containers on VPS (don't break anything!)
ssh -i ~/.ssh/lightnode_vps root@38.54.15.53 "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

# 3. Checked used ports
ssh -i ~/.ssh/lightnode_vps root@38.54.15.53 "ss -tlnp"

# 4. Created docker-compose.yml with UNIQUE names and DIFFERENT ports (8081, 9091)

# 5. Created .env with credentials

# 6. Created directory and fixed permissions
ssh -i ~/.ssh/lightnode_vps root@38.54.15.53 "mkdir -p /opt/alpha-radar/sessions && chmod 777 /opt/alpha-radar/sessions"

# 7. Synced code
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='sessions/' \
  -e "ssh -i ~/.ssh/lightnode_vps" ./ root@38.54.15.53:/opt/alpha-radar/

# 8. Built images
ssh -i ~/.ssh/lightnode_vps root@38.54.15.53 "cd /opt/alpha-radar && docker compose build"

# 9. Started DB first
ssh -i ~/.ssh/lightnode_vps root@38.54.15.53 "cd /opt/alpha-radar && docker compose up -d postgres"

# 10. Created Telegram session (interactive — piped verification code)
ssh -i ~/.ssh/lightnode_vps root@38.54.15.53 "cd /opt/alpha-radar && echo 'CODE' | docker compose run --rm -T app"

# 11. Started everything
ssh -i ~/.ssh/lightnode_vps root@38.54.15.53 "cd /opt/alpha-radar && docker compose up -d"

# 12. Verified all containers (old + new) running
ssh -i ~/.ssh/lightnode_vps root@38.54.15.53 "docker ps --format 'table {{.Names}}\t{{.Status}}'"

# 13. Health check confirmed
ssh -i ~/.ssh/lightnode_vps root@38.54.15.53 "curl -s http://localhost:8081/health"
```

Key lesson: **Always check existing containers and ports BEFORE deploying.** One wrong port mapping can take down a client's production system.

---

*Last updated: February 24, 2026*
*Based on deploying Alpha Radar to 38.54.15.53 alongside 6 existing containers*
