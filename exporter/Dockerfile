FROM python:3.12-slim

ARG LIBRESPEED_CLI_VERSION=1.0.13
ARG TARGETARCH=amd64

# ping nécessite iputils-ping ; curl+tar pour récupérer librespeed-cli
RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Installation du binaire librespeed-cli (client Go pour serveur LibreSpeed self-hosted)
RUN curl -fsSL -o /tmp/librespeed-cli.tar.gz \
      "https://github.com/librespeed/speedtest-cli/releases/download/v${LIBRESPEED_CLI_VERSION}/librespeed-cli_${LIBRESPEED_CLI_VERSION}_linux_${TARGETARCH}.tar.gz" \
    && tar -xzf /tmp/librespeed-cli.tar.gz -C /usr/local/bin librespeed-cli \
    && chmod +x /usr/local/bin/librespeed-cli \
    && rm /tmp/librespeed-cli.tar.gz \
    && librespeed-cli --version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY exporter.py .

# Valeurs par défaut, surchargeables via docker-compose / docker run -e
ENV PING_HOSTS="1.1.1.1,8.8.8.8" \
    PING_INTERVAL=15 \
    SPEEDTEST_INTERVAL=300 \
    EXPORTER_PORT=8000 \
    PING_TIMEOUT=2 \
    LIBRESPEED_SERVER_URL="" \
    LIBRESPEED_SERVER_NAME="self-hosted" \
    LIBRESPEED_DL_PATH="backend/garbage.php" \
    LIBRESPEED_UL_PATH="backend/empty.php" \
    LIBRESPEED_PING_PATH="backend/empty.php" \
    LIBRESPEED_GETIP_PATH="backend/getIP.php" \
    SPEEDTEST_TIMEOUT=120

EXPOSE 8000

CMD ["python", "exporter.py"]