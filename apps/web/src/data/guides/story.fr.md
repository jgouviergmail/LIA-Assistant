# Diriger une IA qui code

> Retour d'expérience — un système complet, de la conception à la production.

**Version** : 1.6
**Date** : 2026-08-17
**Application** : LIA v1.30.8
**Licence** : AGPL-3.0 (Open Source)

---

## 1. L'essentiel

LIA est un assistant IA multi-agents complet — connecteurs métier, voix, mémoire, connexions entre utilisateurs, six langues — conçu, développé et exploité en production en continu, en projet personnel.

La quasi-totalité du code a été écrite par une IA, sous direction humaine : référentiel d'ingénierie écrit, contrôles automatiques bloquants, revue systématique, audits récurrents. Le résultat est mesuré : **8,3/10** à l'audit technique sur 24 périmètres. Le dépôt est open-source ; les conclusions de l'audit — points forts comme faiblesses — sont assumées et résumées dans ce document.

| Indicateur | Valeur |
| --- | --- |
| Code écrit par une IA — dirigée, encadrée, contrôlée | **≈ 100 %** |
| Lignes de code (hors tests) — 40 domaines fonctionnels | **520 000** |
| Tests automatisés, exécutés à chaque commit et livraison | **23 900+** |
| Décisions d'architecture documentées (ADR) | **223** |
| Versions livrées à rythme régulier | **210** |
| Langues, parité vérifiée automatiquement | **6** |
| Audit technique sur 24 périmètres | **8,3/10** |

Conviction d'expérience : le développement assisté par IA est industrialisable dès aujourd'hui. Le facteur limitant n'est pas l'outil — c'est le cadre de direction qu'on lui donne.

## 2. La démarche

L'IA générative transforme à la fois ce que les équipes produisent et la façon dont elles le produisent. Sur ces deux sujets, je ne voulais pas fonder mes convictions sur les discours du marché : j'ai choisi de me confronter à la réalité complète d'un système d'IA en production — les coûts, les risques, l'exploitation, la dette — et à la réalité du développement assisté par IA, en les pratiquant jusqu'au bout.

Le terrain d'exercice : LIA, un assistant IA conversationnel multi-agents — mail, agenda, contacts et fichiers chez Google, Apple et Microsoft, interface vocale temps réel, mémoire de long terme, recherche documentaire — auto-hébergé et multilingue.

Les contraintes étaient volontaires : seul, hors temps professionnel, budget matériel minimal, et l'IA comme unique développeur. Ce projet ne mesure donc pas une vélocité individuelle ; il mesure ce qu'une direction exigeante obtient d'une IA correctement encadrée.

