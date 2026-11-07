# WASKITA API — image produksi
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# libgomp1 dibutuhkan LightGBM; build-essential untuk paket tanpa wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# Hanya salin kode aplikasi (bukan .venv, data lokal, atau .env).
COPY app ./app
COPY scripts ./scripts
COPY static ./static

# Jalankan sebagai user non-root.
RUN groupadd --system waskita \
    && useradd --system --gid waskita --home-dir /app --no-create-home waskita \
    && mkdir -p /app/models /app/data \
    && chown -R waskita:waskita /app/models /app/data

USER waskita

ENV PORT=8000
EXPOSE $PORT

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys,os; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{p}/health', timeout=4).status == 200 else 1)"

# SATU worker: detektor NILM per perangkat dan penjadwal APScheduler
# menyimpan state di memori proses. Lebih dari satu worker akan memecah
# state tersebut (event ON/OFF hilang, pesan WhatsApp terkirim ganda).
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers
