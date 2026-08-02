# Programme Relations / Pairs / 360° — dossier de reprise

**Date** : 2026-08-01
**Statut** : **IMPLÉMENTÉ** — voir ADR-193. Ce dossier reste l'historique de
l'enquête ; la décision et son état final sont dans
`docs/architecture/ADR-193-Read-Capabilities-And-Merged-Identity.md`.
**Nature** : dossier de passation entre sessions. Ce n'est ni un ADR, ni un changelog.

---

## 0. Ce que la mise en œuvre a corrigé dans cette analyse

Quatre affirmations de ce dossier se sont révélées fausses à la mesure, et
trois défauts qu'il ne voyait pas ont été trouvés. Elles sont conservées
ci-dessous **telles quelles** (l'enquête a de la valeur), mais lisez d'abord :

| Ce que disait ce dossier | Ce que la mesure a montré |
|---|---|
| « Tout bascule sur `router_medium_confidence` » (§5) | **Faux** : ce seuil n'est qu'un `logger.warning` ; tous les paliers ≥ low routent pareil. La bascule est la variance du planificateur. |
| « Le planificateur a pris le seul outil de son domaine primaire » (§5.1) | **Juste sur le fond, faux sur le mécanisme** : ce n'est pas le filtrage du catalogue (7 outils dont le 360° étaient présents) mais le **prompt**, qui annonce `Primary domain: telephony`. |
| « Enregistrer le schéma pour que le validateur cesse de s'abstenir » (P0-3) | **Action inerte** : `_validate_against_reference_examples` valide AVANT d'atteindre le schéma. Le manifeste est la seule autorité — il doit dire vrai. |
| Lot 5, constat 2 : « ne le reconnaît pas → doublon » | Le doublon ne se produit pas (`[:cap]` final) ; le vrai symptôme est la **perte** de l'adresse du pair. |
| §7-Q3 « d'autres manifestes ? » | **Oui, pluriel** : `total` était faux dans 13 déclarations sur 14. |
| *(absent du dossier)* | La résolution conversationnelle des contacts était **structurellement morte** (les 5 `reference_fields` valaient None). |
| *(absent du dossier)* | `place_phone_call_tool` était rattaché au domaine **`places`** — la règle de couverture se déclenchait à tort sur toute demande d'appel. |
| *(absent du dossier)* | Rattacher les 3 outils à `contact` via `serves_domains` **évince 6 outils de mutation** du catalogue (mesuré). D'où la variante retenue : chacun dans son propre domaine.

Trois autres défauts, trouvés par les gardes une fois le code écrit — c'est
leur rôle, et ils valent d'être notés parce qu'aucun n'était visible en lisant
le code de la fonctionnalité :

| Garde | Ce qu'elle a attrapé |
|---|---|
| `test_user_data_map_guard` | `relation_aliases` n'était pas classée dans la carte RGPD : la table aurait survécu à la suppression du compte, et manqué à l'export. |
| `test_no_infra_info_guard` | Le **nom réel et le numéro** d'une personne servaient de fixtures dans un dépôt open source. Anonymisés partout (y compris là où la garde ne regardait pas : elle ne scanne que les fichiers *suivis*, donc les nouveaux tests lui échappaient). |
| `test_cc_ratchet_guard` | Le repli d'extrait de mail faisait franchir CC 15 à `normalize_graph_message`. Extrait en `_build_snippet` plutôt que compensé par un relèvement de plafond. |

Et une mesure que le programme n'avait pas demandée mais que le test des
cibles tactiles a rendue possible en devenant vert pour la première fois : sur
un écran de 390 px, **six contrôles** étaient sous le plancher de 44 px, dont
la croix « réduire le compagnon » (16 px, `opacity-0` sans survol — donc
**invisible et pourtant cliquable** au doigt) et son point de restauration
(12 px). Voir §10.

Enfin, une **relecture ligne à ligne** du code écrit (pas seulement l'exécution
des tests) a sorti treize défauts que les suites vertes ne voyaient pas — c'est
le propre d'une revue : les tests confirment ce qu'on a pensé à tester, et
deux des gardes censées protéger ne protégeaient rien. Voir §11.

---

## 1. Comment reprendre

**Première action de la nouvelle session** — ne rien coder avant :

1. Lire ce document en entier.
2. Lire `CLAUDE.md` (racine) et `apps/web/CLAUDE.md`.
3. Vérifier l'état du dépôt (§8) : un correctif non commité occupe l'arbre de travail.
4. Choisir un lot avec l'utilisateur. **Ne jamais implémenter sans feu vert explicite**
   (`CLAUDE.md` → « Present findings and wait for approval »).

**Contraintes de session, permanentes** :

- Inline uniquement, **aucun sous-agent**, aucun workflow.
- Aucune action git (commit, push, checkout) sans demande explicite de l'utilisateur.
- Jamais de `--no-verify`. Tout avertissement rencontré est corrigé, même hors périmètre.
- Toute affirmation porte une preuve `fichier:ligne` ou une sortie de commande.
- Validation par conteneurs de développement, jamais par serveur local.

---

## 2. Origine

L'utilisateur a posé quatre questions (A/B/C/D) sur le CRM Relations et les pairs :

- **A** — inclure le contenu des mails dans la fiche ; utiliser l'adresse du pair et
  toutes les adresses du contact pour retrouver mails et rendez-vous.
- **B** — « de quand date mon dernier appel à ma femme » ne fonctionne pas ; idem pour
  les autres blocs de la fiche relation (mails et rendez-vous semblent marcher).
- **C** — existe-t-il un enrichissement automatique de contexte sur une personne
  mentionnée dans le chat et identifiée comme pair ?
- **D** — créer un pair, rapprocher automatiquement des doublons, ou à défaut fusionner.

Décisions d'arbitrage déjà prises par l'utilisateur :

| Sujet | Décision |
|---|---|
| Granularité des outils de lecture | **Un outil par bloc** |
| Contenu des mails | **Extrait court, plafonné, configurable** |
| Fusion des doublons | **Manuelle**, pas de proposition automatique |
| Adresses | **Ne pas créer de doublon** entre adresse du pair et adresses du contact |
| Enrichissement (C) | Clé d'activation + **sources locales seulement** : engagements, appels, messages relayés. **Pas les souvenirs** (déjà injectés nativement) |

---

## 3. Ce qui est mesuré — preuves

Tout ce tableau a été vérifié dans le code ou dans les journaux de production.

| Constat | Preuve |
|---|---|
| Aucun outil ne lit l'historique d'appels, les engagements ou les messages relayés | Liste exhaustive des fonctions `*_tool` du dépôt ; `person_tools.py` n'en expose qu'une, `telephony_tools.py` n'expose que `place_phone_call_tool` |
| `get_person_overview_tool` est le seul accès à ces données | `apps/api/src/domains/agents/tools/person_tools.py` |
| Il est rattaché à `contact_agent` et sert aussi `peer` | `apps/api/src/domains/agents/google_contacts/person_overview_manifest.py` |
| `ToolFilter` ne fait **aucune** expansion de `related_domains` | `apps/api/src/domains/agents/analysis/query_intelligence.py` (`from_intelligence` recopie `intelligence.domains`) |
| Mais l'analyseur, lui, **étend** les domaines par types sémantiques | `apps/api/src/domains/agents/services/query_analyzer_service.py` (`_expand_domains_for_semantic_types`) |
| Un `serves_domains` inconnu fait échouer le démarrage | `apps/api/src/domains/agents/registry/agent_registry.py` |
| Les agrégats CRM sont exacts (`GROUP BY` sur l'ensemble, pas sur une page) | `apps/api/src/domains/telephony/repository.py`, `apps/api/src/domains/open_loops/repository.py` |
| La portée 360° est stockée par utilisateur et relue côté serveur | `apps/api/src/domains/relations/overview_scope.py`, `apps/api/src/domains/relations/service.py` |
| Un seul lieu plie l'identité | `_spellings_for` dans `apps/api/src/domains/relations/service.py` |
| Les favoris portent une contrainte d'unicité `(user_id, name_key)` | `apps/api/src/domains/relations/models.py` |
| La déduplication pair ↔ fiche existe déjà | `apps/api/src/domains/relations/providers/service.py` (`_match_addresses`) |
| Mais `_addresses_of` ne plie **rien** avant de plafonner | `apps/api/src/domains/relations/providers/service.py` |
| La recherche inverse de numéro existe déjà | `_search_contacts_with_phones` dans `apps/api/src/domains/agents/tools/telephony_tools.py` |
| Les souvenirs sont déjà injectés par pertinence sémantique | `apps/api/src/domains/agents/middleware/memory_injection.py`, appelé par `apps/api/src/domains/agents/services/response_context.py` |

---

## 4. Ce qui est **rétracté** — ne pas refaire ces erreurs

### 4.1 « `['telephony']` rend le 360° inatteignable » — FAUX

Mesure initiale : catalogue filtré sur `['telephony']` → 2 outils, 360° absent.
**Cette combinaison n'arrive jamais en production** quand la question nomme une
personne : l'analyseur ajoute `contact` par expansion sémantique
(`has_person_reference: true`, raison « contact provides person_name for referenced
entity »).

Conclusion tirée d'un état inexistant. Le 360° **est** atteignable.

### 4.2 « La description du domaine `telephony` bloque le routage » — NON VÉRIFIÉ

Le domaine se décrit comme « NOT for … reading past call history »
(`apps/api/src/domains/agents/registry/domain_taxonomy.py`) et l'analyseur route bien
sur ces descriptions. Mais **la mesure montre qu'il route quand même vers `telephony`**
pour une question d'historique. La description est trompeuse ; rien ne prouve qu'elle
nuise. **Ne pas la modifier sans preuve.**

### 4.3 « Trois outils de lecture réparent le défaut B » — REQUALIFIÉ

Ils ne réparent pas ce qui est cassé (§5.1 donne la vraie cause). Ils restent
justifiés, mais par un argument différent et mesuré : voir P1 au §6.

---

## 5. Les défauts trouvés en production

Deux requêtes consécutives, même utilisateur, même journée, **même routage** :

| Formulation | Confiance | Plan | Résultat |
|---|---|---|---|
| « de quand date mon dernier appel à ma femme ? » | 0.90 | 1 étape → `get_person_overview_tool` | ✅ 1624 ms |
| « c'était quand date mon dernier appel à ma femme ? » | 0.70 | 2 étapes → **appel téléphonique** | ❌ |

Domaines identiques dans les deux cas : LLM `['telephony']`, puis expansion `+contact`.
Tout bascule sur un seuil de confiance (`router_medium_confidence`).

### 5.1 D1 — une question de lecture produit un plan d'appel téléphonique

Plan construit pour la requête en échec :

- `step_1` = `get_contacts_tool` — résoudre « ma femme » — succès, 175 ms
- `step_2` = **`place_phone_call_tool`**, `objective` = « Rappeler ma femme pour
  vérifier la date de notre dernier appel »

L'utilisateur demandait **quand** ; le plan était de **téléphoner pour le demander**.
Seul l'échec de la référence (§5.2) l'a arrêté. Le HITL aurait exigé un clic — aucun
appel ne serait parti seul — mais une question de lecture qui débouche sur
« confirmez-vous cet appel ? » est une rupture de confiance.

**Le mécanisme est structurel.** La sélection sémantique classait pourtant
`get_person_overview_tool` **premier** (0.561) devant `place_phone_call_tool` (0.412).
Mais le domaine primaire est `telephony`, et `telephony` n'offre qu'**une seule
capacité : passer un appel**. Le planificateur a pris le seul outil de son domaine
primaire.

### 5.2 D2 — le manifeste publie un chemin que l'outil ne produit pas

```
Failed to resolve $steps.step_1.contacts[0].name:
path 'contacts[0].name' not found in step result. Error: 'name'
```

Or `apps/api/src/domains/agents/google_contacts/catalogue_manifests.py` publie
littéralement `contacts[0].name` dans `reference_examples`, et déclare `name` dans
`reference_fields`.

**Le planificateur a lu le contrat, l'a suivi, et a échoué pour cela.** C'est la
doctrine ADR-184 vue dans l'autre sens : ce qui est publié doit être ce qui est
produit. Un exemple de référence est une promesse.

### 5.3 D3 — les deux garde-fous se sont tus

- `reference_validation_no_schema` : « No schema registered for tool
  'get_contacts_tool' - skipping validation ». Le validateur bâti exactement pour ce
  cas s'abstient faute de schéma enregistré.
- `semantic_validation_skipped`, raison `well_formed_cross_domain_mutation`, puis
  `is_valid: true, issue_count: 0, confidence: 1.0` sur le plan qui allait téléphoner
  par erreur.

Deux gardes, deux silences, sur le même plan.

---

## 6. Plan d'implémentation

Ordre recommandé. Chaque lot est indépendant sauf mention contraire.

### P0 — D2 + D3 : le contrat de référence et les gardes muettes

**Pourquoi d'abord** : touche **tout plan multi-étapes**, pas seulement cette requête.
C'est le défaut le plus large et le moins visible.

**À faire** :

1. Mesurer d'abord la forme réelle du résultat de `get_contacts_tool` — dans quelles
   conditions `contacts[0].name` existe ou non. **Une seule occurrence mesurée ;
   ne pas généraliser sans une deuxième.**
2. Réconcilier le manifeste et la production : soit l'outil produit `name`, soit le
   manifeste cesse de le promettre. Le sens de la correction dépend de l'étape 1.
3. ~~Enregistrer le schéma de sortie pour que `reference_validator` cesse de
   s'abstenir.~~ **TRANCHÉ AUTREMENT — ADR-194 (2026-08-02).** Mesure faite : le
   validateur n'a jamais rien rejeté depuis le premier commit (0 erreur sur 254
   références ; en production 28 tentatives, 0 succès sur 30 jours), et **le
   réparer coûtait plus cher que le supprimer** — 63 chemins légitimes rejetés
   sur 112 pour le bras manifeste, 13 sur 35 pour le bras schéma, dont
   `contacts[0].name` lui-même. Le sous-système est supprimé ; la garde qui tient
   le contrat est `test_manifest_reference_examples_truthful`, en CI.
4. ~~Chercher les autres manifestes dans le même cas.~~ **FAIT — le défaut était
   bien pluriel** : les trois outils météo publiaient 7 chemins de référence faux
   sur 7 (plus 10 `outputs` faux), `list_labels_tool` déclarait un champ produit
   seulement sur appel filtré. Couverture de la garde portée de 6 à 11 outils ;
   ce qui reste non couvert est nommé dans l'ADR.

**Non-régression** : un plan valide aujourd'hui doit rester valide. Le validateur
devient plus strict — vérifier qu'il ne rejette pas des références légitimes.

### P1 — D1 : donner une capacité de lecture à la téléphonie

**Pourquoi** : tant que `telephony` ne sait que téléphoner, une question sur les
appels a vocation à devenir un appel.

**À faire** : trois outils de lecture, un par bloc (décision utilisateur) —
appels, engagements, messages relayés.

- Implémentation interne **unique** partagée par les trois, et **une seule**
  résolution d'identité, pour que l'outil interrogé et la fiche ne divergent jamais.
- Réutiliser les agrégats existants (§3), qui rendent déjà des comptes exacts.
- Rattachement : domaine `contact`, avec `serves_domains` étendu (`telephony` pour
  les appels, `task` pour les engagements, `peer` pour les messages).
- Obligations : `@track_tool_metrics` **et** `@rate_limit`, `ToolResponse` /
  `ToolErrorModel`, manifeste avec bornes publiées (ADR-184), assert de complétude
  au démarrage, i18n 6 langues, **aucun nom de personne au niveau INFO**.

**Risque à mesurer** : le catalogue s'élargit d'un outil sur trois domaines. C'est
l'effet qui a cassé la production le 2026-07-30. Mesurer avant/après.

**Vérification d'acceptation** : rejouer les deux formulations du §5 et vérifier
qu'aucune ne produit un plan d'appel.

### P2 — Lot 2 : la recherche inverse du numéro

**Constat** : `_search_contacts_with_phones` existe déjà et interroge les contacts
avec `fields=["names", "phoneNumbers"]`. Le seul manque est le court-circuit en tête
de `_resolve_callee` (`apps/api/src/domains/agents/tools/telephony_tools.py`) : un
numéro brut devient son propre `callee_display`, d'où les doublons de relations
constatés par l'utilisateur (`0612345678` et `alice vernier` = la même personne).

**Conception** : lever le court-circuit, chercher le contact, puis **vérifier**
obligatoirement que le candidat porte réellement ce numéro, comparé sous forme
normalisée.

**Piège identifié** : `_person_first_phone` ne lit que `phones[0]`. Vérifier contre
le premier numéro seul rejetterait un contact dont le numéro correspondant est le
deuxième — **faux négatif**. La vérification doit parcourir **tous** les numéros.

**Cas limites** : aucun candidat → garder le numéro (comportement actuel) ; plusieurs
candidats → garder le numéro, ne pas deviner ; erreur ou lenteur du fournisseur →
garder le numéro, l'appel n'est **jamais** bloqué par la recherche ; contact sans nom
→ garder le numéro.

**Non-régression structurelle** : seul le **nom affiché** change. Le numéro composé
reste celui fourni par l'utilisateur. Aucun appel ne peut partir vers quelqu'un
d'autre.

### P2 — Lot 4 : l'extrait de mail

**Précondition — défaut préexistant à corriger d'abord.** Chez Microsoft,
`search_emails` demande `bodyPreview`
(`apps/api/src/domains/connectors/clients/microsoft_outlook_client.py`) mais le
normalisateur fabrique l'extrait depuis `msg["body"]["content"]`
(`apps/api/src/domains/connectors/clients/normalizers/microsoft_email_normalizer.py`),
champ que `$select` n'a jamais demandé. Résultat : **extrait vide sur tout résultat
de recherche Outlook**. Sans ce correctif, la fonctionnalité naît morte pour ces
utilisateurs et la cause serait mal attribuée.

**Plafond réel** : Google récupère les messages en `format=metadata` et n'extrait le
corps que pour `format=full`
(`apps/api/src/domains/connectors/clients/google_gmail_client.py`). Donc **l'extrait
est gratuit chez les trois fournisseurs ; le corps complet coûte un appel par
message**. La décision utilisateur (« extrait court ») tombe exactement sur ce qui
est gratuit.

**À faire** : correction Microsoft (repli sur `bodyPreview`), puis étendre
`ExchangedEmail` (`apps/api/src/domains/relations/providers/schemas.py`), borne
configurable **et publiée**, affichage fiche + charge 360°.

**Cas limites** : message sans corps → extrait absent, jamais une ligne vide ; HTML
seul → déjà réduit en texte par le normalisateur ; **contenu au niveau INFO
interdit**.

### P2 — Lot 5 : les adresses, sans doublon

**Constat** : la déduplication pair ↔ fiche existe. Deux trous restent dans
`apps/api/src/domains/relations/providers/service.py` :

1. `_addresses_of` ne plie **rien** : une fiche portant `Jean@x.com` et `jean@x.com`
   consomme deux des trois créneaux pour une seule boîte, et paie six recherches de
   courrier pour une adresse.
2. La comparaison pair ↔ fiche se fait contre la liste **déjà plafonnée** : une fiche
   à cinq adresses dont la cinquième est celle du pair ne le reconnaît pas.

**Conception** : plier l'ensemble complet, dédoublonner sur `fold_email`, **puis**
plafonner, en réservant un créneau au pair **uniquement s'il n'y figure pas**. Sans
doublon par construction ; ferme aussi le gaspillage intra-fiche.

**Dépendance à dire** : l'adresse du pair n'est disponible que s'il a activé
`peer_email_visible`.

### P2 — Lot 3 : fusion manuelle des relations

**Rappel** : une « relation » CRM est **dérivée**, pas stockée — une ligne par
orthographe distincte. Le seul état persisté est le favori.

**Conception** : table d'alias (clé pliée → clé canonique), **réversible**, intégrée
**dans** `_spellings_for` et non à côté. ADR-185 impose une seule autorité sur
l'identité ; un alias posé à côté en créerait une seconde.

**Cas limites** : chaînes A→B→C ; annulation ; **collision de favoris** (contrainte
`uq_relation_favorites_user_name` — fusionner deux relations toutes deux en favori
viole l'unicité) ; relation fusionnée devenant ensuite un pair ; fusions concurrentes.

### P2 — Lot 6 : enrichissement d'un pair mentionné

**Constat** : aujourd'hui, seule une **correction de routage** existe
(`apply_peer_domain_correction` dans
`apps/api/src/domains/agents/services/analysis/peer_directory.py` ajoute le domaine
`peer`). **Aucune donnée n'est injectée.**

**Conception** : sources locales seulement — engagements, appels, messages relayés.
Pas les souvenirs (déjà injectés par pertinence sémantique). Portée =
`scope.sections ∩ {open_loops, calls, peer_messages}` : un décochage sur la fiche
reste souverain. Clé d'activation, sur le modèle de
`RESPONSE_CONTEXT_PREFETCH_ENABLED`.

**Point d'insertion** : détection déjà présente dans `query_analyzer_service.py` ;
les données iraient dans `ResponseContextBundle`
(`apps/api/src/domains/agents/services/response_context.py`), le prélecteur conçu
pour les lectures d'E/S ne dépendant que du message.

**Obligation** : passer par le budget existant
`relations_provider_rate_limit_calls` (`apps/api/src/core/config/relations.py`), ne
pas le contourner.

---

## 7. Questions ouvertes — à mesurer, pas à deviner

1. Dans quelles conditions exactes `contacts[0].name` est-il absent du résultat de
   `get_contacts_tool` ? Une seule occurrence mesurée.
2. Le choix de `place_phone_call_tool` se reproduit-il systématiquement sur un plan à
   deux étapes ancré sur `telephony` ? Deux reproductions suffiraient.
3. D'autres manifestes publient-ils des exemples de référence sans schéma enregistré ?
4. Le défaut B initial (« tous les blocs de la fiche relation ne marchent pas ») est-il
   entièrement expliqué par D1/D2, ou reste-t-il une cause distincte ? Les journaux du
   test initial ont été perdus au redémarrage du conteneur le 2026-08-01 à 13:24 UTC.

**Note sur les journaux de production** : le conteneur est `lia-api-prod` (et non
`lia-api`). La rétention est courte — un redémarrage efface tout. Capturer les traces
**avant** de redéployer.

---

## 8. État du dépôt à la reprise

- **Un correctif non commité occupe l'arbre de travail** : ADR-192 (les liens
  profonds du chat sont de vraies navigations), ~36 fichiers. L'utilisateur a
  contesté l'ampleur (13 sites d'appel → 13 fichiers de tests) et **l'arbitrage de
  portée n'est pas tranché**. Ne rien commiter, ne rien annuler sans décision.
