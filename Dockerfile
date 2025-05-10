FROM python:3.11-slim


WORKDIR /app


ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1


RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*


COPY requirements.txt .
COPY .env .
COPY src/ src/
COPY run.py /app/run.py


RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p data/covers

EXPOSE 5000


CMD ["python", "run.py"]