*Socle technique : FastAPI · Next.js/React · LangGraph (orchestration d'agents) · PostgreSQL · Redis · Docker · Prometheus/Grafana/Loki/Tempo · 7 fournisseurs de modèles d'IA intégrés.*

## 3. La méthode

Une IA qui code produit du volume ; elle ne produit de la qualité que sous contrainte. Quatre dispositifs ont porté ce projet — aucun n'est un outil, les quatre sont des actes de management :

- **Un référentiel écrit, comme pour une équipe.** Règles d'architecture, conventions, patterns imposés avec leur exemple canonique dans le code, pièges connus documentés — versionnés dans le dépôt, opposables à chaque livraison.
- **Des contrôles automatiques bloquants.** Chaque règle structurante est doublée d'un contrôle qui refuse le commit non conforme : typage strict, analyse de code, détection sur mesure des patterns de bugs récurrents, parité des six langues, batterie de tests complète. Le niveau d'exigence ne dépend ni de la vigilance du moment, ni de la bonne volonté de l'IA.
- **Une revue qui décide.** Rien n'entre sans un cycle imposé — analyse d'impact, proposition, validation explicite, implémentation, vérification. L'IA propose, l'humain décide ; les décisions structurantes sont consignées et indexées, pour que chaque « pourquoi » survive à son auteur.
- **Des audits qui dérangent.** À intervalles réguliers, le système entier est réexaminé de façon contradictoire — constats vérifiés sur pièces, faux positifs éliminés, remédiation planifiée par vagues. C'est ce qui arrête la dérive lente qu'aucune revue au fil de l'eau ne détecte.

> La vitesse vient de l'IA. La qualité vient du cadre. Et le cadre est un travail de direction.

## 4. Les arbitrages

Trois décisions structurantes, parmi les 223 documentées :

**Souveraineté & réversibilité — aucune dépendance fournisseur irréversible.** Les modèles d'IA (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, modèles locaux via Ollama) sont placés derrière une abstraction unique : chaque usage peut changer de fournisseur par configuration, avec comparaison de coût. Même principe côté métier : Google, Apple et Microsoft sont interchangeables par catégorie fonctionnelle. L'hébergement est intégralement maîtrisé ; les données personnelles sont chiffrées et restent sur l'infrastructure.

**Économie de l'IA — le coût par requête est un critère de conception.** Deux modes d'exécution coexistent : un pipeline déterministe et économe pour les demandes courantes, un mode agent autonome pour les demandes exploratoires — l'écart de consommation mesuré va de 1 à 4-8, à service rendu équivalent sur les cas standards. Chaque appel est compté au token, valorisé en euros, agrégé par utilisateur et par modèle, gouverné par quotas.

**Maîtrise du risque — aucune action irréversible sans validation humaine.** Six niveaux de contrôle humain, gradués selon la sensibilité de l'action — de la clarification à la confirmation des opérations destructives. Le comportement en cas d'interruption est spécifié et testé : une validation en attente survit aux redémarrages, sans perte ni double exécution.

## 5. L'exploitation

Un système qu'on pilote aux instruments :

- **Observabilité** : vingt-cinq tableaux de bord — santé applicative, engagements de service, coûts d'IA, comportement des agents, infrastructure. Plus de 470 métriques ; journaux structurés centralisés avec filtrage des données personnelles ; traçage distribué de bout en bout. Une quarantaine de procédures d'exploitation écrites — diagnostic, remédiation, restauration.
- **Livraison** : déploiement conteneurisé, migrations de schéma automatisées, images publiées pour deux architectures matérielles (amd64/arm64).
- **Coûts** : infrastructure frugale par choix — environ 150 € de matériel, zéro licence, briques open-source dimensionnées au besoin réel.
- **Conformité** : sécurité revue point d'accès par point d'accès ; chiffrement des données personnelles ; cycle de vie des comptes aligné sur le RGPD.

## 6. La preuve

Le niveau annoncé dans ce document résulte d'un audit technique complet : 24 périmètres notés, chaque constat vérifié dans le code et contre-vérifié pour éliminer les faux positifs. L'audit applique la méthode du projet lui-même — conduit avec l'outillage IA, en posture contradictoire, chaque conclusion ancrée dans une preuve vérifiée sur pièces. Dernière évaluation : **8,3/10**, avec un profil assumé. Le rapport complet — grille de notation, méthode, constats ouverts et protocole de reproduction — est public : [rapport d'audit complet](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md).

**Points forts confirmés :**

- Couche de données solide : intégrité référentielle complète, migrations sans rupture, accès concurrents maîtrisés.
- Observabilité et outillage qualité complets, et réellement utilisés au quotidien.
- Traçabilité des décisions et discipline de livraison tenues sur toute la durée.

**Ce qu'il reste à faire — connu, planifié :**

- Sauvegardes : chiffrement et copie hors site — l'automatisation quotidienne, elle, est en production et vérifiée.
- Alertes : recalibrage des seuils du parc historique — le noyau critique est actif et prouvé de bout en bout, e-mail compris.
- Poursuite de la décomposition des composants les plus denses, désormais pilotée par la mesure (complexité, couplage) — les principaux monolithes du backend sont traités.

Le plan d'action est organisé en vagues, chacune avec des critères de sortie mesurables. C'est la façon de rendre compte de ce projet : pas un niveau proclamé, un niveau mesuré — écarts compris.

La preuve a aussi son épisode le plus instructif : trois recalibrages d’un simple espacement, trois « je ne vois aucun changement » — et une chaîne de livraison prouvée saine jusqu’à l’octet servi au navigateur. Deux fausses pistes plausibles (cache navigateur, service worker) sont tombées l’une après l’autre, jusqu’à la mesure qui ne pardonne pas : dans un navigateur piloté, la marge était calculée à 16 pixels et l’écart rendu en faisait 3. La primitive d’étiquette était restée `inline`, et un élément inline ignore ses marges verticales — le défaut précédait tout le chantier. Le correctif tient en un mot, l’arbitrage s’est fait sur trois captures réelles, et la règle est devenue doctrine : mesurer le rendu avant de soupçonner la livraison.

