# Argus — container image for Cloud Run (deployability concept).
FROM python:3.13-slim

WORKDIR /app

# System deps kept minimal; the MCP server runs as a subprocess of the app.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run provides $PORT; default to 8080 locally.
ENV PORT=8080
EXPOSE 8080

# GOOGLE_API_KEY is injected at deploy time (never baked into the image).
CMD ["sh", "-c", "uvicorn serve:app --host 0.0.0.0 --port ${PORT}"]
