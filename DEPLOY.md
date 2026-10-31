# Putting the site live on invite-all.com (cheapest setup)

**How it fits together:** you keep working on the code on your PC and push to GitHub. The server
pulls from GitHub. Don't run the live site from your PC: it must stay online 24/7.

## What it costs

| Item | Cheapest choice | Cost |
|---|---|---|
| Domain `invite-all.com` | **Cloudflare Registrar** (sells at cost, no renewal mark-up) | **≈ ₹900 / year** |
| Server | **Oracle Cloud Always Free** (ARM, up to 4 CPU / 24 GB RAM / 200 GB disk) | **₹0** |
| HTTPS certificate | Let's Encrypt via Caddy (automatic) | ₹0 |
| DNS + DDoS protection | Cloudflare free plan | ₹0 |
| Code hosting | GitHub | ₹0 |
| Email to customers | Gmail SMTP (500/day) or Brevo free (300/day) | ₹0 |
| WhatsApp | wa.me share links (no API) | ₹0 |
| Uptime alerts | UptimeRobot free | ₹0 |
| AI artwork (Gemini) | Off: free built-in designs | ₹0 (≈ ₹3.5/image if you turn it on) |
| Payments | Razorpay: no monthly fee | ≈ 2% + GST per payment (≈ ₹0.21 on ₹9) |
| **Total** | | **≈ ₹900 per year** |

**Backup plan** if Oracle won't give you a free server (it sometimes runs out in Indian regions, or rejects
some cards): **Hetzner CX22** (2 CPU, 4 GB) ≈ €3.79/month ≈ **₹380/month**. Same steps, just a different provider.

(`render.yaml` is also included: the easiest option with nothing to manage, but ≈ $26/month.)

---

## Step 1: Buy the domain (Cloudflare)
1. Create a free account at https://dash.cloudflare.com, then **Domain Registration → Register Domains**.
2. Search `invite-all.com` and buy it (≈ ₹900/yr, renews at the same price).
3. You now manage DNS in Cloudflare (used in Step 3).

## Step 2: Get the free server (Oracle Cloud)
1. Sign up at https://www.oracle.com/cloud/free/ and pick **India West (Mumbai)** or **India South (Hyderabad)** as the
   home region (it can't be changed later). A card is needed for verification only: a small hold is refunded.
2. **Compute → Instances → Create instance**:
   - Image: **Ubuntu 24.04**
   - Shape: **Ampere (VM.Standard.A1.Flex)**, **2 OCPU, 12 GB** (free; up to 4/24 is free)
   - Download the **SSH key** it offers, and note the **public IP** after it starts.
   - "Out of capacity"? Try another availability domain, or try again later.
3. **Networking → your VCN → Security List → Add Ingress Rules**: TCP **80** and **443** from `0.0.0.0/0`.
4. Recommended: upgrade the account to **Pay As You Go**. It stays ₹0 within the free limits, and
   Oracle won't reclaim "idle" free servers. Add a **budget alert of ₹100** so you're told if anything ever costs money.

## Step 3: Point the domain at the server
In Cloudflare → `invite-all.com` → **DNS**, add (proxy **off / grey cloud** at first, so HTTPS can be issued):

| Type | Name | Content |
|---|---|---|
| `A` | `@` | your server's public IP |
| `A` | `www` | your server's public IP |

## Step 4: One command on the server
Connect: `ssh -i <your-key> ubuntu@<server-ip>`, then run:
```bash
curl -fsSL https://raw.githubusercontent.com/manishchakrawarti/wedding-invitation/main/deploy/setup_server.sh | bash
```
It installs Docker, opens the firewall, adds swap on small machines, starts the site with automatic HTTPS,
schedules daily database backups, and **prints your admin password** (also saved in `~/invite-all-admin.txt`).

Then set your details:
```bash
nano ~/invite-all/.env      # BRAND_NAME, WHATSAPP_NUMBER, SUPPORT_EMAIL, OWNER_EMAIL, RAZORPAY_ME_URL or keys, SMTP_*
cd ~/invite-all && sudo docker compose up -d
```
Open **https://invite-all.com**. (Once HTTPS works you may switch Cloudflare's proxy to orange for extra protection.)

## Updating the site later
On your PC: `git add -A && git commit -m "what changed" && git push`. Then on the server:
```bash
cd ~/invite-all && git pull && sudo docker compose up -d --build
```

## After launch (all free)
- [ ] Log in at `/admin` and create a test invitation at `/create`.
- [ ] **Free email**: Gmail app password → `SMTP_HOST=smtp.gmail.com`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`.
- [ ] **Razorpay**: give `https://invite-all.com` during KYC. If using API keys, add webhook
      `https://invite-all.com/webhooks/razorpay` (events `payment.captured`, `order.paid`).
- [ ] **UptimeRobot** (free): monitor `https://invite-all.com/healthz` and get an email if the site goes down.
- [ ] **Google Search Console** (free): submit `https://invite-all.com/sitemap.xml`.
- [ ] Every month or so, download a backup: `scp -i <key> ubuntu@<ip>:~/invite-all-backups.tar .` (see below).
- [ ] Keep `TEST_COUPON_CODE` / `TEST_ORDER_CODE` empty in production (the setup script does this).

### Copying backups to your PC
Backups are made daily inside the server's data volume. To download them:
```bash
# on the server
cd ~/invite-all && sudo docker compose cp app:/data/backups ./backups && tar -cf ~/invite-all-backups.tar backups
```
