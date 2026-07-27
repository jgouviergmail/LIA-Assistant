# ADR-158: La parité de clés ne mesure pas le contenu — cliquet sur la troncature des traductions

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA

## Contexte

`scripts/i18n/validate_translations.py` (hook pre-commit + job CI `code-hygiene`)
compare les **ensembles de clés** des 6 locales à celui de `en` et refuse toute
clé manquante ou en trop. C'est la seule garde i18n du dépôt, et elle est
aveugle à ce qui se trouve **derrière** la clé.

Une locale qui remplace une réponse de 500 caractères par un résumé de 150 passe
ce contrôle indéfiniment. Personne ne le voit : la page s'affiche, la recherche
FAQ fonctionne, aucun test ne rougit.

**Mesuré le 2026-07-27** : **23 chaînes** réparties sur **13 clés** portaient
entre **31 % et 58 %** du contenu servi par les autres locales latines
(`de` 9, `it` 13, `es` 1). Certaines depuis plusieurs versions.

Deux d'entre elles n'étaient pas seulement plus courtes, elles étaient
**fausses** :

| Erreur | Locales | Réalité vérifiée |
|---|---|---|
| « Réglages > **Apparence** > Fuseau horaire » | de, it | `Réglages > **Préférences** > Personnalisation > Fuseau horaire` — *Apparence* est la section du thème, pas un parent (`settings/page.tsx:264-278`) |
| « bouton avec l'icône **d'actualisation** » | de, it | C'est une **corbeille** (`Trash2`, `chat/page.tsx:22,900`) |

Et une troisième inexactitude était présente dans **les six langues** ainsi que
dans `docs/knowledge/02_chat.md` — donc dans ce que LIA raconte d'elle-même :
la FAQ annonçait que la réinitialisation supprime « l'historique », alors que
`POST /conversations/me/reset` purge en plus **toutes les pièces jointes de
l'utilisateur, images générées par l'IA comprises**, les résumés de jetons, les
checkpoints LangGraph et les contextes d'outils. Le dialogue de confirmation
disait déjà la vérité ; la FAQ, non. Quelqu'un sur le point de perdre ses images
générées méritait de l'apprendre avant.

## Décision

**1. Réparer les troncatures.** 52 chaînes réécrites sur 10 clés × 6 langues
(les locales complètes sont réalignées en même temps, pour que le chemin de
navigation vérifié et le périmètre réel de la réinitialisation soient identiques
partout). Troncatures restantes : **23 → 5**.

**2. Poser un cliquet exécutable.**
`apps/web/src/__tests__/locale-truncation.guard.test.ts` signale toute chaîne
d'au moins 150 caractères tombant sous **60 % de la médiane** des locales
latines. Le signal est volontairement grossier, donc difficile à contester : il
attrape l'**abrègement**, qui est le mode d'échec récurrent. Il ne voit pas une
traduction fidèle mais fausse, et ne prétend pas le faire.

`zh` est **exclu de la comparaison** : le chinois porte le même sens en environ
un tiers des caractères, un ratio de longueur n'y signifie rien. Il reste couvert
par la relecture, pas par cette mesure.

La liste d'exemption est **shrink-only**, et un test refuse toute entrée périmée
comme toute croissance au-delà des 5 entrées mesurées à la pose.

## Ce que la mesure a exhumé et que nous ne corrigeons PAS ici

Les 5 exemptions ne sont pas des troncatures : ce sont des **permutations de
section**. `tool_examples_services` est décalée entre `{en, fr}` et
`{de, es, it}` sur q4→q14 — q11/q12 valent « rechercher / lire un fichier Drive »
d'un côté et « lire / répondre à un e-mail » de l'autre. Les deux jeux de
contenu sont **complets** ; seuls les index divergent. Idem pour
`connectors.q6` (« préférences par connecteur » vs « quelles permissions Google
sont demandées »).

Y coller la réponse de référence **détruirait** du contenu que ces locales
portent légitimement. La réparation correcte est un **réalignement de section
entier** : choisir l'ordre canonique `en` et ré-indexer le contenu existant de
chaque locale. C'est un travail mécanique mais à part, avec sa propre revue.

Une mesure plus large, par empreinte invariante à la langue (emoji, `<code>`,
étiquettes de version, identifiants ASCII), donne **126 entrées sur 223** qui
divergent de `en`. C'est une **borne haute** : l'empreinte signale aussi une
simple perte d'emoji. Elle est consignée ici comme point de départ du lot de
réalignement, pas comme un chiffre à corriger tel quel.

## Alternatives écartées

- **Étendre `validate_translations.py`** — ce script est le gardien de la
  parité de clés, appelé par le hook sur un budget de quelques secondes.
  Charger 6 fichiers de ~850 Ko et calculer des médianes y est possible mais
  mélange deux responsabilités ; le faire côté vitest le met dans le même
  harnais que les autres cliquets frontend, avec le même contrat shrink-only.
- **Comparer à `en` plutôt qu'à la médiane** — une seule locale de référence
  rend le seuil otage de sa propre verbosité. La médiane des cinq résiste à un
  `en` exceptionnellement court ou long.
- **Inclure `zh` avec un seuil dédié** — un facteur d'échelle par script serait
  une constante inventée. Mieux vaut une couverture honnêtement partielle qu'un
  seuil arbitraire qui rougit au hasard.
- **Traduire automatiquement les 126 divergences** — la moitié n'est pas un
  défaut, et une traduction automatique non relue sur une FAQ produit
  exactement la classe de défaut qu'on vient de corriger.

## Conséquences

- La classe « traduction abrégée » ne peut plus croître en silence.
- `docs/knowledge/{02_chat,03_settings,19_usage_limits}.md` sont réalignés sur
  les faits vérifiés — c'est la base que LIA lit pour se décrire.
- Le lot de réalignement des sections permutées reste ouvert et documenté.

## Références

- Garde : `apps/web/src/__tests__/locale-truncation.guard.test.ts`
- Parité de clés : `scripts/i18n/validate_translations.py`
- Garde de comptage des sections FAQ :
  `apps/web/src/components/faq/__tests__/section-count-wiring.test.ts`
- Une garde exécutable par classe de défaut : [ADR-095](ADR-095-Systemic-Guards-Wave2-Audit.md)
