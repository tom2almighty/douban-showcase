FROM python:3.11-slim AS builder

WORKDIR /app


ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1


COPY requirements.txt .

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*


FROM python:3.11-slim

WORKDIR /app


ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1


COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/


COPY .env .
COPY src/ src/
COPY run.py /app/run.py


EXPOSE 5000

CMD ["python", "run.py", "--sync-incremental"]