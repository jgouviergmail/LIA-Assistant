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
| Nettoyage automatique | Dual : reset conversation + scheduler TTL — un fichier genere que la personne conserve n'expire pas (ADR-319) |
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
| `GENERATED_FILES_SEARCH_MAX_RESULTS` | `10` | Fichiers au plus qu'un appel de `find_generated_files_tool` renvoie et montre (ADR-318) |
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

### `POST /api/v1/attachments/from-knowledge-document` (ADR-295)

Joint une COPIE d'un document déjà indexé dans un espace de connaissances de
la personne — espace actif ou en pause. Le fichier stocké est copié sous un
nouveau nom UUID dans le magasin des pièces jointes, son texte extrait par le
pipeline des espaces (`rag_spaces.processing.extract_text`, quinze formats)
sous `ATTACHMENTS_MAX_PDF_TEXT_CHARS`, la ligne créée en `origin = upload`
(la réinitialisation la retire, le TTL l'expire, l'espace n'est jamais touché).

**Request** : `{"space_id": "<uuid>", "document_id": "<uuid>"}` — les deux
capacités (pièces jointes ET espaces de connaissances) doivent être actives.

**Response** (201) : la même forme que l'upload.

**Erreurs** :
- `404` : l'espace ou le document n'est pas celui de la personne (un espace
  système n'appartient à personne), ou son fichier stocké a disparu
- `409 {"code": "document_not_ready"}` : le document n'est pas `ready`

Le composeur liste ce qu'il peut joindre par `GET /api/v1/rag-spaces/documents`
(`q`, `limit` ≤ `max_limit`, `offset`) : les documents `ready` de tous les
espaces de la personne, l'espace nommé à côté de chacun, page et total EXACT.

Le bloc `[Document: …]` injecté au nœud de réponse ÉNONCE sa coupe (« the
first N characters of the document ») quand le texte extrait est au cap —
pour toute pièce jointe document, uploads compris.

### `GET /api/v1/attachments/{attachment_id}`

Telecharge le fichier original.

**Response** : `FileResponse` avec `Content-Type` et `Content-Disposition` corrects.
Images use `Content-Disposition: inline` (enables native browser "Save Image" on long-press), other files use `attachment`.

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

## Ce que LIA a produit : la galerie (ADR-279)

Trois familles de fichiers sont ecrites dans la meme table que les
televersements — images generees, documents generes, captures de navigateur —
et la colonne `origin` les distingue. Le vocabulaire est **clos** : `upload`
plus `GENERATED_ORIGINS` partitionnent l'enumeration (verifie par un test), et
une valeur que personne n'a declaree n'est **jamais** lue comme « generee ».

Deux colonnes accompagnent l'origine : `title` (le nom qu'un producteur
connait — « Bilan du trimestre » — `NULL` renvoyant a `original_filename`) et
`conversation_id` en `SET NULL` (supprimer une conversation ne detruit pas ce
qu'elle a produit).

### `GET /api/v1/generated-assets`

Une page d'une famille, et le total EXACT derriere elle.

**Query** : `family` (`images` | `documents` | `screenshots`), `q`,
`created_after`, `created_before`, `expires_before`, `sort`
(`created_desc` | `created_asc` | `expires_asc` | `name_asc`), `limit`, `offset`.

**Response** : `items`, `total`, `total_bytes`, `limit`, `offset`, `max_limit`,
`keep` (ADR-319 : fichiers et octets conserves par le compte, EXACTS sur tout le
compte, et les deux plafonds). Le tri `expires_asc` range les fichiers conserves
en dernier (`NULLS LAST`).

Trois regles portent l'enonce :

- **la page et son total sortent du MEME `WHERE`** (ADR-185) — construits
  separement, ils decriraient deux ensembles differents des le premier filtre
  ajoute d'un seul cote ;
- **tout tri se termine sur la cle primaire** — sans ordre total, deux fichiers
  crees dans la meme milliseconde se repetent ou disparaissent a la frontiere
  d'une page ;
- **un besoin de recherche est une DONNEE**, passee par `escape_like` : un `_`
  non echappe matche toutes les lignes.

`max_limit` est **publie** parce qu'il est impose (ADR-184). `upload` n'est pas
listable : `GalleryFilters` le refuse a la construction.

### `DELETE /api/v1/generated-assets/{asset_id}` et `POST /api/v1/generated-assets/delete`

La suppression unitaire (`204`) et la suppression en lot, qui repond
`{deleted, skipped}`. Un identifiant que l'appelant ne possede pas, un qui
designe un televersement, et un que le nettoyage a retire entre le listing et
le clic sont **ecartes**, jamais comptes comme supprimes (ADR-185).

### Conserver un fichier au-dela de son echeance (ADR-319)

Un fichier conserve n'a **pas d'echeance** : `attachments.expires_at` est
`NULL`. Le balayage supprime `expires_at <= now()` et ne peut donc pas l'atteindre,
par la semantique de `NULL` et non par un filtre qu'il faudrait penser a ecrire.
Une contrainte `CHECK` (`ck_attachments_upload_expires`) garde l'invariant d'un
televersement : il a toujours une echeance.

`POST /api/v1/generated-assets/keep` prend `{ids, kept}` (1 a 100 identifiants)
et repond `{updated, skipped, keep}` :

- **seuls les fichiers generes de l'appelant** sont concernes ; un televersement,
  un fichier d'un autre compte ou un identifiant disparu est ecarte, jamais
  compte (ADR-185) ; un doublon est UN fichier ; conserver deux fois repond
  « conserve » deux fois ;
- **deux plafonds par compte**, `GENERATED_ASSETS_KEEP_MAX_FILES` et
  `GENERATED_ASSETS_KEEP_MAX_MB` (l'un des deux a 0 = conservation coupee : l'epingle disparait,
  un fichier deja conserve reste liberable), publies avec chaque page de la
  galerie (ADR-184). Une selection qui depasserait l'un des deux est refusee
  ENTIERE (`409`, `GeneratedAssetKeepLimitError`, phrase traduite portant les
  deux plafonds), jamais conservee a moitie ;
- **compter et ecrire sous un verrou consultatif par compte**, porte par la
  transaction (`infrastructure/database/owner_lock.py`, partage avec ADR-316) :
  deux conservations qui se disputent la derniere place ne passent pas toutes les
  deux (prouve a deux acteurs sur PostgreSQL) ;
- **ne plus conserver** redonne une echeance d'un TTL a partir de maintenant,
  jamais une suppression immediate ;
- un fichier dont l'echeance est passee mais que le balayage n'a pas encore
  atteint peut encore etre sauve : la mise a jour et la suppression sont deux
  instructions conditionnelles, et celle qui s'engage la premiere gagne.

**Les cartes du chat suivent le fichier.** Une carte d'image ou de document porte
l'echeance ecrite a la production ; conserver ou supprimer la rendrait fausse. La
lecture de l'historique (`GET /conversations/me/messages`) la restitue depuis la
ligne (`attachments/card_lifetimes.py`) : conserve → `expires_at: null,
kept: true` ; present → son echeance actuelle ; absent → `gone: true`. Une carte
se reconnait a sa FORME (une URL `/api/v1/attachments/{id}` et une cle
`expires_at`), en une lecture groupee par page. Le web dessine un fichier disparu
comme une carte inerte : ni apercu, ni telechargement, ni partage. Le chemin direct
porte le meme drapeau (`PendingImage.kept`, `PendingDocument.kept`, poses quand la
recherche d'ADR-318 montre un fichier conserve) : une carte se lit pareil en direct
et apres rechargement.

### La garde de capacite

`capability_dependencies(ATTACHMENTS)` est posee sur **`POST /attachments/upload`
seule**, pas sur le routeur. Televerser et consulter sont deux capacites qui
partagent une table : couper la premiere ne doit pas fermer la porte sur des
fichiers que la personne garde legitimement, ni l'empecher de les supprimer. Le
routeur `generated-assets` est inclus **sans condition**.

### Retrouver un fichier depuis la conversation (ADR-318)

`find_generated_files_tool` (domaine `generated_file`, les deux modes
d'exécution) lit la galerie pour le modèle : les familles demandées — ou toutes —
fusionnées de la plus récente à la plus ancienne sous un plafond publié
(`GENERATED_FILES_SEARCH_MAX_RESULTS`), avec le total EXACT des correspondances.
Seuls les fichiers dont l'échéance n'est pas passée sont lus
(`GalleryFilters.expires_after`, `expires_at > instant` ou conservé — ADR-319) : la galerie, elle,
garde toutes ses lignes et montre l'échéance, mais un fichier que le nettoyage
va retirer ne se remontre pas. Chaque fichier trouvé est MONTRÉ comme la carte
que le chat dessine déjà, par les files des producteurs (images, documents),
indexées par la conversation ; le modèle ne doit ajouter ni lien ni image. Le
chemin d'une pièce jointe a une seule écriture (`attachments/urls.py`,
`attachment_url`, `ATTACHMENT_PATH_PREFIX`), lue par les quatre producteurs qui
l'écrivaient à la main et par la liste blanche d'URL de la réponse.

La livraison des cartes ne dépend plus de QUI a mis la carte en file : les
garde-fous sur `IMAGE_GENERATION_ENABLED` et `DOCUMENT_GENERATION_ENABLED` qui
entouraient la livraison sont retirés (`image_generation/delivery.py`, sur le
modèle de `document_generation/delivery.py`). Une carte mise en file derrière
une porte fermée n'était jamais montrée, ni libérée.

Le téléphone ne propose pas cet outil : il montre des cartes qu'aucune surface
vocale ne dessine.

### Envoyer un fichier ou une réponse par e-mail (ADR-321)

Depuis une carte du chat (image, document, capture), une tuile de la galerie, la
rangée d'actions d'une réponse ou un signet, « Envoyer par e-mail » ouvre une
boîte de dialogue : destinataires, objet, message facultatif. Le bouton de la
boîte EST la confirmation (précédent ADR-316) ; aucun modèle n'écrit rien.

- **Deux routes** (`domains/email_share/service.py::resolve_route`) : la boîte
  connectée, vers des destinataires libres (10 au plus) ; sinon le relais de LIA,
  vers la SEULE adresse du compte, et seulement si elle est vérifiée (règle
  ADR-314). Une boîte en erreur est dite (`mailbox_needs_reconnect`) pendant que
  le relais sert. `GET /api/v1/email-share/options` publie la route, son
  destinataire unique, le plus gros fichier et chaque borne du formulaire.
- **Ce qui part** : un fichier GÉNÉRÉ de la personne dont l'échéance n'est pas
  passée (conservé : aucune échéance), lu sur disque hors de la boucle ; ou une
  réponse, en fichier `.md` construit par le client exactement comme
  « Télécharger » (`messageToPlainText`, `bookmarkToMarkdown`, mêmes noms
  datés). Un téléversement n'est jamais envoyé.
- **Un MIME sortant unique** (`infrastructure/email/outgoing.py`) sert Gmail,
  Apple et le relais ; Graph porte le même `OutgoingAttachment` en
  `fileAttachment`. Un message Gmail avec fichier part par l'URI « upload »
  (`GmailSendMixin`).
- **Un plafond par route, dérivé du fournisseur** (`OUTGOING_FILE_MAX_BYTES`,
  `max_file_bytes`) : Gmail d'après ses 36 700 160 octets de message, iCloud
  d'après ses 20 Mo, Outlook 3 000 000 octets par fichier, le relais d'après
  `EMAIL_SHARE_RELAY_MAX_MESSAGE_BYTES`. Au-delà : `413` `email_share_too_large`
  avec le plafond, avant qu'un octet ne soit lu.
- **Aucune transaction pendant l'envoi** (ADR-304) : la route lit, valide, puis
  `commit` avant d'ouvrir la boîte (`open_active_client`) ou le relais.
- **Refus codés** (`detail.code`, traduits en six langues côté web) :
  `email_share_file_gone`, `_too_large`, `_no_recipient`, `_recipients_locked`,
  `_unavailable`, `_mailbox_reconnect`, `_refused` (502), `_failed` (503) ; la
  limite par compte répond `429`. Chacun est compté
  (`email_shares_total{route,outcome}`, tableau 10).
- **Capacité d'opérateur** `PlatformCapability.EMAIL_SHARE`
  (`EMAIL_SHARE_ENABLED`), coupée sur le démonstrateur.
- **Suggestions de destinataires** (amendement ADR-321) : sur la route de la
  boîte, avec un connecteur de contacts actif, le champ « À » propose les
  contacts de la personne pendant qu'elle tape, par nom ou prénom (accents et
  ponctuation ignorés), par adresse ou par numéro de téléphone normalisé ; un
  choix insère l'ADRESSE. `/options` publie `recipient_suggestions`,
  `recipient_query_min_chars` et `recipient_suggestions_max` ;
  `GET /api/v1/email-share/recipients?q=` répond pour UN destinataire, sous sa
  propre limite (`EMAIL_SHARE_SUGGEST_RATE_LIMIT_*`), et renvoie la requête
  reçue pour qu'aucune réponse tardive ne s'affiche. Le carnet est lu entier par
  le client de contacts (`list_email_directory`, borné par
  `EMAIL_SHARE_DIRECTORY_MAX_CONTACTS`, la coupe dite `truncated`), compacté et
  mis en cache sous la famille `contacts_directory` avec un tampon de version,
  invalidé par chaque écriture de contact ; la correspondance
  (`email_share/recipient_match.py`) passe par `fold_name`, `fold_email` et les
  variantes de numéro de la téléphonie. Une lecture réelle du carnet est une
  consultation (surface `email_share`), comptée
  (`email_share_recipient_directory_reads_total{outcome}`, tableau 10). Sans
  connecteur de contacts, le champ reste un simple champ d'adresses.

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

Quand un utilisateur reinitialise sa conversation
(`POST /api/v1/conversations/me/reset`), les pieces jointes **qu'il a
televersees lui-meme** sont supprimees :
- Suppression des fichiers sur disque
- Suppression des metadonnees en DB
- Synchrone dans le flow de reset

**Ce que LIA a produit n'est PAS supprime** (ADR-279) : le service recoit
`origins={upload}` et retire ce que la personne a mis, rien d'autre. Avant ce
lot, la reinitialisation appelait `delete_all_for_user(user_id)` sans filtre :
« effacer cette conversation » effacait aussi les images generees la semaine
precedente, dans d'autres conversations. C'est la doctrine d'ADR-260 appliquee
aux fichiers — une purge retire ce que sa famille declare, jamais ce qui lui
ressemble.

#### 2. Scheduler TTL

Job APScheduler periodique (`infrastructure/scheduler/attachment_cleanup.py`,
enregistre dans `startup/schedulers.py`), qui appelle
`AttachmentService.cleanup_expired` :
- chaque piece jointe recoit a l'ecriture `expires_at = now + ATTACHMENTS_TTL_HOURS` ;
- **UNE instruction conditionnelle** supprime toutes les lignes dont
  `expires_at <= now()` et rend leurs fichiers (`delete_expired`,
  `DELETE … RETURNING file_path`) — la condition est evaluee par l'instruction
  qui supprime, jamais par une lecture anterieure ;
- la transaction est validee, PUIS les fichiers sont retires du disque hors de la
  boucle d'evenements (`asyncio.to_thread`) : un arret entre les deux laisse un
  fichier orphelin, jamais une ligne qui pointe vers rien ;
- **s'applique aussi aux fichiers generes, sauf a ceux que la personne a
  conserves** (ADR-319) : un fichier conserve n'a pas d'echeance, la condition ne
  le voit pas ;
- publie `attachments_active_count`, `attachments_kept_count` et
  `attachments_kept_bytes` a chaque passe.

---

## Observabilite

### Prometheus Metrics (9 metriques)

Definies dans `infrastructure/observability/metrics_attachments.py`, suivant la methodologie RED (Rate, Errors, Duration).

| Metrique | Type | Labels | Description |
|----------|------|--------|-------------|
| `attachments_uploaded_total` | Counter | content_type, status | Total des fichiers uploades (status: success\|error) |
| `attachments_upload_size_bytes` | Histogram | content_type | Taille des uploads en bytes |
| `attachments_upload_duration_seconds` | Histogram | content_type | Duree du traitement upload (validation + save + extraction) |
| `vision_llm_requests_total` | Counter | model | Total des requetes vision LLM |
| `vision_llm_duration_seconds` | Histogram | model | Duree des appels vision LLM |
| `attachments_cleanup_deleted_total` | Counter | reason | Fichiers supprimes (reason: expired\|conversation_reset\|user_deleted, vocabulaire clos — ADR-279) |
| `attachments_active_count` | Gauge | — | Nombre courant de pieces jointes actives (non expirees) |
| `attachments_kept_count` | Gauge | — | Fichiers generes conserves par les personnes, toute l'instance (ADR-319) |
| `attachments_kept_bytes` | Gauge | — | Octets que tiennent ces fichiers : le disque que le balayage ne recuperera pas (ADR-319) |

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
| HEIC/HEIF | Décodé côté serveur depuis 2026-09-17 (`pillow-heif`, enregistré par `infrastructure/media/heif.py` aux trois sites qui ouvrent l'image d'un tiers : upload, pièce jointe de mail, retouche d'image) — l'upload convertit en JPEG, la lecture vision rend une page PNG | — |
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
