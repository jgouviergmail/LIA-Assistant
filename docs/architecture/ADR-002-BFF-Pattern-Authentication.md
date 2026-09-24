# ADR-002: BFF Pattern pour Authentication

**Status**: ✅ ACCEPTED (2025-10-20) — toujours en vigueur (vérifié 2026-07-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Sécurisation de l'authentification (v0.1.0 JWT → v0.3.0 BFF)

> **Note de provenance (2026-07-21)** : fichier **reconstitué** depuis le résumé de
> `ADR_INDEX.md` (l'ADR original n'a jamais été committé). Confirmé contre le code :
> l'authentification repose sur un cookie de session HTTP-only
> (`SecuritySettings`, `src/lib/api-client.ts` en `credentials: 'include'`), pas sur
> des JWT en stockage client. Dates d'origine conservées du résumé.

---

## Context and Problem Statement

L'authentification initiale reposait sur des **JWT stockés côté client**. Trois
problèmes : vulnérabilité XSS (token en `localStorage`), surcoût de taille (données
utilisateur embarquées dans chaque token), et révocation impossible (JWT stateless).

## Decision

Adopter le **BFF Pattern** (Backend-For-Frontend) : sessions serveur en Redis,
identifiées par un **cookie HTTP-only** `SameSite=Lax`.

- Le frontend n'a jamais accès au matériel de session (pas de token en JS).
- Le cookie porte uniquement un `session_id` ; l'état vit côté serveur (Redis).
- La révocation est instantanée (suppression de la clé Redis).

## Alternatives Considered

- ❌ **JWT en `localStorage`** — surface XSS, pas de révocation.
- ❌ **JWT en cookie** — révocation toujours impossible (stateless).
- ✅ **BFF + sessions Redis** — immunité XSS, révocation instantanée, empreinte réduite.

## Consequences

- ✅ Cookies HTTP-only : immunité XSS sur le matériel d'auth.
- ✅ `SameSite=Lax` : protection CSRF.
- ✅ Révocation instantanée (delete Redis).
- ✅ ~90 % de mémoire en moins (session_id seul vs données embarquées).
- ⚠️ État serveur requis (Redis) — dépendance d'infrastructure sur le chemin d'auth.

## Metrics (à l'acceptation)

- Empreinte mémoire : 1,2 Mo → 120 Ko (~90 % de réduction).
- Lookup de session : P95 < 5 ms (Redis).
- Score sécurité : B+ → A (OWASP 2024).

## Related

- [ADR_INDEX.md](./ADR_INDEX.md) · [AUTHENTICATION.md](../technical/AUTHENTICATION.md) (détail BFF, sessions, cookies)

## Amendement 2026-09-23 — une identité fédérée ne donne aucun droit

**Constat, mesuré en production.** Le 2026-09-18, une inscription par e-mail
(compte inactif en attente d'approbation, adresse jamais vérifiée) s'est
activée 68 secondes plus tard par une connexion Google sur la même adresse.
Quand elle trouvait le compte par son adresse, la liaison écrivait
`is_active=True`. Cette branche ne notifiait personne, et la notification
admin du parcours normal part à la vérification de l'e-mail, qui n'a jamais eu
lieu : l'approbation a donc été contournée **en silence**. Reproduit sur
PostgreSQL réel, le même chemin **débloquait aussi un compte qu'un admin avait
bloqué**, s'il n'avait pas encore d'identité Google.

**Décision.**

1. Rattacher une identité ne change **jamais** le statut d'un compte : la
   liaison n'écrit plus `is_active` (`AuthService._link_google_identity`).
2. L'adresse annoncée par Google n'est crue, pour atteindre un compte existant
   ou en créer un, que si Google s'en porte garant. Le schéma userinfo v2
   déclare `verified_email` avec la valeur par défaut `true`, donc seul un
   `false` explicite refuse (`google_email_is_verified`). L'`id` Google reste
   l'identité et se compare tel quel.
3. Quand personne n'avait prouvé l'adresse, la liaison la prouve, et le compte
   passe à celui qui l'a prouvée. Le mot de passe et les sessions du déclarant
   n'ont jamais été liés à l'adresse : ils sont révoqués (pré-détournement de
   compte, sinon le mot de passe du déclarant ouvrirait le compte de la
   personne le jour où un admin l'approuve). L'inscription attend alors
   l'approbation comme après une vérification d'e-mail : les admins sont
   notifiés, la personne est prévenue.
4. Un compte supprimé (ligne conservée pour la facturation) n'est jamais
   ranimé : refus `account_deleted`.
5. Un refus est une exception typée à motif **borné**
   (`GoogleSignInRefusedError`) : le callback le transmet tel quel à la page
   d'erreur ou au lien profond natif, et en libellé de métrique, sans passer par
   la classification par message du gestionnaire générique.
6. Mettre fin à sa propre session n'exige aucun statut : `/auth/logout` accepte
   un compte inactif. La page « compte inactif » n'offre que cette action, et
   elle répondait 403.

**Preuves.** `apps/api/tests/integration/test_auth_service_refactored.py`
(`TestGoogleLinkNeverChangesStanding`, `TestGoogleEmailClaim`, sur PostgreSQL et
Redis réels) ; `apps/api/tests/unit/domains/auth/test_google_oauth_native_and_mfa.py`
(`TestRefusedSignInNamesItsReason`) ; `apps/api/tests/integration/test_auth.py`
(`test_an_inactive_account_can_end_its_own_session`).

**Écartés.** Refuser toute liaison sur un compte non vérifié : la personne qui
possède l'adresse resterait bloquée (l'adresse est prise, et Google serait
refusé). Supprimer le compte non vérifié puis le recréer : plus lourd
(provisionnement, connecteurs) pour la même garantie que la révocation.
