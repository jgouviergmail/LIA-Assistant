# ADR-136 : Posture COEP `credentialless` et états d'échec des widgets

**Statut** : Accepté — implémenté (frontend), matrice moteur mesurée sur WebKit 26.4 et Chromium.
**Date** : 2026-07-21
**Contexte** : fait suite à [ADR-098](ADR-098-CSP-Widget-Airlock.md) (sas CSP des widgets), qui avait restauré ces mêmes widgets sur Chromium sans que le comportement WebKit soit vérifié.

## Contexte

Sur iPhone, les widgets qui chargent un document par le réseau — la carte
Google Maps du skill `interactive-map` et les MCP Apps — s'affichaient comme un
**cadre présent mais vide**, sans message ni trace, alors que le morpion
(`srcDoc`, aucun chargement réseau) fonctionnait. Aucun signal n'était émis :
ni erreur utilisateur, ni log, ni métrique.

Cinq hypothèses ont été formulées puis **réfutées par la mesure** avant
d'atteindre la cause : registre non persisté, attribut avalé par React,
configuration cassée sur Chromium mobile, course du handshake du sas
(10/10 runs conformes, dont CPU ×20 sur Slow 3G), sous-ressources CDN bloquées
par COEP (5/5 classes passent). L'absence d'état d'échec est ce qui a rendu
cette élimination nécessaire depuis l'extérieur du produit.

### Cause racine

L'application émet `Cross-Origin-Embedder-Policy: require-corp` sur toutes les
routes, pour le `SharedArrayBuffer` du mot-clé vocal (Sherpa-onnx KWS). Sous
`require-corp`, un document imbriqué cross-origin doit **lui-même** déclarer
COEP. Le point d'embarquement Google Maps n'envoie ni COEP ni CORP (vérifié) :
l'embed ne survit que grâce à l'attribut d'iframe `credentialless`, **présent
uniquement dans Chromium**.

Banc Playwright, en-têtes de production répliqués, embed Maps réel :

| en-tête COEP | Chromium : isolé / SAB / carte | WebKit : isolé / SAB / carte |
| --- | --- | --- |
| `require-corp` + attribut | oui / oui / oui | oui / oui / **bloquée** |
| `require-corp` sans attribut | oui / oui / bloquée | oui / oui / bloquée |
| **`credentialless` + attribut** | **oui / oui / oui** | **non / non / oui** |
| absent | non / non / oui | non / non / oui |

Message exact renvoyé par WebKit : *« Cancelled load to
`https://www.google.com/maps/embed?…` because it violates the resource's
Cross-Origin-Resource-Policy response header »*.

Deux points mesurés qui ferment des alternatives :

- **L'isolation cross-origin n'est pas délégable.** Un iframe porteur de COEP
  dans un top-level non isolé n'obtient ni `crossOriginIsolated` ni
  `SharedArrayBuffer` (vérifié sur les deux moteurs). Isoler le KWS dans son
  propre document est donc impossible.
- **Le sas MCP n'est pas en cause** : sur WebKit il franchit ses quatre
  verrous (`window.origin === "null"`), reçoit sa charge utile et l'exécute,
  dans les cinq configurations testées.

## Décision

### 1. Posture COEP par défaut : `credentialless`

`resolveCoepMode()` (`apps/web/src/lib/csp.ts`) résout la valeur émise, avec
`credentialless` par défaut et repli sur ce défaut pour toute valeur non
reconnue — une faute de frappe ne doit jamais faire émettre un en-tête que le
navigateur ignorerait, ce qui supprimerait silencieusement l'isolation.

Réglable par `COEP_MODE` sans reconstruction (même schéma que `HSTS_MAX_AGE`),
donc réversible en production par un simple redémarrage.

**Compromis assumé** : sur WebKit, `credentialless` n'est pas implémenté, la
page perd donc l'isolation et le mot-clé vocal. Cette dégradation **préexiste
et est déjà gérée** : `isSherpaKwsSupported()` teste `crossOriginIsolated` et
`VoiceModeBadge` bascule en appui-pour-parler. Sur Chromium, rien ne change :
isolation, `SharedArrayBuffer` et carte restent identiques.

La garantie de sécurité est préservée : `credentialless` est un mode
standardisé d'isolation cross-origin, où les requêtes no-cors partent **sans
credentials** au lieu d'être bloquées — une ressource tierce ne peut donc pas
exposer de données authentifiées.

### 2. Ne jamais rendre un embed condamné

