# ADR-253 — The answer declares its own register

**Statut** : Accepté — 2026-09-01
**Portée** : `apps/api/src/domains/agents/expressivity/`, `apps/web/src/components/eyes/tone.ts`
**Voisins** : [ADR-252](ADR-252-Expressive-Eyes-Animation-Rig.md) (le rig), [ADR-240](ADR-240-expressive-eyes-widget.md) (le widget)

## Le défaut, mesuré

Le visage du chat choisissait son expression de fin de tour dans l'émotion
dominante de la psyché. Quatorze tours de production consécutifs, lus en base :

```
enthusiasm 0,50 · 0,50 · 0,51 · 0,52 · 0,52 · 0,52 · 0,52 · 0,33 · 0,69 · 0,64 · 0,65 · 0,65 · 0,60
```

Treize tours sur quatorze nomment la même émotion, dans un mouchoir de 0,02.
C'est normal et voulu : **une psyché est un TRAIT**, elle bouge lentement. Mais
un `argmax` sur un vecteur quasi constant est une constante — donc chaque
réponse, quelle qu'elle soit, gagnait le même visage.

Le repli censé couvrir ce cas — une heuristique de ponctuation — n'avait rien à
dire non plus : sur ces mêmes quatorze réponses, **neuf ne contenaient ni « ! »,
ni emoji, ni bloc de code**. Et le multiplicateur d'emphase qui en découlait
mesurait de 0,94 à 1,21 : ±13 % sur deux groupes de canaux, sous une expression
qui ne changeait jamais. Invisible par construction.

Le prompt de la psyché interdisait déjà explicitement, en toutes lettres, de
« ne pas se rabattre sur enthusiasm à chaque tour ». Il était ignoré. Ce n'est
pas un problème de formulation : on demandait à un modèle d'état lent de
répondre d'un événement ponctuel.

## La décision

**Le modèle qui écrit la réponse déclare lui-même le REGISTRE de cette
réponse**, dans un vocabulaire qui appartient à l'animation et à rien d'autre.

```
<lia_tone register="assured" intensity="0.4" accent="nod"/>
```

Douze registres, douze visages réellement distincts — c'est la contrainte sous
laquelle le vocabulaire a été construit, et la raison pour laquelle la liste
n'est pas plus longue : *deux registres que l'avatar jouerait à l'identique sont
un seul registre portant deux noms.*

| Registre | Visage | Registre | Visage |
|---|---|---|---|
| `celebratory` | `excited` | `careful` | `thinking` |
| `playful` | `joy` | `questioning` | `question` |
| `warm` | `tender` | `surprised` | `surprise` |
| `curious` | `attentive` | `concerned` | `worried` |
| `assured` | `focused` | `apologetic` | `sad` |
| `factual` | `neutral` | `weary` | `tired` |

`intensity` est une **indication de jeu**, pas une confiance : le rendu est
censé la **surjouer**, pas la reproduire. Une caricature qui joue un 0,8 à 0,8
ressemble à un appel visio.

