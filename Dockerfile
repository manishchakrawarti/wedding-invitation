FROM python:3.12-slim

# libfribidi0 lets Pillow's bundled libraqm shape Hindi and other Indian scripts correctly.
RUN apt-get update && apt-get install -y --no-install-recommends libfribidi0 fonts-dejavu-core \
    chromium fonts-noto-color-emoji libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt google-cloud-storage
COPY . .
RUN python scripts/fetch_fonts.py

# DATA_DIR must be on a persistent disk/volume (database + uploaded photos + generated files).
ENV PORT=8080 DATA_DIR=/data
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8080'))"
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips="*"
