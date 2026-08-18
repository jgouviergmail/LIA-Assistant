# ADR-226 : agent de génération de documents — LLM structuré dédié + renderers purs sur le socle Attachments

**Statut**: ✅ IMPLEMENTED (2026-08-17)
**Date**: 2026-08-17
**Origine**: demande propriétaire — donner à l'assistant la capacité de créer des documents téléchargeables (csv, xlsx, docx, pptx, pdf…), visualisables/téléchargeables puis purgés automatiquement, à l'image de la génération d'images.
**Spec**: `docs/superpowers/specs/2026-08-17-document-generation-design.md` — plan : `docs/superpowers/plans/2026-08-17-document-generation.md`

## Contexte

LIA sait générer des images (`generate_image`, domaine `image_generation`) mais
aucun document. Les demandes du type « fais une recherche puis formalise en
CSV » ou « génère une présentation sur l'Alsace » n'ont pas d'outil cible : le
pipeline sait chercher, pas livrer un fichier.

L'analyse préalable (12 points d'intégration vérifiés dans le code, 9 probes
exécutées) a établi que le socle existe presque intégralement :

- le modèle `Attachment` connaît déjà `content_type="document"`, un TTL indexé
  (`expires_at`) et une purge planifiée toutes les 6 h
  (`attachment_cleanup`) ;
- `GET /api/v1/attachments/{id}` sert les non-images en
  `Content-Disposition: attachment` avec contrôle de propriété ;
- le patron « agent virtuel » (manifest catalogue + outils, aucun graphe
  LangGraph) est prouvé par `image_generation_agent`, exposé automatiquement
  aux deux modes d'exécution via la taxonomie de domaines ;
- la livraison de cartes sous la réponse (store pending → done chunk SSE +
  persistance `message_metadata`, un seul sérialiseur) est le patron
  `image_store` ;
