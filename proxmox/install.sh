#!/usr/bin/env bash

# Financisto Web - Proxmox LXC Install Script
# Run from Proxmox host shell:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/wikibrikofix/financisto-web/main/proxmox/install.sh)"

set -euo pipefail

APP="Financisto Web"
REPO="https://github.com/wikibrikofix/financisto-web.git"
INSTALL_DIR="/opt/financisto-web"

# --- Colors ---
RD='\033[0;31m'; GN='\033[0;32m'; YW='\033[0;33m'; BL='\033[0;34m'; CL='\033[0m'

msg_info() { echo -e "${BL}[INFO]${CL} $1"; }
msg_ok() { echo -e "${GN}[OK]${CL} $1"; }
msg_error() { echo -e "${RD}[ERROR]${CL} $1"; exit 1; }

header() {
    echo -e "${GN}"
    echo "  ╔═══════════════════════════════════════╗"
    echo "  ║         Financisto Web Installer       ║"
    echo "  ║   Self-hosted personal finance app     ║"
    echo "  ╚═══════════════════════════════════════╝"
    echo -e "${CL}"
}

# --- Check if running inside LXC or VM ---
install_inside_container() {
    header

    msg_info "Updating system"
    apt-get update -qq && apt-get upgrade -y -qq
    msg_ok "System updated"

    msg_info "Installing Docker"
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
    msg_ok "Docker installed"

    msg_info "Installing git"
    apt-get install -y -qq git
    msg_ok "Git installed"

    msg_info "Cloning Financisto Web"
    git clone "$REPO" "$INSTALL_DIR"
    msg_ok "Cloned to $INSTALL_DIR"

    msg_info "Configuring"
    cd "$INSTALL_DIR"
    cp .env.example .env

    # Interactive configuration
    echo ""
    echo -e "${YW}=== Configuration ===${CL}"
    read -rp "Gmail address: " GMAIL_USER
    read -rsp "Gmail App Password: " GMAIL_PASS; echo
    read -rp "Bank email sender (e.g. notifications@bank.com): " BANK_SENDER
    read -rp "Bank email subject filter (e.g. 'operation executed', leave empty for none): " BANK_SUBJECT
    read -rp "Card notification sender (leave empty to skip): " CARD_SENDER

    cat > .env <<EOF
GMAIL_USER=${GMAIL_USER}
GMAIL_APP_PASSWORD=${GMAIL_PASS}
ACCOUNT_MAP={"bank": 1, "card": 2}
BANK_SENDER=${BANK_SENDER}
BANK_SUBJECT=${BANK_SUBJECT}
CARD_SENDER=${CARD_SENDER}
EOF
    msg_ok "Configuration saved to .env"

    msg_info "Starting services"
    docker compose up -d
    msg_ok "Services started"

    # Get IP
    IP=$(hostname -I | awk '{print $1}')

    echo ""
    echo -e "${GN}════════════════════════════════════════════${CL}"
    echo -e "${GN} ${APP} installed successfully!${CL}"
    echo -e "${GN}════════════════════════════════════════════${CL}"
    echo ""
    echo -e " Access:  ${BL}http://${IP}:8080${CL}"
    echo -e " Config:  ${INSTALL_DIR}/.env"
    echo -e " Logs:    docker compose -f ${INSTALL_DIR}/docker-compose.yml logs -f"
    echo ""
    echo -e "${YW} Next steps:${CL}"
    echo "  1. Open the web UI and import your Financisto .backup"
    echo "  2. Go to Accounts and note the account IDs"
    echo "  3. Edit ${INSTALL_DIR}/.env and set ACCOUNT_MAP with correct IDs"
    echo "  4. Restart: cd ${INSTALL_DIR} && docker compose restart email-worker"
    echo ""
}

# --- Proxmox host: create LXC and run installer inside ---
create_lxc() {
    header

    # Defaults
    CT_ID=$(pvesh get /cluster/nextid)
    HOSTNAME="financisto"
    DISK="8"
    RAM="1024"
    CPU="2"
    STORAGE="local-lvm"

    echo -e "${YW}=== LXC Container Settings ===${CL}"
    read -rp "Container ID [$CT_ID]: " input; CT_ID="${input:-$CT_ID}"
    read -rp "Hostname [$HOSTNAME]: " input; HOSTNAME="${input:-$HOSTNAME}"
    read -rp "Disk size GB [$DISK]: " input; DISK="${input:-$DISK}"
    read -rp "RAM MB [$RAM]: " input; RAM="${input:-$RAM}"
    read -rp "CPU cores [$CPU]: " input; CPU="${input:-$CPU}"
    read -rp "Storage [$STORAGE]: " input; STORAGE="${input:-$STORAGE}"

    msg_info "Downloading Debian template"
    TEMPLATE=$(pveam available --section system | grep "debian-1[23]-standard" | tail -1 | awk '{print $2}')
    if [[ -z "$TEMPLATE" ]]; then msg_error "No Debian template found"; fi
    pveam download local "$TEMPLATE" 2>/dev/null || true
    msg_ok "Template ready: $TEMPLATE"

    msg_info "Creating LXC container $CT_ID"
    pct create "$CT_ID" "local:vztmpl/$TEMPLATE" \
        --hostname "$HOSTNAME" \
        --memory "$RAM" \
        --cores "$CPU" \
        --rootfs "${STORAGE}:${DISK}" \
        --net0 name=eth0,bridge=vmbr0,ip=dhcp \
        --unprivileged 1 \
        --features nesting=1 \
        --onboot 1 \
        --start 1
    msg_ok "Container $CT_ID created"

    msg_info "Waiting for container to start"
    sleep 5
    msg_ok "Container running"

    msg_info "Running installer inside container"
    pct exec "$CT_ID" -- bash -c "curl -fsSL https://raw.githubusercontent.com/wikibrikofix/financisto-web/main/proxmox/install.sh | bash -s -- --inside"
    msg_ok "Installation complete"

    IP=$(pct exec "$CT_ID" -- hostname -I | awk '{print $1}')
    echo ""
    echo -e "${GN} Access Financisto Web at: ${BL}http://${IP}:8080${CL}"
}

# --- Entry point ---
if [[ "${1:-}" == "--inside" ]]; then
    install_inside_container
elif command -v pct &>/dev/null; then
    create_lxc
else
    # Running directly inside a VM/container
    install_inside_container
fi
