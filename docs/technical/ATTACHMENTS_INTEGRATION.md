# File Attachments & Vision Analysis Integration (evolution F4)

> Architecture et guide d'integration pour les pieces jointes (images, PDF) avec analyse vision LLM.

**Phase**: evolution Feature 4 — File Attachments & Vision Analysis
**Cree**: 2026-03-09
**Statut**: Implemente

---

## Vue d'Ensemble

LIA supporte les **pieces jointes** (images et documents PDF) dans les conversations. Les utilisateurs peuvent joindre des fichiers a leurs messages ; les images sont analysees par un modele LLM vision, les PDF sont extraits en texte. L'ensemble est integre au pipeline agent pour enrichir les reponses contextuelles.

L'architecture utilise le pattern **"Reference + Late Resolution"** : les fichiers sont uploades separement, references par ID dans le message chat, puis resolus en contenu (base64/texte) uniquement au moment de l'appel LLM. Ce design minimise la taille des checkpoints LangGraph et isole les donnees binaires du graph state.

### Fonctionnalites

| Fonctionnalite | Description |
|---------------|-------------|
| Upload images | JPEG, PNG, WebP, GIF — validation MIME par magic bytes |
| Upload PDF | Extraction texte (PyPDF2/pdfplumber), tronque a `ATTACHMENTS_MAX_PDF_TEXT_CHARS` |
| Compression client | Canvas API (1600px max, JPEG 0.82) avant upload |
| Vision LLM | Analyse d'image via modele configurable (35e type LLM) |
| Annotation planner | `[Piece jointe: image/jpeg, 1.2 MB]` injecte dans le contexte router/planner |
| Nettoyage automatique | Dual : reset conversation + scheduler TTL (24h) |
| Isolation user | Segmentation stricte par `user_id`, UUID stored filenames |

---

## Architecture

### Flux Upload + Reference

```
UPLOAD (separee du message chat):
Client (compression Canvas API)
  → POST /api/v1/attachments/upload (multipart/form-data)
  → AttachmentService.upload()
    → MIME validation (magic bytes via filetype lib)
    → Size check (image vs doc limits)
    → Store on disk: {ATTACHMENTS_STORAGE_PATH}/{user_id}/{uuid}.{ext}
    → Insert AttachmentMetadata en DB
    → Return attachment_id (UUID)

REFERENCE (dans le message chat):
Client envoie ChatRequest { message: "...", attachment_ids: ["uuid-1", "uuid-2"] }
  → ChatRoute validates ownership (user_id match)
  → attachment_ids injectes dans MessagesState["current_turn_attachments"]

LATE RESOLUTION (juste avant l'appel LLM):
response_node.py
  → Pop current_turn_attachments from state
  → Pour chaque attachment:
    - Image → load from disk → base64 encode → HumanMessage image_url content block
    - PDF → load extracted text → HumanMessage text content block
  → Appel LLM vision (si images) ou LLM standard (si texte seul)
  → Turn isolation: pop() garantit pas de leak vers les turns suivants
```

### Structure des Fichiers

```
apps/api/src/domains/attachments/        # Domaine
├── models.py                            # AttachmentMetadata (SQLAlchemy)
├── schemas.py                           # Pydantic: UploadResponse, AttachmentInfo
├── repository.py                        # AttachmentRepository (CRUD)
├── service.py                           # AttachmentService (upload, validate, resolve, cleanup)
├── router.py                            # FastAPI endpoints (upload, get, delete)
└── cleanup.py                           # Scheduler job: TTL-based cleanup

apps/api/src/core/config/attachments.py  # AttachmentsSettings

apps/web/src/
├── components/chat/AttachmentPreview.tsx # Preview avec thumbnail + progress
├── components/chat/ChatInput.tsx         # Bouton Paperclip (trombone)
├── components/chat/ChatMessage.tsx       # Rendu inline des pieces jointes
└── hooks/useFileUpload.ts               # XHR upload avec progress callback
```

---

## Configuration

### Variables d'environnement

