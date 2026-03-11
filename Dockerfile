FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WHISPER_MODEL_SIZE=turbo
ENV WHISPER_DEVICE=cpu
ENV WHISPER_COMPUTE_TYPE=int8

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-web.txt ./requirements-web.txt
RUN pip install --no-cache-dir -r requirements-web.txt

COPY app.py ./app.py
COPY whisper_web ./whisper_web

EXPOSE 8010

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010"]
