# ADR-166: Ce qui mérite de devenir un centre d'intérêt ou un souvenir

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA
**Amende**: ADR-053 (apprentissage des centres d'intérêt), ADR-131 (déduplication), ADR-164 (couverture des extractions)

## Contexte

Question posée : « le prompt d'extraction des centres d'intérêt est trop
permissif — à chaque sujet mentionné il est ajouté ».

Le prompt livré l'ordonnait explicitement. Sa règle n°1 disait :
*« Thematic curiosity = INTEREST: User wants to LEARN about a subject.
"search for X", "tell me about X" → extract »*. Sa règle n°5 exigeait bien un
« signe d'intérêt authentique », mais sa première entrée était « curiosity » —
que la règle n°1 venait de déclarer satisfaite par toute demande d'information.
Deux règles en conflit, tranchées du côté permissif par celle qui portait des
exemples opérationnels. Le seul garde-fou quantitatif était une **auto-confiance
non calibrée** (plancher 0,6), notée par le modèle qui venait de décider
d'extraire.

### Ce que la production disait

Mesures du 2026-07-27 sur la base de production :

| Constat | Chiffre |
|---|---|
| Intérêts créés en juillet 2026 | 10 |
| **Bloqués par l'utilisateur lui-même** | **7 (70 %)** |
| Bloqués sur les 25 intérêts antérieurs | 0 |
| Doublons « Cycle de l'eau » créés le même jour | 2 |

Les sept rejets sont exactement le symptôme : un schéma demandé une fois, un
morpion, une remarque sur l'avatar de LIA, un écart de capteur météo. Le statut
`blocked` n'est écrit que par `apply_feedback` — aucun automate ne bloque : ces
sept rejets sont des verdicts utilisateur.

### Ce que le rejeu a ajouté

45 fenêtres de conversation **réelles** de production, rejouées à travers
l'ancien prompt avec la configuration LLM de production et les 19 intérêts
actifs réels injectés :

- **16 fenêtres sur 45 (36 %)** déclenchaient une écriture ;
- dont une fenêtre — une simple demande de localisation sur une carte — qui
  proposait **19 suppressions, soit la totalité du profil actif**.

Ce dernier point n'était pas un défaut de sélectivité mais un risque de perte de
données : les suppressions ne portent aucun champ de confiance et ne sont
validées que sur la validité de l'UUID et la propriété.

### Trois défauts structurels indépendants du prompt

1. **La déduplication ne voyait que les intérêts actifs.** Chronologie de
   production du 2026-07-21 : création à 12:51, **blocage par l'utilisateur à
   19:14**, recréation par l'extracteur à **19:39** sous un libellé voisin. La
   similarité cosinus entre les deux libellés est de **0,9821** — très au-dessus
   du seuil de fusion de 0,89. Le blocage était contourné en 25 minutes.
2. **Les intérêts dormants étaient invisibles pour la même raison**, rendant la
   branche de réactivation de `consolidate_on_mention` inatteignable depuis ce
   chemin.
3. **La fenêtre de déduplication était de 20 lignes**, triées par date de
   création décroissante, pour 19 intérêts actifs : une création de plus et les
   plus anciens — donc les mieux établis — sortaient du champ.

## Décision

### 1. Le prompt pose une autre question

Non pas « de quoi parle ce message ? » mais « l'utilisateur a-t-il révélé une
relation **durable** à ce sujet ? ». **Demander est une tâche, pas un goût.**

Une création exige un **fondement nommé** (champ `signal`) parmi quatre, et la
**citation** des mots de l'utilisateur qui le portent (champ `evidence`) :

| Fondement | Exigence | Confiance ancrée |
|---|---|---|
| `stated_passion` | il dit qu'il aime / suit / est passionné | 0,95 |
| `own_practice` | il rapporte le pratiquer lui-même | 0,95 |
| `prior_knowledge` | vocabulaire, opinion défendue, comparaison de praticien | 0,85 |
| `deep_dive` | il a creusé le même sujet ≥ 2 fois dans cet échange | 0,75 |

Six **classes** d'exclusion sont nommées (le sujet d'une demande, une remarque
sur l'assistant, le goût d'un tiers, une chose essayée une fois, les actions
utilitaires, ce que l'assistant a introduit). Le modèle doit reconnaître la
classe, pas l'exemple.

`update` exige **le même fondement** : sans cela, durcir `create` déplace
simplement le bruit vers `update`, qui consolide de la même façon. Ce
déplacement a été mesuré comme nul (0 action sur 45 fenêtres).

### 2. La déduplication voit tous les statuts

`InterestRepository.get_for_dedup` remplace `get_active_for_user` sur ce chemin,
et la décision se prend **par statut** : `blocked` → rien (compté sous
`extraction_action_rejected_total{reason="blocked_interest"}`), `dormant` →
réactivation, `active` → consolidation. Refuser aussi `update` et `delete` sur
un intérêt bloqué : supprimer la ligne **détruirait le blocage** et rouvrirait
le sujet.

La fenêtre passe à 200 (`interest_dedup_scan_limit`), distincte de la liste
montrée au prompt (`interest_dedup_search_limit`, bornée par le budget tokens).

### 3. Un plafond de suppressions

`enforce_delete_cap` (partagé par les deux extracteurs) : au-delà de
`extraction_max_deletes_per_run` (2 par défaut), **toutes** les suppressions du
lot sont écartées et comptées. Un lot qui en propose dix-neuf n'est pas une
intention utilisateur, c'est une génération qui déraille.

Les actions non destructrices du même lot sont **conservées** : elles sont
récupérables et individuellement filtrées ailleurs ; perdre une création
légitime parce que la même réponse contenait des suppressions serait un second
défaut.

### 4. Le plancher de confiance devient opposable

`INTEREST_EXTRACTION_MIN_CONFIDENCE` passe de 0,6 à **0,75** et devient un
`Settings` (`interest_extraction_min_confidence`). Sur huit passes de batterie
et 90 fenêtres rejouées, toute création émise valait 0,75, 0,85 ou 0,95 —
jamais entre les deux : le plancher rend la règle écrite exécutoire sans rien
écarter de ce que le modèle produit réellement.

### 5. Le seuil de fusion reste à 0,89

Re-mesuré sur **16 couples réels** de production (doublons observés, et
« sortie du nouveau prompt » × « ligne existante »). 0,83 et 0,89 sont à
**égalité, 2 erreurs chacun** — mais leurs erreurs diffèrent en nature :

- 0,83 → 0 fusion ratée, **2 fusions abusives** (`android`~`ios` à 0,857 ;
  `Histoire de Caen`~`Histoire de Strasbourg` à 0,890) : destructif,
  irréversible ;
- 0,89 → 2 fusions ratées (variantes « OpenAI », variantes « LangGraph ») : un
  doublon, rattrapable.

Le seuil ne change pas, et la justification est désormais écrite dans la
constante.

## Résultats mesurés

Configuration de production (`deepseek-v4-flash`, température 0,1), 6
répétitions par scénario :

| Batterie | Bruit sur négatifs | Rappel sur positifs |
|---|---|---|
| Intérêts — prompt précédent | 0,50 | 0,75 |
| Intérêts — prompt actuel | **0,00** | **1,00** |
| Intérêts — actuel, **held-out** | **0,00** | **1,00** |
| Mémoire — prompt précédent | 0,167 | 0,75 |
| Mémoire — prompt actuel | **0,00** | **1,00** |

La batterie *held-out* porte les mêmes classes sur des sujets **absents des
prompts** : sans elle, un score parfait ne mesurerait que la capacité à
recopier ses propres exemples.

**Deux modèles, pas un.** Les chiffres ci-dessus valent sur `deepseek-v4-flash`
(configuration de production) et sont reproduits sur `gpt-5.2` — la doctrine ne
dépend donc pas d'un fournisseur. Un cas limite l'illustre : le scénario
`h_pos_optics` (fondement `prior_knowledge`) a été mesuré à 1,00 puis, quelques
heures plus tard, à 0,00 sur `deepseek-v4-flash` — **avec l'ancien comme avec le
nouveau prompt**, quelle que soit la liste d'intérêts existants. Il reste à 1,00
sur `gpt-5.2`. C'est une dérive côté fournisseur, pas une régression du prompt,
et c'est précisément ce qu'un harnais permet de distinguer.

Sur les 45 fenêtres réelles : 16/45 écritures (18 créations, 19 suppressions,
1 mise à jour) avant, **4/45** après (2 créations, 2 mises à jour, **aucune
suppression**).

## Conséquences

- Le harnais `apps/api/scripts/measure_extraction_selectivity.py` devient la
  méthode de re-réglage : toute retouche de ces prompts se mesure avant/après,
  sur les deux batteries.
- `tests/unit/domains/agents/prompts/test_extraction_prompt_doctrine.py`
  verrouille les règles d'admission (jamais la mise en forme : les guards
  normalisent les espaces).
