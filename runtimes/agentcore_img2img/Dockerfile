FROM --platform=linux/arm64 python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY runtimes ./runtimes

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "." && \
    pip install --no-cache-dir "bedrock-agentcore>=1.0.0"

EXPOSE 8080

CMD ["python", "runtimes/agentcore_img2img/app/main.py"]
