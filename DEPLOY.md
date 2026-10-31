# Putting the site live on invite-all.com

**How it fits together:** you keep working on the code on your PC and push to GitHub
(`manishchakrawarti/wedding-invitation`). The host builds the site from GitHub and
redeploys on every push. Don't run the live site from your PC: it must stay online 24/7.

The app needs: Docker (Chromium for PDF/image exports, Hindi text shaping), a **persistent
disk** for the database and photos, and **about 2 GB of RAM** for 2K/4K exports.

---

## Step 1: Buy the domain

Buy **invite-all.com** from any registrar: Cloudflare, Namecheap, GoDaddy or Hostinger
(roughly ₹800–1,200 per year). You'll only need its **DNS settings** page later.

---

## Step 2 (recommended): Render.com, with no server to manage

Cost: **Standard plan ≈ $25/month** (2 GB RAM) **+ 5 GB disk ≈ $1.25/month**.
The free plan does **not** work (no persistent disk, it sleeps).

1. Go to https://render.com and **sign up with GitHub**.
2. **New → Blueprint**, then select the `wedding-invitation` repo. Render reads `render.yaml`.
3. Fill in the values it asks for:
   | Setting | What to put |
   |---|---|
   | `BRAND_NAME` | Your brand, e.g. `Invite All` |
   | `WHATSAPP_NUMBER` | Business WhatsApp, digits only, e.g. `919876543210` |
   | `SUPPORT_EMAIL`, `INSTAGRAM_HANDLE` | Shown in the site footer |
   | `OWNER_EMAIL`, `OWNER_WHATSAPP` | Where you get order/payment alerts |
   | `RAZORPAY_ME_URL` | Your Razorpay.me link (manual confirm) **or** leave empty and set the keys below |
   | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | Razorpay API keys, so customers unlock instantly |
   | `GEMINI_API_KEY`, `SMTP_*` | Optional: AI artwork and email sending |
   An **admin password** is generated automatically: Render → your service → **Environment** → `ADMIN_PASSWORD`.
4. Click **Apply**. The first build takes ~5–10 minutes. The first start then builds the 36 live demos
   in the background (a few minutes).
5. Test it on the temporary address Render gives you (`https://invite-all.onrender.com`).

### Connect invite-all.com
Render → service → **Settings → Custom Domains** shows the exact DNS records. Typically:

| Type | Name | Value |
|---|---|---|
| `A` | `@` | `216.24.57.1` |
| `CNAME` | `www` | `invite-all.onrender.com` |

Add them at your registrar's DNS page (delete any default "parking" records first). Render then issues
the HTTPS certificate automatically (usually within an hour). **Use the values Render shows** if they differ.

### Updating the live site later
```
git add -A && git commit -m "what changed" && git push
```
Render redeploys automatically. Your data on the disk is kept. Render snapshots the disk daily.

---

## Step 2 (cheaper alternative): your own server (VPS)

Cost: ~₹400–700/month for a **4 GB** Ubuntu server (e.g. Hetzner CX22, DigitalOcean, AWS Lightsail).
You manage updates and backups yourself.

1. Create an **Ubuntu 24.04** server with 4 GB RAM. Note its IP address.
2. At your registrar, add DNS records: `A @ → <server IP>` and `A www → <server IP>`.
3. On the server:
   ```bash
   curl -fsSL https://get.docker.com | sh
   git clone https://github.com/manishchakrawarti/wedding-invitation.git && cd wedding-invitation
   cp .env.example .env && nano .env      # set BRAND_NAME, ADMIN_PASSWORD (strong!), Razorpay, etc.
   docker compose up -d --build
   ```
   Caddy gets the HTTPS certificate for invite-all.com automatically.
4. Daily database backup (keeps 14). Add with `crontab -e`:
   ```
   30 2 * * * cd ~/wedding-invitation && docker compose exec -T app python scripts/backup_sqlite.py
   ```
5. Update after pushing new code: `git pull && docker compose up -d --build`

---

## Step 3: After the site is live

- [ ] Open `https://invite-all.com/admin` and log in (check the password works).
- [ ] Create a test invitation at `/create` and download the free version.
- [ ] **Razorpay**: Dashboard → Webhooks → add `https://invite-all.com/webhooks/razorpay`
      (events `payment.captured`, `order.paid`) and set `RAZORPAY_WEBHOOK_SECRET`.
      Razorpay also asks for your website URL during KYC: give `https://invite-all.com`.
- [ ] **Google Search Console**: add the site and submit `https://invite-all.com/sitemap.xml`.
- [ ] Make sure `TEST_COUPON_CODE` / `TEST_ORDER_CODE` are **not** set in production.
- [ ] Have your Terms, Privacy and Refund pages reviewed before taking real payments.
