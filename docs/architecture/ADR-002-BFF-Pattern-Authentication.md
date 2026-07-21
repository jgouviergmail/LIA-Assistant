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
