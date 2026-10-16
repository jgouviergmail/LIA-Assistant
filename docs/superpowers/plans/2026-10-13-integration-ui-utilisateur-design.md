# Intégration visuelle des écrans utilisateur — spécification retenue

Préparation du 13 octobre 2026. Référence : dernières maquettes locales `output/ui-finition-2026-10-13`, sélection dans `config.js`, comparateur sur le port 8780. Le checkout courant est la source des contrats applicatifs ; les maquettes sont la source de composition visuelle. Ce document n’annonce pas une intégration réalisée.

## Périmètre

| Écran | Référence | Point d’entrée applicatif |
|---|---|---|
| Accueil | C | `app/[lng]/dashboard/page.tsx`, `components/dashboard/TodayBriefing.tsx` |
| Réunions | A | `app/[lng]/dashboard/meetings/page.tsx` |
| Notifications | A | `components/notifications/NotificationsHub.tsx` |
| Modes d’affichage | B | `components/settings/CardsDisplaySettings.tsx`, token `display-mode` |
| Fichiers générés | A | `components/settings/GeneratedAssetsSettings.tsx` et sa grille |
| Appels récents | A | `components/settings/TelephonyCallsSection.tsx` |
| Style de LIA | B | `components/settings/PersonalitySettings.tsx` |
| Psyché | A | `components/settings/PsycheSettings.tsx` |
| Connexions LIA | A | `components/settings/PeerConnectionsSettings.tsx` |
| Réglages réunions | A | `components/settings/MeetingsSettings.tsx`, token `meetings` |
| Export consommation | A | `components/settings/ConsumptionExportSection.tsx`, token `user-consumption-export` |

Les chemins frontend de ce tableau sont relatifs à `apps/web/src/`. Relations, détail de compte rendu, Mémoires, Centres d’intérêt et Espaces restent fonctionnels et inchangés visuellement. Les liens vers ces écrans ne deviennent pas des notices de maquette. Les interfaces administrateur ne sont pas dans ce périmètre.

## Présentation et interactions

1. Titre, description et groupes de commandes identifiables. Titres et boutons ne se disputent pas une étroite rangée mobile. Les paramètres s’enchaînent verticalement ; les exceptions utiles sont celles approuvées dans les écrans, pas une règle de colonnes appliquée à tous les groupes.
2. Boutons conformes aux primitives et tokens actuels : action principale remplie, secondaires remplies, suppression/effacement rouge. Aucun changement global du `Button`. Actions de la galerie conservées comme en production, avec leur menu mobile accessible au niveau unique.
3. Informations d’un élément avant ses actions, selon le contrat de cet élément. Exceptions : téléchargement d’export aligné à droite du titre desktop et commandes existantes de galerie.
4. Écrans mobile simplifiés par redistribution des informations, jamais par suppression silencieuse de données ou d’actions. Les replis restent distincts et utiles ; aucune collection unique de réunions/appels ne reçoit un repli global. Les cases et labels restent associés, les titres longs se lisent entièrement.
5. Contenus nombreux, textes longs, données absentes, chargements et erreurs sont des états de conception. Les totaux et paginations proviennent des vrais payloads. Un aperçu borné ne promet pas tout le contenu du fournisseur.
6. Dates et nombres suivent les préférences réellement applicables. Le H1 de l’Accueil utilise le jour du compte et la langue active ; il ne conserve ni Paris ni français en dur. Les dates civiles d’export gardent leur contrat actuel, distinct de cette date d’accueil.
7. Clair/sombre/OLED, accents, polices et taille de texte du compte sont respectés. Les valeurs CSS du prototype ne deviennent pas une nouvelle palette. Focus, noms accessibles et mouvements réduits restent visibles et fonctionnels.

## Contrats spécifiques

