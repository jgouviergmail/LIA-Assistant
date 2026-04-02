# ROUTES - Google Routes API Integration

> Documentation complète de l'intégration Google Routes API pour les calculs d'itinéraires et directions
>
> Version: 1.0
> Date: 2026-01-12

---

## Table des Matières

- [Vue d'Ensemble](#vue-densemble)
- [Architecture](#architecture)
- [Tools Disponibles](#tools-disponibles)
- [Client API](#client-api)
- [Cache Redis](#cache-redis)
- [Intégration Cross-Domain](#intégration-cross-domain)
- [Configuration](#configuration)
- [Métriques](#métriques)

---

## Vue d'Ensemble

Le domaine **Routes** fournit des fonctionnalités de calcul d'itinéraires via l'API Google Routes. Contrairement aux autres connecteurs Google (Gmail, Calendar, Contacts), ce domaine utilise une **API Key globale** et non OAuth par utilisateur.

### Fonctionnalités Principales

- **Route Computation** : Directions de A vers B avec traffic temps réel
- **Route Matrix** : Optimisation N origines vers M destinations
- **Traffic-Aware Routing** : Conditions de trafic en temps réel
- **Multiple Travel Modes** : DRIVE, WALK, BICYCLE, TRANSIT, TWO_WHEELER
- **Route Modifiers** : Éviter péages, autoroutes, ferries
- **Auto-Resolution** : Résolution automatique de l'origine (géolocalisation, adresse domicile)
- **Cross-Domain** : Résolution destinations depuis contacts, événements, lieux

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         routes_tools.py                          │
│  - compute_route (A → B)                                        │
│  - compute_route_matrix (N × M)                                 │
│  - get_directions_to_contact                                    │
│  - get_directions_to_event                                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────────┐
│                    GoogleRoutesClient                            │
│  - API Key authentication (X-Goog-Api-Key header)               │
│  - httpx async client                                           │
│  - Field mask optimization                                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────────┐
│                      RoutesCache (Redis)                         │
│  - TTL configurable par type de requête                         │
│  - Cache key basé sur origin/destination/mode/preferences       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tools Disponibles

### compute_route

Calcule un itinéraire entre deux points.

**Paramètres** :
| Param | Type | Description |
|-------|------|-------------|
| `origin` | str | Point de départ (adresse, coordonnées, ou "current_location") |
| `destination` | str | Point d'arrivée |
| `travel_mode` | TravelMode | Mode de transport (DRIVE par défaut) |
| `avoid_tolls` | bool | Éviter les péages |
| `avoid_highways` | bool | Éviter les autoroutes |
| `avoid_ferries` | bool | Éviter les ferries |
| `departure_time` | datetime | Heure de départ pour traffic prediction |

> **Timezone handling (v1.12.1, updated v1.14.0):** Naive datetimes from LLM tool calls (without
> timezone info) are normalized to the user's local timezone via
> `normalize_user_datetime()` from `time_utils.py` before being processed.
> This function treats the hour value as **local time intent** — it must only
> receive LLM-generated datetimes, never API-returned UTC datetimes (use
> `convert_to_user_timezone()` for those).
>
> **Cross-domain binding caveat (v1.14.0):** When the route tool receives
> `arrival_time` from a calendar event via the `event["date"]` top-level alias,
> this alias must be set **after** `convert_event_dates_in_payload()` in the
> calendar mixin. Setting it before conversion would pass the raw UTC value
> (e.g., `13:00:00Z`) instead of the converted local time (`15:00:00+02:00`),
> causing a timezone-offset error in departure time calculations.

**Retour** : `UnifiedToolOutput` avec `RouteItem`

```python
# Exemple d'utilisation
result = await compute_route(
    origin="Paris",
    destination="Lyon",
    travel_mode=TravelMode.DRIVE,
    avoid_tolls=True,
)
# Retourne: distance, durée, polyline, ETA, URL Google Maps
```

### compute_route_matrix

Calcule une matrice de routes (N origines × M destinations).

**Cas d'usage** : Trouver la destination la plus proche parmi plusieurs options.

### get_directions_to_contact

Calcule l'itinéraire vers l'adresse d'un contact.

**Cross-Domain** : Utilise Google Contacts pour résoudre l'adresse du contact.

### get_directions_to_event

Calcule l'itinéraire vers le lieu d'un événement.

**Cross-Domain** : Utilise Google Calendar pour résoudre le lieu de l'événement.

---

## Client API

### GoogleRoutesClient

**Fichier** : `apps/api/src/domains/connectors/clients/google_routes_client.py`

```python
class GoogleRoutesClient:
    """
    Client Google Routes API avec authentification API Key.

    Utilise une clé API globale (GOOGLE_API_KEY) partagée entre tous les utilisateurs.
    Pas d'OAuth required - contrairement aux autres APIs Google.
    """

    async def compute_route(
        self,
        origin: dict[str, Any],
        destination: dict[str, Any],
        travel_mode: TravelMode = TravelMode.DRIVE,
        routing_preference: RoutingPreference = RoutingPreference.TRAFFIC_AWARE,
        departure_time: datetime | None = None,
        avoid_tolls: bool = False,
        avoid_highways: bool = False,
        avoid_ferries: bool = False,
    ) -> dict[str, Any]:
        ...
```

### Travel Modes

```python
class TravelMode(str, Enum):
    DRIVE = "DRIVE"           # Voiture
    WALK = "WALK"             # À pied
    BICYCLE = "BICYCLE"       # Vélo
    TRANSIT = "TRANSIT"       # Transports en commun
    TWO_WHEELER = "TWO_WHEELER"  # Deux-roues motorisé
```

### Routing Preferences

```python
class RoutingPreference(str, Enum):
    TRAFFIC_UNAWARE = "TRAFFIC_UNAWARE"      # Ignore le trafic
    TRAFFIC_AWARE = "TRAFFIC_AWARE"          # Prend en compte le trafic
    TRAFFIC_AWARE_OPTIMAL = "TRAFFIC_AWARE_OPTIMAL"  # Optimise pour le trafic
```

---

## Cache Redis

### RoutesCache

**Fichier** : `apps/api/src/infrastructure/cache/routes_cache.py`

Le cache Redis optimise les performances en évitant les appels API répétitifs.

**Stratégie de cache** :
- Clé basée sur : origin, destination, travel_mode, preferences
- TTL par défaut : 5 minutes (trafic peut changer)
- Invalidation : Automatique par TTL

```python
cache = RoutesCache(redis_client)
cached_route = await cache.get_route(origin, destination, mode)
if not cached_route:
    route = await client.compute_route(...)
    await cache.set_route(origin, destination, mode, route)
```

---

## Intégration Cross-Domain

Le domaine Routes s'intègre avec d'autres domaines pour la résolution automatique des destinations.

### Résolution de l'Origine

1. **Géolocalisation navigateur** : Si l'utilisateur autorise, utilise la position actuelle
2. **Adresse domicile** : Via les préférences utilisateur (si configuré)
3. **Fallback** : Demande explicite à l'utilisateur

```python
# Helpers de résolution
origin = await resolve_location(
    location_str="current_location",
    user_id=user_id,
    config=config,
)
# Essaie: browser geolocation → user home address → error
```

### Résolution Cross-Domain

| Source | Destination | Méthode |
|--------|-------------|---------|
| Contacts | Adresse du contact | Google People API |
| Calendar | Lieu de l'événement | Google Calendar API |
| Places | Coordonnées du lieu | Google Places API |

---

## Configuration

### Variables d'Environnement - API & Authentification

```bash
# API Key Google (requis - partagee entre utilisateurs)
GOOGLE_API_KEY=AIza...
```

### Variables d'Environnement - LLM Agent

| Variable | Default | Description |
|----------|---------|-------------|
| `ROUTES_AGENT_LLM_PROVIDER` | openai | Provider LLM pour agent routes |
| `ROUTES_AGENT_LLM_MODEL` | gpt-4.1-nano | Modele LLM (fast, cheap) |
| `ROUTES_AGENT_LLM_TEMPERATURE` | 0.3 | Temperature pour generation |
| `ROUTES_AGENT_LLM_MAX_TOKENS` | 2000 | Max tokens reponse |
| `ROUTES_AGENT_LLM_REASONING_EFFORT` | low | Effort de raisonnement (o-series) |

### Variables d'Environnement - Limites API

| Variable | Default | Description |
|----------|---------|-------------|
| `ROUTES_MAX_WAYPOINTS` | 25 | Limite waypoints Google Routes API |
| `ROUTES_MAX_MATRIX_ELEMENTS` | 625 | Max elements matrice (25x25) |
| `ROUTES_MAX_STEPS` | 10 | Max steps dans route condensee |
| `ROUTES_WALK_THRESHOLD_KM` | 1.0 | Distance sous laquelle WALK mode par defaut |
| `ROUTES_HITL_DISTANCE_THRESHOLD_KM` | 20.0 | Distance au-dessus = confirmation HITL |

### Variables d'Environnement - Cache Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `ROUTES_CACHE_TRAFFIC_TTL_SECONDS` | 300 | TTL routes avec traffic (volatile, 5 min) |
| `ROUTES_CACHE_STATIC_TTL_SECONDS` | 1800 | TTL routes sans traffic (stable, 30 min) |
| `ROUTES_CACHE_MATRIX_TTL_SECONDS` | 600 | TTL matrice routes (10 min) |

### Exemple .env

```bash
# Routes API Configuration
GOOGLE_API_KEY=AIza...

# Routes LLM Agent
ROUTES_AGENT_LLM_PROVIDER=openai
ROUTES_AGENT_LLM_MODEL=gpt-4.1-nano
ROUTES_AGENT_LLM_TEMPERATURE=0.3
ROUTES_AGENT_LLM_REASONING_EFFORT=low

# Routes Tool Limits
ROUTES_MAX_WAYPOINTS=25
ROUTES_MAX_MATRIX_ELEMENTS=625
ROUTES_WALK_THRESHOLD_KM=1.0
ROUTES_HITL_DISTANCE_THRESHOLD_KM=20.0
ROUTES_MAX_STEPS=10

# Routes Cache TTL
ROUTES_CACHE_TRAFFIC_TTL_SECONDS=300
ROUTES_CACHE_STATIC_TTL_SECONDS=1800
ROUTES_CACHE_MATRIX_TTL_SECONDS=600
```

### HITL Trigger

Les routes significatives (distance > `ROUTES_HITL_DISTANCE_THRESHOLD_KM`) declenchent une confirmation HITL avant execution.

---

## Métriques

### Prometheus Metrics

```python
# Métriques exposées
routes_api_requests_total{method, status}
routes_api_latency_seconds{method}
routes_cache_hits_total
routes_cache_misses_total
routes_distance_km{travel_mode}  # Histogram des distances calculées
```

### Observabilité

- **Langfuse** : Tracing des appels API avec latence
- **Structured Logs** : origin, destination, mode, distance, duration

---

## Références

- [Google Routes API Documentation](https://developers.google.com/maps/documentation/routes/overview)
- [Compute Route Directions](https://developers.google.com/maps/documentation/routes/compute_route_directions)
- [Route Matrix](https://developers.google.com/maps/documentation/routes/compute_route_matrix)
