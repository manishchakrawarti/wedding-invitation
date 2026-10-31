# Invite All (invite-all.com): invitations for weddings and every occasion

A complete web app for selling Indian wedding invitations. Customers order, pay, approve a proof and receive their cards and RSVP page. Behind the scenes, an AI pipeline designs each card and you review it before it goes out.

Brand: **Invite All** (invite-all.com). Change it in `.env` (`BRAND_NAME`).

## Run it locally

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python scripts\fetch_fonts.py      # card fonts (already in app/assets/fonts)
copy .env.example .env                            # edit brand, admin password, keys
.venv\Scripts\python -m uvicorn app.main:app --reload
```

| Page | URL |
|---|---|
| Website | http://localhost:8000 |
| Admin (login from `.env`) | http://localhost:8000/admin |
| Tests | `.venv\Scripts\python -m pytest -q` |

**The app works with no API keys.** Without them, payments show a "Simulate payment" button, designs come from the built-in offline generator, and WhatsApp/email messages are only logged under *Admin → Messages*. Add keys one at a time as you go live.

## What makes us different: smart guest invites

A free AI tool can make a picture. We run the whole invitation:

| Feature | Where |
|---|---|
| **Cinematic invite page:** palace doors open, petals fall, the family's music plays, with a countdown, timeline, dress codes, map, story and blessings wall | `/e/<slug>` (general) and `/i/<code>` (personal), template `experience.html` |
| **Personal invite per guest:** greets them by name and shows only the functions they're invited to | `Invitee` model, `app/services/invites.py` |
| **One-tap WhatsApp sending:** opens WhatsApp with a personal message and link, with no WhatsApp API needed | Family console "Send" |
| **Live tracking:** sent, opened (×N) and replied; headcount per function; veg/Jain/non-veg counts; arrival dates and pickup list; CSV export for the caterer | `/e/<slug>/guests?key=<order token>` (`family.html`) |
| **Shagun via UPI** (QR and deep link), **add-to-calendar** (.ics with a 1-day reminder), **live-stream link** | Event details form in the console |
| **Growth loop:** every invite page ends with "Create one for your family's wedding →" | `experience.html` footer |
| **Live demo** for Instagram and WhatsApp marketing: a full sample wedding with guests and RSVPs | `/demo` (guest view), `/demo/console` (family view) |

## What's built (mapped to the plan in `prompt.txt`)

| Plan item | Where |
|---|---|
| A1 Brand | `.env` (name, Instagram, WhatsApp, email) |
| A2 Policies | `/terms` (incl. photo consent), `/privacy` (DPDP Act 2023), `/refund`: `app/templates/legal.html`. **Have a lawyer review them.** |
| A3 Price list | `app/catalog.py`: packages, add-ons, styles, languages |
| B1 Landing page | `/`: samples gallery, how it works, pricing, FAQ, WhatsApp button |
| B2 Order form | `/order`: couple, family, language and script names, functions with date/time/venue, photos with consent, referral code |
| B3 Payment | Razorpay (UPI/cards), full or advance payment, balance after approval, webhook, offline UPI entry in admin |
| B4 Proof approval | `/o/<token>/proof`: watermarked low-res proofs, approve or request changes |
| B5 Delivery | Download page plus WhatsApp and email messages at each step |
| B6 RSVP page | `/e/<couple-slug>`: schedule, Google Map, RSVP form, QR (also printed on the card); private guest list and CSV for the couple |
| C1 Order database | SQLAlchemy: SQLite locally, Postgres/Cloud SQL via `DATABASE_URL` |
| C2 Photo storage | Local disk or GCS (`STORAGE_BACKEND=gcs`). Photos deleted after 30 days (daily job, plus `deploy/gcs-lifecycle.json`); EXIF/GPS stripped on upload |
| C3 Image generation | `app/services/generation.py`: Gemini, with retries, plus the offline fallback |
| C4 Prompt library | `app/catalog.py` STYLES and `app/services/prompts.py`: 8 styles (North/South Indian, Bengali, Nikah, Christian, Haldi, Mehndi, Modern) |
| C5 Text overlay | `app/services/overlay.py`: the AI paints **no text**; names are typeset with real fonts, so spellings are always exact |
| C8 Orchestrator | `app/services/pipeline.py`: paid → generate → overlay → QC → owner review → proof → final |
| C9 Quality check | `app/services/qc.py`: text match, fit, Indic shaping, contrast, resolution, optional face detection |
| C10 Retry & monitoring | 3 attempts with backoff; failure alerts to the owner; unfinished orders re-queued on restart; event timeline per order |
| D1 Admin dashboard | `/admin`: orders, filters, review, send proof, regenerate with notes, edit details, deliver, cancel, upload video |
| D2 Revision tracker | 2 free revisions (configurable), paid extra revisions, admin can grant more |
| D4 Revenue dashboard | In-app stats (revenue, margin, season by wedding month) plus `/admin/export/orders.csv` for Looker Studio / Power BI |
| D5 Cost tracker | API cost recorded per generated image (`IMAGE_COST_INR`), margin per order |
| E2 WhatsApp automation | `/webhooks/whatsapp`: auto-reply with price list and order link; replies with order status when sent an order ID |
| E3 Referrals | Every order gets a code; friends get ₹100 off |

### Not built yet (next phases)
- **C6/C7 Video generation**: Video and Premium packages sell the video, but for now you make it by hand and upload it on the admin order page (the customer is notified). The dashboard flags orders with a pending video.
- **D3 Partner/reseller portal, E1 content engine, E4 reseller kit, E5 anniversary follow-ups, F expansion products.** The data model already records `source`, `marketing_consent` and `referred_by_code` to support these.

## Going live checklist

1. **Brand and admin:** set `BRAND_NAME`, `WHATSAPP_NUMBER`, `INSTAGRAM_HANDLE`, a strong `ADMIN_PASSWORD`, and `BASE_URL` (your domain).
2. **Gemini:** set `GEMINI_API_KEY`. Check `IMAGE_COST_INR` against current Gemini pricing. Test a few orders and replace the offline sample images: put real outputs at `app/static/samples/<style>.jpg`.
3. **Razorpay:** add the API keys. Add a webhook to `https://<domain>/webhooks/razorpay` (events `payment.captured`, `order.paid`) and set `RAZORPAY_WEBHOOK_SECRET`.
4. **WhatsApp Cloud API:** set the token and phone number ID. Point the webhook to `https://<domain>/webhooks/whatsapp` with `WHATSAPP_VERIFY_TOKEN`. Messages sent more than 24 hours after a customer's last message need **approved templates**; create them in Meta Business Manager.
5. **Email:** any SMTP provider (`SMTP_*`).
6. **Deploy (Cloud Run):**
   ```bash
   gcloud run deploy shaadi --source . --region asia-south1 --allow-unauthenticated \
     --set-env-vars STORAGE_BACKEND=gcs,GCS_BUCKET=...,DATABASE_URL=postgresql+psycopg://... \
     --no-cpu-throttling --min-instances 1
   gsutil lifecycle set deploy/gcs-lifecycle.json gs://YOUR_BUCKET
   ```
   Add `psycopg[binary]` to `requirements.txt` for Postgres. `--no-cpu-throttling` keeps background generation running after the request returns.

