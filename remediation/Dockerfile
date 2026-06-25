FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && ansible-galaxy collection install community.docker
COPY hook.py .
COPY playbooks/ /app/runner/project/
RUN mkdir -p /app/runner/inventory /app/audit \
 && printf 'localhost ansible_connection=local\n' > /app/runner/inventory/hosts
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1
CMD ["uvicorn", "hook:app", "--host", "0.0.0.0", "--port", "8080"]
