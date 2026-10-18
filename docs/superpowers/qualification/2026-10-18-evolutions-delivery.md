# Livraison des évolutions — vérification des 18 et 19 octobre 2026

Exécution et revues adversariales réalisées strictement INLINE, sans sous-agent.
Ce rapport consigne la qualification du code avant son intégration Git locale.
Aucun push ni déploiement de production n'a été effectué. La demande Word/PDF
a été annulée par le propriétaire.

## Périmètre et arbitrages

| Évolution | Comportement et choix retenu |
|---|---|
| [Recherche de réunions](../../technical/MEETINGS.md) | Recherche serveur dans le CR courant complet, avant pagination ; total et page issus du même ensemble. Normalisation et jokers littéraux, annulation des lectures obsolètes, conservation de recherche/page/origine dans la navigation. Aucun LLM. |
| [Partage de capacités](../../technical/PEER_CAPABILITY_TRANSFERS.md) | Prévisualisation puis confirmation d'un paquet immuable ; copie appartenant au destinataire, installée désactivée, sans credentials/grants/exemptions HITL. Badge d'origine, gestion native, anonymisation de l'origine et rétention. Exception de confiance authored expressément choisie pour les skills reçus, y compris enfants de plugins. |
| [Qualifications email/agenda](../../technical/EMAIL_EVENT_CLASSIFICATION.md) | Décisions JEV natives, catégories et priorité indépendantes, abstention sans badge, même annotation consultative dans les données du modèle et l'affichage. Phishing/Arnaque rouge avec attention limitée et mouvements réduits respectés. **Implémentation présente ; validation native indépendante non acquise.** Les usages, laissés désactivés par la campagne, sont observés activés en DEV lors du contrôle ultérieur ; l'agent ne les a pas modifiés. |
| [Position](../../technical/HTML_CARDS.md) | Une carte en tête de réponse pour les Google Places sélectionnés, dans tous les modes dont HTML et Markdown ; coordonnées sources, repères distincts même coïncidents, liste de repli. Admission et coût explicites au clic, SDK partagé avec les itinéraires, aucun appel de géocodage/GPS ajouté. |

Les imports natifs, contrôles d'accès, éditeurs et registres existants ont été
réutilisés. Les nouvelles données restent typées ; aucune clé LangGraph ni entité
de registre fictive n'a été ajoutée pour les cartes ou annotations.

## Impacts et risques effectivement vérifiés

| Périmètre | Risque examiné | Protection et preuve |
|---|---|---|
| SQL/CR | Faux résultats, mauvais total, page vide, gros rapports | JSONPaths stricts sur les seuls champs du CR courant, snapshot de pagination et tests PostgreSQL. Sonde sur des rapports longs : mémoire ORM bornée, mesure de recherche sans résultat consignée ; aucun index/moteur de recherche supplémentaire. |
| Partages | Autre compte, blocage après preview, secret, traversée ZIP, doublon | Propriété et relation revérifiées au commit, redaction/refus des formats non sûrs, digest confirmé, baux et fencing. Tests PostgreSQL, fichiers, annulation, crash/reprise, collisions et copies partielles. |
| Rétention | Paquets conservés indéfiniment quand peers est coupé | Maintenance toujours enregistrée ; expiration avec peers désactivé testée en base. Ni messages réclamés ni notifications publiées dans cet état. |
| Confiance | Confondre badge et autorité, accorder des droits système | Provenance écrite côté serveur et unique seam de confiance ; imports tiers ordinaires isolés, absence de credentials/grants/HITL copiés, copie initialement désactivée. |
| Vie privée | Identifiants d'un autre compte dans exports ou après effacement | Projection/export et libération des ressources contrôlées ; origine anonymisée, copies propres au destinataire conservées. Métadonnées UI absentes des inventaires natifs qui ne les exposent pas. |
| JEV/LLM | Injection, faux phishing, coût non compté, timeout, tempête de cache | Evidence limitée aux champs effectivement publiés, labels consultatifs, prompts versionnés, gates indépendants, clés de cache par compte/binding/révision/politique/temps, budgets bornés, coalescence et annulation jointe. Échec payé comptabilisé, aucun repli génératif ajouté. |
| Lecteurs indirects | Label présent à l'écran mais absent du modèle, ou corps masqué réintroduit | Outils pipeline/ReAct, briefing et relations intégrés ; port partagé typé pour éviter un cycle. Tests sur builders/projections réels et round-trip JSON, corps MIME masqué exclu ; polling contextuel sans appel de classification supplémentaire. |
| Cartes/coûts | Carte automatique payante, réponse tardive d'un ancien compte, double facture | Aucune admission/SDK avant clic, fencing de cycle de vie et compte, un report après construction. Concurrence et acquittement perdu : une écriture durable en PostgreSQL. Échec de marqueur après construction nettoyé mais comptabilisé ; échec avant construction non comptabilisé. |
| HTML/UX | Bloc de code à la place de Position, labels forgés, clavier/mobile | Titre HTML natif corrigé après reproduction navigateur ; fixture native vérifiée puis lue par React et navigateur. Sentinels réservés nettoyés des sorties modèle, payload fermé, thèmes, reflow, focus et axe vérifiés. |
| SDK | API dépréciée, listeners survivant à la carte | Contrat DOM `gmp-click` du canal quarterly vérifié dans la documentation Google, listeners annulés à la destruction ; test du clic du repère jusqu'à la sélection dans les deux moteurs. Aucun changement CSP. |

