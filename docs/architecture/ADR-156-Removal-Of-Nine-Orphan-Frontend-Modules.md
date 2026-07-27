# ADR-156 : Suppression de neuf modules frontend orphelins

**Status**: ✅ IMPLEMENTED (2026-07-26)
**Date**: 2026-07-26
**Deciders**: jgouvier + Claude
**Technical Story**: Chantier « Respirer & Révéler », phase 1 (déblayage). Un scan multi-vecteurs des imports a révélé neuf modules à **zéro consommateur applicatif**, dont deux référençaient des clés i18n qui n'existent dans aucune locale — preuve qu'ils n'ont jamais été montés.

Cet ADR consigne la décision exigée par la règle systémique de `CLAUDE.md` : *« Dead code is deleted, not kept "for later" … Wire it or remove it — record the decision in a short ADR. »* Il prolonge [ADR-152](ADR-152-Removal-Of-Orphan-Frontend-Hooks.md), qui avait retiré trois hooks selon la même méthode.

## Constat

Recherche exhaustive sur `apps/web/src`, `apps/web/e2e`, les fichiers `index.ts` (barrels), les imports dynamiques `next/dynamic`, la configuration et la documentation. **Six vecteurs de survie possibles ont été testés, tous négatifs.**

| Module | Lignes | Tests | Verdict |
|---|---:|---:|---|
| `components/settings/APIKeyConnectorForm.tsx` | 322 | 143 | référence `settings.connectors.apiKey.*` — **clés absentes des 6 locales** |
| `components/settings/HomeLocationSettings.tsx` | 237 | 93 | supplanté par `WeatherLocationBlock` / `LocationSettings` |
| `components/voice/VoiceOverlay.tsx` | 224 | 37 + 5 cas | supplanté par `VoiceModeBadge` |
| `components/chat/EmotionalStateIndicator.tsx` | 203 | 74 | jamais monté ; le domaine psyché passe par `AssistantAvatar` |
| `components/settings/GeolocationSettings.tsx` | 176 | 91 | supplanté par `WeatherLocationBlock` / `LocationSettings` |
| `components/ui/status-badge.tsx` | 142 | 41 | référence `status.blocked` — **clé absente des 6 locales** |
| `hooks/useVAD.ts` | 121 | — | doublon mort de `lib/audio/vad`, qu'utilise `useVoiceMode` |
| `components/memory-toggle.tsx` | 85 | 69 | jamais monté ; `memory.toggle.*` entièrement orphelin |
| `components/dashboard/BriefingGreeting.tsx` | 42 | 44 | supplanté par le titre du `HeroLiaCard` |

**1 561 lignes de code, 592 lignes de tests.**

### Deux modules étaient déjà cassés

`APIKeyConnectorForm` et `status-badge` interrogent des clés i18n qui **n'existent dans aucune des six locales**. Montés, ils afficheraient des identifiants bruts à l'écran. Ils n'étaient donc pas seulement inutilisés : ils étaient non fonctionnels.

### Un piège de scan à consigner

Le premier scan avait manqué que `VoiceOverlay` possédait un **second** fichier de test, sous un autre nom et dans un autre dossier (`components/chat/__tests__/chat-image-actions.a11y.test.tsx`). Un scan qui n'apparie les tests que par nom de module rate ce cas. Le bloc `describe('voice overlay')` a été retiré ; la partie `MarkdownContent` du fichier, elle, reste vivante et conservée.

## Décision

Supprimer les neuf modules, leurs tests, les entrées correspondantes de `.cc-baseline.json`, et les clés i18n devenues orphelines — **clé par clé, jamais par espace de noms** : `settings.location.*` et `chat.voice_mode.*` sont partagés avec `LocationSettings` et `VoiceModeBadge`, toujours vivants. 24 clés partagées ont été conservées, 24 orphelines retirées des 6 locales.

## Conséquence sur les seuils de couverture — et sur `VoiceModeBadge`

Le code retiré était **mieux couvert que la moyenne** (82 % de ses branches), donc son retrait fait mécaniquement baisser le ratio global. Le seuil par répertoire `src/components/voice/**` est tombé sous son plancher, `VoiceOverlay` disparu laissant `VoiceModeBadge` seul dans la mesure.

**Aucun seuil n'a été abaissé.** Deux actions ont rétabli la marge :

1. **15 tests comportementaux** ajoutés sur `VoiceModeBadge` : le message d'erreur choisi selon la panne (permission refusée / navigateur non supporté / échec du ticket / générique), l'annulation d'appui long (relâchement, sortie du pointeur, tactile), l'état d'initialisation du mot-clé et son absence quand le KWS n'est pas supporté, la persistance serveur de la préférence, les états désactivés.

2. **Suppression de code inatteignable dans `VoiceModeBadge`.** Le composant retourne `null` quand le mode vocal est désactivé, puis appelait `getAriaLabel` / `getIcon` / `getBadgeClasses` / `getLabel` en leur passant `enabled` — invariablement `true` à cet endroit. Leurs branches `if (!enabled)`, ainsi que la branche « activer » de l'appui long et le garde `!isEnabled` du clic, étaient structurellement mortes : elles expliquaient à elles seules l'essentiel des branches non couvertes du répertoire. Le paramètre a été retiré ; les `default:` des `switch` sont **conservés** (l'état `idle` de `VoiceModeState` les rend atteignables).

Bilan mesuré, planchers `64 / 58 / 58 / 65` inchangés :

| Métrique | Avant | Après |
|---|---:|---:|
| Statements | 65.73 % | **65.76 %** |
| Branches | 59.49 % | 59.31 % |
| Functions | 59.75 % | 59.64 % |
| Lines | 66.34 % | **66.36 %** |

Le ratchet de complexité a été abaissé en conséquence (52 → 50 fonctions au-dessus du seuil, 48 → 46 fichiers).

## Alternatives écartées

- **Câbler `EmotionalStateIndicator`** plutôt que le supprimer. Ce serait livrer une fonctionnalité non spécifiée sous couvert de nettoyage. Si l'état émotionnel doit devenir visible dans le chat, c'est une décision produit à prendre pour elle-même — le composant est dans l'historique git.
- **Abaisser le seuil du répertoire `voice`**. Interdit par la doctrine des ratchets, et cela aurait masqué le vrai constat : le code inatteignable.
- **Conserver le code mort pour préserver la couverture.** Raisonnement inversé : la métrique sert le code, jamais l'inverse.

## Conséquences

- ✅ 2 153 lignes de moins (code + tests), deux composants non fonctionnels retirés
- ✅ Couverture équivalente ou supérieure sur statements et lines, aucun seuil abaissé
- ✅ `VoiceModeBadge` simplifié et nettement mieux testé (5 → 20 tests)
- ✅ Ratchet de complexité abaissé
- ⚠️ Les modules restent récupérables dans l'historique git si un besoin réapparaît