**La psyché garde ce qu'elle fait bien** : la famille d'humeur au repos
(respiration, cadence de clignement, poids des gestes d'inactivité). Un trait
doit colorer un comportement de repos, jamais une réaction ponctuelle. Elle
n'est plus consultée pour choisir un visage — le type `ReactionSource` n'a plus
de porte pour elle, ce qui en fait une garantie de compilation.

## Pourquoi en bande, et pas ailleurs

Deux exigences se croisent, et une seule forme les satisfait toutes les deux :

1. le signal doit être **déclaré par le modèle qui a écrit la réponse** — rien
   d'autre ne connaît le registre qu'il a choisi ;
2. il doit **arriver à l'instant où la réponse arrive** — l'avatar réagit sur la
   complétion, et une passe d'arrière-plan perd cette course. Les journaux de
   production le montrent : l'appraisal existant, en fire-and-forget, la rate
   sur la majorité des tours (`has_appraisal: false`).

Une passe d'annotation séparée aurait coûté un appel LLM par tour **et** aurait
couru après cet instant. Un marqueur en bande sur la même génération ne coûte
aucun appel et arrive avec le dernier jeton.

Le motif n'est pas inventé pour l'occasion : **c'est exactement celui de
`<psyche_eval/>`**, en production depuis des mois. Les fragments sont filtrés
dans le flux SSE pour que rien ne clignote à l'écran, et le marqueur complet est
retiré du contenu persisté dans le nœud de réponse.

## Invariants

- **Un seul motif de nettoyage, où qu'il tourne.** Deux détacheurs indépendants,
  c'est ainsi qu'un marqueur finit dans une ligne de base : le filtre de flux et
  le nettoyeur de contenu lisent les mêmes regex.
- **Un marqueur malformé est nettoyé quand même.** Rendre le texte intact parce
  que les attributs n'ont pas été lus mettrait du balisage brut sous les yeux du
  lecteur. On perd l'annotation, jamais la réponse.
- **Un registre inconnu ne donne AUCUNE annotation**, jamais un défaut. Un
  visage que personne n'a dessiné est pire qu'une absence de réaction.
- **Ce qui est appliqué est publié** (doctrine ADR-184). Un registre que le
  prompt propose mais que le code refuse produit un tour sans visage, en
  silence ; un registre que le code accepte mais que le prompt tait est un
  visage qui n'arrivera jamais. Un test tient les deux listes ensemble, et un
  autre tient la copie TypeScript sur la copie Python.
- **Le registre PLAFONNE ce que l'intensité peut acheter.** Une réponse
  `factual` déclarée à 1,0 reste un visage neutre livré avec conviction, jamais
  une célébration. L'intensité dit avec quelle force le registre est passé ;
  elle ne dit jamais lequel c'était.
- **L'accent tire sur le vocabulaire de gestes EXISTANT.** `nod` est le petit
  bond déjà écrit et déjà testé, pas une cinquième animation. `sparkle` est
  l'exception qui le prouve dans l'autre sens : c'est un accessoire, pas un
  mouvement, et il part sur le canal des accessoires.
- **L'annotation n'est pas persistée.** Une réaction est un événement vivant ;
  un historique rechargé ne doit pas rejouer les visages d'hier.

## Le dessin, au passage

Deux corrections d'art direction accompagnent la décision, toutes deux venues de
l'œil du propriétaire et vérifiées au navigateur.

**La bouche est une FORME PLEINE, pas un trait** — sous deux yeux pleins et
lumineux, un filet est un dessin au trait déguisé en écran de robot. Un seul
élément porte tout le vocabulaire : la hauteur croît avec la courbe et
l'ouverture, le bord supérieur s'aplatit quand la courbe se creuse, et
`scale: 1 -1` retourne le tout pour une moue. C'est pour cela que `mouthArc` est
publié **sans unité** : la feuille de style en a besoin comme hauteur *et* comme
ratio de rayon, et CSS ne sait pas diviser une longueur par une longueur.

Le miroir a coûté une correction trouvée au navigateur, pas à la lecture :
retourner la forme autour de son bord haut fait pousser la moue **vers le haut,
dans le visage**. Mesuré avant correctif, toute bouche retournée mordait sur les
yeux de 3,2 à 7,7 px aux trois tailles quand les autres dégageaient 5,5 à 13,8 ;
après, 4,3 à 13,8 px, positif partout.

**Un demi-cercle plein n'est pas une bouche**, c'est une figure géométrique.
Trois écarts au compas, mesurés sur un `joy` réel : le bord supérieur garde un
plancher de courbure (16,9 %, jamais mathématiquement plat) ; les deux coins bas
sont **différents** et penchent avec la bouche (55,07 % contre 44,93 %) ; et la
forme **s'élargit** en se courbant, si bien qu'un grand sourire fait 2,71 de
rapport largeur/hauteur — large et peu profond, là où la hauteur seule donnait
un bol.

Enfin, **les coins partent avant la courbe** : un vrai sourire commence aux
coins et la courbe les suit. Le mécanisme de départ décalé ne pouvait pas
l'exprimer, parce que les trois canaux vivent dans le même groupe `pose` — un
groupe, un départ. D'où `CHANNEL_LEAD_MS`, un décalage par CANAL qui prime sur
celui du groupe.

## Le marqueur arrive une fois sur huit, et c'est mesuré

Première observation en conditions réelles, seize tours consécutifs de
l'instance de dev : le marqueur de ton **et** le marqueur d'auto-évaluation de
la psyché — deux mécanismes indépendants, le second en production depuis des
mois — ont été émis sur **exactement les deux mêmes tours**. Aucun des deux sur
les quatorze autres, aucun échec d'analyse, aucune fuite du marqueur en base.

Le taux d'émission (~12 %) est donc une propriété **du modèle de réponse**, pas
de cette fonctionnalité : elle réussit précisément quand un mécanisme éprouvé
réussit. Mais un visage qui ne réagit qu'un tour sur huit est un visage cassé,
et la première version de ce repli renvoyait `null` sur la plupart des réponses
— ce qui aurait laissé le visage inerte la majorité du temps.

**Le repli ne renvoie donc plus jamais rien.** Il lit la FORME de la réponse —
longueur, blocs de code, densité de ponctuation, emoji — jamais les mots, si
bien que les six locales se comportent à l'identique (le chinois inclus, par ses
marques pleine chasse). Et il parle **le même vocabulaire** que le marqueur
déclaré : une seule table de registres, une seule courbe d'amplitude, une seule
route. Le marqueur reste le meilleur signal — il connaît le registre que le
modèle a *choisi*, là où la forme ne voit que la façon dont il a été tapé.

Une conséquence assumée : chaque tour terminé gagne un visage. Une réponse
ordinaire est `factual`, c'est-à-dire le visage de repos **joué avec
intention** — pas un sourire que personne n'a demandé, et pas un vide non plus.

## Conséquences

- Le vocabulaire déclaré et le vocabulaire inféré sont le même vocabulaire. Une
  seule table `REGISTER_EXPRESSIONS`, une seule `toneAmplitude` : la voie
  parallèle qui existait (`deriveReaction`, `contentHeuristicExpression`,
  `responseEmphasis`, la table émotion→expression) a été **supprimée**, pas
  gardée en réserve.
- Le prompt coûte ~1 900 caractères par tour de réponse. `EXPRESSIVITY_ENABLED`
  le coupe entièrement : jamais demandé, jamais analysé.
- Le contrat SSE gagne un champ `expressivity` dans les métadonnées `done`, et
  il est déclaré dans **les deux** types de métadonnées — la copie de
  `chat-state.ts` avait déjà pris du retard une fois (ADR-117).