Les revues à froid ont notamment corrigé la reprise d'une facture non acquittée,
le fencing A/B/A, l'ajustement initial sur tous les repères, les coordonnées
coïncidentes, la rétention feature-off, les mutations de payload et la projection
native de métadonnées qui ne concernent que l'interface. Les contrôles de qualité
n'ont reçu ni suppression ni augmentation de seuil.

La vérification finale a également corrigé la transmission de la priorité normale
au modèle, extrait les responsabilités cohérentes des fichiers dépassant leur
ratchet de taille et stabilisé la mesure CPU du test Telegram sur Windows. Les
bornes de croissance et de durée sont conservées ; un contrôle quadratique est
rejeté. Le ratchet de taille a été resserré, sans exemption nouvelle.

## Environnements locaux

Les 23 fichiers d'environnement présents ont été inventoriés. Les 11 configurations
applicatives et leurs modèles disposent des paramètres Maps et de partage lus par
le code ; leurs valeurs préexistantes sont conservées et validées avec les types
réels. Les deux archives SOPS locales sont mises à jour et déchiffrées pour vérifier
leur MAC et l'intégrité des valeurs antérieures. La clé navigateur rejoint la règle
de chiffrement SOPS. Les dix fichiers frontend, alerting et seuils Prometheus
n'ont aucun nouveau paramètre applicable et restent identiques.

La reproduction DEV signalée par le propriétaire a confirmé une clé navigateur
présente et un map ID manquant. L'identifiant de test Google est désormais configuré
uniquement en développement ; l'API DEV rechargée annonce Position disponible et
tarifé. Un vrai map ID Cloud reste requis pour la production. Aucun environnement
de production ou de démonstrateur n'a été démarré ni déployé. Les interrupteurs JEV
sont des réglages en base ; aucun faux interrupteur `.env` n'a été introduit.

## Validation exécutée

| Instrument | Résultat final |
|---|---|
| `task test:backend:unit:coverage` | 44 507 tests passent, 31 exclusions de plateforme et 9 désélections explicites ; couverture finale 79,30 %, seuil CI respecté. Données isolées et sources fonctionnelles figées ; code de sortie 0. |
| `task test:backend:unit:fast` | Passage initial : 44 501 tests passent, 31 exclusions de plateforme explicites ; les six cas ajoutés ensuite sont inclus dans le passage complet final. |
| `task test:frontend:coverage` | 13 231 tests passent dans 1 075 fichiers ; tous les seuils globaux et ciblés passent. Couverture finale mesurée : statements 87,81 %, branches 81,99 %, fonctions 85,62 %, lignes 89,35 %. |
| Intégrations concernées | 68 tests passent sur PostgreSQL jetable et Redis de test : recherche, transfers, migrations, qualifications et metering Maps. Après l'extraction MCP, les 7 scénarios de commits natifs sont rejoués et passent avec code de sortie 0. Aucune base de production utilisée. |
| Chromium, build de recette Docker | 20 parcours initiaux passent : réunions/navigation, trois capacités partagées, itinéraires/Position et badges. Après extension des modes et de l'ordre, les 11 parcours Position/itinéraires finaux passent dans le conteneur dédié : desktop/mobile, thèmes, clavier, absence de débordement et axe ciblé. |
| WebKit, build final dédié | Les mêmes 11 parcours passent, dont HTML/Markdown, ordre Position/lieux, attention phishing, mouvements réduits et formats étroits ; 22 exécutions finales pour les deux moteurs. |
| Qualité statique | Ruff/Black/MyPy backend, ESLint/typecheck frontend sans cache et ratchets passent. Vérification individuelle des nouvelles fonctions effectuée en plus du ratchet agrégé. Parité des six langues, hygiène, lockfiles, observabilité, couplage et couverture des marqueurs CI passent. |
| Documentation | `docs:sync-agents`, `docs:maps` et `lint:docs:preview` passent ; aucun lien vivant cassé ni fait périmé. Les avertissements de liens historiques préexistants sont conservés. |
| Installateur/déploiement hermétiques | Garde de readiness sans erreur, 172 tests Pester passent, dont le round-trip SOPS sous Windows ; matrice Compose : 24 scénarios valides. Les suites d'installateur et de release passent avec leurs exclusions POSIX explicites. Aucun déploiement exécuté. |

