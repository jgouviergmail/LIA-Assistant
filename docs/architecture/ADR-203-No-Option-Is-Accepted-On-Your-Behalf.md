# ADR-203 : aucune option proposée au téléphone n'est acceptée à votre place

- **Statut** : accepté
- **Date** : 2026-08-04
- **Portée** : `domains/telephony`, débrief d'appel frontend

## Contexte

Le débrief d'un appel passé par LIA proposait des suites sous forme de puces
d'action. Ces puces **envoyaient le message au chat immédiatement**
(`?intent=`, auto-envoyé selon ADR-173). Un appel où l'interlocuteur avait
proposé une date, un lieu ou un supplément tarifaire produisait donc une puce
qui, d'un clic, engageait le lecteur sur cette proposition.

Par ailleurs, l'appel produisait des données structurées
(`StructuredCallData` : date proposée, lieu, coût supplémentaire, décision en
attente) que **le schéma de réponse n'exposait pas**. Ce que l'interlocuteur
avait effectivement proposé restait donc invisible, pendant que la puce qui
l'acceptait, elle, était bien là.

## Décision

**Une puce de débrief PRÉ-REMPLIT, elle n'envoie pas.** Le lien passe par
`chatDraftHref` (`?draft=`, qui pré-remplit sans envoyer — ADR-173) et non plus
`?intent=`. L'icône passe de « envoyer » à « écrire », et le nom accessible dit
ce que le contrôle fait réellement.

**Ce que l'interlocuteur a proposé est publié.**
`TelephonyCallSummary.structured_data` expose la donnée structurée que le
domaine produisait déjà. Le composant `CallDecisions` l'affiche **avant** le
débrief : date proposée, lieu, surcoût, décision en attente. Le lecteur voit
l'offre avant de voir les suites possibles.

**Chaque suite reste un brouillon ou une approbation distincte.** Créer un
rappel, prendre un engagement, planifier une rencontre : chacune ouvre le flux
correspondant avec son propre point de validation. Aucun chemin ne transforme
« l'interlocuteur a proposé X » en « vous avez accepté X ».

## Conséquences

Le débrief devient plus long d'un bloc et d'un clic. C'est le prix exact de la
règle : une action qui engage de l'argent ou du temps ne part pas d'un survol.

## Références

- ADR-173 — `?intent=` est auto-envoyé, `?draft=` pré-remplit
