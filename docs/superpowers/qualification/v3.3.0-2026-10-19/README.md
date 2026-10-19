# Qualification locale de v3.3.0 — 19 octobre 2026

Ce dossier consigne les vérifications préalables à la publication. La CI du
commit, puis la qualification d'installation jetable liée aux digests candidats,
restent obligatoires avant la promotion ; les verdicts distants sont consultables
dans [les workflows du dépôt](https://github.com/jgouviergmail/LIA-Assistant/actions).

## Périmètre consolidé

Recherche des comptes rendus, copies de capacités entre pairs, qualifications
consultatives email/agenda et Position avant les lieux dans tous les formats.
Le complément Word/PDF a été annulé : les en-têtes et pieds de page existaient.
Les fichiers staged de configuration et d'outillage média sont également relus.
Les identités d'opérateur restent privées et les modèles sont configurés par
leurs slots, sans réintroduire les anciennes familles d'environnement inutilisées.

## Résultats exécutés

| Contrôle | Résultat local |
|---|---|
| Couverture unitaire backend | 44 669 réussis, 31 skips sous Windows, 9 désélectionnés ; 79,27 %, seuil maintenu à 78 % |
| Agents | 1 101 réussis, 36 désélectionnés |
| Couverture frontend | 13 231 réussis dans 1 075 fichiers ; tous les seuils globaux et ciblés passent |
| Navigateurs et axe | 649 réussis ; le seul skip concerne le sink HMR DEV, absent de cette construction de production |
| Intégrations impactées | 172 réussies : peers, réunions, skills et configuration LLM, avec PostgreSQL jetable |
| Reproduction de l'ordre fautif des skills | Deux tests isolés passent ; après leur producteur, deux échecs reproduits ; après correction du nettoyage, 36 tests voisins passent |
| Installateur | 243 réussis, 6 skips POSIX sous Windows ; MyPy strict sur 30 fichiers |
| Installation et publication | 24 scénarios Compose valides, 79 tests d'artefacts réussis, 91 contrats backend réussis et 3 skips POSIX ; la garde « défauts → Settings » passe |
| Déploiement et alertes | Assertions shell sans échec, 172 tests Pester réussis ; promtool valide les règles et leurs scénarios |
| Média staged | Typage et 44 tests Node réussis ; 8 tests Python hermétiques réussis ; aucune génération payante supplémentaire |
| Inventaire final | 50 770 tests backend collectés et 13 231 tests frontend : 64 001 au total, arrondis à 64 000+ sur les surfaces publiques |

`task ci:fast` est exécuté intégralement avec succès, y compris les contrats
d'installation et la garde « défauts → Settings ». Le premier passage
d'intégration global a identifié la pollution de fixture décrite ci-dessous ;
il n'est pas présenté comme vert. Les intégrations impactées sont rejouées sur une
nouvelle base après correction. La CI complète du commit est le verdict global
requis avant le tag.

La première CI distante a ensuite révélé 126 échecs d'intégration : 125 venaient
du champ UI `shared_origin` transmis à la projection MCP fermée ; le dernier
masquait la même incompatibilité pour les plugins derrière l'ancien décompte
de requêtes. Les deux échecs sont reproduits localement avant correction, ainsi
que quatre nouveaux tests unitaires avec provenance absente ou renseignée.
Après exclusion explicite de ce champ UI, les 15 tests unitaires de contrat et
165 intégrations MCP/plugins/skills/provenance passent. Les schémas restent
fermés, les contrôles d'autorisation et les instantanés gardent leur portée.
La provenance des plugins est lue par une requête groupée supplémentaire,
vérifiée avec 1, 3 et 12 plugins ; aucun N+1 n'est introduit. Un nouveau verdict
CI complet reste obligatoire avant le tag.

## Revue adversariale et contre-vérifications

| Frontière | Vérification et correction |
|---|---|
| JEV | Les 23 usages passent par le contrat commun ; 138 cas de transport réel simulé couvrent simple/lot/mixte Choice-Noul, quota, atomicité, erreur payée et absence de reprise. Les trois corpus natifs finaux passent leurs critères, sans baisser les seuils. Voir [le dossier natif](../jev-classification-2026-10-19/README.md). |
| Preuve reproductible | La garde des octets figés échoue après conversion des fins de ligne ; la règle Git conserve les octets d'origine, vérifiés dans l'index et l'archive Linux. Les empreintes et rapports ne sont pas réécrits. |
| État et métriques | Le modèle de l'analyse est capturé avec son opération, plutôt que relu après un changement à chaud. Les annotations utilisent les contrats existants, sans nouvelle clé LangGraph ni dérivation de permission. |
| Isolation des tests | Le test d'export d'une skill système commitait une ligne sans propriétaire ; le nettoyage des comptes ne pouvait pas la retirer. Une fixture à clôture garantie supprime uniquement sa propre ligne. Les assertions métier restent identiques. |
| Sondes de santé CI | `pg_isready` sans identité rapporte un succès tout en générant un faux FATAL pour le rôle root ; la reproduction utilise seulement PostgreSQL jetable. Chaque sonde CI nomme désormais son utilisateur et sa base déclarés, sans créer de rôle supplémentaire. |
| Navigateur | Chromium tente un RPC natif d'autoremplissage au montage du champ de recherche. Le proxy le refuse toujours ; seule sa reconnaissance dans le relevé des sondes natives change. Le contrôle séparé des requêtes émises par la page reste inchangé. |
| Secrets et installation | Les données Maps sont un couple optionnel privé, exclu de l'état public, des journaux et du bootstrap LLM. Les 23 fichiers d'environnement examinés conservent leurs autres valeurs ; les deux archives SOPS sont vérifiées après déchiffrement en mémoire. |
| Scan pré-push | Quatre fixtures fictives de refus de credentials sont signalées dans leur commit et son merge : huit empreintes historiques exactes sont documentées, sans exemption de chemin ni réécriture d'historique. Les lignes actuelles sont marquées individuellement. Le scanner accepte ces fixtures mais refuse un nouveau canari non marqué ; les 29 tests de refus passent. |
| Publication média | Les fichiers d'auteur et leurs licences/provenances sont relus. La prévisualisation utilise une origine configurable ; ses fichiers locaux sont exclus des images de production. Les médias déjà publiés ne sont pas remplacés. |
| Présentation | Six langues, 496 questions FAQ, guides et cartes vivantes synchronisés. Les présentations restent des explications d'usages et de conception. Les cartes FAQ sont raccourcies et leurs plafonds agrégés resserrés dans cinq langues. |

## Coûts, dépendances et limites explicites

Le relevé des campagnes JEV et du service totalise **0,025937 EUR**, sous le
plafond autorisé de 0,05 EUR. Aucun mail ni rendez-vous réel n'est lu pour ces
corpus. Les concentrations du modèle ne sont pas des taux d'exactitude : les
170 observations finales sont une qualification bornée, pas une garantie de
détection de fraude ou d'exhaustivité sur toute entrée future.

`pip-audit` ne trouve aucune vulnérabilité connue. L'audit frontend garde
l'exception `GHSA-vfj7-8cjw-p6xm` déjà déclarée dans le dépôt ; aucune exclusion
supplémentaire n'est ajoutée. `braces` est absent du graphe de production et du
standalone Linux examiné. La veille des dépendances ne laisse aucun nouveau
constat sans décision ; ses acceptations existantes restent explicites.

La carte interactive nécessite une clé navigateur restreinte et un Cloud map ID
valide. Sans configuration complète, Position conserve la liste des lieux ; le
chargement de tuiles Google et sa facturation réelle ne sont pas déduits des
tests hermétiques. L'activation des usages JEV dépend des réglages administrateur.

## Auto-évaluation

Le périmètre implémenté est confronté aux sources, aux tests et aux simulations
décrits ici ; les limites de modèle, de configuration et de plateforme sont
nommées. Les seuils de qualité ne sont pas abaissés, les factures d'échec restent
comptées et les garde-fous d'autorisation demeurent indépendants du modèle.
Cette preuve permet la qualification du candidat par le parcours de release
existant ; elle ne constitue ni une certification de déploiement ni une
promesse d'absence universelle de défaut.
