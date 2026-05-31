FROM --platform=linux/arm64 python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY runtimes ./runtimes

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "."

EXPOSE 8080

CMD ["uvicorn", "runtimes.agentcore_img2img.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
