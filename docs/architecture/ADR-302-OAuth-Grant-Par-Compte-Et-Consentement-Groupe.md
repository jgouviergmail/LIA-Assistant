# ADR-302 — Un grant OAuth par compte vérifié, un consentement par fournisseur

**Date** : 2026-09-21
**Status** : Accepted
**Amends** : ADR-021 (le cycle de vie des connecteurs liés est désormais porté par un grant commun ; son schéma de révocation par connecteur reste historique)

## Contexte

Les connecteurs Google et Microsoft étaient autorisés service par service. Après
une longue inactivité ou une révocation, plusieurs services d'un même compte
demandaient autant de parcours OAuth. « Tout connecter » répétait également les
écrans de consentement. Un refresh en arrière-plan ne peut pas rendre valide un
refresh token que le fournisseur a révoqué ou fait expirer. En particulier, la
[politique Google](https://developers.google.com/identity/protocols/oauth2#expiration)
limite à sept jours les refresh tokens d'une application externe en **Testing**
qui demande des scopes de services : la publication est un chantier distinct.

Une adresse e-mail ne prouve pas l'identité d'un compte et peut changer. Deux
connecteurs historiques de même fournisseur ne prouvent pas qu'ils ont été
autorisés par le même compte. Les serveurs MCP ont leurs propres autorités OAuth.

## Décision

1. **Un parcours par fournisseur et par compte.** Les deux routes groupées,
   `POST /connectors/oauth-bulk/{provider}/authorize` (« Reconnecter mes
   services ») et `POST /connectors/oauth-bulk/{provider}/connect-all/authorize`
   (« Tout connecter »), convergent sur le même callback par fournisseur. Le
   serveur, pas le navigateur, choisit les services admissibles et l'union de
   leurs scopes. Une initiation émet un state Redis à usage unique, un PKCE S256
   et un nonce ; le callback consomme ce state avant toute écriture.
2. **Une identité signée et stable.** Le callback vérifie la signature du
   `id_token` avec les clés du fournisseur, son issuer, son audience et son
   nonce, puis le subject Google ou le couple tenant/object Microsoft. Quand
   l'ID token contient `at_hash`, le jeton d'accès issu du **même échange** est
   fourni à la vérification. Omettre ce jeton faisait échouer un véritable
   callback Google après un échange réussi ; désactiver `at_hash` aurait retiré
   une protection. Le compte choisi à l'initiation est comparé au compte signé
   au retour, jamais à l'e-mail affiché.
3. **Un propriétaire de credentials par compte.** `oauth_grants` porte le token
   chiffré pour `(user_id, provider, client_id, subject)` ; les connecteurs
   logiques référencent ce grant. Les copies chiffrées dans `connectors` restent
   synchronisées pour les lecteurs historiques. La migration ajoute le modèle
   sans réunir rétroactivement les anciens tokens : seul un nouveau consentement
   vérifie puis lie les comptes. Le refresh proactif et à la demande ne rafraîchit
   qu'une fois par grant, sous verrou de ligne et avec double lecture après
   attente ; une rotation de refresh token est propagée aux services liés.
4. **L'état de chaque service reste individuel.** Le callback utilise les
   scopes effectivement accordés, pas seulement demandés. Un service refusé
   reste en erreur lors d'une reconnexion, ou absent lors de « Tout connecter ».
   Une connexion existante d'un autre compte ou fournisseur n'est pas écrasée.
   Les scopes des services actifs du grant sont préservés lors d'un consentement
   incrémental ; une réponse qui les retirerait est refusée. Le callback
   reverrouille et revalide les lignes avant une transition atomique. La
   déconnexion retire un seul connecteur et le dernier lien supprime le grant
   local. Elle ne révoque pas le token commun chez le fournisseur, car cela
   interromprait les autres services ; une révocation globale reste une action
   distincte côté fournisseur ou lors de la suppression du compte LIA.
5. **Les frontières restent explicites.** Google et Microsoft ont chacun leur
   client OAuth et leur URI de callback à déclarer par environnement. Les
   callbacks de login et les connexions unitaires précédentes restent valables.
   Aucun écran groupé ne tente d'autoriser des serveurs MCP indépendants.
   Aucun appel LLM ni registre de conversation n'est ajouté à ce parcours.

## Alternatives écartées

- **Enchaîner les parcours unitaires** : répète le consentement et multiplie les
  retours et les échecs partiels sans résoudre le problème utilisateur.
- **Fusionner les tokens historiques par e-mail** : associerait potentiellement
  des comptes distincts sans preuve cryptographique.
- **Un grant par fournisseur pour tous les comptes d'une personne** : permettrait
  à un consentement sur le mauvais compte de remplacer les autres.
- **Révoquer au premier service déconnecté** : casserait les services frères.
- **Ignorer `at_hash` pour accepter un ID token Google** : affaiblirait la
  vérification de la liaison entre identité et access token.

## Conséquences et preuves

Un consentement unique simplifie connexion et reconnexion **pour un même compte**.
Des comptes distincts nécessitent encore des parcours séparés et la
déconnexion reste unitaire. Les refus de scopes, les changements de compte et
les pannes temporaires ont des issues distinctes ; un incident réseau ne marque
pas abusivement tous les services en erreur. La publication Google reste
nécessaire pour sortir de la limite de Testing.

La validation couvre les calculs de scopes et de compte, les transitions et
verrous sur PostgreSQL, la sécurité des ID tokens avec et sans `at_hash`, les
parcours front et les callbacks groupés. Le 2026-09-21, les logs Docker dev
ont montré un vrai échange Google puis l'échec `No access_token provided to
compare against at_hash claim` ; après correction, un nouveau callback n'a
plus émis cette erreur et plusieurs services Google étaient actifs sur un
grant commun. La preuve du fournisseur Microsoft reste celle des tests : aucun
consentement Microsoft réel n'est revendiqué ici.

## Références d'implémentation

- `apps/api/src/domains/connectors/oauth_bulk.py`
- `apps/api/src/domains/connectors/oauth_bulk_service.py`
- `apps/api/src/domains/connectors/oauth_identity.py`
- `apps/api/src/domains/connectors/oauth_refresh.py` (la porte de rafraîchissement,
  amendement du 2026-10-23)
- `apps/api/src/domains/connectors/oauth_refresh_exchange.py`
- `apps/api/src/domains/connectors/oauth_refresh_targets.py`
- `apps/api/src/infrastructure/scheduler/token_refresh.py`
- `apps/web/src/components/settings/connectors/hooks/useBulkConnect.ts`
- `apps/web/src/hooks/useBulkReconnect.ts`
- [Procédure et callbacks](../technical/OAUTH.md)
- [Schéma des grants](../technical/DATABASE_SCHEMA.md)

## Amendement 2026-10-01 — « Tout reconnecter » depuis l'alerte de connexion

**Amende** : le parcours « Reconnecter mes services » (demande du propriétaire :
quand l'alerte d'un connecteur OAuth expiré s'affiche et qu'au moins deux sont
expirés, proposer « Tout reconnecter » comme dans « Mes connecteurs »).

- **Le serveur dit ce qui est groupable.** `bulk_reconnect_provider` (dans
  `oauth_bulk.py`) répond le fournisseur d'un connecteur en erreur que le parcours
  groupé sait reconnecter, et rien sinon ; la liste des connecteurs ET le bilan de
  santé (`ConnectorHealthItem`, avec le grant et le compte) le publient. Le client
  ne devine plus le fournisseur à partir du type.
- **Un seul mécanisme, deux surfaces.** Le hook et le dialogue de choix de compte
  sont sortis des réglages (`hooks/useBulkReconnect.ts`,
  `components/connectors/BulkReconnectDialog.tsx`) ; l'alerte et la fenêtre de
  reconnexion proposent le bouton groupé dès que deux connecteurs d'un même
  fournisseur sont en erreur, et le réglage partage le même calcul
  (`lib/connectors/bulk-reconnect.ts`).

## Amendement 2026-10-15 — Autoriser encore au moment de l'activation

Une attente du fournisseur ne réserve pas l'autorisation d'un compte. Les
activations unitaires et groupées relisent un propriétaire actif, non supprimé,
puis verrouillent les configurations globales dans un ordre stable avant les
grants et les connecteurs. `ConnectorService._lock_activation` est leur garde
commune, également utilisée par une modification de statut vers `ACTIVE`.

La désactivation administrative prend les mêmes verrous transactionnels par
type, y compris lorsque la configuration utilise encore son défaut sans ligne.
Si elle passe d'abord, l'activation est refusée ; si l'activation passe d'abord,
la désactivation attend son commit puis révoque le connecteur. Une simple
lecture avant l'attente, ou le seul verrou d'une ligne absente, ne suffit pas.

Les probes Apple et l'appel Hue Remote prennent leur préflight sur une session
fermée avant l'attente réseau (ADR-304), puis relisent cette autorisation avant
la persistance. Une révocation survenue pendant l'appel Hue empêche le stockage
local ; elle ne peut pas annuler une whitelist déjà acceptée par le bridge.
Les preuves PostgreSQL utilisent des sessions indépendantes et des fournisseurs
simulés, sans revendiquer un nouveau consentement externe réel.

## Amendement 2026-10-23 — Une seule porte de rafraîchissement, aucun verrou pendant l'appel

**Amende** le point 3 (audit V14, AC-029). Il disait « sous verrou de ligne » : le
runtime du grant gardait le grant verrouillé (`FOR UPDATE`) pendant l'appel au point de
jeton du fournisseur, ce qu'ADR-304, postérieure, interdit. Les jetons hérités avaient
quatre chemins de rafraîchissement, dont un seul sous un verrou Redis, et Hue Remote un
POST sans verrou ni marge ; tous écrivaient sans condition. Deux rafraîchissements
simultanés d'un même jeton sont un danger, pas un gaspillage : un fournisseur qui fait
tourner son refresh token répond `invalid_grant` au second, et ce refus déconnectait une
personne dont le consentement était intact.

**Décision.** Un seul chemin, `ensure_fresh_credentials`
(`connectors/oauth_refresh.py`), pour les jetons hérités, les grants et Hue Remote ; un
seul échange (`oauth_refresh_exchange.py`, seul module autorisé à envoyer
`grant_type=refresh_token`, garde `test_refresh_grant_single_sender_guard.py`) ; une
cible par magasin (`oauth_refresh_targets.py`), qui garde le format de chacun.

1. **Un échange par jeton.** Dans un processus, les appels concurrents rejoignent un même
   vol (`run_single_flight`) ; entre processus, un seul prend la réclamation Redis
   (`run_shared_flight`), dont la durée et le budget d'attente sont dérivés de la
   politique de relance de l'échange et de la borne d'écriture, jamais d'un littéral.
   Chaque tentative publie `<tentative>:<verdict>`, un échec qu'elle n'attendait pas
   compris (sans quoi l'attendant d'un autre processus attendait la réclamation entière,
   ~40 s aux défauts) ; un attendant n'accepte qu'un verdict publié après le début de son
   attente. Un rafraîchissement forcé rejoint un rafraîchissement en cours.
2. **Aucune transaction pendant l'appel.** La porte n'utilise jamais la session de son
   appelant : elle lit sur une session courte, appelle le fournisseur sans transaction
   ouverte, puis écrit sur une autre. Un appelant qui POSSÈDE sa session lit en deux
   temps — `ConnectorService.read_connector_credentials`, fin de sa transaction, puis
   `StoredCredentials.fresh()` : le client OAuth, l'emballage du tour du chat (qui
   relâche aussi son verrou avant la porte) et `open_active_client`.
   `get_connector_credentials` enchaîne les deux pour un appelant qui prête sa session.
3. **Une écriture conditionnée et bornée.** L'écriture verrouille le grant puis ses
   liens, dans l'ordre de l'amendement du 2026-10-15, et n'aboutit que si le chiffré lu
   au départ est toujours celui stocké et le propriétaire toujours actif ; sinon le
   jeton du gagnant est servi. Elle attend sa ligne au plus
   `OAUTH_REFRESH_WRITE_LOCK_TIMEOUT_MS` (`SET LOCAL lock_timeout`) : un appelant dont la
   transaction ouverte tient la ligne attendrait la porte, qui attendrait son verrou —
   un cycle que PostgreSQL ne voit pas. Passé la borne (SQLSTATE lu, jamais le message),
   le demandeur reçoit le jeton que le fournisseur vient d'émettre, non stocké, et les
   attendants reçoivent un échec, jamais le jeton périmé resté stocké. Une écriture
   commencée survit à l'annulation de l'appelant (`write_through_cancellation`).
4. **`invalid_grant` est revérifié.** Les services liés ne passent en `ERROR` que si le
   chiffré stocké est toujours celui qui a été refusé : un refus causé par une rotation
   faite ailleurs n'est pas une révocation. Une révocation que la borne empêche de
   vérifier est rapportée comme un échec, jamais comme une déconnexion.
5. **L'admission est celle de chaque appelant.** Les services d'un grant partagent son
   rafraîchissement, mais savoir si un appelant peut être servi reste la question de SON
   lien. Un service détaché du grant pendant un rafraîchissement est refusé pour
   lui-même : un appelant qui rejoint ce vol, ou qui lit le verdict publié par un autre
   worker, redemande une fois pour son propre lien, et deux refus visant d'autres
   porteurs sont rapportés comme un échec — jamais comme un « reconnectez » pour un lien
   qu'il tient encore.
6. **Ce qui disparaît.** `OAuthGrantRuntime`, `OAuthLock` (sa famille de clés Redis,
   ses cinq séries, `connector_token_refresh_total` et `OAUTH_LOCK_TIMEOUT_SECONDS`).
   Le tableau 10 lit `oauth_refresh_outcomes_total{kind, outcome}` et
   `oauth_refresh_flights_total{kind, how}`.

**Preuves.** Tests unitaires écrits avant le code, passes de mutation (porte,
magasins, transitions bornées, lecture en deux temps), et tests sur un vrai PostgreSQL
et un vrai Redis : un échange pour deux workers, `invalid_grant` après une rotation
faite ailleurs, écritures conditionnelles sur la colonne de statut, ligne tenue par
l'appelant (la porte rend la main dans sa borne), session d'une unité hors transaction au
moment de l'échange. Observé ensuite sur Docker dev (2026-10-23) : de vrais échanges par
la porte, côté appelant (le tableau de bord : une autorisation partagée Google et deux
jetons de connecteur) comme côté ordonnanceur (deux jetons Microsoft), tous `refreshed`.

**Résidu assumé.** Les appelants qui lisent par `get_connector_credentials` sur une
session qu'ils tiennent gardent leur transaction de lecture pendant un rafraîchissement :
rare, borné par l'échange, sans verrou de ligne. Une écriture contestée sert le jeton
émis sans le stocker : chez un fournisseur qui invaliderait l'ancien refresh token à
chaque rotation, le rafraîchissement suivant lirait `invalid_grant` sur un chiffré
inchangé et déconnecterait la personne. Google ne fait pas tourner ses refresh tokens et
Microsoft laisse l'ancien valide ; le pont Hue n'est pas mesuré.
