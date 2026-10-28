# Revue adversariale à froid du lot sécurité GitHub

## Verdict

**Je ne donne pas une validation sans réserve de l’état fonctionnel complet. Trois défauts P2 sont reproduits par des tests adversariaux de parcours réels.** Les mêmes tests échouent avec les sources HEAD antérieures : ces défauts sont préexistants, et ne sont pas des régressions démontrées des corrections de sécurité ou de la migration React. Ils révèlent cependant des trous dans la qualification des composants remaniés et de leurs appelants.

Aucun nouveau P0/P1 introduit par ce diff n’a été établi par cette revue. Le classement des alertes justifiées et le nettoyage #984 ne sont pas invalidés par les constats ci-dessous. La commande E2E globale, auparavant accompagnée de rejoués ciblés, a cette fois été exécutée intégralement en un passage réussi : **768 scénarios réussis, un ignoré, aucun échec ni flaky**.

La revue seule est réalisée : aucun correctif produit n’a été ajouté, aucune assertion ou règle n’a été assouplie. Les nouveaux tests adversariaux sont des preuves temporaires sous `.tmp/security-adversarial-20261027/`, pas des tests silencieusement supprimés de la suite. Ils sont prêts à servir de socle rouge à la correction.

## Périmètre et provenance

- HEAD examiné : `3be6294f1c9f4f59083cd35b11b4b58dba964cdb` ; diff non commité du lot précédent.
- **89 fichiers attribuables à l’intervention**, y compris les deux Compose partagés avec les modifications préexistantes ; 101 fichiers inventoriés à l’ouverture de la revue. Le fichier OAuth non suivi et les travaux World d’un autre fil sont exclus de l’attribution et préservés.
- Relecture des 43 fichiers frontend de runtime, des deux sources backend modifiées, des tests, des sept workflows, des Dockerfiles/Compose, des manifests/locks, des ratchets, du patch axe et des faits documentaires modifiés. Les appelants directs et les helpers natifs sont inspectés pour confronter les contrats annoncés aux chemins réellement accessibles.
- Les 30 dispositions CodeQL sont relues par règle, motif et chemin ; à l’ouverture, seule la source de #984 diffère parmi leurs 23 fichiers, conformément au correctif prévu. Au contrôle final, le travail World parallèle ajoute un import et un `include_router` dans le fichier de #1004 : la divergence d’empreinte est détectée, et les AST de ses fonctions existantes sont comparés séparément. Le site qualifié de #1004 reste inchangé. Cela ne constitue ni une nouvelle analyse CodeQL de tout le frontend remanié, ni une validation du nouveau développement World.
- `snapshot.json` fige les empreintes avant la revue. Le passage global utilise l’image de qualification identifiée et une copie figée de la dernière correction de métadonnées ; aucun fichier d’environnement ni identifiant fournisseur n’y est chargé.

## Constats reproductibles

### R1 — P2 — « Réessayer » ne relance pas la lecture Drive

**Sites :** `apps/web/src/components/spaces/DriveFolderPickerDialog.tsx:110`, `apps/web/src/hooks/useDriveSources.ts:155`, `apps/web/src/hooks/useDriveSources.ts:165`.

Après une erreur de listing, le bouton appelle `navigateBack(breadcrumb.length - 1)`. Cette opération reconstruit le même fil d’Ariane avec le même dernier identifiant. La lecture automatique dépend de `currentFolderId` et du callback de lecture ; aucune de ces identités ne change. Le bouton n’émet donc pas de nouvel appel HTTP, l’erreur demeure, et l’utilisateur ne récupère pas son sélecteur après une panne transitoire.

**Preuve :** le test ouvre le vrai dialogue, fait échouer son premier GET, clique sur le bouton accessible de récupération et attend un deuxième GET. Le nombre reste à un. Il échoue ainsi sur le candidat et sur le hook antérieur. Ce n’est ni un délai à rallonger, ni une dépendance à inventer sur l’identité du tableau.

**Correction attendue :** brancher le bouton sur une véritable opération de rafraîchissement liée à la lecture courante ; conserver le même dossier et la même position dans le fil d’Ariane. Tester aussi la deuxième panne, le succès ultérieur, la fermeture pendant le retry et la navigation avant sa réponse.

### R2 — P2 — Fermer puis rouvrir Drive à la racine laisse un sélecteur vide

**Sites :** `apps/web/src/components/spaces/DriveFolderPickerDialog.tsx:65`, `apps/web/src/hooks/useDriveSources.ts:158`, `apps/web/src/hooks/useDriveSources.ts:170`.

Quand le listing racine a réussi, Annuler appelle `reset()`. Celui-ci vide `folders` et `files` et reconstruit une racine dont l’identifiant reste `root`. Le dialogue demeure monté, son hook ne reçoit pas `open`, et la réouverture ne change donc aucune dépendance de lecture. Le prochain affichage annonce une liste vide alors que Drive contient toujours les dossiers précédemment lus. Aucun nouveau GET n’est déclenché.

