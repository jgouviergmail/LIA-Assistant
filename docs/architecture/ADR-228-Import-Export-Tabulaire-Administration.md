# ADR-228: Import/export tabulaire des administrations — le classeur est le formulaire

**Statut**: ✅ IMPLEMENTED (2026-08-19)
**Date**: 2026-08-19
**Décideurs**: Propriétaire (arbitrages sur périmètre, sémantique de suppression, portée du socle) + Équipe LIA

## Contexte

Le catalogue LLM compte **124 modèles**, chacun portant 24 caractéristiques et un
tarif à quatre dimensions. Il s'administrait ligne par ligne, dans une grille
web, à raison d'une boîte de dialogue par modèle. Mettre à jour une grille
tarifaire complète — ce que fait un fournisseur deux ou trois fois par an —
demandait 124 allers-retours.

Le propriétaire a demandé un export Excel structuré, éditable hors ligne, et un
réimport en masse ; avec un socle générique, déclinable aux autres écrans
d'administration.

### Ce que l'instruction du chantier a révélé avant d'écrire une ligne de code

L'analyse préalable a mis au jour **cinq défauts préexistants**, dont deux de
facturation en production. Ils ne sont pas des dommages collatéraux : sans eux,
l'export n'a pas d'objet.

1. **« Le » tarif actif d'un modèle n'existait pas.** Aucune contrainte
   `UNIQUE(model_id) WHERE is_active`, et quatre chemins de lecture qui
   sélectionnaient sans `ORDER BY`. Mesuré en base de développement : 96 des 114
   modèles actifs portaient deux ou trois tarifs actifs. Sonde d'exécution sur
   `gemini-2.5-flash-preview-tts`, même base, même instant : le cache retournait
   0,30/2,50 et `AsyncPricingService` 0,50/10,00 — **un facteur 4** ; sur
   `scribe_v2`, les deux chemins divergeaient sur l'**unité de facturation**
   elle-même (heure d'audio contre million de jetons).

   Ce n'était pas de l'historisation : celle-ci fonctionne et n'utilise même pas
   `is_active` — `get_model_price_at_date` trie par `effective_from` et ignore le
   drapeau. Les volumes le confirmaient : 248 lignes dont **206 actives** et
   seulement 42 historiques.

2. **Le cache de tarifs était rempli par nom brut et lu par nom normalisé.**
   Mesuré **en production** : `gpt-4o-2024-05-13` possède son propre tarif
   5,00/15,00 mais était facturé 2,50/10,00 — celui de `gpt-4o`. Sous-facturation
   d'un facteur 2 en entrée, 1,5 en sortie. Les modèles Claude datés, eux, se
   normalisaient vers des noms inexistants : facturés zéro.

3. **Neuf modèles actifs sans tarif actif en production**, facturés zéro en
   silence par un chemin volontairement tolérant aux pannes.

4. **Un prix de cache ne pouvait pas être effacé** : `exclude_none` avalait le
   `None`, sur un champ NULL dans 73 des 206 lignes actives.

5. **`deactivate` n'avait aucun inverse.** Un modèle éteint ne pouvait plus être
   rallumé par l'application.

## Décision

### 1. Un socle générique, un consommateur

`src/infrastructure/tabular_io/` décrit un classeur de façon **déclarative** —
`WorkbookSpec` / `SheetSpec` / `ColumnSpec` — et en dérive les deux sens :
`writer.py` produit le fichier, `reader.py` le relit. Le socle n'importe aucun
domaine.

Le domaine ne fournit qu'une déclaration (`domains/llm/pricing_sheet.py`) et un
applicateur (`pricing_import_service.py`). **Décliner le mécanisme à une autre
administration, c'est écrire une déclaration — pas du code de format.**

### 2. Une migration n'invente jamais un prix

La règle intuitive « garder la ligne au `effective_from` le plus récent » a été
confrontée aux quatre cas divergents réels. Elle est **fausse quatre fois sur
quatre**, la production faisant autorité :

| Modèle | Production | « Plus récente » |
|---|---|---|
| gemini-2.5-flash-preview-tts | 0,30 / 2,50 | 0,50 / 10,00 |
| gemini-2.5-pro-preview-tts | 1,25 / 10,00 | 1,00 / 20,00 |
| scribe_v1 · scribe_v2 | `per_audio_hour` | `per_1m_tokens` |

La migration `6e7f8a9b0c1d` fusionne donc **uniquement** les doublons
strictement identiques — 92 modèles et 2 paires de devises, sans perte
d'information — et **s'arrête en nommant** les divergents. L'arbitrage est
humain, jamais implicite.

### 3. Le fichier dit ce qui EST

Trois colonnes dérivées, en lecture seule, existent parce que la donnée brute
induit en erreur :

- `time_slots_summary` et `time_slots_mode` portent le tarif fenêtré **sur la
  ligne qui porte le prix**. Sans elles, une ligne DeepSeek affichait
  `0,22 / 0,66` — son tarif creux — et se lisait comme un tarif plat, les
  fenêtres vivant sur un autre onglet que personne n'avait de raison d'ouvrir.
  **Ce défaut a été trouvé par le propriétaire sur un export réel.**
- `statut` énonce ce que ferait vraiment l'exécution : aucun tarif actif,
  plusieurs tarifs actifs, ou facturé sous un autre nom.
- `reasoning_shape` garde le fichier auto-descriptif pour les modèles qu'aucun
  gabarit n'exprime.

Le mode de plages exporté vaut toujours l'état réel — `flat` ou `windows` —
jamais `inherit`, qui est une instruction et non un état.

### 4. Rien n'est supprimé implicitement

Une ligne absente du fichier **ne supprime jamais rien** : un filtre Excel
oublié ne peut pas vider un catalogue. Le retrait passe par `is_active = FAUX`,
et le remettre à VRAI réactive — ce qui comble au passage le cul-de-sac de
`deactivate`.

### 5. Un aperçu qui engage

L'import est en deux temps. `dry_run=true` n'écrit rien et renvoie le plan,
champ par champ. L'application **re-dérive le plan** et refuse s'il diffère de
celui qui a été relu : l'aperçu approuvé est l'aperçu écrit. Un verrou optimiste
**par ligne** — empreinte transportée dans une colonne masquée — ne refuse que
les lignes modifiées sous les pieds de l'administrateur ; un collègue touchant
un modèle sans rapport ne fait pas rejeter tout le fichier.

L'import est **intégral ou nul**, et ce qui n'a pas changé n'est pas écrit :
sans cette règle, importer 124 lignes laisserait 124 versions de tarif inutiles.

### 6. La complétude est gardée, pas mémorisée

Une première version du classeur exportait 16 colonnes contre un schéma réel de
24 + 11, et le test de fidélité ne pouvait pas le voir : il comparait une
extraction à elle-même. L'oracle est désormais le **schéma de la base** — toute
colonne métier est exportée ou exclue avec une raison écrite, et une colonne
ajoutée demain rougit la CI. Même doctrine que les asserts de complétude de
registre (ADR-085).

## Conséquences

### Positives

- La grille tarifaire complète s'édite en une fois, avec listes déroulantes,
  notice traduite et validations Excel.
- **Deux défauts de facturation en production corrigés** : le tarif propre d'un
  modèle daté est enfin honoré, et les chemins de lecture sont déterministes.
- Deux capacités manquantes construites : réactivation et effacement explicite.
- Trois factorisations : garde anti-zip-bomb partagée avec l'importeur de
  plugins, `replace_active_rate` partagée entre le router et le planificateur
  (dont le `.first()` était la cause racine des taux dupliqués), et
  `apiEndpointUrl` substituée à deux copies privées côté frontend.

### Négatives / limites assumées

- `provider`, `effective_from` et `effort_values` restent en lecture seule : le
  contrat d'écriture ne sait pas les exprimer. Un changement de fournisseur est
  **signalé**, jamais avalé.
- Une famille de raisonnement inédite ne se crée pas depuis un tableur ; le
  dialogue d'administration reste l'endroit pour cela.
- Seul Microsoft Excel sous Windows a été validé de bout en bout. LibreOffice,
  Google Sheets et Excel pour Mac utilisent des constructions OOXML standard et
  devraient se comporter à l'identique — non mesuré.
- La protection de feuille rend les groupes de colonnes repliables inertes
  (`EnableOutlining=False`, non persistable sans macro) : les 27 colonnes sont
  organisées par blocs colorés et volets figés.

## Pièges mesurés, à ne pas repayer

- `ws.protection.sheet = True` seul émet `insertRows="1" autoFilter="1"`, où `1`
  signifie **bloqué** : la feuille protégée **interdisait d'ajouter un modèle**.
  Chaque option doit être forcée à `False`.
- `showDropDown="1"` **masque** la flèche de liste. Un correctif de bonne foi
  sur ce booléen supprimerait toutes les listes déroulantes.
- `data_only=True` renvoie `None` sur un classeur jamais ouvert par Excel : la
  lecture se fait en `data_only=False` et toute cellule-formule est refusée.
- `max_row` est gonflé par le pré-formatage (500 pour 4 lignes de données) :
  aucun décompte ne peut en être tiré.
- Une chaîne vide écrite revient en `None` : les traiter à part produisait 122
  différences fantômes sur 124 lignes.
- `Decimal` accepte `NaN` et `inf`, qui franchissent le contrôle de minimum
  (toute comparaison avec NaN est fausse) puis cassent le calcul d'échelle —
  une faute de frappe devenait une erreur 500.
- Une clé de regroupement n'est pas une identité : l'onglet des plages horaires
  a N lignes par modèle, et les refuser en doublon rendait **tout export réel**
  irrecevable à la relecture.

## Preuves

Sur le catalogue réel de 124 modèles, via le code de production :

- **Fidélité** : 0 erreur de lecture, 0 écart aller-retour sur les 27 colonnes.
- **Idempotence** : un export intact réimporté produit 124 lignes inchangées et
  **0 tarif réécrit**.
- **Sensibilité** : quatre modifications injectées, quatre détectées et
  correctement classées — aucun faux positif, aucun faux négatif.
- **Cycle complet** : export → 3 éditions → import → ré-export rend exactement
  les 3 éditions ; le second import du même fichier, devenu périmé, est refusé.
- **Excel réel** : ouverture sans réparation, 15 listes déroulantes, exactement
  5 colonnes verrouillées, écriture acceptée sur une cellule éditable et refusée
  sur une colonne calculée.
- **Performance** : 41 Ko, 76 ms de lecture, 110 ms d'écriture — traitement
  synchrone, aucun travail de fond justifié.

## Liens

- Spécification : `docs/superpowers/specs/2026-08-18-tabular-admin-io-design.md`
- Plan : `docs/superpowers/plans/2026-08-18-tabular-admin-io.md`
- Documentation technique : `docs/technical/TABULAR_ADMIN_IO.md`
- ADR-223 (plages horaires UTC), ADR-085 (asserts de complétude), ADR-208
  (barre de section), ADR-207 (altitudes d'action)
