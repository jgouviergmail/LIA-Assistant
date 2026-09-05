# Inaltérabilité des registres — chaîne de hachage (ADR-263, lot 5)

> Arbitrage propriétaire du 2026-09-04 : **chaîne de hachage**.
> Ce document n'argumente pas la conception, il la **déduit de mesures**. Chaque
> décision ci-dessous porte le chiffre qui l'a tranchée, obtenu contre la vraie
> base PostgreSQL du conteneur de développement.

---

## 1. Ce que la mesure a établi

| # | Hypothèse testée | Mesure | Conséquence de conception |
|---|---|---|---|
| F1 | Combien de processus écrivent ? | `WEB_CONCURRENCY=4` | **Aucun état de chaîne en mémoire.** L'ordre doit être établi en base, atomiquement. |
| F2 | Une chaîne SYNCHRONE dans la transaction de claim coûte quoi ? | séquentiel **+0,19 ms (1,12×)** ; **8 claims concurrents du même compte : 12,58 ms/claim contre 0,45 — ×28** | **Rejetée.** C'est exactement la forme du `parallel_executor` : une régression technique sur le chemin de réponse. |
| F3 | Un notaire ASYNCHRONE unique tient-il la charge ? | **12 036 lignes/s**, par lots de 200 | Retenu. Trois ordres de grandeur au-dessus de la charge réelle (100 appels/jour/utilisateur). |
| F4 | Vérifier coûte quoi ? | **50 000 entrées en 0,14 s** en lecture paginée (354 830 entrées/s) ; une rupture au milieu trouvée après 24 999 entrées en **0,04 s** | Vérification à la demande ET périodique abordable, et elle **s'arrête à la rupture** au lieu de parcourir le reste. |
| F11 | Ce que la chaîne COÛTE | **387 octets/entrée** mesuré, index compris (~291 en `bytea`) | Plus que la ligne qu'elle protège (~250 o). À compter dans la jauge de volume, et à dire. |
| F12 | L'encodage proposé était-il sûr ? | **NON** : `sha256("a|b")` collisionne pour deux découpages différents — démontré | Encodage **préfixé par longueur et typé**, plus une colonne `digest_version`. |
| F5 | Le balayage grandit-il avec le registre ? | `LEFT JOIN` **9,93 ms** vs **index partiel 0,64 ms** sur 50 000 lignes | **Index partiel `WHERE notarised_at IS NULL`** : coût en O(en attente), pas en O(registre). |
| F6 | Le **commit tardif** crée-t-il un angle mort ? | passe pendant la transaction ouverte : 0 ; après commit : 1 ; **restant : 0** | Aucun filigrane temporel. L'ensemble « en attente » est défini par `NULL`, qu'un commit tardif rejoint naturellement. |
| F7 | **Deux notaires** simultanés peuvent-ils bifurquer la chaîne ? | 1 passe refusée par `UNIQUE (user_id, seq)` ; séquence contiguë ; 20 entrées / 20 sujets distincts ; 0 restant | La contrainte rend la bifurcation **impossible par construction**, et le perdant refait le travail. |
| F8 | Combien d'états mutent une ligne d'action ? | **4** : `claim` (INSERT), `close` (UPDATE), `refuse` (INSERT), `abandon_stale` (UPDATE) | Une empreinte posée sur la ligne mutable produirait des **faux positifs**. → notarisation **en deux étapes**. |
| F9 | La suppression de conversation touche-t-elle les registres ? | **non** (aucune référence ; la FK ne porte que sur `users`) | Une remise à zéro ne perce jamais la chaîne. |
| F10 | La suppression de compte ? | `ondelete="CASCADE"` sur les deux registres | Une chaîne **par compte** disparaît ENTIÈRE — pas de trou. La tension inaltérabilité / effacement **s'évapore**. |

### La mesure qui décide de tout

F2 est le pivot. Une chaîne écrite dans la transaction de claim est *correcte*
(la séquence mesurée était bien 1→8, contiguë, sans doublon) mais elle
sérialise le seul endroit où le produit est délibérément parallèle. Vingt-huit
fois plus lent sur le chemin qui répond à l'utilisateur n'est pas un compromis
acceptable pour une propriété qui n'a besoin d'être vraie qu'**après coup**.