- **Accueil** : date du jour ; commandes Personnaliser/Tout rafraîchir à leur position actuelle dans Mon dashboard ; Chat puis Services en pleine largeur avant les raccourcis mobile. Contenus mobiles ouverts au départ, personnalisation fermée. Cartes égales sur desktop lorsque le contenu tient, lecteur intégral du payload reçu et actions existantes. Consommations période et cumul distinctes. Un seul propriétaire des hooks, de l’écoute et de la radio.
- **Réunions** : fin sous début desktop ; icône horloge puis début/fin mobile ; statut bien placé, case indépendante. Le titre ouvre réellement le CR : un contrôle distinct replie les détails locaux sur téléphone. Pagination en bas ; aucune modification des modèles/CR hors sélection.
- **Notifications** : chaque famille et décision conservée ; timeline sur ses données réellement chargées. Pagination sous chaque famille, ni pagination globale fictive ni requête historique supplémentaire pour la décoration.
- **Modes d’affichage** : quatre formats de réponse réels, exemple illustratif traduit sans appel API/LLM. Ce token n’est pas le réglage clair/sombre/système/OLED. Aucun retraitement des messages déjà générés.
- **Galerie** : présentation, filtres, conservation, sélection et actions actuels conservés. Ajouter uniquement les aperçus des documents éligibles : vraie page 1 raster PDF ; extrait Office/texte explicitement nommé. Chargement borné/lazy, fallback, URLs/auth et ancre de document existants. Pas de renderer Office ni de dépendance PDF supplémentaire.
- **Appels** : même hiérarchie mobile que Réunions ; statut, outcome, kind, mode, relay, décisions, debrief et coût DTO conservés. `created_at`/`completed_at` sont les instants de suivi serveur, pas des timestamps audio précis. Fin fournie prioritaire ; repli calculé signalé ≈ ; absence explicite. Limite et polling actuels conservés.
- **Style** : scène courante et catalogue serveur variable, descriptions entières, sélection sans liseret et état accessible. Aucun nombre fixe de styles ou profil OCEAN inventé pour une personnalité.
- **Psyché** : switch près du titre ; Comprendre/Réglages/Réinitialisations sur trois lignes ; point avant humeur, section permanente. Préconisation : génération explicite avant première lecture, puis Actualiser, pour éviter la facture automatique à chaque visite. État null/disabled lisible, aucun humeur/coût/date inventé. Conserver catégories, métriques, quatre graphiques et périodes actuels, ainsi que confirmations et requêtes différées d’historique.
- **Connexions** : Visibilité/Blocages/Journal en tête, recherche directement avant les connexions ; partages reçus/envoyés sur deux colonnes comparables desktop, empilés mobile. Reçu readonly, envoyé editable ; privacy et consentements inchangés. Saisie/focus survivant aux replis et refetch.
- **Réglages réunions** : titre explicite, accès direct au nombre réel d’enregistrements, modèles privés/intégrés séparés, conservation audio sous envoi email. Supprimer le bouton Save seulement avec sauvegarde immédiate frontend sérialisée du DTO complet, états pending/échec et validation. La file est owner-bound et activée paresseusement au layout dashboard pour survivre aux changements de section/page SPA ; aucune requête de préférence globale avant première consultation. Les formulaires de création de modèle gardent leur validation.
- **Exports** : registre des cinq ressources réelles ; Du/date puis Au/date, préréglages sur une rangée si leur texte tient ; téléchargement à droite du titre desktop, description immédiatement dessous. Mobile description pleine largeur et bouton avec icône. Contrat CSV, droits et paramètres conservés ; nettoyage/annulation/focus des téléchargements assurés.

## Adaptations nécessaires par rapport au prototype

Le rendu statique conserve les corps repliés ; `ui/Disclosure` applicatif les démonte. Garder le montage différé par défaut, les brouillons dans leurs propriétaires et les historiques réellement différés. Réutiliser `Button`, `Card`, `FormSection`, `Pagination`, `RowActions`, `Dialog`, `Badge`, `LLMUsageBadge` et les helpers de compte/URL. Nouveaux génériques limités à `SectionHeader` et `TimelineGroup` ; extension optionnelle de `Disclosure.summaryContent` et `SettingsSection.headerAccessory`.

Deux adaptations de contrat frontend sont identifiées : sérialisation des préférences réunions lors de l’autosave et pagination locale des actions planifiées si le serveur ne pagine pas sa liste. Les risques hérités de réponses tardives entre comptes sont à reproduire dans les tests avant tout correctif limité. Ils ne justifient pas une refonte générale des hooks.

Le point Psyché permanent ne contient pas systématiquement un texte avant sa première commande : c’est l’écart recommandé pour préserver la dépense actuelle. Le DTO summary ne fournit pas coût/date. Les aperçus Office ne reproduisent pas fidèlement une première page. Une convention de journées d’export dans le fuseau du compte serait un changement serveur distinct, hors intégration visuelle.

## Livraison et limites

Intégration par lots frontend, sans migration, nouveau catalogue, nouvelle route ou dépendance structurante prévue. Les API et checks serveur existants restent en place. La preuve finale portera sur l’application Next.js et ses hooks, avec API interceptées, échecs/retry, compte changé, clavier/focus, formats intermédiaires, texte agrandi et thèmes. Les validations de maquettes ne sont pas une validation applicative.

Le dossier local `output/ui-finition-2026-10-13/integration-preparation/` contient les inventaires détaillés, preuves source et matrice de risques. Le plan voisin définit les lots. Aucun code métier, test applicatif, serveur, build, compte ou déploiement n’est modifié/exécuté pendant cette préparation.
