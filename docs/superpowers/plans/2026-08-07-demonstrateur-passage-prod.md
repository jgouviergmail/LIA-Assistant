# Démonstrateur libre — plan de passage en production

> **État au 2026-08-07.** L'instance tourne de bout en bout **en dev**, prouvée.
> Rien n'est déployé. Ce document est le mandat de la session suivante : il
> liste ce qui reste, dans l'ordre où il doit être fait, avec ce qu'il faut
> savoir pour ne pas refaire les erreurs déjà payées.

## Ce qui est acquis (ne pas refaire)

Lots 1→6 et 8 livrés — voir [ADR-216](../../architecture/ADR-216-Plafond-De-Depense-D-Instance.md),
[ADR-217](../../architecture/ADR-217-Capacites-Administrables.md),
[ADR-218](../../architecture/ADR-218-Surface-Verifiee-Du-Demonstrateur.md) et
[DEMO_INSTANCE.md](../../technical/DEMO_INSTANCE.md).

Prouvé en dev, à la main, contre l'instance réelle :

| Ce qui a été vérifié | Résultat observé |
|---|---|
| Surface réseau (`task demo:verify`) | `surface OK` — connecteurs, admin, `/metrics`, sign-in fédéré en 404 |
| Inscription | 400 `terms_not_accepted` sans acceptation, 201 avec |
| E-mail de vérification | `status=sent 250 OK` via le relais confiné |
| Conversation | réponse DeepSeek en streaming |
| Recherche web | réponse correcte via Brave |
| Plafond d'instance | 429 `instance_budget_exhausted`, `Retry-After` jusqu'à minuit UTC |
| Purge nocturne | 1 → 0 compte, 11 → 0 messages, marqueur conservé |
| Auto-réparation | `demo_llm_configuration_restored llm_types=55` au démarrage |

## Chantiers restants, dans l'ordre

### 1. Audit de sécurité AVANT le nettoyage (priorité absolue)

Le nettoyage ne rapproche pas d'une mise en ligne sûre ; une faille d'accès, si.
À couvrir, avec **tests et simulations**, pas seulement lecture de code :

- **Cloisonnement réseau** : prouver qu'un visiteur ne peut atteindre ni la
  prod, ni le Raspberry, ni un autre conteneur. L'API n'est sur aucun réseau
  sortant ; seuls `demo-instance-egress` (HTTPS liste blanche) et
  `demo-instance-smtp` (SMTP smarthost) sortent. Le vérifier depuis l'intérieur
  du conteneur API : tentatives vers 192.168.x, vers le tunnel, vers la prod.
- **Secrets** : aucune clé provider dans le processus qui parle aux visiteurs
  (déjà fait pour le SMTP — le vérifier pour les autres). Le conteneur est
  `read_only`, `cap_drop: [ALL]`, `no-new-privileges`, user 1000.
- **Abus** : rate limiting par IP et par compte, coût d'un visiteur seul borné
  par `DEFAULT_COST_LIMIT_PER_CYCLE_EUR`, inscriptions en masse, e-mails en
  masse (le relais peut-il servir de relais ouvert ? le vérifier).
- **Injection / évasion** : ce qu'un visiteur peut faire exécuter par les
  agents. `SKILLS_ENABLED=false`, `MCP_ENABLED=false`, `BROWSER_ENABLED=false`
  ferment l'essentiel — le prouver, pas le supposer.
- **Tunnel Cloudflare** : le bord ne publie aucun port hôte en prod ; vérifier
  qu'aucun autre service ne le fait, et que le tunnel n'expose que le bord.

### 2. Préparation production

- `.env.demo-instance.prod` : clés provider (DeepSeek au minimum, Gemini pour
  les embeddings, ElevenLabs si dictée), `DEMO_INSTANCE_MAIL_DOMAIN`,
  `FRONTEND_URL=https://demo-lia.jeyswork.com`, `APP_URL_SERVER` identique.
- Vérifier la cohérence des trois URL (piège déjà payé : `FRONTEND_URL` construit
  le lien de vérification, `APP_URL_SERVER` non).
- Tâche de déploiement prod (le Raspberry est en arm64 — vérifier les images :
  `boky/postfix`, `caddy`, `pgvector`, `squid`).