L'inaltérabilité ne demande pas la simultanéité. Elle demande que ce qui a été
écrit ne puisse pas être changé **sans que cela se voie**.

---

## 2. La conception qui en découle

### 2.1 Un notaire, asynchrone, unique

Un job périodique, **élu leader** (`SchedulerLeaderElector` existe déjà) et
**jitteré** (`jitter_seconds_for` — règle systémique : six jobs à la même
seconde, mesuré 2026-09-01). Il ne fait qu'une chose : prendre les lignes non
notarisées, dans l'ordre, et les ajouter à la chaîne de leur compte.

Le chemin d'écriture des registres **ne change pas d'une ligne**. La propriété
qui rend le portail acceptable — *0,64 µs et zéro session de base sur une
lecture*, épinglée par `test_the_read_path_opens_no_database_session` — reste
intacte par construction, puisque rien n'est ajouté sur ce chemin.

### 2.2 Une chaîne PAR COMPTE

Trois raisons, dans l'ordre de leur poids :

1. **Elle dissout la tension avec l'effacement (F10).** Supprimer un compte
   retire sa chaîne entière : les autres chaînes restent vérifiables, et la
   sienne n'existe plus. Une chaîne globale, elle, garderait des trous
   permanents à chaque suppression — soit on garde des empreintes d'un compte
   effacé, soit la chaîne ne vérifie plus jamais.
2. **Elle borne la contention** au compte, et le notaire étant unique, il n'y
   en a aucune.
3. **Elle rend la preuve exportable** : la chaîne d'un utilisateur part avec
   son archive de compte, complète et vérifiable isolément.

### 2.3 Elle NOTARISE, elle ne recopie pas

Une entrée de chaîne ne contient **aucun contenu** :

```
seq · occurred_at · kind · subject_id · payload_digest · prev_hash · entry_hash
```

`payload_digest` est l'empreinte des colonnes **métier** de la ligne visée ;
`entry_hash = sha256(encodage_canonique(prev_hash, seq, kind, subject_id, payload_digest))`.

Trois conséquences, toutes voulues :