`canEmbedOpaqueCrossOriginFrame({ credentiallessApplied })`
(`apps/web/src/lib/frame-embedding.ts`) répond **avant le rendu** : document non
isolé (COEP n'impose rien), **ou** moteur supportant `credentialless` **et
attribut effectivement posé** → embed tenté ; sinon → carte de repli avec lien
externe. Seuls les `frame_url` cross-origin sont concernés ; `srcDoc` et le sas
same-origin ne le sont jamais.

La capacité du moteur ne suffit pas, et l'oublier laissait un trou : l'attribut
n'est posé que sur les URL de skills **système**. Un frame non fiable — ou
réhydraté depuis l'historique avec `is_system_skill` remis à faux ([ADR-137](ADR-137-Host-Owned-Widget-Sentinels-And-Message-Persistence.md)) — est
refusé sur Chromium aussi, et **le refus y est invisible** : Chromium déclenche
`load` sur son document d'erreur, donc le chien de garde ne le voit pas non
plus. La décision d'embarquer et la décision de poser l'attribut partagent
désormais une seule source de vérité.

L'attribut `credentialless` reste posé sur les frames de skills système : il
est ce qui fait fonctionner l'embed sous `COEP_MODE=require-corp`, et il est
inerte ailleurs.

### 3. Tout widget a un état d'échec

`useFrameLoadWatchdog()` observe l'événement `load` et bascule sur un état
actionnable (message + *Réessayer* + lien externe) au-delà de
`NEXT_PUBLIC_WIDGET_FRAME_TIMEOUT_MS` (défaut 15 s). Il complète la sonde de
façon symétrique aux deux comportements moteur sur un embed refusé :

- WebKit annule la navigation — **aucun événement `load`** → le chien de garde
  se déclenche ;
- Chromium déclenche `load` sur son document d'erreur — la sonde a déjà empêché
  le rendu dans ce cas.

Le dépassement journalise `widget_frame_load_timeout` avec
`crossOriginIsolated` et `credentiallessSupported` : les deux faits qui
expliquent presque toute refus COEP, capturés au moment de l'échec pour qu'un
signalement distant soit exploitable seul.

**Le signal de vie diffère selon la famille de widget** (`readiness`) :

| famille | signal | pourquoi |
| --- | --- | --- |
| skill (`frame-load`) | l'événement `load` de la frame | le document **est** le widget : le charger, c'est toute l'histoire |
| MCP App (`bridge-ready`) | la poignée de main du protocole (`ui/initialize` / `ui/notifications/initialized`) | `load` ne prouve que le chargement du **sas**, jamais la vie du widget tiers |

Cette distinction est née d'une mesure. Sur WebKit, **chaque maillon du chemin
LIA fonctionne** : le sas se charge, ses quatre verrous passent, la charge utile
est livrée et s'exécute, le parent reçoit bien `event.origin === "null"`, et une
charge de 205 ko avec JSON inline et canvas se rend correctement. Un widget
tiers qui meurt au démarrage laissait pourtant un rectangle opaque — que
l'événement `load` ne peut pas voir. La poignée de main, si.

Le fond de la frame MCP passe aussi en `transparent` : `--lia-bg` en mode sombre
donnait un **rectangle noir** plutôt qu'une zone visiblement vide.

**La notice MCP est non destructive**, et c'est délibéré. Pour une frame de skill
qui n'a jamais chargé, il n'y a rien à préserver : le repli remplace l'iframe.
Pour une MCP App, le sas **a** chargé et le widget peint peut-être quelque chose
même s'il n'a jamais parlé le protocole. La spécification fait de la poignée de
main le préalable à la livraison des données — donc un widget muet devrait être
vide — mais c'est un argument de spécification, pas une mesure, et détruire un
widget qui fonctionne (avec l'état que l'utilisateur y a construit) pour afficher
une erreur serait la pire des deux pannes. La notice s'affiche **au-dessus** de
la frame, qui reste montée. Une poignée de main tardive fait disparaître la
notice : le widget s'est prouvé vivant, l'interface se rétablit.

## Conséquences

- iOS récupère la carte ; il perd le mot-clé vocal (l'appui pour parler reste
  disponible).
- iOS récupère aussi le **sas** des MCP Apps — mais pas nécessairement le widget
  tiers qu'il héberge. Mesuré : tout le chemin LIA fonctionne sur WebKit ; un
  runtime tiers peut malgré tout mourir au démarrage. LIA ne peut pas le
  corriger, elle peut désormais le **dire** (mode `bridge-ready` ci-dessus) au
  lieu d'afficher un rectangle muet. Le cas Excalidraw sur iPhone reste ouvert
  côté widget, et c'est ce chien de garde qui le documentera.
- Chromium est inchangé, à l'octet près.
- Un widget qui échoue le dit désormais, avec un recours et une trace.
- `COEP_MODE=require-corp` restaure l'ancienne posture sans reconstruction si
  le mot-clé vocal sur iOS devait primer.

## Alternatives écartées

| Alternative | Raison |
| --- | --- |
| Isoler le KWS dans un document dédié porteur de COEP | Mesuré impossible : l'isolation n'est pas héritable depuis un top-level non isolé. |
| Retirer COEP entièrement | Supprime le mot-clé vocal sur **tous** les navigateurs, alors que `credentialless` le préserve sur Chromium. |
| Proxifier le document Maps derrière notre origine pour lui ajouter CORP | Le document proxifié rechargerait ensuite ses propres sous-ressources cross-origin sans CORP — déplace le blocage d'un cran. |
| Garder `require-corp` et se contenter du repli (option A seule) | Laisse iOS sans carte interactive alors qu'une valeur d'en-tête suffit à la restaurer. |

## Complément post-livraison (2026-07-21)

Le lien « Ouvrir dans un navigateur » du repli ouvrait `frame_url` — pour la
carte, l'endpoint d'embed que Google refuse hors iframe (*« The Google Maps
Embed API must be used in an iframe »*) : un cul-de-sac exactement là où l'état
d'échec devait donner un recours. Le contrat de sortie de script gagne un
`link_url` optionnel (https imposé, comme `url`) : l'URL **navigable** du même
contenu, fournie par le skill (`render_map.py` émet `google.com/maps?q=…`),
transportée jusqu'au payload et préférée à `frame_url` par les deux replis.

### Relais d'erreurs de démarrage (même jour)

Le chien de garde `bridge-ready` dit qu'un widget MCP est mort, jamais
**pourquoi** — et son diagnostic atterrit dans la console du navigateur,
illisible sur un téléphone. Le sas installe désormais des hooks d'erreurs
(`error` en phase capture pour les échecs de chargement de ressources,
`unhandledrejection`) qui relaient au parent un message
`lia:widget-error` plafonné (5 relais, 300 caractères) ; la notice de timeout
affiche ce détail en **texte brut uniquement** (`mcp_apps.frame_error_detail`,
6 langues) — un widget hostile peut forger le message, il n'obtient que des
mots, jamais de balisage ni de lien.

**Découverte de banc qui a corrigé la conception** : `document.open()` efface
**tous les listeners de la Window** (mesuré sur les deux moteurs) — ce qui
survit au `document.write`, c'est l'**identité** de la Window
(`contentWindow`, `event.source`), pas ses listeners. Les hooks sont donc
installés **après** `document.close()` : le script du sas continue de
s'exécuter, et les modules (le mode d'échec réel — imports CDN) s'exécutent
toujours après la tâche courante. Seul un `throw` synchrone d'un script
classique inline pendant le parse échappe au relais (assumé : la notice sans
détail reste). Un module inline dont l'import statique échoue émet un
événement **sans message ni src** (mesuré) — le sas nomme alors le suspect :
*« Widget script failed — its CDN imports may be unreachable »*, précisément
le scénario d'un CDN bloqué côté appareil. Prouvé au banc : payload cassé →
relais sur Chromium et WebKit ; payload de production réel → aucune fausse
alerte, poignée de main et rendu intacts.

Réserve de déploiement : `widget-frame.html` est un fichier public que le
navigateur ou le CDN peut avoir en cache — d'anciens sas sans relais peuvent
survivre quelque temps après déploiement (dégradé : notice sans détail,
jamais cassé).

## Vérification

- `apps/web/src/lib/__tests__/csp.test.ts` — défaut, opt-in explicite, repli sur valeur inconnue.
- `apps/web/src/lib/__tests__/frame-embedding.test.ts` — les quatre états de la sonde.
- `apps/web/src/hooks/__tests__/useFrameLoadWatchdog.test.tsx` — machine à états, contenu du rapport, nettoyage du timer.
- `apps/web/src/components/chat/__tests__/SkillAppWidget.test.tsx` — embed vs repli à charge utile identique, seul l'état du moteur changeant.
