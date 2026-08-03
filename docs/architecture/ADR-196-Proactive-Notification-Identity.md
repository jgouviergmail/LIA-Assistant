# ADR-196 : l'identité d'une notification proactive est décidée avant son envoi

**Statut**: ✅ IMPLEMENTED (2026-08-03)
**Date**: 2026-08-03
**Décideurs**: Équipe LIA
**Complète**: [ADR-135](ADR-135-Heartbeat-Interest-Quality.md) (registre unifié des mentions), [ADR-185](ADR-185-Exact-CRM-Counts-And-Readable-Relayed-Messages.md) (un chiffre montré est une affirmation)

## Contexte

Une notification proactive « heartbeat » est archivée comme message de chat.
La bulle porte 👍/👎, et le clic appelle
`PATCH /heartbeat/notifications/{id}/feedback` avec la clé `target_id` que
portent ses métadonnées.

Cette route déclare `notification_id: UUID`.

### Ce que la lecture du code établit

`generate_content` forgeait `target_id = f"heartbeat_{uuid4().hex[:8]}"` —
une chaîne que rien ne peut parser en UUID. Le dispatcher écrivait cette valeur
dans les métadonnées du message archivé, puis `on_notification_sent` insérait la
ligne d'audit avec un UUID **neuf et sans rapport**.

Trois conséquences, toutes silencieuses :

1. **Le vote depuis le chat mourait en 422.** Le paramètre de chemin est validé
   avant qu'aucun gestionnaire ne s'exécute. Le composant avale l'échec par
   conception — « crier sur l'utilisateur à propos d'un signal de préférence est
   pire que de le perdre » — donc rien ne remontait.
2. **`mark_proactive_feedback_submitted` ne trouvait jamais rien.** Il cherche le
   message archivé *par ce même `target_id`* ; comparé à un UUID, il ne pouvait
   correspondre à aucune ligne. Le mécanisme est correct pour les intérêts, dont
   le `target_id` **est** l'UUID de l'intérêt.
3. **La jointure de coûts était morte.** La colonne `run_id` se documente comme
   « Unique ID linking to token tracking » et stockait le `target_id`, alors que
   le suivi écrit sous `proactive_heartbeat_<…>_<hex>`. Aucune notification
   heartbeat n'était joignable à `message_token_summary`.

### Pourquoi la suite ne l'a pas vu

`test_router_feedback.py` portait, en commentaire, l'affirmation exacte
*« target_id is the notification id — the same key the archived metadata carries
for a proactive_heartbeat card »*. Les deux moitiés y étant simulées, le test ne
pouvait pas constater la divergence : il **épinglait la croyance**, pas le
contrat.

Le défaut était actif en production : `PROACTIVE_FEEDBACK_ENABLED` vaut `true`
par défaut *et* dans `.env.example` comme dans `.env.prod.example`. Les boutons
ont donc été livrés, affichés, et pressés.

## Décision

**L'identifiant d'une notification proactive est sa clé primaire, décidée par le
producteur avant l'envoi.**

`generate_content` produit `target_id = str(uuid4())`. `on_notification_sent`
crée la ligne d'audit **sous cet identifiant** (`notification_id`, nouvel
argument optionnel de `create`). Le `run_id` de la ligne reçoit le vrai run de
suivi, que le runner injecte dans les métadonnées du résultat avant le dispatch.

L'ordre est contraint et c'est ce qui impose la pré-génération : le dispatcher
écrit les métadonnées de la carte **avant** que la ligne n'existe. Laisser la
base choisir la clé revient à la choisir après que la carte a été figée.

**Le repli reste unique.** `run_id` est `UNIQUE` : en l'absence de run de suivi
(appelants plus anciens, doublures de test), la valeur de repli est
l'identifiant de la notification, unique par construction — jamais une
constante, qui ferait échouer l'insertion suivante.

**Un contrôle qui ne peut pas aboutir n'est pas offert.** Les notifications
archivées **avant** ce correctif gardent leur identifiant synthétique ; leur vote
est réellement impossible. `proactiveFeedbackProps` exige désormais la forme
`8-4-4-4-12` — la forme générique, celle que `UUID()` accepte côté Python, et
non un motif v4 qui masquerait des boutons que le serveur aurait honorés.

## Conséquences

Le vote depuis le chat atteint sa ligne, la carte archivée se verrouille sur le
verdict rendu (et donc à travers les rechargements et les appareils), et la
jointure de coûts existe pour les notifications créées à partir d'ici.

**Aucune migration.** Le schéma est inchangé : seule la valeur écrite change.
Les lignes historiques conservent leur `run_id` synthétique — non réparable
après coup, puisque le run de suivi correspondant n'a jamais été enregistré à
côté d'elles.

**Le registre unifié des mentions** (ADR-135) passe de `hb_heartbeat_<8>` à
`hb_<uuid>`, soit 39 caractères pour une colonne `String(100)`.

**Garde de non-récurrence** : `test_notification_identity.py` épingle les trois
propriétés séparément — l'identifiant est parseable, la ligne est créée sous
lui, `run_id` porte le run de suivi. Le commentaire de `test_router_feedback.py`
renvoie désormais à ce fichier, en disant explicitement qu'il ne peut pas,
seul, distinguer les deux valeurs.

## Alternatives écartées

**Joindre par `run_id` au moment de la lecture.** Fonctionne — les deux côtés
portent la même chaîne synthétique — mais consacre comme clé de jointure ce qui
est précisément le symptôme, et laisse le 422 du chat intact.

**Assouplir la route en `str`.** Déplace la validation dans le gestionnaire,
retire une garantie que le typage donnait gratuitement, et n'aurait rien réparé
du marquage de la carte ni de la jointure de coûts.

**Ne rien faire.** Le coût n'est pas l'absence de mesure : c'est une interface
qui recueille un avis et le jette, sur une fonctionnalité dont l'objet même est
d'apprendre ce que l'utilisateur veut recevoir.
