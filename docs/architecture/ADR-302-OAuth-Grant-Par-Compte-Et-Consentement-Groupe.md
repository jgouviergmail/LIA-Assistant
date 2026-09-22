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
- `apps/api/src/domains/connectors/oauth_grant_runtime.py`
- `apps/api/src/infrastructure/scheduler/token_refresh.py`
- `apps/web/src/components/settings/connectors/hooks/useBulkConnect.ts`
- `apps/web/src/components/settings/connectors/hooks/useBulkReconnect.ts`
- [Procédure et callbacks](../technical/OAUTH.md)
- [Schéma des grants](../technical/DATABASE_SCHEMA.md)