- Décider où tourne l'instance : le Pi de prod ou une machine dédiée.
- `SESSION_COOKIE_DOMAIN=demo-lia.jeyswork.com` strict (déjà posé) — ne jamais
  mettre un domaine parent, il partagerait la session avec l'instance principale.

### 3. Nettoyage de l'ancien showroom live (lot 7)

**À supprimer** : `src/public_demo_app.py`, `src/domains/public_demo/` (47
fichiers), 39 tests, `LiveShowroomMission.tsx`, `useLiveShowroom.ts`,
`app/api/public-demo/`, `lib/public-demo-*.ts`, `.env.public-demo*`,
`docker-compose.public-demo.yml`, `infrastructure/public-demo/`,
`scripts/public_demo/`, ~26 lignes du Taskfile, `PUBLIC_DEMO_RUNTIME.md`,
`lint:public-demo-boundary`, 3 suites Playwright.

**À GARDER absolument** : `GuidedShowroom`, `ShowroomMission`,
`ShowroomRichResponse`, `useShowroomMission` — les 6 missions guidées sont le
socle et le fallback (arbitrage propriétaire 4). Elles partagent le dossier
`showroom/` avec le nouveau `LiveDemoInvitation`.

### 4. Revue de code de CHAQUE fichier

Périmètre : tout ce que la session a créé ou modifié (485 fichiers stagés, dont
~60 réellement nouveaux pour ce programme). Lire le corps, pas le docstring.

### 5. Documentation et guides

- Guide d'exploitation du démonstrateur (mise en route, incident, purge).
- Mettre à jour `README.md`, `docs/INDEX.md`, `ARCHITECTURE.md` si besoin.
- `GUIDE_SHOWROOM_LIVE.md` décrit l'ANCIEN système : à réécrire ou supprimer
  avec le lot 7.

### 6. Gates finaux

`task lint`, `task ci:fast`, `task test:backend:unit:coverage` (plancher 65 %,
réel 68,16 % au 2026-08-06), `task test:frontend:coverage`, ratchets.

## Pièges déjà payés — ne pas les refaire

1. **`FRONTEND_URL` ≠ `APP_URL_SERVER`** : le premier construit les liens des
   e-mails. Trois variables décrivent la même adresse, elles bougent ensemble.
2. **La base est en tmpfs** : recréer le conteneur postgres efface marqueur,
   réglages et configuration LLM. La configuration LLM revient seule au boot ;
   le marqueur demande `task demo:provision` (ou `:force` si des comptes
   existent déjà).
3. **Le serveur sait, l'interface l'ignore** — motif rencontré 3 fois (bouton
   Google, case CGU, message d'activation). Toute règle appliquée côté serveur
   doit être publiée au front : `/auth/features` est le canal.
4. **Ne jamais repointer les types LLM vocaux** (`voice_transcription`
   ElevenLabs, `voice_tts` Edge) vers un modèle de texte.
5. **Les embeddings ne sont pas dans `LLM_TYPES_REGISTRY`** :
   `memory_embedding_model` = `models/gemini-embedding-001`. Sans clé Gemini,
   mémoire et intérêts ne fonctionnent pas.
6. **Une liste blanche trop étroite casse le produit** : 7 préfixes laissaient
   les personnalités, fuseaux, psyché, journaux en 404. 235 routes sont gelées
   dans `test_demo_instance_exposed_routes.py`.
7. **`task` n'a pas `grep`/`sleep`** sur cette machine : utiliser
   `docker compose up --wait`, jamais une boucle shell.
8. **Compose interpole tout le fichier avant de filtrer les profils** : jamais
   de `${VAR:?}` dans un service sous `profiles`.
9. **`--env-file` obligatoire** : l'interpolation lit le `.env` du dossier,
   jamais le `env_file` d'un service.
10. **L'identité de déploiement n'est pas un défaut de code** — garde
    `test_no_deployment_identity_in_defaults.py`.

## Ce qu'il reste à décider

- Où héberge-t-on l'instance de démonstration en production ?
- Active-t-on la mémoire (clé Gemini) et la dictée (clé ElevenLabs) ?
- L'encart de 9 lignes est-il trop dense à l'écran ?
