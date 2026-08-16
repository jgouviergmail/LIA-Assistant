# ADR-219 : une position mémorisée ne vaut que si tout le monde la lit — et si son âge voyage avec elle

**Statut**: ✅ IMPLEMENTED (2026-08-16)
**Date**: 2026-08-16
**Complète partiellement**: ADR-073 (persistance de la dernière position, portée météo)

## Contexte

L'ADR-073 a livré une mécanique saine — position navigateur persistée en
opt-in, chiffrée, non historisée, TTL de fraîcheur, throttle d'écriture —
mais l'a cloisonnée aux jobs proactifs : seule la cascade
`get_effective_location_for_proactive` la consultait (heartbeat, briefing,
intérêts). Le chokepoint de résolution des outils (`resolve_location`), lui,
ne connaissait que deux sources : la position navigateur vivante, sinon
l'adresse du domicile.

Sur téléphone (PWA Android/iOS), la position vivante meurt vite : une
application gelée puis réveillée ne remonte jamais son hook, le cache de
5 minutes expire, et chaque message part avec `geolocation: null`. Sur iOS
standalone, la permission retombe en plus sur `prompt` après inactivité.
Résultat mesuré par le propriétaire en déplacement : « restaurants dans le
coin » répondait depuis le domicile, les actions planifiées — qui n'ont
jamais de contexte navigateur — aussi, et il fallait taper une phrase de
localisation pour qu'une bannière propose enfin de réactiver.

Trois défauts distincts, une seule racine : la donnée existait, personne ne
la lisait, et rien ne la rafraîchissait.

## Décision

### 1. Le flag et les endpoints cessent de mentir sur leur portée

`users.weather_use_last_known_location` devient `use_last_known_location`
(migration `0d1e2f3a4b5c`), `PATCH /auth/me/weather-location-preference`
devient `PATCH /auth/me/location-preference`. Un nom qui revendique une
portée que le code n'a plus est le même défaut qu'une docstring mensongère.
Frontend et backend se déploient ensemble : aucun alias de compatibilité.

### 2. La cascade du chokepoint intègre la position mémorisée

`resolve_location` (runtime_helpers) résout désormais :

- **implicite** (aucune phrase de localisation) : navigateur >
  **last_known (opt-in + fraîche < TTL)** > domicile > silence ;
- **position courante / « où suis-je »** : navigateur > **last_known avec
  son âge** > message d'invitation — le domicile n'entre JAMAIS dans cette
  branche : répondre « chez toi » à « où suis-je » est le mensonge que cette
  fonctionnalité supprime ;
- **« chez moi »** : inchangé (domicile > navigateur > message) — une
  position captée sur la route ne dit rien du domicile.

La branche implicite est extraite en `resolve_implicit_location`, que les
trois sites des outils places qui recopiaient « navigateur sinon domicile »
à la main utilisent désormais. Les actions planifiées, sans contexte
navigateur, héritent de la cascade sans une ligne de code.

Le seuil de distance de 50 km reste propre à la cascade proactive (il y
stabilise les notifications) : au bureau à 5 km du domicile, « restos dans
le coin » doit utiliser la vraie position. Le TTL reste unique
(`LAST_KNOWN_LOCATION_TTL_HOURS`, 24 h) : une seule notion de fraîcheur.

### 3. Une position datée s'annonce datée

`ResolvedLocation` gagne `as_of`, renseigné uniquement pour
`source="last_known"`. L'outil « où suis-je » le publie dans sa réponse
(`Source: last known position, captured at …Z (not live)`), le contexte du
skill runner le suffixe (`(last_known 2026-08-16T09:30Z)`) et le prompt
versionné enseigne au modèle d'énoncer l'âge dans la langue de
l'utilisateur — jamais de présenter un point daté comme la position
courante (même doctrine que les comptes exacts d'ADR-185).

### 4. Le cycle de vie PWA est géré, dans la limite de ce que la plateforme permet

`useGeolocation` écoute `visibilitychange`/`pageshow` : au retour au premier
plan, permission re-vérifiée ; si `granted` → rafraîchissement silencieux
(aucun prompt) ; si retombée à `prompt` → `needsReactivation`, que la
bannière du chat consomme en mode proactif dès l'ouverture, avant toute
phrase, une fois par session — son bouton fournit le geste utilisateur
qu'iOS/Android exigent pour rouvrir la feuille native. C'est le plafond de
la plateforme : aucune réactivation automatique n'est possible sans geste.

### 5. L'alimentation ne dépend plus d'une page ouverte

Le push throttlé vers `PUT /auth/me/last-location` quitte le bloc de
réglages météo (qui ne tournait que pendant la visite de cette page) pour
`useLastKnownLocationSync`, monté dans le layout authentifié. Le chat
continue de pousser à chaque message (fire-and-forget). Un échec de push ne
tamponne pas le throttle : le prochain changement de coordonnées réessaie.

### 6. Le réglage vit sur le connecteur Google Places, seul

Opt-in généralisé + transparence (coordonnées stockées, date, staleness,
effacement) rejoignent `LocationSettings`, entre la géolocalisation live et
le domicile — l'ordre de la cascade. Le bloc des notifications proactives
est supprimé sans trace (arbitrage propriétaire 2026-08-16). Clés i18n
migrées ×6, anciennes clés supprimées ×6.

## Conséquences

- En mobilité, un message envoyé après des heures d'inactivité répond
  depuis la dernière position connue (< 24 h) au lieu du domicile — y
  compris pour les actions planifiées et le briefing du matin.
- « Où suis-je » sans GPS vivant donne une réponse honnête et datée au lieu
  d'une invitation à activer la géolocalisation.
- Le consentement reste opt-in (défaut off), le stockage chiffré et non
  historisé, l'effacement immédiat à l'opt-out — rien de l'ADR-073 n'est
  affaibli.
- La cascade proactive existante est fonctionnellement inchangée.
- Limite assumée : si la permission est retombée ET que l'utilisateur
  ignore la bannière, la dernière position vieillit jusqu'au TTL puis le
  domicile reprend — c'est le fallback voulu.

## Références

- Spec : `docs/superpowers/specs/2026-08-16-generalized-last-known-location-design.md`
- Runbook : `docs/runbooks/LAST_KNOWN_LOCATION.md`
- Tests pivots : `tests/unit/domains/agents/tools/test_resolve_location.py`,
  `useGeolocation.test.ts` (cycle de vie PWA), `useLastKnownLocationSync.test.ts`,
  `GeolocationPrompt.test.tsx` (mode proactif)
