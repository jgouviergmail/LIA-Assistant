# ADR-190 : le point 360° lit ce que le lecteur a coché, et la fiche contact ne montre pas quatre champs sur douze

**Statut**: ✅ IMPLEMENTED (2026-08-01)
**Date**: 2026-08-01
**Décideurs**: Équipe LIA
**Complète**: [ADR-188](ADR-188-CRM-Provider-Sections.md) (sections adossées aux providers), [ADR-184](ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md) (une limite appliquée doit être dite), [ADR-141](ADR-141-Active-Knowledge-Layer.md) (outil 360°)

## Contexte

Deux défauts, remontés le même jour, tous deux sur la même fiche relation.

**1. L'outil 360° était catalogué mais absent du registre.** En production
(`docker logs lia-api-prod`, 2026-07-31), un point 360° sur un pair connecté
répond « je n'ai pas réussi à remonter ses interactions récentes ». Les logs
disent exactement ce qui s'est passé : `"tool": "get_person_overview_tool"` puis
`"error": "Tool 'get_person_overview_tool' not found"`. Le planificateur avait
raison — le catalogue annonçait l'outil. C'est `_import_tool_modules` qui ne
chargeait jamais `person_tools` (ni `documents_tools`, ni `automation_tools`) :
trois familles annoncées, zéro enregistrée.

Et même trouvé, l'outil aurait mal répondu : il cherchait le courrier par le
**nom** de la personne et l'agenda par une requête texte. Une recherche de
courrier est appariée contre les en-têtes MIME, `list_events(query=)` n'a
aucune parité entre providers et aucune notion de « cette personne est
participante ».

**2. La fiche contact montrait quatre champs.** Nom, organisation, emails,
téléphones. Le carnet d'adresses en stocke bien davantage — adresses postales,
anniversaire, relations familiales, liens, pseudonyme, note libre. Une fiche
CRM qui montre quatre champs sur douze est une fiche que le lecteur cesse de
croire, et il retourne dans son carnet d'adresses.

**3. La portée du 360° n'était pas choisissable.** Le lecteur voulait pouvoir
dire *ce que* le point 360° consulte : quelles sections, émission ou réception,
participant ou organisateur, combien d'éléments. Or la demande part de la page
sous forme de `?intent=` — **du texte, et rien d'autre**. Laisser le
planificateur déduire la portée d'une phrase ferait de la sélection une
suggestion.

## Décision

### 1. Ce que le catalogue annonce, le registre le tient — vérifié en CI

`_import_tool_modules` importe désormais les trois modules manquants, et une
garde (`test_catalogue_registry_parity.py`) compare l'ensemble des manifestes
annoncés à l'ensemble des outils réellement enregistrés APRÈS import. Un
manifeste sans outil est une promesse que l'exécuteur ne peut pas tenir : le
planificateur choisit bien, et c'est l'utilisateur qui reçoit l'échec.

L'oracle doit lire le registre **après** `_import_tool_modules()`, comme le
fait le boot : le lire avant signalait ~80 faux positifs, puis exactement 5
vrais trous une fois corrigé.

### 2. Le 360° délègue aux services du CRM — par ADRESSE

L'outil n'interroge plus les providers lui-même : il appelle `build_detail` et
`RelationContextService.build`, exactement ce que lit la page Relations. Donc
la même résolution d'identité (les adresses du carnet), le même cache Redis —
un 360° demandé juste après l'ouverture de la fiche ne coûte aucun appel
provider — et **les deux surfaces répondent la même chose**.

La recherche par nom survit comme **repli de dernier recours**, et seulement
quand le statut est `NO_ADDRESS` : sans adresse au carnet, une réponse vide
serait pire qu'une réponse imprécise. Ses résultats sont **marqués**
(`*_matched_by_name`) pour que l'assistant puisse dire qu'ils sont peut-être
incomplets au lieu de les présenter comme un fait. Un connecteur absent ou en
erreur, lui, n'est **jamais** rejoué par nom : réessayer autrement une question
qu'on n'a pas pu poser, c'est fabriquer une réponse.

### 3. La portée est écrite AVANT que le chat s'ouvre

Nouvelle colonne `users.relation_overview_scope` (JSONB, NULL = défauts) et
deux routes `GET/PUT /relations/overview-scope`. Le bouton « Lancer le point
360° » **attend** l'écriture puis navigue. C'est ce qui transforme la
sélection en garantie : le `?intent=` ne porte que de la prose, l'outil lit la
colonne. Naviguer d'abord ferait courir l'écriture contre l'outil qui la lit,
et le lecteur recevrait sa portée précédente sans que rien ne le dise.

Le même objet sert de **préremplissage** la fois suivante — « ce que je veux
d'habitude ». Une valeur stockée, deux usages, plutôt qu'une préférence plus
une charge utile par requête.

Trois conséquences que la forme impose :

- **Chaque champ est un ensemble d'inclusions.** Une liste vide veut dire
  « cette source ne fait pas partie de mon 360° », jamais « tout ». Le silence
  ne doit pas être généreux ici : une portée qui grandit quand on la vide
  dépenserait le quota provider qu'on venait d'économiser.
