# aiops-api — the platform control plane. Built from the REPO ROOT context so it
# can bake the model code + trained models (plug-and-play, no host venv).
FROM python:3.12-slim
WORKDIR /app
COPY control-plane/requirements.txt control-plane/requirements.txt

# FIXED: Added default-timeout to prevent huge package downloads from crashing midway
RUN pip install --default-timeout=1000 --no-cache-dir -r control-plane/requirements.txt

COPY ai/ ./ai/
COPY chaos/ ./chaos/
COPY models/ ./models/
COPY control-plane/ ./control-plane/
EXPOSE 8050
HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8050/api/health')" || exit 1
# dir name has a hyphen (not import-safe) -> add it to the path via --app-dir
CMD ["uvicorn", "server:app", "--app-dir", "/app/control-plane", "--host", "0.0.0.0", "--port", "8050"]
