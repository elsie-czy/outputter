FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Keep image small and deterministic.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy project files.
COPY . /app

# Runtime defaults (can be overridden by .env / compose env).
ENV WEB_HOST=0.0.0.0 \
    WEB_PORT=8101

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8101", "scripts.web_app:app"]
