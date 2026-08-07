# ADR-218 : une protection qu'aucun test ne recalcule finit par protéger le passé

**Statut**: ✅ IMPLEMENTED (2026-08-06)
**Date**: 2026-08-06
**Contexte programme**: démonstrateur public libre (lot 6/8)

## Contexte

Les lots 1 à 5 ont posé les protections du démonstrateur : plafond de dépense
(ADR-216), comptes visiteurs éphémères, capacités administrables (ADR-217),
liste blanche à l'entrée réseau, interrupteur du lien public. Chacune a été
livrée avec ses tests.

Ces tests avaient tous la même forme : **ils épinglaient ce que le code
faisait le jour de la livraison**. La liste blanche est comparée à une liste
attendue écrite à la main. Les chemins sensibles sont énumérés à la main. Les
familles de coût sont additionnées depuis un tuple écrit à la main.

Une liste écrite à la main ne décrit pas le système : elle décrit ce que son
auteur savait du système. Le lot 6 a construit les gardes qui **recalculent**
la protection à partir de la réalité — les routes réellement montées, les
champs réellement publiés — et les confrontent à une décision écrite.

Les trois gardes ont trouvé trois failles. Aucune n'aurait été trouvée par les
tests existants, qui étaient verts.

## Décision

Toute promesse du démonstrateur est **recalculée depuis la source de vérité**
et confrontée à une classification exhaustive. Une nouveauté non classée fait
rougir la CI ; elle n'est jamais absorbée par un défaut silencieux.

### 1. Le plafond voit chaque euro (`instance_budget.py`)

`_COST_FIELDS` additionne les familles de coût, `_EXCLUDED_COST_FIELDS` porte
celles qu'on refuse de compter **avec la raison écrite**. La garde lit par AST
les clés `*_cost_eur` que `TrackingContext.get_summary` publie réellement, et
exige que chacune soit dans l'un des deux ensembles.

**Faille trouvée** : `tts_cost_eur` était publié dans le résumé de run, passé
à `record_run_summary`… et absent de la somme. La synthèse vocale était
facturée au propriétaire sans jamais compter contre le plafond de 1 €/jour.
Le STT, lui, ne prenait même pas la route : `record_remote_stt` possède sa
propre session et écrivait uniquement dans `user_statistics`.

Sur un démonstrateur public où la voix est une capacité activable, le plafond
était aveugle à ce qu'un visiteur essaie en premier.

### 2. La surface publique est une liste de routes, pas de préfixes

`test_demo_instance_exposed_routes.py` énumère les routes que l'API monte
vraiment, calcule celles que le bord transmettrait — **en modélisant l'ordre
d'évaluation de Caddy**, refus avant liste blanche — et compare à
`EXPECTED_EXPOSED_ROUTES`, gelée après revue route par route (53 routes).

Une liste de préfixes est ce qui permet à une surface de grandir sans que
personne ne décide : il suffit de monter un point d'entrée sous un préfixe
déjà ouvert.

**Faille trouvée** : `GET /auth/google/login` et `/auth/google/callback`
étaient publics. Le lot 2 a rendu les CGU obligatoires **sur le chemin
d'inscription** ; `_find_or_create_google_user` crée le compte directement
depuis les informations du fournisseur. Un visiteur arrivant par là
n'acceptait rien — et le document qui lui apprend que tout est effacé chaque
nuit est précisément celui qu'il ne voyait jamais. En prime, son identité
Google réelle atterrissait sur une instance publique, aux frais du client
OAuth du propriétaire.

Fermé en trois couches : le bord (`path_regexp`, avant la liste blanche), la
dépendance de routeur (`forbid_federated_signin_in_demo`), et l'interface —
`/auth/features` publie `federated_signin_enabled` et `OAuthButtons` ne
dessine rien quand l'instance ne l'offre pas. Un bouton qui répond 404 est
pire que pas de bouton.