- **387 octets par entrée** (mesuré, index compris ; ~291 avec des empreintes
  en `bytea` plutôt qu'en hexadécimal) — à comparer aux ~250 octets d'une ligne
  de consultation : **la chaîne coûte plus cher que le registre qu'elle
  protège.** C'est un fait à assumer, pas à cacher, et la jauge de volume doit
  la compter séparément ;
- altérer une ligne de registre **contredit** la chaîne sans pouvoir la forger ;
- **supprimer** une ligne de registre laisse son entrée orpheline — donc
  détectable. C'est la propriété que la simulation a confirmée : la chaîne
  restait cohérente *après* l'altération, et c'est la ligne qui était en tort.

### 2.3 bis L'encodage canonique — le défaut que la revue à froid a trouvé

Ma première rédaction écrivait `sha256(prev ‖ seq ‖ kind ‖ subject ‖ digest)`,
et le banc d'essai concaténait avec un `|`. **Démontré, pas supposé :**

```
1. collision par séparateur (deux lignes DIFFÉRENTES, même empreinte) : True
   naive("get_emails", "ok|failed") == naive("get_emails|ok", "failed")
2. str(datetime) est de largeur variable :
   '2026-09-04 17:02:26+00:00'  vs  '2026-09-04 17:02:26.123456+00:00'
```

La première ligne est une **faille de falsifiabilité** : un dispositif censé
rendre l'altération détectable acceptait deux contenus distincts sous la même
empreinte. La seconde est une **fabrique à faux positifs différés** : le jour
où un pilote change sa façon de rendre un horodatage, toutes les chaînes
existantes cessent de vérifier — et ce jour-là, personne ne saura si c'est une
altération ou une mise à jour de bibliothèque.

*(Une troisième crainte s'est révélée infondée : `None` et la chaîne vide ne
collisionnent pas, `str(None)` valant `'None'`. Je la mentionne parce qu'une
inquiétude écartée par la mesure vaut une inquiétude confirmée.)*

**La forme retenue**, vérifiée sur les mêmes cas :

- **préfixage par longueur** — chaque champ est écrit `<len>:<nom>=<len>:<valeur>`,
  ce qui rend toute ambiguïté de découpage impossible ;
- **typage explicite** — `n:` (absent), `t:` (instant), `u:` (identifiant),
  `s:` (texte) — donc `None`, `"None"` et `""` sont trois choses distinctes ;
- **rendu figé par type** — instant en UTC `%Y-%m-%dT%H:%M:%S.%fZ` à largeur
  fixe, identifiant en hexadécimal minuscule, énumération par sa **valeur**
  stockée (jamais son nom de membre) ;
- **clés triées**, pour que l'ordre des colonnes ne fasse pas partie du secret.

Résultat mesuré : `collision: False`, `None != "": True`.

### 2.3 ter Une VERSION d'empreinte, sinon la première évolution casse tout

La table porte `digest_version`. Sans elle, changer un jour la règle
d'encodage — ajouter une colonne, corriger un rendu — invaliderait **toutes**
les chaînes existantes, et l'audit deviendrait un générateur d'alarmes.
Avec elle, la vérification choisit la règle **par la version que l'entrée
déclare** : une évolution est une nouvelle version, jamais une réinterprétation
silencieuse du passé.

### 2.4 Deux étapes, parce qu'il y a quatre transitions (F8)

| Étape | Déclencheur | Empreinte sur |
|---|---|---|
| `effect.claimed` | la ligne existe | l'ensemble **immuable** : id, user, thread, run, source, mode, outil, politique, clé d'idempotence, `args_digest`, libellé, autorité (`approval_kind`/`approval_ref`), `draft_digest`, `claimed_at`, `schema_version`, `catalogue_fingerprint` |
| `effect.settled` | `status != claimed` | l'**issue** : status, `closed_at`, `provider_ref`, `result_digest`, `result_truncated`, `error_code`, `retry_of` |
| `treatment.recorded` | la ligne existe | toutes ses colonnes (elle n'est jamais mutée) |

`refuse` produit les deux étapes d'un coup ; `abandon_stale` déclenche l'étape 2.
**Aucune transition légitime ne peut donc être lue comme une altération** — c'est
la garantie anti-faux-positif, et elle sera testée comme telle.

L'ensemble empreinté est une **liste explicite**, jamais « toutes les colonnes » :
même doctrine que `TechnicalSpec`, avec la même garde « toute colonne du modèle
est classée » — sinon une colonne ajoutée demain casserait toutes les chaînes
existantes le jour de sa migration.

### 2.5 Ce que la chaîne ne prouve pas

À écrire dans l'ADR, parce qu'un dispositif d'audit qui sur-promet est pire
qu'aucun :

- elle prouve qu'une ligne n'a **pas changé depuis sa notarisation** ; elle ne
  prouve pas ce qui s'est passé **avant** ;
- une fenêtre de non-notarisation existe (l'intervalle du notaire) ; elle est
  **mesurée et alertée**, pas passée sous silence ;
- quiconque détient la base **et** le droit d'écrire peut réécrire une ligne
  *et* sa chaîne. La chaîne rend l'altération **détectable par un tiers qui
  détient une empreinte antérieure**, pas impossible. L'ancrage externe (étape
  facultative, hors périmètre) est ce qui fermerait cela.

---

## 3. Vue systémique : où en est l'assistant vis-à-vis de l'article 12

| Exigence art. 12 | Aujourd'hui | Après le lot 5 | Reste |
|---|---|---|---|
| Identifiant de corrélation | `run_id` sur 5 tables + `trace_id` OTel | idem | **objet « décision » manquant** (lot 6) |
| Horodatage absolu UTC | ✅ garde AST | ✅ | — |
| Contexte système | `model_name`, catalogue LLM, `catalogue_fingerprint` | ✅ notarisé | version de prompt et d'index RAG (lot 6) |
| Entrées | message brut ; prompts versionnés | idem | **paramètres d'inférence** (lot 7) |
| Sorties | réponse ; décision métier + `provider_ref` + `result_digest` | ✅ notarisé | score de confiance : **nous n'en produisons pas** — en inventer un serait pire |
| Événements de risque | existants mais dispersés | idem | **flux dédié** (lot 8) |
| Supervision humaine | `approval_kind` + `approval_ref` | ✅ notarisé | — |
| **Inaltérabilité** | ❌ | ✅ **chaîne + vérification** | ancrage externe (hors périmètre) |

---

## 4. Plan d'actions consolidé

### Lot 5 — La chaîne et le notaire *(l'arbitrage rendu)*

| # | Action | Non-régression garantie par |
|---|---|---|
| 5.1 | Table `ledger_chain` (chaîne par compte, `UNIQUE (user_id, seq)`, FK CASCADE) + migration écrite à la main | `db:migrate:replay-check` ; dérive structurelle nulle |
| 5.2 | Colonnes `notarised_at` / `settled_notarised_at` + **index partiels** | F5 : coût O(en attente) |
| 5.3 | `ledger_digest.py` : listes explicites de colonnes + garde « toute colonne classée » | même doctrine que `TechnicalSpec` |
| 5.4 | `notary.py` : une passe = trouver, ordonner, chaîner, marquer — en **une transaction** | F6/F7 : ni angle mort ni bifurcation |
| 5.5 | Job périodique **élu leader + jitteré** | `test_scheduler_jitter` |
| 5.6 | `verify_chain(user_id)` — fonction **pure**, réutilisée par l'endpoint, le job et l'export | une seule implémentation de la vérité |
| 5.7 | Métriques : `lia_ledger_chain_pending`, `lia_ledger_chain_entries`, `lia_ledger_chain_broken` | ratchet de couverture des métriques |
| 5.8 | Alertes `LedgerChainBroken` (critique, sans seuil réglable) et `LedgerNotaryStalled` + runbooks | promtool, cas positif ET négatif sur la même chronologie |
| 5.9 | Déclarations `user_data_map`, `account_deletion_service`, export de compte | F10 : la chaîne part avec le compte |
| 5.10 | Entrée **genèse** par compte, qui DIT que la chaîne commence ici et que l'antérieur n'est pas couvert | honnêteté sur la reprise de l'existant |
| 5.11 | Surfaces : indicateur « scellé » dans les deux journaux ; vérification dans `AdminRegistersSection` | tests front |

### Pourquoi les lots 6 à 9 sont INCLUS — et pourquoi je les avais d'abord écartés à tort

Ma première version reportait le registre de décisions, les paramètres
d'inférence et les événements de risque. Contre-vérification faite, **deux des
raisons implicites étaient fausses et une troisième s'est retournée**.

**Faux — « chaque table ajoutée plus tard laisse une fenêtre non couverte ».**
Une table créée après le notaire naît vide : elle est notarisée dès sa première
ligne. Zéro antériorité non couverte, mieux que les registres existants. Cet
argument, qui *sonne* juste, ne tient pas.

**Faux — « le registre de décisions oblige à recopier les requêtes brutes, ce qui
contredit notre doctrine de confidentialité ».** Mesuré :
`conversation_messages` est déclaré `_PURGED_FULL`, donc de **même durée de vie**
que les registres. Une ligne de décision **pointe** vers le message et son
empreinte le notarise — aucune copie, aucune nouvelle surface de PII, et la
contradiction disparaît.

**Retourné — « rien ne presse ».** Loki retient **168 h**. Les événements de
risque n'existent aujourd'hui que dans des logs et des compteurs agrégés : **ils
sont détruits au bout de sept jours**. Chaque semaine sans la table est une
semaine d'événements auditables perdue pour toujours — alors qu'une table créée
plus tard, elle, ne perd rien. C'est l'inverse de l'ordre que j'avais proposé.

Ce qui reste vrai, et qui devient un **ordre** et non une exclusion : le notaire
doit exister d'abord, pour que les trois tables soient notarisées **dès leur
naissance** plutôt que rattrapées.

### Lot 6 — Registre de DÉCISIONS *(l'objet de corrélation de l'article 12)*

Une ligne par tour, écrite au **même point** que le `treatment_recorder` (une
écriture protégée de plus, pas un nouveau chemin) : `run_id`, horodatages,
modèle + version, versions de prompts, mode d'exécution, décision de routage,
jetons, issue, **pointeurs** vers le message d'entrée, la réponse, les effets et
les consultations du tour. Notarisée dès la première ligne.

### Lot 7 — Paramètres d'inférence

`ReasoningIntent` (ADR-245) a déjà une forme stockée unique ; les drapeaux
d'échantillonnage sont dans la configuration résolue. C'est une copie de champ
sur un chemin déjà instrumenté, pas un appel de plus.

### Lot 8 — Événements de risque en lignes *(le plus urgent des trois)*

Les signaux existent dans huit modules et sont comptés par 87 compteurs — des
agrégats, sans détail par événement. Le lot les rassemble en lignes auditables :
refus du portail, interruption HITL, sortie de budget ReAct, rejet du validateur
sémantique, limite de débit atteinte, classe d'erreur d'outil.

### Lot 9 — Export article 12 unifié

Un JSONL corrélé par `run_id`, moteur `TechnicalSpec` réutilisé, chaque ligne
portant l'empreinte de chaîne qui la couvre — donc **vérifiable hors ligne** par
qui le reçoit.

---

## 4 bis. Documentation *(exigence explicite du propriétaire)*

| Document | Enrichi ou créé | Ce qu'il doit dire |
|---|---|---|
| `ADR-263` | **enrichi** (§12) | la chaîne, le notaire asynchrone, la chaîne par compte, et surtout **ce que la chaîne ne prouve pas** |
| `docs/technical/AI_ACT_TRACEABILITY.md` | **créé** | la table de correspondance article 12 → ce que LIA enregistre, avec les limites assumées (pas de score de confiance, fenêtre de notarisation, pas d'ancrage externe) |
| `docs/runbooks/alerts/LedgerChainBroken.md` | **créé** | que faire quand une chaîne ne vérifie plus — et ce qu'il ne faut **pas** faire (re-notariser pour « réparer ») |
| `docs/runbooks/alerts/LedgerNotaryStalled.md` | **créé** | le notaire à l'arrêt : la fenêtre non couverte s'allonge |
| `docs/technical/DATABASE_SCHEMA.md` | **enrichi** | les quatre nouvelles tables |
| `CLAUDE.md` / `AGENTS.md` | **enrichi** | le pointeur et les invariants (une chaîne par compte ; le notaire n'est jamais sur le chemin d'écriture) |
| `docs/architecture/ADR_INDEX.md` | **enrichi** | l'entrée |
| Guides `how.*.md` (6 langues) | **enrichis** | ce que l'utilisateur peut vérifier lui-même |

---

## 5. Plan de test *(à enrichir pendant l'implémentation, déroulé en revue)*

### A. Intégrité — la chaîne dit vrai

1. Une chaîne fraîche vérifie.
2. Un compte **sans aucune ligne** vérifie (et n'est pas une erreur).
3. Altérer une colonne empreintée d'une ligne → **détecté**.
4. Altérer une colonne **non** empreintée (`notarised_at`) → **non détecté** *(sinon la notarisation se casserait elle-même)*.
5. Supprimer une ligne de registre → entrée orpheline **détectée**.
6. Supprimer une entrée de chaîne → séquence non contiguë **détectée**.
7. Réécrire une entrée de chaîne → `prev_hash` rompu **détecté**.
8. Restaurer une sauvegarde cohérente → vérifie *(la chaîne est autoportante)*.

### B. Anti-faux-positif — les transitions légitimes

9. `claim → close_success` vérifie.
10. `claim → close_failure` vérifie.
11. `refuse` (les deux étapes d'un coup) vérifie.
12. `abandon_stale` vérifie.
13. Un `retry_of` (nouvelle clé dérivée) vérifie.
14. Une colonne **ajoutée au modèle** sans classement → **la garde casse la CI**, pas les chaînes en production.

### C. Concurrence et pannes

15. Commit tardif → rattrapé, aucun restant *(F6, déjà simulé)*.
16. Deux notaires → une passe refusée, séquence contiguë, aucun sujet doublé *(F7, déjà simulé)*.
17. Le notaire meurt en cours de passe → la passe suivante reprend à l'identique (transaction unique).
18. Bascule de leader entre deux passes → idempotent.
19. Base indisponible → le notaire échoue **sans** casser la boucle périodique.

### D. Non-régression — ce qui ne doit pas bouger

20. Le chemin de lecture **n'ouvre toujours aucune session** *(garde existante)*.
21. Le claim ne gagne **aucune** requête *(compteur de requêtes sur le chemin)*.
22. Le vidage des consultations ne gagne aucune requête.
23. Les 402 tests d'effets existants restent verts.
24. `128` outils enregistrés, gardes de boot passées.

### E. Cycle de vie du compte

25. Suppression de compte → chaîne **entièrement** retirée, aucun orphelin.
26. « Tout oublier » → chaîne **intacte** *(F9)*.
27. Export de compte → la chaîne part avec, et **vérifie hors ligne**.

### E bis. Les nouvelles tables *(lots 6 à 8)*

31. Une décision est écrite pour **chaque** tour, y compris un tour qui échoue ou qui est annulé *(même garantie que le `treatment_recorder` : `__aexit__`)*.
32. Une décision **pointe** vers son message d'entrée et ne le recopie pas *(aucune requête brute dupliquée)*.
33. Le pointeur reste valide, ou la suppression du message le met à NULL sans casser la chaîne *(pierre tombale, doctrine ADR-201)*.
34. Un événement de risque est écrit pour chacune des six sources, et **aucune** n'écrit deux fois.
35. Les trois tables sont notarisées **dès leur première ligne** — aucune entrée de genèse « rattrapage » nécessaire.
36. Les paramètres d'inférence enregistrés sont ceux **réellement envoyés**, pas ceux configurés *(un test qui coerce puis compare)*.

### G. Encodage — le défaut trouvé en revue

37. Deux jeux de valeurs distincts ne peuvent pas produire la même empreinte *(le cas de collision démontré, rejoué comme test)*.
38. `None`, `"None"` et `""` donnent trois empreintes différentes.
39. Un instant sans microsecondes et un instant avec produisent des empreintes stables et distinctes *(largeur fixe)*.
40. Une énumération est empreintée par sa **valeur** stockée, jamais par son nom de membre.
41. L'ordre de déclaration des colonnes ne change pas l'empreinte *(clés triées)*.
42. Une entrée d'une `digest_version` antérieure **vérifie toujours** après l'introduction d'une nouvelle version.
43. **Vecteurs figés** : un jeu d'entrées connues et leurs empreintes attendues, en dur dans le test — c'est ce qui transforme une mise à jour de bibliothèque en test rouge plutôt qu'en fausse alerte d'altération en production.

### F. Échelle

28. Balayage à vide sur 50 000 lignes ≤ 1 ms *(F5)*.
29. Vérification paginée à mémoire bornée *(F4 : 50 000 entrées en 0,14 s, arrêt à la rupture)*.
30. Retard du notaire visible en métrique et alerté.

---

## 6. Ce que je demande avant d'implémenter

1. **Granularité de la vérification périodique** : tous les comptes à chaque
   passe (simple, coûteux à grande échelle) ou par rotation (N comptes par
   passe, chaque compte vérifié au moins une fois par jour) ? Je recommande la
   rotation.
2. **Fenêtre de notarisation** : intervalle du notaire. Je recommande **60 s**
   avec jitter — la fenêtre non couverte reste inférieure à la minute et le
   coût à vide est de 0,64 ms.
3. **Reprise de l'existant** : les lignes déjà écrites (1 action, 30
   consultations en dev ; davantage en production) seront notarisées à la
   première passe, précédées d'une entrée de **genèse** qui dit explicitement
   que rien avant elle n'est couvert. Confirmez-vous cette honnêteté plutôt
   qu'un silence qui laisserait croire l'antériorité couverte ?
4. **Taxonomie des événements de risque** : je propose six sources (refus du
   portail, interruption HITL, sortie de budget ReAct, rejet sémantique, limite
   de débit, classe d'erreur d'outil). C'est la seule liste que le lot 8 rend
   difficile à changer après coup, parce qu'elle devient une colonne bornée et
   un libellé traduit. En manque-t-il une à vos yeux ?
