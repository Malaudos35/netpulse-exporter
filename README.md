# netpulse-exporter

Exporter Prometheus pour surveiller la qualité d'une connexion internet (ping + speedtest), pensé à l'origine pour diagnostiquer des problèmes de réseau Freebox mais utilisable avec n'importe quelle box/FAI.

## Contenu

```
netpulse-exporter/
├── docker-compose.yml
├── exporter/
│   ├── Dockerfile
│   ├── exporter.py
│   └── requirements.txt
└── prometheus/
    └── prometheus.yml
```

- **exporter** : petit service Python qui ping des hôtes toutes les 15s et lance un speedtest toutes les 5 min, et expose le tout en métriques Prometheus sur `http://localhost:8000/metrics`.
- **prometheus** : scrape l'exporter toutes les 15s et stocke l'historique.
- **grafana** : pour visualiser les graphiques.

## Configuration du speedtest (LibreSpeed self-hosted)

Le speedtest utilise [librespeed-cli](https://github.com/librespeed/speedtest-cli), pointé vers **ton propre serveur LibreSpeed** (VPS ou autre), plutôt que les serveurs publics Ookla. Ça permet de mesurer le débit vers un point fixe que tu contrôles, utile pour isoler un problème Freebox/FAI d'un problème tiers.

1. Copie `.env.example` en `.env` :
   ```bash
   cp .env.example .env
   ```
2. Renseigne l'URL de ton instance LibreSpeed dans `.env` :
   ```
   LIBRESPEED_SERVER_URL=https://speedtest.example.com/
   LIBRESPEED_SERVER_NAME=mon-vps
   ```
3. Si ton installation LibreSpeed utilise des chemins de backend non standards (par défaut : `backend/garbage.php`, `backend/empty.php`, `backend/getIP.php`), ajuste les variables `LIBRESPEED_*_PATH` correspondantes dans `.env`.

Sans `LIBRESPEED_SERVER_URL` configurée, le speedtest est simplement ignoré (log d'erreur), le ping continue de fonctionner normalement.

## Démarrage

```bash
cd netpulse-exporter
docker compose up -d --build
```

Puis :
- Metriques brutes : http://localhost:8000/metrics
- Prometheus : http://localhost:9090
- Grafana : http://localhost:3000 (login: `admin` / `admin`, à changer au premier login)

## Configurer Grafana

1. Se connecter sur http://localhost:3000
2. **Connections > Data sources > Add data source > Prometheus**
3. URL : `http://prometheus:9090` (nom du service docker-compose, pas localhost)
4. **Save & test**
5. Créer un dashboard avec des panels utilisant ces requêtes PromQL :

### Latence ping (par host)
```
network_ping_rtt_milliseconds
```

### Disponibilité (ping OK/KO)
```
network_ping_up
```

### Taux de perte de paquets (sur 5 min glissantes)
```
1 - (increase(network_ping_failures_total[5m]) / increase(network_ping_total[5m]))
```
(inverse ça si tu veux directement le taux de perte : enlève le `1 -`)

### Débit descendant / montant (Mbps)
```
network_speedtest_download_mbps
network_speedtest_upload_mbps
```

### Latence et jitter speedtest
```
network_speedtest_ping_milliseconds
network_speedtest_jitter_milliseconds
```

### Speedtest en échec
```
network_speedtest_up == 0
```

## Personnalisation

Dans `docker-compose.yml`, variable d'environnement du service `netpulse-exporter` :

| Variable | Description | Défaut |
|---|---|---|
| `PING_HOSTS` | Liste d'hôtes séparés par des virgules | `1.1.1.1,8.8.8.8` |
| `PING_INTERVAL` | Intervalle entre chaque ping (secondes) | `15` |
| `SPEEDTEST_INTERVAL` | Intervalle entre chaque speedtest (secondes) | `300` |
| `PING_TIMEOUT` | Timeout d'un ping (secondes) | `2` |

Pense à remplacer `192.168.1.254` par l'IP réelle de ta Freebox si tu veux distinguer un problème LAN d'un problème WAN/FAI.

## Notes

- Le speedtest consomme de la bande passante à chaque exécution (toutes les 5 min par défaut) : si tu es sur une connexion limitée ou que tu veux éviter de fausser tes propres mesures de débit, augmente `SPEEDTEST_INTERVAL`.
- `docker compose logs -f netpulse-exporter` pour suivre les pings/speedtests en direct.