Le détecteur d'habitudes a gagné sa confiance de la même manière : exécuté sur les données réelles de production avant d'être cru — et pris en défaut. Une action programmée quotidienne écrivait un message « utilisateur » à 07:00 depuis soixante-six jours ; le détecteur a revendiqué le propre planning du planificateur comme habitude humaine. La réfutation est devenue une liste blanche de sessions humaines, la fenêtre fabriquée a disparu, et les verdicts honnêtes sont tombés. La règle demeure : prouver contre le réel avant de croire la conception.

Le cycle 1.29.0 a ajouté un troisième épisode, et celui-ci porte sur les tests eux-mêmes. Chaque protection du programme avait été livrée avec les siens, tous verts — et tous de la même forme : ils épinglaient ce que le code faisait le jour de la livraison. Une liste écrite à la main ne décrit pas un système, elle décrit ce que son auteur en savait. Trois gardes ont donc été réécrites pour **recalculer** la protection depuis la source de vérité au lieu de la redire. Elles ont trouvé trois failles qu'aucun test existant ne pouvait voir : une synthèse vocale facturée sans jamais compter contre le plafond de dépense, une connexion par fournisseur qui contournait entièrement l'acceptation désormais obligatoire des conditions, et onze chemins de connecteurs qui liaient un identifiant réel sans la moindre garde. Puis chaque garde a été mise en défaut volontairement, pour vérifier qu'elle rougissait — parce qu'une garde qu'on n'a jamais vue échouer n'est qu'une promesse de plus.

Le cycle 1.30.0 a documenté une leçon d'une autre nature : une fonctionnalité peut être livrée, chiffrée, consentie — et ne servir à rien, parce que personne ne la lit. La dernière position connue existait depuis des mois ; seules les notifications proactives la consultaient. En déplacement, l'assistant répondait donc depuis le domicile, avec aplomb. Le diagnostic est venu des journaux de production, la correction a réduit trois chemins divergents à une cascade unique — et la doctrine des comptes exacts s'est étendue à la position : une position datée s'annonce datée, « d'après ta dernière position connue à 9 h 30 », jamais « tu es à ». Le même cycle a rappelé qu'un mécanisme de synchronisation ne se croit que prouvé contre le vrai moteur : le verrou qui sérialise le premier démarrage s'est inter-bloqué avec la création d'index concurrente de PostgreSQL — mesuré dans les verrous du moteur, corrigé en sondage non bloquant, gardé par un test qui interdit le retour de la forme bloquante.

Le cycle 1.30.1 a poussé la logique jusqu'à auditer l'audit. Un rapport interne concluait que les emplacements LLM diffusés ne comptaient aucun jeton — mécanisme exact, conclusion plausible, sévérité maximale. La contre-expertise a fait ce que le rapport n'avait pas pu faire : interroger la production. Cinq cent dix appels sur cinq cent dix étaient comptés. Le défaut réel était ailleurs, et plus sournois : le comptage ne tenait qu'à la générosité d'un fournisseur à qui personne ne le demandait — rien ne le demandait, rien ne le testait, rien ne le surveillait. La réponse n'a pas été un correctif mais un contrat : chaque fournisseur déclare son mode de comptage, l'application refuse de démarrer sans cette déclaration, et un appel payant sans décompte devient une alerte. Le même cycle a réparé le compteur d'actions du tableau de bord, figé à zéro depuis toujours par un vocabulaire que personne n'émettait — jusque dans son historique, reclassé depuis les intentions archivées. Parce qu'un compte affiché est exact, ou n'existe pas.

Le cycle 1.30.2 a appliqué la même discipline à ce qu'on ne regarde jamais : les fondations. Monter l'écosystème d'orchestration de cinq mois de correctifs aurait pu être un simple changement de numéros ; il a été traité comme une opération à preuves — chaque version validée en environnement jetable avant de toucher au dépôt, huit mille cinq cents tests exécutés sous les versions cibles, les points d'intégration privés simulés hors réseau. Et l'audit qui accompagnait la montée a trouvé ce que les métriques de couverture cachaient : mille sept cent cinquante lignes d'une seconde implémentation de la reprise humaine, jamais branchée, maintenue verte par cinquante tests. Supprimée, avec sa décision d'architecture consignée. Un système vitrine ne se juge pas qu'à ce qu'il montre — aussi à ce qu'il refuse de garder.

