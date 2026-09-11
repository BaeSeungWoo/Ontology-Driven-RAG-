FROM nvidia/cuda:12.9.2-cudnn-runtime-ubuntu24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv ffmpeg ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" HF_HOME=/models/huggingface
WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
COPY server.py ./
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15m --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--ws-max-size", "65536", "--ws-max-queue", "8", "--no-access-log", "--log-level", "warning"]
