#!/usr/bin/env python3
"""
Exporter Prometheus pour surveiller une connexion Freebox :
 - ping périodique vers un ou plusieurs hosts (toutes les PING_INTERVAL secondes)
 - speedtest périodique (toutes les SPEEDTEST_INTERVAL secondes)

Metriques exposées sur :PORT/metrics
"""

import json
import os
import re
import subprocess
import threading
import time
import logging

from prometheus_client import start_http_server, Gauge, Counter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("netpulse-exporter")

# ---------------------------------------------------------------------------
# Configuration (via variables d'environnement)
# ---------------------------------------------------------------------------
PING_HOSTS = [h.strip() for h in os.environ.get("PING_HOSTS", "1.1.1.1,8.8.8.8").split(",") if h.strip()]
PING_INTERVAL = int(os.environ.get("PING_INTERVAL", "15"))          # secondes
SPEEDTEST_INTERVAL = int(os.environ.get("SPEEDTEST_INTERVAL", "300"))  # secondes (5 min)
EXPORTER_PORT = int(os.environ.get("EXPORTER_PORT", "8000"))
PING_TIMEOUT = int(os.environ.get("PING_TIMEOUT", "2"))             # secondes

# --- Serveur LibreSpeed auto-hébergé ---
# URL de base de ton instance LibreSpeed, ex: "https://speedtest.example.com/"
LIBRESPEED_SERVER_URL = os.environ.get("LIBRESPEED_SERVER_URL", "").strip()
LIBRESPEED_SERVER_NAME = os.environ.get("LIBRESPEED_SERVER_NAME", "self-hosted")
# Chemins des backends LibreSpeed (par défaut = installation standard, à adapter si custom)
LIBRESPEED_DL_PATH = os.environ.get("LIBRESPEED_DL_PATH", "backend/garbage.php")
LIBRESPEED_UL_PATH = os.environ.get("LIBRESPEED_UL_PATH", "backend/empty.php")
LIBRESPEED_PING_PATH = os.environ.get("LIBRESPEED_PING_PATH", "backend/empty.php")
LIBRESPEED_GETIP_PATH = os.environ.get("LIBRESPEED_GETIP_PATH", "backend/getIP.php")
SPEEDTEST_TIMEOUT = int(os.environ.get("SPEEDTEST_TIMEOUT", "120"))  # secondes

# ---------------------------------------------------------------------------
# Metriques Prometheus
# ---------------------------------------------------------------------------
ping_rtt_ms = Gauge(
    "network_ping_rtt_milliseconds", "Temps de réponse du ping (ms)", ["host"]
)
ping_up = Gauge(
    "network_ping_up", "1 si le ping a réussi, 0 sinon", ["host"]
)
ping_total = Counter(
    "network_ping_total", "Nombre total de pings envoyés", ["host"]
)
ping_failures_total = Counter(
    "network_ping_failures_total", "Nombre total de pings échoués", ["host"]
)

speedtest_download_mbps = Gauge(
    "network_speedtest_download_mbps", "Débit descendant mesuré (Mbps)"
)
speedtest_upload_mbps = Gauge(
    "network_speedtest_upload_mbps", "Débit montant mesuré (Mbps)"
)
speedtest_ping_ms = Gauge(
    "network_speedtest_ping_milliseconds", "Latence mesurée lors du speedtest (ms)"
)
speedtest_jitter_ms = Gauge(
    "network_speedtest_jitter_milliseconds", "Jitter mesuré lors du speedtest (ms)"
)
speedtest_up = Gauge(
    "network_speedtest_up", "1 si le dernier speedtest a réussi, 0 sinon"
)
speedtest_total = Counter(
    "network_speedtest_total", "Nombre total de speedtests exécutés"
)
speedtest_failures_total = Counter(
    "network_speedtest_failures_total", "Nombre total de speedtests échoués"
)
speedtest_last_run_timestamp = Gauge(
    "network_speedtest_last_run_timestamp_seconds", "Timestamp Unix du dernier speedtest"
)

# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------
RTT_REGEX = re.compile(r"time[=<]([\d.]+)")


