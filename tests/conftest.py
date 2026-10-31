import os
import tempfile

# Configure before the app is imported: isolated data dir, no real providers, inline pipeline.
os.environ.update(
    DATA_DIR=tempfile.mkdtemp(prefix="shaadi-test-"),
    DATABASE_URL="",
    RUN_PIPELINE_INLINE="true",
    RETRY_BASE_DELAY_SECONDS="0",
    ADMIN_USERNAME="admin",
    ADMIN_PASSWORD="test-pass",
    RAZORPAY_KEY_ID="",
    RAZORPAY_KEY_SECRET="",
    RAZORPAY_WEBHOOK_SECRET="whsec_test",
    RAZORPAY_ME_URL="",
    TEST_ORDER_CODE="",
    TEST_COUPON_CODE="",
    INSTANT_PREVIEWS_PER_HOUR="1000",
    OWNER_WHATSAPP="",
    OWNER_EMAIL="",
    GEMINI_API_KEY="",
    WHATSAPP_TOKEN="",
    SMTP_HOST="",
    STORAGE_BACKEND="local",
    BASE_URL="http://testserver",
)

import io  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_auth():
    return ("admin", "test-pass")


@pytest.fixture
def photo_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (600, 800), (200, 150, 120)).save(buf, "JPEG")
    return buf.getvalue()