| Variable | Defaut | Description |
|----------|--------|-------------|
| `ATTACHMENTS_ENABLED` | `false` | Feature flag global |
| `ATTACHMENTS_STORAGE_PATH` | `./data/attachments` | Repertoire de stockage sur disque |
| `ATTACHMENTS_MAX_IMAGE_SIZE_MB` | `10` | Taille max par image (MB) |
| `ATTACHMENTS_MAX_DOC_SIZE_MB` | `20` | Taille max par document PDF (MB) |
| `ATTACHMENTS_MAX_PER_MESSAGE` | `5` | Nombre max de pieces jointes par message |
| `ATTACHMENTS_TTL_HOURS` | `24` | Duree de retention sur disque (heures) |
| `ATTACHMENTS_MAX_PDF_TEXT_CHARS` | `50000` | Troncature texte PDF extrait (caracteres) |
| `ATTACHMENTS_ALLOWED_IMAGE_TYPES` | `image/jpeg,image/png,image/webp,image/gif` | Types MIME images autorises |
| `ATTACHMENTS_ALLOWED_DOC_TYPES` | `application/pdf` | Types MIME documents autorises |

### Configuration dans `core/config/attachments.py`

```python
class AttachmentsSettings(BaseSettings):
    ATTACHMENTS_ENABLED: bool = False
    ATTACHMENTS_STORAGE_PATH: str = "./data/attachments"
    ATTACHMENTS_MAX_IMAGE_SIZE_MB: int = 10
    ATTACHMENTS_MAX_DOC_SIZE_MB: int = 20
    ATTACHMENTS_MAX_PER_MESSAGE: int = 5
    ATTACHMENTS_TTL_HOURS: int = 24
    ATTACHMENTS_MAX_PDF_TEXT_CHARS: int = 50000
    ATTACHMENTS_ALLOWED_IMAGE_TYPES: str = "image/jpeg,image/png,image/webp,image/gif"
    ATTACHMENTS_ALLOWED_DOC_TYPES: str = "application/pdf"
```

---

## Securite

| Risque | Mitigation |
|--------|-----------|
| Path traversal | Noms de fichiers stockes en UUID (`{uuid}.{ext}`), jamais le nom original |
| Usurpation de fichier | Ownership check (`user_id` match) sur chaque acces (GET, DELETE, reference) |
| Upload malveillant | Validation MIME par magic bytes (`filetype` lib), pas par extension |
| Depassement taille | Limites separees images vs docs, verifiees cote serveur avant ecriture |
| Fuite cross-user | Segmentation repertoire `{storage_path}/{user_id}/`, isolation stricte |
| Accumulation disque | Dual cleanup : reset conversation + scheduler TTL (24h, toutes les 6h) |
| Fichier reference invalide | Validation a l'upload ET au moment de la reference dans `ChatRequest` |

### Isolation par User

Le stockage sur disque est segmente par `user_id` :

```
data/attachments/
├── {user_id_1}/
│   ├── a1b2c3d4-...-.jpeg
│   └── e5f6g7h8-...-.pdf
├── {user_id_2}/
│   └── i9j0k1l2-...-.png
```

Chaque operation (upload, download, delete, reference dans un message) verifie que `attachment.user_id == request.user_id`. Aucune route publique n'expose le chemin physique.

---

## API Reference

### `POST /api/v1/attachments/upload`

Upload d'une piece jointe (multipart/form-data).

**Request** :
- `Content-Type: multipart/form-data`
- Field `file` : le fichier binaire
- Auth : session cookie (BFF)

**Response** (201 Created) :
```json
{
  "attachment_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "filename": "photo.jpg",
  "content_type": "image/jpeg",
  "size_bytes": 245760,
  "created_at": "2026-03-09T14:30:00Z"
}
```

**Erreurs** :
- `400` : type MIME non autorise, taille depassee
- `401` : non authentifie
- `413` : fichier trop volumineux (depasse la limite)
- `422` : fichier invalide ou corrompu

### `GET /api/v1/attachments/{attachment_id}`

Telecharge le fichier original.

**Response** : `FileResponse` avec `Content-Type` et `Content-Disposition` corrects.

**Erreurs** :
- `401` : non authentifie
- `403` : `user_id` mismatch (fichier appartient a un autre user)
- `404` : fichier non trouve ou expire (TTL)

### `DELETE /api/v1/attachments/{attachment_id}`

Supprime la piece jointe (fichier disque + metadonnee DB).

**Response** : `204 No Content`

**Erreurs** :
- `401` : non authentifie
- `403` : `user_id` mismatch
- `404` : fichier non trouve

---

## LLM Vision Integration

### 35e Type LLM : `vision_analysis`

Un nouveau type LLM `vision_analysis` est ajoute dans `LLM_DEFAULTS` et `LLM_TYPES_REGISTRY` (`domains/llm_config/constants.py`). Ce type est configurable via l'Admin UI (Settings > Administration > LLM Configuration).