**Imprécision trouvée** : `/metrics` ne vit pas sous `/api`, il tombait donc
dans le repli web et répondait 404 *par accident* — jusqu'au jour où le front
servirait une route attrape-tout. Refusé explicitement.

### 3. Le routeur des connecteurs est classé en entier

Chaque route est soit une liaison (refusée en mode démo), soit classée dans
`READ_ONLY_ROUTES` **avec la raison** de sa présence. Le census marche sur le
routeur réel, dans les deux sens : non classée → rouge, classée mais démontée
→ rouge.

**Faille trouvée** : le garde du lot 2 ne connaissait que `authorize` et
`callback`. Le routeur expose aussi `/apple/activate` (« tests credentials,
then creates connectors » : le mot de passe d'application iCloud du visiteur),
`/api-key/activate`, `/api-key/{id}/rotate`, `/philips-hue/pair`, `/discover`,
`/test`. Onze chemins qui lient un identifiant réel, dont aucun n'était gardé.

La classification reconnaît désormais un segment de liaison **n'importe où**
dans le chemin — `/philips-hue/activate/local` ne finit pas par `activate` —
en comparant des segments entiers, jamais des sous-chaînes, pour que
`/connectors/authorized-apps` continue de fonctionner.

Ce census a aussi montré qu'un test historique protégeait
`/connectors/categories`, une route que le routeur n'a jamais montée.

### 4. Un module, une doctrine

`connectors/demo_guard.py` est devenu `core/demo_mode.py` : les deux refus
(liaison de connecteur, connexion fédérée) relèvent de la même règle — rien
qui attache une identité réelle à un compte jetable. Le garde vivait dans le
domaine des connecteurs, il ne pouvait donc voir que `/connectors`. C'est la
raison structurelle pour laquelle la faille n°2 a survécu au lot 2.

## Conséquences

**Positives**

- Trois failles fermées, dont deux avec un impact financier ou de vie privée
  direct sur une instance publique.
- Une nouvelle route, une nouvelle famille de coût ou un nouveau connecteur
  ne peuvent plus élargir la surface sans une décision écrite en revue.
- Les gardes ont été vérifiées à l'envers : chacune a été mise en défaut
  volontairement (famille de coût ajoutée, préfixe ouvert au bord) et a rougi.
- Comportement du bord prouvé contre un vrai Caddy, pas seulement lu :
  `/auth/google/login` → 404, `/auth/login` → transmis, `/metrics` → 404.

**Coûts assumés**

- `EXPECTED_EXPOSED_ROUTES` demande une mise à jour quand la surface change.
  C'est l'objectif : le coût est la revue, et la revue est le produit.
- L'élargissement des segments de liaison (`test`, `discover`…) ne s'applique
  qu'au routeur des connecteurs et qu'en mode démo ; hors démo, aucun effet.

## Alternatives écartées

- **Épingler plus de chemins sensibles à la main** : c'est ce qui existait.
  Une liste à la main ne connaît que les routes qu'on lui a apprises.
- **Tout interdire au bord sauf une liste de chemins exacts** : la surface
  bouge à chaque évolution du produit ; le démonstrateur serait cassé en
  silence à chaque fois. La garde préfère faire rougir la CI que casser le
  visiteur.
- **Compter la voix dans un second compteur dédié** : deux compteurs, deux
  vérités. Le plafond est unique, donc la somme est unique.

## Liens

- ADR-216 (plafond de dépense d'instance), ADR-217 (capacités administrables)
- ADR-085 (assert de complétude de registre), ADR-151 (la CI orchestre)
- `apps/api/src/core/demo_mode.py`, `apps/api/src/domains/usage_limits/instance_budget.py`
- `apps/api/tests/unit/test_demo_instance_exposed_routes.py`,
  `apps/api/tests/unit/domains/usage_limits/test_instance_budget_cost_coverage.py`,
  `apps/api/tests/unit/domains/auth/test_demo_federated_signin_guard.py`