- ~~**`task test:backend:unit:fast` n'a jamais rendu de compte**~~ — **levé** :
  la suite complète rend désormais **15 722 tests verts** (7 min 49), et la
  commande CI verbatim avec couverture **15 719 verts / 66,09 %**.
- ~~**Un test e2e rouge préexistant**~~ — **levé**, voir §10.

---

## 10. Cibles tactiles — ce que le test rouge cachait

Le test « every control on a phone screen is big enough to hit » n'avait
**jamais été vert**, si bien qu'il n'avait jamais rien protégé. Pire : il
échouait sur sa **première** assertion (l'aperçu), donc les deux suivantes — la
fiche 360°, le cœur de son périmètre — n'étaient jamais évaluées. Un test rouge
depuis toujours ne mesure pas ce qu'il annonce ; il masque ce qu'il n'atteint
pas.

En le rendant vert par étapes, chaque assertion débloquée en a révélé une
nouvelle :

| Contrôle | Avant | Correction |
|---|---|---|
| Sélecteur de langue | 39 × 44 | `min-w-11` — sous `xl` l'étiquette tombe à un seul drapeau, la hauteur était bonne et la **largeur** non |
| Compagnon (ouvrir le chat) | 40 × 40 | Boîte 44, anneau et ombre déplacés sur un span interne : **rendu inchangé** |
| Compagnon (réduire) | 16 × 16 | Boîte 44 s'étendant **à l'opposé** de l'avatar + visible sans survol |
| Compagnon (restaurer) | 12 × 12 | Boîte 44 ancrée au même coin, le point ne bouge pas d'un pixel |
| 3 actions rapides de la fiche | 147/87/170 × **30** | `min-h-11` — assez larges pour paraître cliquables, trop courtes pour être atteintes |

Le cas du bouton « réduire » mérite d'être retenu : il était `opacity-0` hors
survol, donc sur un écran tactile **invisible et pourtant cliquable**.
Agrandir sa zone sans le rendre visible aurait agrandi le piège — un doigt
visant l'avatar aurait réduit le compagnon sans prévenir. La taille et la
visibilité devaient être corrigées **ensemble**, ou pas du tout.

Le test a aussi été étendu à l'**état réduit**, qu'aucun parcours n'atteignait :
c'est là que vivait le point de 12 px, sous le plancher AA de 24 px, et il
paraissait couvert parce qu'il n'était jamais visité.

---

## 11. Ce que la revue de code a trouvé (après suites vertes)

Toutes les suites étaient vertes quand cette relecture a commencé. Les treize
défauts ci-dessous ont été trouvés en LISANT le code, puis reproduits par un
test qui échouait avant correction. Le classement est par gravité réelle.

| # | Défaut | Pourquoi les tests ne le voyaient pas |
|---|---|---|
| 1 | `plan_writes_without_write_intent` promettait dans sa docstring que l'absence de verdict ne déclenche rien, et faisait l'inverse (`.get(..., False)`). Un payload sans le champ aurait **renvoyé au planificateur toute demande d'action légitime**. | Tous les tests fournissaient le champ. |
| 2 | Un `limit` non numérique (`"beaucoup"`) plantait l'outil : le clamp s'exécutait **hors** du `try` qui transforme les échecs en erreur honnête. | Les tests passaient des entiers — or un modèle remplit ce champ depuis de la prose. |
| 3 | `error=str(exc)` dans un log de production : une erreur SQLAlchemy sérialise sa requête **et ses paramètres liés**, ici des noms et des adresses. Seul log du domaine à le faire. | Aucun test n'assertait la forme d'un log d'échec. |
| 4 | L'index composite `(user_id, canonical_key)` existait dans la migration mais **pas dans le modèle** : le prochain `--autogenerate` aurait proposé de le supprimer. | `db:migrate:replay-check` ne tournait pas encore ; il l'a confirmé (plus trois commentaires divergents). |
| 5 | `IdentityResolver.from_pairs` acceptait une cible vide : `papa -> ""` aurait plié une vraie relation dans l'**identité vide**, avec toutes les autres lignes corrompues. | Le writer refuse les noms blancs — mais une ligne corrompue ne passe pas par lui. |
| 6 | Le compteur de blocs injectés lisait `sections.count("###")` : dépendant du **libellé d'un fichier de prompt**, et faussé par un message relayé contenant `###`. | Une métrique n'a pas d'oracle tant qu'on ne la lit pas. |
| 7 | `_SECTION_BUILDERS` sans assertion de complétude : ajouter une section sans son constructeur levait un `KeyError` que le `except` de l'enrichissement **avale**, désactivant la fonctionnalité en silence. | Le registre était complet ce jour-là. |
| 8 | Les trois descriptions de manifeste portaient des exemples **en français**, seules parmi 27 fichiers de manifestes — biaisant le catalogue lu par le modèle vers une seule langue. | Aucune garde ne lit la langue des manifestes. |
| 9 | `AGENT_TELEPHONY` défini **deux fois** en littéral au lieu d'être centralisé ; le payload d'un outil se lisait via l'ordre d'insertion d'un dict (`next(iter(...))`), calculé deux fois. | Fonctionnellement corrects — jusqu'à la première clé ajoutée en tête. |

Une **seconde relecture**, portant cette fois sur l'ensemble de l'index git
(ADR-192 compris), en a sorti quatre de plus — dont deux gardes qui ne
gardaient pas :

| # | Défaut | Preuve |
|---|---|---|
| 10 | La garde `chat_deep_link` répondait **OK** sur trois violations réelles : l'appel multiligne (la forme que Prettier produit, donc celle de tous les sites existants), l'href passé par une variable, et `router.replace`. Elle lisait **ligne par ligne** une regex mono-ligne. | Fichier-sonde : 3 violations, 0 détection. Après réécriture (fichier entier, `push|replace`, variables suivies) : 3/3, et aucun faux positif sur le vrai code. |
| 11 | `test_manifest_reference_examples_truthful` ne couvrait que **6 manifestes sur les 56** qui publient des `reference_examples`, via une liste blanche figée et **rien ne signalait l'écart**. Les 50 autres pouvaient mentir comme `contacts[0].name` mentait. | Mesuré : 81 manifestes, 56 avec exemples, 6 couverts. |
| 12 | Et ils mentaient : **six chemins publiés** par trois outils Hue n'existent pas dans le résultat (`name`, `is_on`, `brightness`, `children` à la racine, alors que l'exécution les met dans `hues[]`/`rooms[]`/`scenes[]` — et appelle le dernier `children_count`). Un planificateur les suivant aurait produit `$steps.step_1.name` et serait mort exactement comme le cas contacts. | Vérifié contre le `structured_data` réel de chaque outil, puis corrigé, puis verrouillé par une garde de cohérence portant sur **tout** le catalogue. |
| 13 | `_inject_peer_context` promettait sa « propre frontière d'échec » et convertissait l'UUID **en dehors** — un `langgraph_user_id` malformé remontait par `asyncio.gather` et coûtait à l'utilisateur **toute sa réponse**, pour un enrichissement. Exactement la forme du défaut n°2, à l'autre bout du code. | Test rouge avant correction ; l'injection voisine (`_inject_psyche`) enveloppait déjà son propre `UUID(...)`. |