**Preuve :** un hôte contrôlé conserve le même vrai dialogue, charge un dossier à la racine, annule, puis le rouvre par une action utilisateur. Le dossier n’est plus présenté. Le même test échoue avec le hook antérieur.

**Correction attendue :** définir explicitement le cycle ouverture/fermeture. Soit préserver un listing dont l’identité est encore valide, soit relire à l’ouverture après invalidation. Si `reset()` vide les données, leur prochaine ouverture doit obligatoirement les réacquérir. Le déclencheur ne peut pas dépendre uniquement de l’identifiant du dossier. Qualifier racine, sous-dossier, sélection confirmée, annulation et fermeture avant réponse ; éviter les lectures inutiles d’un sélecteur fermé.

### R3 — P2 — Un rafraîchissement manuel des tarifs peut écraser une recherche plus récente

**Sites :** `apps/web/src/components/settings/AdminLLMPricingSection.tsx:295`, `apps/web/src/components/settings/AdminLLMPricingSection.tsx:797`.

Fermer le dialogue d’import appelle `fetchModels()` sans signal. Si cette lecture est lente, l’administrateur peut ensuite rechercher un autre modèle ; la nouvelle lecture automatique peut répondre d’abord. Quand l’ancienne lecture manuelle termine, `signal` vaut `undefined`, le contrôle d’annulation la laisse passer, et ses `setModels`/totaux remplacent les résultats de la recherche courante. Le champ affiche la nouvelle recherche tandis que la grille montre les anciennes lignes.

**Preuve :** le test utilise le composant et son vrai dialogue : fermeture de l’import, ancien GET retenu, saisie d’une recherche, réponse récente affichée, puis libération de l’ancien GET. Les résultats récents disparaissent. Le même test échoue avec le composant HEAD antérieur. Le problème concerne l’affichage administrateur ; cette preuve ne démontre pas une altération du calcul de facturation serveur.

**Correction attendue :** toute lecture, automatique ou manuelle, doit appartenir à la même génération de requête et de paramètres. Un ancien callback conservé ne doit ni écraser ni annuler la lecture du nouvel écran. Réutiliser le contrat déjà implémenté par `useApiQuery` — contrôleur de lecture actif, durée de vie de l’effet, identité de la lecture et rafraîchissement vérifié — plutôt qu’ajouter des délais ou seulement tester un signal optionnel. Examiner les autres appels manuels des panneaux de tarification avant d’étendre cette correction ; leurs motifs analogues ne sont pas comptés ici comme défauts prouvés supplémentaires.

## Preuves et contre-vérifications

| Vérification | Résultat et portée |
|---|---|
| `task test:e2e`, image officielle Playwright utilisée par le candidat, réseau Docker normal et `CI=true` | **Code de sortie 0 ; 768 réussis, un ignoré ; 18,7 min** pour les tests Playwright. Aucun scénario sélectionné ou retiré pour ce passage. Le transport axe et le typage du package E2E s’exécutent aussi via la tâche. `e2e-global.log`, `e2e-report/`. |
| Échantillon Firefox + WebKit, wrapper média existant et réseau interne sans Internet | **12 réussis**, sans échec : connexion, shell protégé, révocation SSE, flux remplacé et contraste clair/sombre de `/more` animé/en pause. Cela ne remplace pas une matrice complète de tous les scénarios sur ces moteurs. `browsers-sample.log`. |
| Tests UI Drive adversariaux sur le candidat | **Deux échecs attendus du socle rouge**, exactement sur R1 et R2. `drive-picker-two-current.log`. |
| Mêmes tests Drive avec `useDriveSources` de HEAD | **Deux échecs identiques** : caractère préexistant confirmé. `drive-picker-base.log`. |
| Test administrateur adversarial sur le candidat, puis sur le composant HEAD | **Un échec fonctionnel identique dans chaque version**, après affichage préalable du résultat récent. Le filtre de sélection du test laisse les 28 autres cas hors de cette commande ; il ne s’agit pas d’ignorés ajoutés au dépôt. `admin-current.log`, `admin-base.log`. |
| Préparation Capacitor iOS | **Code de sortie 0** : génération native, overlay sans dérive, déclaration des quatre sources Swift. Exécuté dans une copie jetable, sans compilation Xcode. `mobile-ios-prepare.log`. |
| Templates Capacitor Android | **Code de sortie 0** : génération du projet et deux empreintes d’overlays identiques. Aucune compilation Gradle/SDK n’est revendiquée. `mobile-android-template.log`. |
| Lock pnpm | Importeurs modifiés limités à web/mobile ; `lockfileVersion`, settings, overrides et patches inchangés. Pas de gel dissimulé de l’ancien linter. `lock-comparison.json`. |
| Couverture/statique du candidat | Les preuves du lot précédent restent valides tant que leurs sources sont identiques : couverture frontend complète, lint/ratchets/typage, tests backend ciblés et intégration World. Elles ne couvraient pas les trois combinaisons adversariales ajoutées ici. |

