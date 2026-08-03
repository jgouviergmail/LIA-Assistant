# ADR-199 : suggérer seulement ce qu'on sait déjà, et montrer les résultats avant les volumes

**Statut**: ✅ IMPLEMENTED (2026-08-03)
**Date**: 2026-08-03
**Décideurs**: Équipe LIA
**Complète**: [ADR-178](ADR-178-Product-Value-Dashboard.md) (vérité produit), [ADR-185](ADR-185-Exact-CRM-Counts-And-Readable-Relayed-Messages.md) (un chiffre montré est une affirmation)

## Contexte

Deux surfaces disaient la mauvaise chose.

**Le chat vide** proposait trois exemples génériques. Il aurait pu prouver que
LIA connaît déjà la journée — mais la page chat ignore délibérément l'état des
connecteurs, et le docstring de `lib/chat-starters` dit pourquoi : proposer
« montre mes derniers mails » à un compte sans connecteur mail transforme la
toute première interaction en échec.

**Le tableau de bord** ouvrait sur les messages, les tokens, les requêtes Google
et le coût. Des chiffres d'administration, pas le récit de ce à quoi le produit
sert.

## Décision

### Une suggestion n'existe que si la preuve existe déjà

Le nouvel endpoint lit **uniquement le cache du briefing**, jamais une
récupération. Un cache froid répond une liste vide et le client retombe sur ses
amorces génériques : le cas ordinaire, pas un cas dégradé.

Récupérer ici aurait corrigé la connaissance et cassé trois autres choses —
réveiller les connecteurs, dépenser des quotas, et rendre l'ouverture d'un chat
vide plus lente qu'aujourd'hui.

**Aucun LLM** : une poignée de conditions sur des données déjà calculées.

**Trois entrées, toujours.** Les suggestions ancrées passent devant et les
génériques **complètent** : n'en montrer qu'une appauvrirait l'écran d'accueil,
en montrer six transformerait une invitation en menu.

**Le statut de la section fait foi** : `ERROR` n'est pas une preuve (le
connecteur peut être tombé), et `HIDDEN` signifie que le lecteur a retiré cette
carte — une suggestion ne doit pas passer outre.

### Les résultats devant, la consommation derrière

Quatre chiffres, chacun un **agrégat exact** sur son propre ensemble :
résultats utiles confirmés, actions réussies, routines réussies, engagements
clôturés. Seules les lignes `validated` comptent : `produced` signifie
« présenté » (E3), pas « confirmé utile ».

**Deux candidats ont été écartés plutôt qu'estimés.** « Temps gagné » n'a
aucune source dans ce système. « Documents effectivement utilisés » non plus :
les extraits injectés sont calculés à l'exécution et envoyés au seul panneau de
débogage — rien ne les persiste, et *injecté* n'est de toute façon pas *utilisé*.

**Une instance qui ne mesure pas le dit.** Afficher quatre zéros là où
l'enregistrement des résultats est désactivé affirmerait au lecteur qu'il n'a
rien accompli — une phrase différente de « rien n'est compté », et fausse.

Les volumes restent, repliés dans un `<details>` natif : la sémantique de
divulgation, le comportement clavier et l'annonce ouvert/fermé viennent de la
plateforme.

## Conséquences

`BriefingService.read_cached_cards` devient **publique** : « ce qu'on sait déjà,
sans rien payer » est une capacité du domaine, pas un détail interne. Sans elle,
l'appelant irait lire les clés Redis lui-même ou appellerait `build_cards`, qui
réveille tous les connecteurs.

**Le cycle de facturation est le même** que celui des tuiles de consommation :
deux blocs d'un même écran ne doivent jamais décrire des périodes différentes.

**Aucun titre d'événement ni sujet d'engagement dans les journaux** : ce sont
les mots de l'utilisateur, et seul le compte est tracé.

## Alternatives écartées

**Récupérer l'agenda et les mails à l'ouverture du chat.** Rend les suggestions
toujours disponibles, au prix exact que `chat-starters` refuse : la latence, le
quota, et un écran d'accueil qui dépend d'un connecteur.

**Deviner les suggestions côté client** à partir des seules données de la page
(espaces, compétences). Honnête mais pauvre : ni la journée, ni les mails, ni
les engagements n'y sont.

**Estimer « documents utilisés » depuis l'injection RAG.** Le chiffre existerait
et serait faux : un document injecté que le modèle ignore n'a pas été utilisé.
