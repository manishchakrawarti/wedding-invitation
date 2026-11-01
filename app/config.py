"""All runtime settings. Every value can be overridden with an environment variable
or a line in `.env` (e.g. BRAND_NAME="My Studio")."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    # --- Brand (A1) ---
    brand_name: str = "Invite All"
    brand_tagline: str = "Beautiful invitations for weddings and every occasion, ready to share on WhatsApp"
    order_prefix: str = "IA"
    instagram_handle: str = "inviteall"
    whatsapp_number: str = "919999999999"  # country code + number, digits only
    support_email: str = "hello@example.com"
    business_city: str = "India"
    owner_whatsapp: str = ""  # receives failure / review alerts
    owner_email: str = ""

    base_url: str = "http://localhost:8000"
    data_dir: Path = BASE_DIR / "data"
    database_url: str = ""  # empty = SQLite file inside data_dir

    admin_username: str = "admin"
    admin_password: str = "change-me"

    # --- Payments (B3) ---
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    # Until API keys are set: customers pay on this Razorpay.me page and the owner confirms in admin.
    razorpay_me_url: str = ""
    advance_percent: int = 50
    # Secret code for ₹1 test orders: /order?test=<code>. Empty = disabled.
    test_order_code: str = ""
    test_order_price_inr: int = 1
    # Secret coupon that unlocks a ₹99 instant preview for free (owner testing). Empty = disabled.
    test_coupon_code: str = ""

    # --- Generation (C3) ---
    gemini_api_key: str = ""
    gemini_image_model: str = "gemini-2.5-flash-image"
    image_cost_inr: float = 3.5  # what one generated image costs you; feeds the cost tracker
    generation_max_attempts: int = 3
    retry_base_delay_seconds: float = 2.0
    auto_send_proof_if_qc_pass: bool = False  # Phase 3: skip manual review when QC is green

    # --- Notifications (B5, E2) ---
    # Telegram bot (free): owner alerts, customer updates + PDF, guests' personal PDF. Token from @BotFather.
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""  # optional: the bot's @name, otherwise asked from Telegram
    telegram_owner_chat_id: str = ""  # optional: alerts also go here (or tap "Connect Telegram" in admin)
    # WhatsApp Cloud API: Meta charges for business-started messages. Leave empty to stay free.
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_api_version: str = "v21.0"
    whatsapp_verify_token: str = "change-me-verify"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # --- Storage & policies ---
    storage_backend: str = "local"  # local | gcs
    gcs_bucket: str = ""
    photo_retention_days: int = 30
    final_retention_days: int = 90
    max_free_revisions: int = 2
    referral_discount_inr: int = 100
    chrome_path: str = ""  # e-invite PDF/image export; empty = auto-detect Chrome/Edge/Chromium
    max_concurrent_renders: int = 1  # PDF/long-image renders at once (raise on big servers)
    instant_previews_per_hour: int = 6  # free ₹99-funnel previews per visitor (AI images cost money)

    # Tests run the pipeline synchronously instead of on a worker thread.
    run_pipeline_inline: bool = False

    @property
    def payments_live(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def payment_provider(self) -> str:
        if self.payments_live:
            return "razorpay"
        return "manual" if self.razorpay_me_url else "mock"

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.whatsapp_token and self.whatsapp_phone_number_id)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"


settings = Settings()