def do_ping(host: str):
    ping_total.labels(host=host).inc()
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(PING_TIMEOUT), host],
            capture_output=True,
            text=True,
            timeout=PING_TIMEOUT + 2,
        )
        if result.returncode == 0:
            match = RTT_REGEX.search(result.stdout)
            if match:
                rtt = float(match.group(1))
                ping_rtt_ms.labels(host=host).set(rtt)
                ping_up.labels(host=host).set(1)
                log.info("ping %s -> %.2f ms", host, rtt)
                return
        # échec (pas de réponse / hôte injoignable)
        ping_up.labels(host=host).set(0)
        ping_failures_total.labels(host=host).inc()
        log.warning("ping %s -> échec", host)
    except Exception as exc:
        ping_up.labels(host=host).set(0)
        ping_failures_total.labels(host=host).inc()
        log.error("ping %s -> exception: %s", host, exc)


def ping_loop():
    while True:
        start = time.time()
        for host in PING_HOSTS:
            do_ping(host)
        elapsed = time.time() - start
        time.sleep(max(0, PING_INTERVAL - elapsed))


# ---------------------------------------------------------------------------
# Speedtest (via librespeed-cli, pointé vers un serveur LibreSpeed self-hosted)
# ---------------------------------------------------------------------------
LIBRESPEED_SERVERS_FILE = "/tmp/librespeed-servers.json"


def build_librespeed_server_file():
    """Génère le fichier de définition de serveur attendu par librespeed-cli
    (--local-json), pointé vers l'instance self-hosted configurée."""
    server_def = [
        {
            "id": 1,
            "name": LIBRESPEED_SERVER_NAME,
            "server": LIBRESPEED_SERVER_URL.rstrip("/") + "/",
            "dlURL": LIBRESPEED_DL_PATH,
            "ulURL": LIBRESPEED_UL_PATH,
            "pingURL": LIBRESPEED_PING_PATH,
            "getIpURL": LIBRESPEED_GETIP_PATH,
        }
    ]
    with open(LIBRESPEED_SERVERS_FILE, "w") as f:
        json.dump(server_def, f)


def do_speedtest():
    if not LIBRESPEED_SERVER_URL:
        log.error("speedtest -> LIBRESPEED_SERVER_URL non configurée, test ignoré")
        return

    speedtest_total.inc()
    try:
        build_librespeed_server_file()

        result = subprocess.run(
            [
                "librespeed-cli",
                "--local-json", LIBRESPEED_SERVERS_FILE,
                "--server", "1",
                "--json",
                "--no-icmp",  # pas de privilèges root nécessaires pour le ping ICMP
            ],
            capture_output=True,
            text=True,
            timeout=SPEEDTEST_TIMEOUT,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"librespeed-cli a retourné le code {result.returncode}: {result.stderr.strip()}"
            )

        data = json.loads(result.stdout)
        if isinstance(data, list):
            data = data[0]

        download = float(data["download"])
        upload = float(data["upload"])
        ping = float(data["ping"])
        jitter = float(data.get("jitter", 0))

        speedtest_download_mbps.set(download)
        speedtest_upload_mbps.set(upload)
        speedtest_ping_ms.set(ping)
        speedtest_jitter_ms.set(jitter)
        speedtest_up.set(1)
        speedtest_last_run_timestamp.set(time.time())

        log.info(
            "speedtest -> down: %.2f Mbps | up: %.2f Mbps | ping: %.2f ms | jitter: %.2f ms",
            download, upload, ping, jitter,
        )
    except Exception as exc:
        speedtest_up.set(0)
        speedtest_failures_total.inc()
        log.error("speedtest -> exception: %s", exc)


def speedtest_loop():
    # petit délai initial pour laisser l'exporter démarrer proprement
    time.sleep(10)
    while True:
        start = time.time()
        do_speedtest()
        elapsed = time.time() - start
        time.sleep(max(0, SPEEDTEST_INTERVAL - elapsed))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    log.info(
        "Démarrage exporter | hosts=%s | ping_interval=%ss | speedtest_interval=%ss | port=%s",
        PING_HOSTS, PING_INTERVAL, SPEEDTEST_INTERVAL, EXPORTER_PORT,
    )
    start_http_server(EXPORTER_PORT)

    threading.Thread(target=ping_loop, daemon=True).start()
    threading.Thread(target=speedtest_loop, daemon=True).start()

    # garder le process principal en vie
    while True:
        time.sleep(3600)