- Le panneau de debug affiche les mêmes candidats de déduplication que le
  runtime — il ne peut plus montrer une décision que le service ne prendrait pas.
- Un faux positif résiduel a été mesuré (« Projet LIA d'assistant IA
  personnel », alors que l'utilisateur a bloqué « Assistant IA personnel (projet
  LIA) ») : similarité 0,9828, donc **supprimé par la décision n°2**. Les deux
  correctifs convergent sur la même racine.

## Alternatives écartées

- **Baisser le seuil de fusion à 0,83** pour rattraper les doublons : mesuré,
  il échange deux fusions ratées contre deux fusions abusives — on préfère un
  doublon visible à une perte silencieuse.
- **Un palier « candidat »** (créer invisible, promouvoir à la deuxième
  mention) : règle proprement l'arbitrage précision/rappel mais suppose
  migration, filtres de statut, logique de sélection et UI — à reconsidérer si
  la mesure montre une perte de rappel, ce qui n'est pas le cas.
- **Rejeter le lot entier** au-dessus du plafond de suppressions : plus simple à
  décrire, mais punit des créations probablement saines.
- **Rendre `signal`/`evidence` opposables côté code** dès maintenant : les deux
  champs sont produits et ignorés par le parseur (`extra="ignore"`), ce qui rend
  le changement déployable sans toucher au code. Les faire respecter (rejeter
  une création sans preuve citée) est un lot ultérieur, mesurable.
- **Baisser la température** : mesuré inerte — les modèles de raisonnement
  utilisés déclarent `supports_temperature = false`.