Le cycle 1.30.5 est né d'un message utilisateur de trois lignes : « j'ai demandé de transmettre un message, j'ai eu confirmation, rien n'a été envoyé ». L'enquête, menée preuve par preuve — logs de production horodatés, base de données, code du conteneur —, a remonté jusqu'à une ligne : le moteur d'exécution écrasait le verdict de chaque outil par un succès codé en dur, et la couche d'honnêteté conçue précisément pour dire les blocages se faisait désarmer par le mensonge qu'elle devait empêcher. La correction est petite ; la méthode est le vrai livrable : chaque hypothèse contre-vérifiée avant d'écrire une ligne, chaque correctif précédé d'un test qui échoue, et l'assistant qui redit désormais la vérité jusque dans ses refus — avec les chiffres exacts, dans les six langues.

Le cycle 1.30.6 a tourné la même discipline vers l'extérieur — vers le standard que tout l'écosystème parle. Le Model Context Protocol venait de publier une révision qui rend le protocole sans état, et dont la propre matrice de compatibilité condamne les anciens clients face aux serveurs de nouvelle génération. Le chantier a été mené en enquête de conformité avant d'être une migration : la spécification lue exigence par exigence, chaque écart démontré par simulation avant de changer une seule ligne, le nouveau SDK exercé contre de vrais serveurs des deux générations. LIA parle désormais les deux — la nouvelle révision sans état et l'ancien handshake — si bien que chaque serveur déjà configuré continue de fonctionner à l'identique pendant que ceux de nouvelle génération deviennent accessibles ; le flux OAuth a gagné les obligations de sécurité de la révision, chacune assortie d'une règle de tolérance explicite pour les enregistrements existants. Et refuser un écran de consentement n'est plus une page d'erreur : c'est une réponse, reconnue dans les six langues.

Le cycle 1.30.7 a achevé le mouvement : après avoir parlé le protocole de l'écosystème, parler son format de paquet. Le standard ouvert Agent Plugins — piloté par AWS, Microsoft, OpenAI, Cursor et Vercel — venait de donner à tout l'écosystème une façon portable d'expédier ensemble skills et serveurs MCP, et le travail a suivi la discipline désormais familière : le texte normatif lu section par section, chaque hypothèse d'intégration prouvée contre le code par simulation avant d'écrire une ligne, puis un client bâti presque entièrement avec des couches auxquelles LIA faisait déjà confiance — l'importeur de skills durci, le registre MCP par utilisateur, le système de quotas. La revue a trouvé et éliminé deux vrais bugs avant qu'ils n'aient jamais tourné, et le cycle de vie complet a été prouvé au runtime contre la vraie base, deux fois. Ce qui est livré est discrètement radical : un plugin préparé pour ChatGPT ou VS Code s'installe dans LIA tel quel, rapporte exactement ce qu'il a apporté — et ce qu'il n'a pas pu apporter, avec la raison — et repart sans laisser de trace.


## 7. Convictions

Ce que cette expérience change dans une pratique de direction :

- **Le développement assisté par IA se déploie comme un dispositif de management, pas comme un outil.** Les gains de productivité sont réels et importants ; ils ne durent que si le cadre — référentiel, contrôles, revue, audit — est installé avant la généralisation. C'est dans cet ordre qu'il faut l'introduire dans une organisation.
- **La gouvernance économique de l'IA se joue à la conception des usages.** Deux architectures rendant le même service peuvent différer d'un facteur 4 à 8 en consommation : ce choix appartient à la direction technique, en amont — le contrôle de la facture arrive toujours trop tard.
- **Entre l'interdiction générale et la confiance aveugle, il existe une voie gouvernable.** Le contrôle humain gradué se spécifie, se teste et s'audite ; c'est l'approche que dessinent les exigences réglementaires, et elle est opérationnelle dès maintenant.
- **Un dirigeant qui pratique arbitre mieux.** Faire ou faire faire, dette acceptable ou non, promesse fournisseur crédible ou non — ces décisions gagnent en justesse quand on a éprouvé la matière. Ce projet est une façon d'entretenir cette proximité avec le terrain.

*Projet personnel, mené en dehors de toute activité professionnelle. Chiffres issus de l'audit technique de juillet 2026 — tests exécutés, mesures effectuées sur le code, constats contre-vérifiés. Dépôt : [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*
