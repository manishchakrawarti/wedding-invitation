#!/usr/bin/env bash
# One-command setup for a fresh Ubuntu 22.04/24.04 server (Oracle Cloud Always Free, Hetzner, any VPS;
# x86 or ARM). Installs Docker, opens the web ports, adds swap on small machines, clones the app,
# creates a production .env with a strong admin password, starts the site with automatic HTTPS
# (Caddy + Let's Encrypt) and schedules daily database backups.
#
#   curl -fsSL https://raw.githubusercontent.com/manishchakrawarti/wedding-invitation/main/deploy/setup_server.sh | bash
#
# Point your domain's DNS (A records for @ and www) at this server's public IP first, so HTTPS works.
set -euo pipefail

REPO="${REPO:-https://github.com/manishchakrawarti/wedding-invitation.git}"
DOMAIN="${DOMAIN:-invite-all.com}"
APP_DIR="${APP_DIR:-$HOME/invite-all}"

say() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }

say "Installing Docker and git"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo apt-get update -y && sudo apt-get install -y git
sudo usermod -aG docker "$USER" || true

say "Opening ports 80 and 443"
# Oracle Cloud Ubuntu images block everything except SSH in iptables; open the web ports and persist them.
if sudo iptables -L INPUT -n 2>/dev/null | grep -q "REJECT"; then
  for port in 80 443; do
    sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 6 -p tcp --dport "$port" -j ACCEPT
  done
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent && sudo netfilter-persistent save || true
fi
if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
fi

say "Adding swap on small machines"
MEM_MB=$(free -m | awk '/^Mem:/{print $2}')
if [ "$MEM_MB" -lt 3500 ] && ! swapon --show | grep -q "/swapfile"; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
fi

say "Getting the code"
if [ -d "$APP_DIR/.git" ]; then git -C "$APP_DIR" pull --ff-only; else git clone "$REPO" "$APP_DIR"; fi
cd "$APP_DIR"
sed -i "s/invite-all\.com/$DOMAIN/g" deploy/Caddyfile docker-compose.yml

if [ ! -f .env ]; then
  say "Creating production .env"
  ADMIN_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
  cp .env.example .env
  sed -i "s|^BASE_URL=.*|BASE_URL=https://$DOMAIN|; s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=$ADMIN_PASSWORD|" .env
  sed -i "s|^TEST_ORDER_CODE=.*|TEST_ORDER_CODE=|; s|^TEST_COUPON_CODE=.*|TEST_COUPON_CODE=|" .env
  echo "Admin login → user: admin  password: $ADMIN_PASSWORD" | tee "$HOME/invite-all-admin.txt"
  chmod 600 .env "$HOME/invite-all-admin.txt"
fi

say "Building and starting the site (first build takes ~5-10 minutes)"
sudo docker compose up -d --build

say "Scheduling a daily database backup (02:30, keeps 14)"
CRON="30 2 * * * cd $APP_DIR && docker compose exec -T app python scripts/backup_sqlite.py >> $HOME/invite-all-backup.log 2>&1"
( crontab -l 2>/dev/null | grep -v "backup_sqlite.py"; echo "$CRON" ) | crontab -

say "Done"
echo "Site:  https://$DOMAIN   (HTTPS appears once DNS points here)"
echo "Admin: https://$DOMAIN/admin  (password saved in $HOME/invite-all-admin.txt)"
echo "Edit $APP_DIR/.env for brand, WhatsApp number, Razorpay, email; then: cd $APP_DIR && sudo docker compose up -d"
echo "Update after a git push: cd $APP_DIR && git pull && sudo docker compose up -d --build"