## Hindi and regional-language cards

Indian scripts need *shaping* (matras, conjuncts). Pillow does this through libraqm and **FriBiDi**:
- **Docker / Cloud Run:** included (`libfribidi0` in the Dockerfile), so Hindi, Marathi, Bengali, Gujarati, Punjabi, Tamil and Telugu all render correctly.
- **Windows dev machine:** FriBiDi isn't installed, so QC marks regional-script cards as **failed** rather than send broken text. English cards work everywhere. To test Hindi locally, run the Docker image (`docker build -t shaadi . && docker run -p 8080:8080 shaadi`).

The headings in each language (e.g. "शुभ विवाह", "সাদর আমন্ত্রণ") are in `app/catalog.py`. Have a native speaker proofread them.

## Project layout

```
app/
  catalog.py         prices, packages, add-ons, functions, languages, styles + prompts
  config.py          all settings (.env)
  models.py          orders, assets, payments, revisions, events, costs, notifications, guests
  routes/            public.py (site, order, pay, proof, downloads), rsvp.py, admin.py, webhooks.py
  services/          pipeline, generation, overlay, cards, qc, payments, notify, orders, storage, maintenance
  templates/         Jinja pages (+ admin/)
  static/css/        styles
  assets/fonts/      OFL fonts used on cards
scripts/fetch_fonts.py
tests/test_flow.py   end-to-end business-flow tests
```
