FROM python:3.12-slim

# libfribidi0 lets Pillow's bundled libraqm shape Hindi and other Indian scripts correctly.
RUN apt-get update && apt-get install -y --no-install-recommends libfribidi0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt google-cloud-storage
COPY . .
RUN python scripts/fetch_fonts.py

ENV PORT=8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips="*"