À quoi s'ajoute un durcissement sans défaut constaté : `openChatDeepLink`
n'acceptait qu'une convention. Il vérifie désormais que l'href est un chemin
interne — `//host` et `/\host` compris, que `startsWith('/')` laisse passer —
selon la même doctrine que `safe-navigation.ts` : garder la primitive plutôt
que compter sur chaque appelant.

Deux corrections ont été **annulées après mesure**, et c'est aussi un résultat :
remonter deux imports locaux préexistants cassait 13 tests d'une autre session
(ils patchent au module source, ce que seul un import à l'appel résout), pour un
gain nul — le détecteur de cycles compte 25 dans les deux configurations. Les
imports sont restés locaux, avec un commentaire disant enfin la vraie raison.

---

## 12. Références internes

- `CLAUDE.md` — règles systémiques, portes de qualité, points d'intégration runtime
- `docs/architecture/ADR_INDEX.md` — 193 décisions ; ADR-184 (limites publiées),
  ADR-185 (comptes exacts, pliage d'identité unique), ADR-190 (portée du 360°),
  ADR-191 (capacités atteignables), ADR-192 (liens profonds)
- `docs/guides/GUIDE_TOOL_CREATION.md` — création d'outils
- `docs/guides/GUIDE_TESTING.md` — stratégie de test et ratchets