Les premiers passages ont exposé des contrats de tests anciens (signature de
liste et ordre de tabulation), une projection native trop dépendante du schéma UI
et le titre HTML Position. Ils ont été corrigés puis rejoués. La couverture
backend lancée avant les dernières corrections a été arrêtée et remplacée par
un passage sur les sources figées. Un helper Docker devenu absent après la
recréation du conteneur a été reconstruit ; son lien public circulaire, créé par
le script de préparation, a été supprimé et les vraies pages HTTP vérifiées avant
la recette finale. Aucun fichier public applicatif n'a été écrasé. Une omission
du drapeau WebKit dans le wrapper local a été réparée par un lancement dédié ;
les résultats des deux moteurs ci-dessus concernent les scénarios réellement
exécutés, pas le code de sortie de ce premier wrapper.

Les recréations ultérieures du web DEV ont de nouveau coupé la recette
(`ECONNREFUSED`). La validation finale utilise un conteneur dédié, sans port
publié, nettoyé une fois ses parcours terminés. Le registre de fixture complet
traverse le rendu natif ; les tests ouvrent le panneau de détails existant avant
de vérifier les badges repliés. Position reste visible au-dessus de ce panneau.
Une assertion de fixture a été précisée pour distinguer le lien de Position de
celui de la carte de lieu. Trois scénarios hors périmètre ont également échoué
sous contention, puis leurs 48 tests ont passé inchangés en isolement ; le passage
frontend complet séquentiel ci-dessus est vert. Aucun timeout n'a été relevé.

Enfin, une configuration Maps absente retourne désormais son offre publique
désactivée sans émettre d'erreur de service ; une activation explicitement tentée
reste refusée. Trois échecs TDD puis les 50 contrats ciblés finaux le vérifient,
avec l'ordre et les quatre modes de réponse.

## Recette native payante et limites de livraison

Le [dossier JEV](email-event-2026-10-18/README.md) conserve les quatre rapports :
calibration initiale, calibration clarifiée, holdout gelé et rejeu du même
protocole. Aucun prompt/seuil/oracle n'a changé après ouverture du holdout.
Les deux tentatives de holdout ont été interrompues sur `probability_sum`.
Une absence de faux label accepté dans les réponses traitées ne valide pas les
cas non traités : **la qualification native reste non acquise**. La campagne
n'a pas activé les deux nouveaux usages. Une lecture ultérieure en DEV les
trouve activés ; cet état est préservé et ne constitue pas une validation du
fournisseur ni une réussite rétroactive du holdout. Les lignes de préférences
portent le compte administrateur autorisé et des dates antérieures au rechargement
de l'API effectué pour Maps ; l'interrupteur global est lui aussi actif.

La lecture de contrôle en DEV confirme 32 écritures de consommation et quatre
synthèses, toutes attribuées au compte autorisé ; coût cumulé des journaux arrondis
par appel : EUR 0,008418. Les rapports conservent aussi les coûts avant arrondi.
Le plafond autorisé est respecté. Aucun vrai email/agenda n'a été lu, aucun
credential, modèle ou réglage JEV n'a été modifié par l'agent.

Les cartes nécessitent une clé navigateur explicite et un map ID valides. La
recette navigateur utilise le vrai build et un SDK/API simulés ; les restrictions
Cloud, le rendu des tuiles Google réelles et leur facture n'ont pas été vérifiés.
Les écritures concurrentes du ledger ont été éprouvées sur un vrai PostgreSQL.
Aucune certification sur iPhone/Android physique ni déploiement de production n'est revendiqué.

## Auto-évaluation sans réserve masquée

| Critère | Conclusion |
|---|---|
| Confiance technique et fonctionnelle du code | Revues et preuves couvrent les contrats, cas dégradés et dépendances identifiés ; aucun constat critique connu n'est laissé sans traitement dans le code livré. |
| Plan de tests | Groupes unitaires, intégrations et parcours ci-dessus exécutés avec succès ; collecte CI sans nouvel orphelin. Les exclusions de plateforme sont explicites. La qualification sémantique JEV a échoué et n'est pas comptée comme verte. |
| Tokens, coûts, registres et responsive | Budgets et comptabilité réels vérifiés, projections fermées et cycles contrôlés, deux moteurs et formats étroits éprouvés. La qualité intrinsèque du fournisseur reste distincte de ces preuves. |
| Garantie de perfection à 100 % | Non revendiquée. La validation JEV nécessite une nouvelle qualification indépendante ; Google Cloud et appareils physiques restent hors recette. Les réglages runtime ne valent pas certification : l'activation DEV observée après campagne est conservée et n'a pas été effectuée par l'agent. |
