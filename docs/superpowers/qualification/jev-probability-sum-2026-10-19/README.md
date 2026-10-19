# JEV — cause et correction de `probability_sum`

Suite : la [qualification sémantique et l'audit de tous les usages](../jev-classification-2026-10-19/README.md)
traitent la réserve de couverture décrite ci-dessous, avec de nouveaux prompts
email et des mesures conservées. Ce document garde les résultats du diagnostic
initial ; ils ne sont pas réécrits rétroactivement.

Correction réalisée directement dans `D:\Developpement\LIA`, sur `main`, sans
worktree supplémentaire. Les changements de configuration et les fichiers déjà
indexés des autres chantiers sont conservés.

## Cause reproduite

Un premier rejeu isolé a réussi ; le défaut est intermittent. Le parcours suivant
des lots email fictifs a reproduit le rejet. La distribution fautive contient
`unknown=0.05`, `personal=0.93`, `phishing_scam=0.01`, les autres valeurs nulles :
sa somme est `0.99`. Voir les [valeurs reçues](diagnostic-scan.json) et la
[fixture de régression du lot entier](../../../../apps/api/tests/fixtures/jev_choice_rounded_batch.json).

Le [contrat HTTP officiel](https://api.typesafe.ai/openapi.json) décrit une somme
**approximativement** égale à un. Les valeurs observées sont quantifiées au
centième, avec parfois un résidu de représentation flottante. Le transport LIA
imposait une tolérance plus petite ; la politique email/agenda répétait le
contrôle avec une autre tolérance encore plus petite. Le rejet d'une réponse
invalidait le lot entier et interrompait le protocole de recette.

Le défaut établi est donc une incompatibilité de validation numérique dans
l'intégration LIA. Le message ne prouvait pas que JEV avait choisi une mauvaise
catégorie ni que le fournisseur était indisponible.

## Correction et revue adversariale

Le [transport natif](../../../../apps/api/src/infrastructure/llm/typesafe_client.py)
et la [politique de publication](../../../../apps/api/src/domains/agents/services/qualification/policy.py)
partagent le même validateur et le même calcul conservateur de concentration.

- La précision fine conserve sa tolérance antérieure. Pour les valeurs compatibles
  avec la quantification observée, la somme doit pouvoir provenir d'une vraie
  distribution : les intervalles d'arrondi par option sont bornés aux probabilités
  possibles. Un simple élargissement uniforme de la tolérance ne suffit pas.
- Les valeurs reçues restent intactes. Une masse manquante n'augmente pas le
  gagnant ; un excès de masse abaisse sa concentration. La confiance appliquée ne
  dépasse jamais celle reçue. Les seuils métier, prompts et réponses attendues ne
  sont pas modifiés.
- Les schémas, ensembles d'options/questions, choix gagnants, valeurs non finies,
  masses impossibles et facturation des erreurs gardent leurs contrôles. Une
  vraie réponse malformée invalide toujours le lot.
- La revue à froid a éprouvé aussi une masse nulle au nombre maximal d'options :
  un test rouge supplémentaire a conduit à son refus explicite.
- Le contrat numérique est versionné dans l'empreinte du cache de classification.
  Les anciennes décisions ne sont pas réutilisées sous la nouvelle règle ; le
  format public des annotations et l'état LangGraph restent identiques.

Les [tests de régression](../../../../apps/api/tests/unit/infrastructure/llm/test_choice_probability_precision.py)
éprouvent le lot reçu entier, les sommes déficitaires/excédentaires, les résidus
flottants, les erreurs impossibles, les ex æquo, les frontières de confiance,
l'absence de promotion d'une alerte phishing et la révision du cache. Les contrats
natifs, quotas, annulations et écritures de consommation sont également vérifiés
par les suites backend existantes et les hooks habituels de livraison.

## Recette réelle et limite restante

Le [rejeu complet](holdout-complete.json) exécute les 70 cas fictifs et termine ses
10 appels natifs avec `success`, sans arrêt de protocole. Le corpus, ses réponses
attendues, les prompts et les seuils restent inchangés. Ce rejeu est une preuve de
non-régression du protocole ; ce n'est pas une nouvelle étude indépendante de
justesse en population.

La [vérification du service complet](service-cache.json) utilise cinq observations
fictives : deux lectures renvoient les mêmes annotations et produisent une seule
écriture de consommation native, la seconde lecture utilisant Redis.

**Le score de qualité sémantique reste en échec.** Aucun faux label n'est accepté
sur ces cas ; la couverture reste sous les objectifs figés pour les catégories
professionnelle et spam et pour la priorité critique. JEV choisit `critical`
sur les six exemples correspondants, mais leur concentration reste sous le seuil
d'alerte, donc aucun badge critique n'est publié. La couverture phishing observée
est de huit cas sur huit ; cela ne démontre pas une fiabilité générale.
Les seuils n'ont pas été abaissés pour faire passer ce score.

L'erreur technique `probability_sum` est corrigée. La réserve restante porte sur
la couverture sémantique et doit être présentée ainsi. Les interrupteurs DEV
préexistants sont actifs et conservés ; leur activation ne constitue pas une
qualification du modèle. Le message du script de recette indique maintenant que
les réglages sont laissés inchangés, sans supposer qu'ils étaient désactivés.

## Coût et intégrité

Les [journaux de consommation relus en base](accounting.json) recensent les quatre
essais historiques et les quatre essais de diagnostic/vérification : 53 écritures
natives et huit synthèses, toutes attribuées au compte autorisé. Leur coût cumulé
arrondi par appel est de **0,013901 EUR**, dans le plafond autorisé.

Le [premier diagnostic](diagnostic-single.json), le parcours qui reproduit le
rejet et le rejeu complet sont conservés séparément. Le total du diagnostic de
parcours inclut le premier diagnostic ; le budget du rejeu standard est réduit
du coût des diagnostics, qui sont ensuite ajoutés au bilan global. Aucun essai
précédent n'est effacé ni présenté comme réussi rétroactivement.

Aucun email ou agenda réel n'est lu. Aucun credential, modèle, préférence JEV ou
configuration d'environnement n'est modifié. Aucune dépendance, variable d'env,
reprise automatique ou génération de secours n'est ajoutée. Aucun push ni
déploiement de production n'est effectué.
