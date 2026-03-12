#!/bin/bash
# Script d'application des corrections monitoring
# Applique toutes les corrections pour Prometheus 3.0, Loki 3.2, Tempo 2.6, pgAdmin 9.9

set -e

echo "🔧 Application des corrections monitoring..."

# 1. Prometheus: Ajouter retention flags
echo "1️⃣ Correction Prometheus 3.0 retention flags..."
sed -i "/- '--storage.tsdb.path=\/prometheus'/a\\      - '--storage.tsdb.retention.time=15d'\\n      - '--storage.tsdb.retention.size=10GB'" docker-compose.dev.yml

# 2. Loki: Supprimer champs obsolètes
echo "2️⃣ Correction Loki 3.2 configuration..."
sed -i '/max_transfer_retries:/d' infrastructure/observability/loki/loki-config.yml
sed -i '/shared_store: filesystem/d' infrastructure/observability/loki/loki-config.yml
sed -i '/max_look_back_period:/d' infrastructure/observability/loki/loki-config.yml
sed -i '/chunk_store_config:/,/max_look_back_period:/d' infrastructure/observability/loki/loki-config.yml
sed -i '/cache_config:/,/validity:/d' infrastructure/observability/loki/loki-config.yml

# 3. Tempo: Renommer champs v2
echo "3️⃣ Correction Tempo 2.6 field names..."
sed -i 's/index_downsample_bytes:/v2_index_downsample_bytes:/' infrastructure/observability/tempo/tempo.yml
sed -i 's/encoding:/v2_encoding:/' infrastructure/observability/tempo/tempo.yml
sed -i '/overrides:/,/global_overrides:/d' infrastructure/observability/tempo/tempo.yml

# 4. pgAdmin: Upgrade vers 9.9
echo "4️⃣ Upgrade pgAdmin 8.14 → 9.9..."
sed -i 's/dpage\/pgadmin4:8.14/dpage\/pgadmin4:9.9/' docker-compose.dev.yml

# 5. Jaeger: Vérifier docker-compose.prod.yml existe
if [ -f "docker-compose.prod.yml" ]; then
    echo "5️⃣ Upgrade Jaeger 1.51 → 1.62..."
    sed -i 's/jaegertracing\/all-in-one:1.51/jaegertracing\/all-in-one:1.62/' docker-compose.prod.yml
else
    echo "⚠️  docker-compose.prod.yml non trouvé, skip Jaeger upgrade"
fi

echo "✅ Corrections appliquées avec succès!"
echo ""
echo "Prochaine étape: redémarrer les services monitoring"
echo "  docker compose -f docker-compose.dev.yml up -d prometheus loki tempo grafana pgadmin"
