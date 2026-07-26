# ADR-154: Frontière de phrase pour la synthèse vocale — un délimiteur ne compte que suivi d'une espace

**Statut**: ✅ IMPLEMENTED (2026-07-26)
**Date**: 2026-07-26
**Décideurs**: Équipe LIA
**Contexte technique**: `src/domains/voice/service.py::_extract_sentences`, `src/domains/voice/sentence_streamer.py::_build_sentence_end_regex`

---

## Contexte

La voix de LIA est découpée en phrases avant d'être synthétisée : chaque phrase
part vers le moteur TTS séparément, ce qui permet de commencer à parler avant la
fin de la génération. Deux implémentations indépendantes décidaient où une phrase
se termine :

- `VoiceCommentService._extract_sentences` — chemin direct (un seul appel) ;
- `ProgressiveSentenceStreamer` — chemin progressif (le défaut), qui dispatche
  une phrase vers le TTS **dès** qu'il voit une frontière dans son tampon.

Les deux traitaient **tout `.` comme une fin de phrase**, quel que soit ce qui
suivait. Mesuré :

| Entrée | Phrases obtenues |
|---|---|
| `Il fait 3.5 degrés dehors.` | `Il fait 3.` + `5 degrés dehors.` |
| `Le prix est 12.99 EUR.` | `Le prix est 12.` + `99 EUR.` |
| `Version 1.2.3 disponible.` | `Version 1.` + `2.` + `3 disponible.` |
| `Voir https://exemple.fr/page pour plus.` | `Voir https://exemple.` + `fr/page pour plus.` |

L'utilisateur entendait donc « il fait trois. » puis, dans un **chunk audio
distinct**, « cinq degrés dehors ». Températures, prix, durées, numéros de
version, URL : tout ce que LIA énonce en chiffres était coupé en deux. Rien ne
lève, rien ne s'écrit dans les logs — le défaut n'est audible que par un humain
qui écoute, ce qui explique qu'il ait survécu.

Sur le chemin progressif, un second mécanisme aggravait le premier : le tampon
grandit token par token, si bien que `"3."` est un état **transitoire** parfaitement
normal. Dispatcher sur ce tampon, c'est parler avant d'avoir lu la suite.

## Décision

Un délimiteur (`.`, `!`, `?` — la liste est configurable) ne ferme une phrase que
s'il est **en fin d'entrée ou suivi d'une espace**. Un point collé au caractère
suivant appartient au token, pas à la prose.

- `_extract_sentences` découpe désormais sur une frontière de largeur nulle
  (`(?<=[délims])(?=\s|$)`) au lieu de capturer `([^délims]*[délims])` : chaque
  fragment conserve son délimiteur, et un point interne ne peut plus fermer.
- `_build_sentence_end_regex` exige `(?=\s)`. En streaming, cela signifie qu'un
  délimiteur en fin de tampon **n'est pas** une frontière : on attend le
  caractère suivant. La queue qui n'obtient jamais d'espace est vidée par
  `close_input()`, qui existait déjà pour le cas « le LLM s'arrête sans
  ponctuation ».

Les deux règles sont épinglées par une table de cas **partagée**
(`tests/unit/domains/voice/test_sentence_boundaries.py`) appliquée aux deux
implémentations, plus une classe qui exige leur accord — deux implémentations
d'une même règle dérivent, c'est la classe de défaut récurrente de ce dépôt.
Le cas décisif est joué **caractère par caractère** : c'est la seule façon de
reproduire le tampon qui se termine sur un point.

## Conséquences

**Positives**
- Un nombre décimal, un prix, une version ou une URL est prononcé d'un seul
  tenant, dans un seul chunk audio.
- Le streaming ne décide plus d'une frontière sur un tampon incomplet.
- Les deux découpeurs répondent la même chose sur la même entrée, et un test le
  vérifie.

**Négatives / limites**
- Une phrase terminée par un délimiteur **collé** à la suivante
  (`"Bonjour.Comment ça va ?"`, une faute de frappe du modèle) n'est plus
  découpée : elle part en une seule phrase. Le TTS la prononce correctement, la
  latence du premier chunk est simplement un peu plus longue.
- Une abréviation suivie d'une espace (`"M. Dupont"`) reste découpée. La
  corriger demanderait un lexique par langue ; la prosodie obtenue est
  acceptable et le coût ne le justifie pas.
- La règle est indépendante de la langue, donc du zh (qui utilise `。`) : ce
  délimiteur n'est pas dans la liste par défaut, le comportement y est inchangé.

## Alternatives écartées

- **Ne pas découper sur un point entouré de chiffres** (`(?<!\d)\.(?!\d)`) :
  corrige les décimaux et rien d'autre — ni les URL, ni les versions, ni le
  tampon transitoire du streaming, qui est le vrai piège.
- **Unifier les deux découpeurs** en un seul : souhaitable, mais leurs contrats
  diffèrent (l'un rend `(phrase, complète)`, l'autre consomme un tampon
  incrémental). La table de cas partagée capture l'essentiel — l'accord — sans
  la refonte ; l'unification reste ouverte.

## Références

- `tests/unit/domains/voice/test_sentence_boundaries.py` — table partagée + classe d'accord
- [ADR-153](ADR-153-HITL-Action-Taxonomy.md) — même classe : deux implémentations d'une règle qui dérivent