Toutes les preuves de cette revue sont conservées sous `.tmp/security-adversarial-20261027/`. Les fichiers du lot examiné sont restés inchangés ; les cas négatifs sont montés en lecture seule dans des conteneurs dédiés. Les sources antérieures proviennent de `git show HEAD:<chemin>`, sans checkout ni modification de l’index. Des ajouts World sont apparus dans d’autres fichiers pendant la revue ; ils sont inventoriés séparément et préservés. Les résultats du snapshot figé ne sont pas étendus au nouvel ensemble de l’arbre de travail.

## Hypothèses examinées et écartées

- Le déplacement des lectures dans `useEffectRequest` n’est pas évalué comme une correction universelle des courses. Son contrat couvre une lecture d’effet et l’annulation avant départ ; les chemins manuels doivent conserver leur propre propriété de génération. Le helper native `useApiQuery` montre précisément la différence, mise en défaut par R3.
- Une course Drive au niveau de son API `refetch()` est également reproductible, mais le sélecteur actuel n’appelle pas cette méthode : elle n’est pas ajoutée comme quatrième défaut utilisateur. Le chemin réel conduit à R1. Cela évite de confondre une sonde de hook et une entrée produit réellement accessible.
- L’alpha de bordure ajouté dans une illustration `/more` ne constitue pas une régression du garde des lignes neutres : ce garde déclare explicitement son périmètre authentifié, qui exclut le site public. Les véritables scans de contraste multi-moteurs passent.
- Les scopes d’identité scalaire, les refs synchronisées après commit, les snapshots SSR constants, la fermeture immédiate SSE et l’annulation des métadonnées de l’ancien compte ne montrent pas de nouvelle régression dans le diff et les parcours contrôlés. Cela ne promet pas une absence de toute course dans le monorepo.
- Les changements Node/Prometheus/axe sont confrontés aux owners de versions, aux checksums, aux manifestations de build déjà observées et aux tests de contrats. Aucun nouveau droit GitHub, aucune règle de sécurité désactivée et aucune baseline augmentée ne sont introduits par le lot.

## Ordre de correction recommandé et tests de sortie

1. **Lot Drive atomique : R1 + R2.** Conserver les deux tests UI rouges, formaliser la propriété ouverture/dossier de la lecture, raccorder le vrai retry et rendre le reset cohérent avec la réouverture. Ajouter la réponse tardive après fermeture/navigation, l’erreur persistante puis récupération, et vérifier le nombre de requêtes pour éviter la répétition de calls fournisseur. GET uniquement ; sélection explicite toujours nécessaire pour l’indexation.
2. **Lot lecture administrateur : R3.** Utiliser la même génération pour lectures automatiques et rafraîchissements manuels. Éprouver ancien succès, ancienne erreur, tri, recherche, page, fermeture/démontage et callback de mutation conservé. Le résultat visible doit toujours correspondre aux paramètres courants, et un ancien finally ne doit pas éteindre le spinner de la lecture récente.
3. **Qualification.** Exécuter les tests ciblés et de cycle de vie, le lint/typage propre, les seuils de couverture concernés et les parcours navigateur réellement modifiés. Aucun seuil ou délai à relever. Une nouvelle publication devra toujours faire exécuter la CI distante et CodeQL sur ses révisions ; cette revue ne publie rien.

Les corrections ne requièrent aucun nouveau schéma, prompt ou appel LLM. Le principal enjeu de quotas reste de ne pas multiplier les lectures externes de Drive/Gmail ; le principal enjeu de registre est la cohérence entre l’identité de ressource visible et la réponse acceptée. Les primitives de dialogue, les noms accessibles, le focus et le responsive doivent être conservés.

## Confiance et limites

Le lot de correction des alertes et de migration du linter reste étayé ; la réserve méthodologique du passage E2E agrégé est levée par un passage global réussi. **La satisfaction complète est refusée au regard des trois défauts fonctionnels prouvés dans le périmètre transverse.** Ils doivent être traités ou explicitement suivis comme dette avant d’annoncer une clôture fonctionnelle sans réserve.

Cette revue porte sur le diff identifié et ses dépendances directes, pas sur chaque ligne du monorepo. Elle ne prouve ni une exécution arm64, ni les builds natifs Android/iOS complets, ni un essai sur téléphone physique, ni le comportement d’un fournisseur payant réel, ni l’état de l’instance déployée. Aucun de ces environnements n’est annoncé validé. Les alertes du kit GPU demeurent un risque accepté par décision de périmètre, et non des versions corrigées.
