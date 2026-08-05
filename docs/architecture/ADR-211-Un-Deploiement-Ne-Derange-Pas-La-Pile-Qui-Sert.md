# ADR-211 : un déploiement ne dérange pas la pile qui sert

**Statut** : ✅ IMPLEMENTED (2026-08-05)
**Contexte** : audit des logs de production API sur 7 jours (2026-07-29 → 2026-08-05)

## Contexte

Le déploiement reconstruisait le répertoire distant **en place** :

```sh
sudo rm -rf ~/lia/* ~/lia/.[!.]*   # puis transfert, build, up --force-recreate
```

Un bind mount est résolu vers un **inode** à la création du conteneur. Supprimer
le contenu du répertoire ne « remplace » donc pas les fichiers vus par les
conteneurs en cours : cela détruit les inodes sous leurs pieds.

**Observé en direct le 2026-08-05**, pendant un déploiement, sur le conteneur qui
servait les utilisateurs :

```
docker exec lia-api-prod ls /app/config           -> vide
docker exec lia-api-prod ls /app/docs/knowledge   -> vide
docker exec lia-api-prod ls /app/data/skills/system -> vide
```

alors que les répertoires hôtes étaient peuplés. Ils ne revenaient qu'au
`--force-recreate`, soit **une dizaine de minutes plus tard** : toute la durée du
build distant. Pendant cette fenêtre, les notifications push échouaient
(`firebase_init_failed`), la FAQ RAG ne répondait plus
(`system_rag_startup_error`) et les skills système disparaissaient — un service
dégradé silencieux à chaque déploiement, que rien ne reliait à la cause.

Le même `rm -rf` emportait aussi les **sauvegardes PostgreSQL** :
`POSTGRES_BACKUP_HOST_DIR` valait `./backups/postgres`, donc *dans* l'arborescence
remplacée. Constat le 2026-08-05 : répertoire vide, horodaté à l'heure exacte du
déploiement. Le sidecar ADR-109 produisait des dumps qu'aucune restauration
n'aurait pu utiliser — rétention réelle nulle, sans que rien ne le signale.

## Décision

**Le déploiement ne touche jamais le répertoire vivant tant que la nouvelle
version n'est pas prête.**

1. Le bundle est déposé dans un répertoire de **staging** (`~/lia.staging`), qui
   n'est monté par aucun conteneur. Le wipe, le transfert et le durcissement des
   permissions y opèrent ; le répertoire vivant est intact pendant tout le build.
2. La bascule finale se fait par **renommage** (`mv`), pas par copie ni
   suppression. Un rename **préserve l'inode** : les conteneurs encore en vie
   gardent des montages valides jusqu'à leur recréation délibérée, juste après.
   Le shell qui exécute `deploy.sh` conserve également son descripteur ouvert,
   pour la même raison.
3. Les deux générations précédentes sont conservées (`~/lia.prev.<horodatage>`)
   pour un retour arrière manuel ; au-delà elles sont purgées, sinon le disque de
   la carte SD se remplit en silence.
4. Une exécution **hors pipeline** (relance manuelle depuis `~/lia`) détecte
   l'absence de staging et enchaîne sans erreur : échouer là priverait
   l'exploitant de la relance la plus simple, au pire moment.
5. **Les sauvegardes vivent hors de l'arborescence déployée**
   (`../lia-data/postgres-backups`). Un dump qu'un déploiement peut atteindre
   n'est pas un dump. Le `.env` de l'exploitant pouvant écraser ce défaut,
   `deploy.sh` avertit explicitement lorsque la valeur configurée est interne.

## Conséquences

- Plus de fenêtre de service dégradé : le conteneur en place conserve ses
  montages pendant les ~10 minutes de build, la bascule dure quelques
  millisecondes.
- La reprise après sinistre redevient réelle : les dumps survivent aux
  déploiements.
- Coût disque : staging + deux générations précédentes coexistent avec le
  répertoire vivant. Borné et purgé, contrairement à l'accumulation silencieuse
  qu'aurait produite une rétention illimitée.

## Preuves

- `apps/api/tests/unit/test_backup_dir_outside_deploy_guard.py` — le défaut de
  `POSTGRES_BACKUP_HOST_DIR` doit s'échapper de l'arborescence déployée, dans le
  compose **et** dans les gabarits que les exploitants recopient.
- `scripts/deploy/deploy-prod.Tests.ps1` (Describe « keeps the live directory
  intact during the build ») — le wipe ne vise jamais le répertoire vivant, la
  bascule utilise `mv` avec des chemins **dérivés** (donc valables pour tout
  `-RemoteDir`), elle se place après le build et avant le `up`, et une exécution
  hors staging reste sans effet.
- 59 tests Pester verts, dont la fixture corrigée pour porter `apps/api/locales`.

## Écartés

- **Conserver le `rm -rf` en accélérant le build** : traite la durée, pas la
  cause — le service resterait dégradé, seulement moins longtemps.
- **Monter les répertoires en lecture seule depuis une image** : supprimerait la
  possibilité de corriger un fichier de connaissance sans reconstruire.
- **Sauvegardes dans un volume nommé** : les rend moins accessibles à la
  synchronisation hors site prévue (ADR-109, phase 2).