| Propriete | Valeur par defaut |
|-----------|-------------------|
| Provider | `openai` |
| Model | `gpt-4o` |
| Temperature | `0.3` |
| Max tokens | `1024` |
| Category | `analysis` |

### Annotation Router/Planner

Quand un message contient des pieces jointes, le contexte injecte dans le router et le planner inclut une annotation :

```
[Piece jointe: image/jpeg, 1.2 MB, "photo.jpg"]
[Piece jointe: application/pdf, 3.5 MB, "rapport.pdf"]
```

Cela permet au planner de generer un plan adapte (ex: "analyser l'image", "extraire les informations du PDF").

### Late Resolution dans `response_node.py`

Le pattern "Reference + Late Resolution" fonctionne en 3 etapes :

1. **Injection** : `ChatRoute` valide les `attachment_ids` et les injecte dans `MessagesState["current_turn_attachments"]` (liste de `AttachmentInfo`)
2. **Resolution** : `response_node.py` pop les attachments du state et les resout :
   - **Image** : lecture depuis le disque, encodage base64, injection comme `image_url` content block dans le `HumanMessage`
   - **PDF** : lecture du texte extrait (stocke en DB a l'upload), injection comme content block texte
3. **Turn Isolation** : `pop("current_turn_attachments")` garantit que les pieces jointes ne persistent pas dans le state au-dela du turn courant. Pas de memoire multi-turn des images.

```python
# Pseudo-code response_node.py
attachments = state.pop("current_turn_attachments", [])
if attachments:
    content_blocks = []
    for att in attachments:
        if att.is_image:
            data = await attachment_service.load_base64(att.id)
            content_blocks.append({"type": "image_url", "image_url": {"url": f"data:{att.content_type};base64,{data}"}})
        elif att.is_pdf:
            text = await attachment_service.load_pdf_text(att.id)
            content_blocks.append({"type": "text", "text": f"[Contenu PDF: {att.filename}]\n{text}"})
    # Append to HumanMessage content
    # Use vision_analysis LLM type if images present
```

---

## Frontend

### Compression Client (Canvas API)

Avant l'upload, les images sont compressees cote client pour reduire la bande passante et le temps de transfert :

- **Redimensionnement** : max 1600px sur le plus grand cote (preserve aspect ratio)
- **Format** : JPEG avec qualite 0.82
- **Exclusions** : GIF (animation preservee), PNG < 100KB (pas de recompression)

### Hook `useFileUpload`

```typescript
const { upload, progress, isUploading, error } = useFileUpload({
  maxSizeMB: 10,
  allowedTypes: ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'application/pdf'],
  maxFiles: 5,
  onSuccess: (attachment) => addAttachment(attachment),
});
```

- Upload via **XHR** (pas `fetch`) pour le suivi de progression (`onprogress`)
- Progress expose en pourcentage (0-100)
- Validation client-side des types et tailles avant envoi

### Composant `AttachmentPreview`

Affiche les pieces jointes en attente d'envoi ou deja envoyees :
- **Images** : thumbnail avec overlay de progression pendant l'upload
- **PDF** : icone fichier + nom + taille
- Bouton de suppression (X) sur chaque preview
- Etat d'erreur avec retry

### Integration `ChatInput`

- Bouton **Paperclip** (trombone) a gauche du champ de saisie
- Ouvre un file picker natif (accept: images + PDF)
- Drag & drop supporte sur la zone de chat
- Paste d'image depuis le clipboard (Ctrl+V)
- Les `attachment_ids` sont envoyes dans `ChatRequest.attachment_ids[]`

### Rendu `ChatMessage`

- Images inline avec lightbox au clic (zoom)
- PDF affiches comme lien cliquable avec icone
- Coherence visuelle avec le design system (TailwindCSS 4)

---

## Cleanup (Nettoyage)

### Strategie Duale

Deux mecanismes complementaires pour eviter l'accumulation de fichiers :

#### 1. Reset Conversation

Quand un utilisateur reset sa conversation (`POST /api/v1/conversations/{id}/reset`), tous les attachments associes sont supprimes :
- Suppression des fichiers sur disque
- Suppression des metadonnees en DB
- Synchrone dans le flow de reset

#### 2. Scheduler TTL

Job APScheduler periodique (toutes les 6h) :
- Scanne les attachments dont `created_at + TTL_HOURS < now()`
- Supprime fichiers disque + metadonnees DB
- Log le nombre de fichiers nettoyes
- TTL par defaut : 24h (`ATTACHMENTS_TTL_HOURS`)

```python
# cleanup.py — enregistre dans le scheduler (main.py lifespan)
async def cleanup_expired_attachments():
    """Supprime les pieces jointes expirees (TTL depasse)."""
    async with get_db_context() as db:
        expired = await attachment_repo.find_expired(db, ttl_hours=settings.ATTACHMENTS_TTL_HOURS)
        for att in expired:
            await attachment_service.delete(db, att)
        logger.info("attachment_cleanup_completed", deleted_count=len(expired))
```

---

## Observabilite

### Prometheus Metrics (7 metriques)

Definies dans `infrastructure/observability/metrics_attachments.py`, suivant la methodologie RED (Rate, Errors, Duration).

| Metrique | Type | Labels | Description |
|----------|------|--------|-------------|
| `attachments_uploaded_total` | Counter | content_type, status | Total des fichiers uploades (status: success\|error) |
| `attachments_upload_size_bytes` | Histogram | content_type | Taille des uploads en bytes |
| `attachments_upload_duration_seconds` | Histogram | content_type | Duree du traitement upload (validation + save + extraction) |
| `vision_llm_requests_total` | Counter | model | Total des requetes vision LLM |
| `vision_llm_duration_seconds` | Histogram | model | Duree des appels vision LLM |
| `attachments_cleanup_deleted_total` | Counter | reason | Fichiers supprimes par le cleanup (reason: expired\|conversation_reset) |
| `attachments_active_count` | Gauge | — | Nombre courant de pieces jointes actives (non expirees) |

### Recording Rules

Groupe `attachments_metrics` dans `infrastructure/observability/prometheus/recording_rules.yml` (4 regles, intervalle 30s) :

```yaml
# Taux d'upload reussis (5m rolling window)
- record: attachments_upload_rate:5m
  expr: sum(rate(attachments_uploaded_total{status="success"}[5m]))

# Taux d'erreurs upload (5m rolling window)
- record: attachments_upload_error_rate:5m
  expr: sum(rate(attachments_uploaded_total{status="error"}[5m]))

# Latence P95 vision LLM par modele
- record: vision_llm_latency:p95_5m
  expr: |
    histogram_quantile(0.95,
      sum by (model, le) (rate(vision_llm_duration_seconds_bucket[5m]))
    )

# Taux de requetes vision LLM par modele
- record: vision_llm_requests_rate:5m
  expr: sum by (model) (rate(vision_llm_requests_total[5m]))
```

### Grafana Dashboards

Les metriques attachments sont integrees dans les dashboards existants :
- **01-app-overview** : panneau upload rate + erreurs
- **05-llm-tokens-cost** : panneau vision LLM requests + latence + cout tokens
- **09-conversations-users** : 6 panneaux dedies aux attachments (uploads, tailles, vision, cleanup)

### structlog Events

`attachment_uploaded`, `attachment_downloaded`, `attachment_deleted`, `attachment_validation_failed`, `attachment_vision_analysis_started`, `attachment_vision_analysis_completed`, `attachment_cleanup_completed`

---

## Limitations Connues

| Limitation | Detail | Evolution possible |
|------------|--------|-------------------|
| PDF scannes | Extraction texte uniquement (pas d'OCR en v1). Les PDF scannes (images) retournent un texte vide | Integration OCR (Tesseract) en v2 |
| Pas de memoire multi-turn | Les images sont resolues uniquement pour le turn courant (`pop`). Les turns suivants n'ont pas acces aux images precedentes | Ajout d'un cache memoire vision en v2 |
| HEIC/HEIF | Pas de support natif serveur. Repose sur la conversion automatique iOS (HEIC → JPEG) lors du file picker | Ajout `pillow-heif` pour conversion serveur |
| Pas de preview PDF | Le frontend affiche un lien, pas un apercu inline du PDF | Integration PDF.js pour preview inline |
| Taille checkpoint | Les textes PDF extraits (jusqu'a 50K chars) transitent dans le MessagesState, ce qui peut augmenter la taille des checkpoints | Externaliser le texte extrait via une reference |
| Un seul modele vision | Toutes les images utilisent le meme modele LLM (`vision_analysis`). Pas de routing par complexite | Multi-model routing en v2 |

---

## Tests

```bash
# Tous les tests attachments
task test:backend:unit:fast -- tests/unit/domains/attachments/

# Tests specifiques
.venv/Scripts/pytest tests/unit/domains/attachments/test_service.py -v
.venv/Scripts/pytest tests/unit/domains/attachments/test_router.py -v
.venv/Scripts/pytest tests/unit/domains/attachments/test_cleanup.py -v
```
