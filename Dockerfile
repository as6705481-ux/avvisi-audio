# ── Base ───────────────────────────────────────────────────────────────────
FROM python:3.13-slim

# ── App ────────────────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ── Runtime ────────────────────────────────────────────────────────────────
ENV PORT=8000
EXPOSE 8000

# 2 workers es suficiente para el plan gratuito de Render (512 MB RAM).
# Aumentar a 4 en plan paid. Timeout 120s por compilación LaTeX.
CMD gunicorn main:app \
    --bind 0.0.0.0:$PORT \
    --workers 2 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