- **zéro nouvelle dépendance** : openpyxl, python-docx, python-pptx et PyMuPDF
  (déjà embarqués pour l'extraction RAG, prod ARM64 incluse) savent aussi
  écrire — prouvé par simulation, y compris le HTML→PDF paginé via l'API
  Story de PyMuPDF ;
- deux probes de sécurité/robustesse ont requalifié des hypothèses :
  openpyxl stocke `"=1+2"` comme **formule** (`data_type "f"`) — la
  neutralisation anti-injection est une obligation, pas une suggestion — et
  Starlette encode correctement les noms de fichiers accentués (RFC 5987).

Le seul point sans analogue image : d'où vient le **contenu**. Le prompt d'une
image tient en une phrase ; un document est un artefact long que le planner
(volontairement économe) ne produira jamais en paramètre d'outil.

## Décision

**Nouveau domaine `document_generation` décalqué sur `image_generation`, avec
un type LLM dédié en guise de « générateur externe ».**

1. **Contenu par LLM interne dédié** : l'outil `generate_document(instructions,
   doc_type, source_data?, filename?)` appelle le slot `document_generation`
   (ajouté à `LLM_TYPES_REGISTRY`/`LLM_DEFAULTS`, administrable comme les
   autres) en **sortie structurée typée par famille de format** — tabulaire
   (csv/xlsx), sectionné (docx/pdf/md/txt), diapositives (pptx). Le schéma est
   choisi AVANT l'appel (pas d'union discriminée : compatibilité strict mode).
   `source_data` est le canal de matière première (`$steps.…` en pipeline,
   composition directe en ReAct), plafonné par
   `document_generation_max_source_chars` avec troncature **annoncée**.
2. **Renderers purs, zéro dépendance nouvelle** : un module de rendu par
   format (`bytes` en sortie, testé par round-trip avec les lecteurs déjà
   embarqués), registre complet asserté à l'import (doctrine ADR-085).
   PDF via PyMuPDF Story (HTML échappé → pagination A4).
3. **Sécurité des cellules** : neutralisation OWASP des valeurs actives
   (`= + - @`, tab, CR) avec **exemption des littéraux numériques signés**
   (un `-5.2` de données ne doit pas être défiguré) ; CSV encodé `utf-8-sig`
   (BOM requis par Excel) ; noms de fichiers assainis (l'UUID anti-traversal
   reste le nom disque) ; titres de feuilles xlsx assainis et dédupliqués.
4. **Stockage et purge** : réutilisation intégrale d'`Attachment`
   (`content_type="document"`, `expires_at = now + attachments_ttl_hours`,
   purge existante) — l'échéance est portée par la carte (règle N2 : inconnue
   → on ne dit rien). Pas de nouveau scheduler, pas de nouvelle table.
5. **Livraison** : store pending miroir (`document_store`), injection dans le
   done chunk ET la `message_metadata` archivée via **un unique sérialiseur**
   (`to_wire_metadata`) — la leçon `GeneratedImage` (dérive entre deux sites
   d'émission) est close par construction.
6. **Visualisation v1** : carte de téléchargement (icône par type, nom
   signifiant proposé par le LLM et assaini, taille, échéance) ; le PDF
   s'ouvre dans l'onglet — la route attachments passe `application/pdf` en
   `inline` (les PDF uploadés en profitent aussi : fichiers du propriétaire,
   contrôle de propriété inchangé).
7. **Coût et limites** : coût = tokens LLM via le tracking standard (aucune
   table de pricing dédiée — il n'existe pas de prix unitaire externe) ;
   `@rate_limit` + `@track_tool_metrics` ; famille de timeouts dédiée
   plancher/plafond (doctrine ADR-160) ; flags 3 niveaux (env
   `DOCUMENT_GENERATION_ENABLED`, capacité admin runtime
   `PlatformCapability.DOCUMENT_GENERATION`, opt-in utilisateur
   `User.document_generation_enabled`).
8. **HITL non requis** : création non destructive, comme l'image.
9. **Honnêteté d'échec** : un rendu ou un stockage qui échoue APRÈS l'appel
   LLM payé retourne un échec explicite — jamais de carte fantôme ni de
   succès implicite (doctrine v1.30.4).

## Conséquences

- **Positives** : capacité nouvelle sans dépendance ni table nouvelles ;
  chaînage recherche→document opérationnel dans les deux modes ; coût visible
  dans le tracking existant ; purge et sécurité héritées d'un socle éprouvé.
- **Négatives / assumées** :
  - dépendance implicite carte→capacité ATTACHMENTS (identique aux images) :
    capacité coupée = lien de carte en 404, jamais de fuite ;
  - un document dépassant `max_tokens` du slot échoue honnêtement plutôt que
    d'être livré tronqué en silence ;
  - la neutralisation laisse une apostrophe visible sur les rares chaînes
    actives légitimes — arbitrage assumé (règle uniforme et auditable) ;
  - qualité visuelle PPTX/PDF v1 = mise en page sobre par défaut ; thèmes et
    aperçus riches relèvent du v2.
- **Résiduels runtime** (non architecturaux, vérifiés au smoke) : propension
  du planner à câbler spontanément `$steps → source_data` ; qualité de mise
  en page sur contenus complexes.

## Amendement 2026-08-18

L'opt-in par utilisateur (`User.document_generation_enabled` + section
Réglages) livré en v1.30.8 est **retiré** sur décision propriétaire : le
réglage n'apportait rien (la capacité se pilote au niveau instance). Colonne
supprimée par migration `5d6e7f8a9b0c`, garde d'outil et surface Réglages
retirées — le flag de déploiement et la capacité admin restent les deux seuls
niveaux de contrôle.

## Alternatives rejetées

1. **Contenu fourni en paramètre par le planner/ReAct seul** : le planner est
   économe par conception → documents squelettiques en pipeline, plans
   géants ; rejeté comme canal unique, conservé comme canal `source_data`.
2. **Passer par le mécanisme Skills (`run_skill_script`)** : sandboxé mais
   hors circuit cartes/TTL/catalogue, invisible du planner comme domaine.
3. **reportlab pour le PDF** : dépendance nouvelle sans gain prouvé face à
   l'API Story de PyMuPDF déjà embarquée (probe concluante, ARM64 prod déjà
   validé par l'extraction RAG).
4. **ODT/ODS via odfpy** : présent dans le lock mais demande non prouvée —
   YAGNI, consigné comme v2 potentiel.