- **Une portée illisible dégrade vers le défaut** (`from_stored`), jamais vers
  une demi-forme : le JSONB peut avoir été écrit par une version antérieure.
- **`max_items` est borné ET publié** (défaut 5, plafond 25) : ADR-184 — ce
  qu'un validateur peut rejeter, son producteur doit pouvoir le lire. Le champ
  du formulaire porte le même plafond, et un champ vidé ne devient jamais 0
  (une écriture rejetée ferait perdre toutes les cases cochées).

**Un seul point d'entrée.** Le bouton « Préparer un point 360° » de l'entête a
été retiré : une fois la portée choisie juste au-dessus des sections, un
raccourci dans l'entête contourne le choix même que la section existe pour
offrir — et deux boutons peuvent diverger sur ce qui a été enregistré. Le
lancement vit désormais à côté des cases qui le paramètrent.

### 4. Un rôle que le provider n'expose pas ne filtre rien

Le filtre participant/organisateur ne s'applique qu'aux événements dont le
provider a effectivement exposé un organisateur (`organizer_known`). Apple n'en
expose aucun : filtrer par rôle y supprimerait **tous** les rendez-vous au lieu
d'admettre que la distinction est inconnue. Même doctrine qu'ADR-184 —
« je n'ai pas pu regarder » n'est pas « il n'y a rien ».

### 5. La fiche contact porte tout ce que le carnet d'adresses détient

Treize blocs : nom, pseudonyme, organisation, fonction, anniversaire, note,
emails, téléphones, adresses postales, relations, liens, dates importantes,
messageries. Trois règles :

- **Un bloc que le provider ne stocke pas ne s'affiche pas** — pas de « aucune
  adresse » : `relations`, `links`, `important_dates` et `messaging` n'existent
  que chez Google, et un texte de remplacement se lirait comme « le carnet ne
  contient rien », un négatif que personne n'a vérifié.
- **La parité est inégale et la fiche le dit par omission.** Nom, emails,
  téléphones, adresses, anniversaire, note et organisation viennent des trois
  providers ; la fonction est lue dans `occupations` (Google) *ou* dans le
  `title` de l'organisation (Apple, Graph) — sans quoi elle n'apparaîtrait
  jamais hors Google.
- **La photo est délibérément absente.** C'est le portrait d'un tiers :
  l'afficher est une décision d'identité, pas une question de complétude.

L'anniversaire est une **chaîne**, pas une date : `--MM-DD` (la notation de la
RFC 6350) quand le carnet ne porte pas d'année. Parser cela en date
inventerait l'année manquante ; le front met en forme selon la locale via
`partialDateLabel`, qui réutilise `parseBirthdayIso`.

Enfin, l'outil renvoie **la même** fiche que l'écran : demander « que sais-tu
de cette personne » et ouvrir sa fiche ne doivent pas donner deux réponses
différentes. Les blocs vides y sont **absents** plutôt que `[]` — une clé vide
inviterait le modèle à conclure « il n'a aucune famille enregistrée ».

## Conséquences

**Positives**

- Le défaut de production est fermé, et une garde CI empêche sa classe entière
  de revenir (un manifeste sans outil).
- La page et l'assistant lisent la même chose, par la même identité, avec le
  même cache.
- Le lecteur choisit ce que le 360° consulte, et ce choix est appliqué et non
  deviné.
- La fiche contact cesse d'être un extrait.

**Coûts / limites**

- Les trois blocs Google-only resteront vides chez Apple et Microsoft. C'est
  une limite de provider, pas un défaut ; elle est documentée dans le schéma et
  visible par omission.
- La portée est **globale à l'utilisateur**, pas par relation : c'est
  « comment je veux mes points 360° », pas « pour Gérard, ceci ». Un besoin par
  personne demanderait une table, pas une colonne.
- `search_contacts` demande maintenant treize groupes de champs au lieu de
  quatre : réponse provider plus lourde, cache adressé par la liste de champs.

## Alternatives écartées

- **Passer la portée dans le `?intent=`** — c'est-à-dire l'écrire en toutes
  lettres dans la phrase. Le planificateur en aurait fait ce qu'il voulait, et
  la garantie serait redevenue une suggestion.
- **Un paramètre d'outil `scope`** exposé au planificateur : même problème par
  un autre chemin, et un catalogue qui grossit d'un objet imbriqué que le
  modèle doit reconstruire à chaque appel.
- **Rendre la photo du contact** : écartée **par défaut** — voir §5. C'est le
  seul point de cet ADR qui relève d'un arbitrage produit plutôt que d'une
  contrainte technique : le champ existe chez les trois providers, seul le
  `readMask` l'exclut, et l'inverser tient en une ligne si le produit tranche
  autrement.
- **Reconstruire l'adresse postale depuis ses parties** : imposerait l'ordre
  d'un pays à tous les carnets. Les trois providers pré-formatent déjà
  `formattedValue`.
