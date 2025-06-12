###########################
# Builder image           #
###########################
FROM python:3.11-slim AS builder

WORKDIR /install

# Install build tools and OpenMP runtime needed for LightGBM
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Increase pip timeout and retries to avoid network timeouts in CI
RUN PIP_DEFAULT_TIMEOUT=120 pip install --no-cache-dir --prefix=/install -r requirements.txt --retries 10

###########################
# Runtime image           #
###########################
FROM python:3.11-slim

# Runtime dependency for LightGBM
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /install /usr/local

COPY . .

CMD ["python", "back_end/store_listings.py", "--pages", "1"]
