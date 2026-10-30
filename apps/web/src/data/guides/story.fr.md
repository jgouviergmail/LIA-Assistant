# Diriger une IA qui code

> Retour d'expérience — un système complet, de la conception à la production.

**Version** : 3.0
**Date** : 2026-10-23
**Application** : LIA v4.2.0
**Licence** : AGPL-3.0 (Open Source)

---

## 1. L'essentiel

LIA est un assistant IA multi-agents complet. Elle dispose de connecteurs métier, parle, se souvient, relie ses utilisateurs entre eux et fonctionne en six langues. Je l'ai conçue, j'en ai dirigé le développement et je l'exploite en production en continu, en projet personnel.

La quasi-totalité du code a été écrite par une IA. Mon travail a été de la diriger : un référentiel d'ingénierie écrit, des contrôles automatiques qui bloquent ce qui n'est pas conforme, une revue de chaque changement et des audits réguliers. Le résultat se mesure : le dernier audit technique donne **7,9/10** sur 24 périmètres. Le dépôt est open source, et le rapport complet de l'audit est public, avec ses points forts et ses faiblesses, que j'assume.

| Indicateur | Valeur |
| --- | --- |
| Code écrit par une IA, dirigée, encadrée et contrôlée | **≈ 100 %** |
| Lignes de source (hors tests), réparties en 60 paquets de domaines backend | **1 059 000+** |
| Tests automatisés inventoriés, en suites adaptées au commit et à la livraison | **69 000+** |
| Décisions d'architecture documentées (ADR) | **364** |
| Versions livrées à rythme régulier | **292** |
| Langues, avec une parité vérifiée automatiquement | **6** |
| Audit technique sur 24 périmètres | **7,9/10** |

Ce que j'en retiens : le développement assisté par IA peut déjà s'industrialiser. Ce qui le limite, ce n'est pas l'outil, c'est le cadre de direction qu'on lui donne.

J'ai appliqué la même discipline au produit. Quand LIA confie une petite décision à un modèle, par exemple choisir un parcours ou un format, elle limite les choix possibles, mesure ce que cela coûte et garde l'autorité de vérifier et de confirmer le résultat. Ces décisions sont facultatives, et la confiance d'un modèle ne devient jamais une permission.

Les fonctions qui servent dans la durée montrent, elles aussi, leur limite. On retrouve une décision dans le compte rendu complet d'une réunion. On transmet un savoir-faire réutilisable à une personne de confiance : une capacité partagée arrive désactivée, sans les identifiants de la personne qui l'envoie. LIA peut qualifier un e-mail, mais cette qualification reste un indice et ne prouve pas qu'il est sûr. Elle peut placer sur une même carte les lieux qu'elle propose ; ouvrir cette carte interactive reste le choix de la personne, et son coût est affiché. Un lieu choisi sur la carte livre ses détails et un itinéraire, facturé une fois et compté.

LIA peut aussi ouvrir d'elle-même une discussion personnelle, mais seulement aux heures, à partir des sources et sur les sujets que la personne a permis. Elle montre pourquoi elle écrit, sur quel contexte elle s'appuie et ce que cela coûte, et quatre réactions permettent d'y répondre. Les SMS relayés par un téléphone rejoignent une archive privée, que l'assistante ne lit qu'avec un consentement à part.

## 2. La démarche

L'IA générative change ce que les équipes produisent, et aussi la façon dont elles le produisent. Sur ces deux questions, je ne voulais pas me forger un avis à partir des discours du marché. J'ai préféré me confronter moi-même à la réalité complète d'un système d'IA en production, avec ses coûts, ses risques, son exploitation et sa dette, et à celle du développement assisté par IA, en allant jusqu'au bout des deux.

Mon terrain d'exercice est LIA, un assistant IA conversationnel multi-agents, auto-hébergé et multilingue. Elle gère les e-mails, l'agenda, les contacts et les fichiers chez Google, Apple et Microsoft, elle offre une interface vocale en temps réel, une mémoire de long terme et la recherche dans les documents, et un personnage animé l'incarne.

Je me suis imposé des contraintes : travailler seul, en dehors de mon temps professionnel, avec un budget matériel minimal, et confier tout le développement à l'IA. Ce projet ne mesure donc pas ce qu'une personne peut produire vite. Il mesure ce qu'une direction exigeante obtient d'une IA correctement encadrée.

*Socle technique : FastAPI · Next.js/React · LangGraph (orchestration d'agents) · PostgreSQL · Redis · Docker · Prometheus/Grafana/Loki/Tempo · 7 fournisseurs de modèles d'IA intégrés.*

## 3. La méthode

Quatre dispositifs ont porté ce projet, et aucun n'est un outil : ce sont quatre actes de management. Une IA qui code produit vite et en volume, mais elle ne produit de la qualité que sous contrainte, et poser cette contrainte est un travail de direction.

- **Un référentiel écrit**, comme pour une équipe. Il fixe les règles d'architecture, les conventions, les patterns imposés avec leur exemple de référence dans le code et les pièges déjà connus. Il est versionné dans le dépôt, et chaque livraison doit s'y conformer.
- **Des contrôles automatiques bloquants**. Chaque règle importante est doublée d'un contrôle qui refuse le commit non conforme : typage strict, analyse du code, détection sur mesure des bugs qui reviennent, parité des six langues, batterie de tests complète. Le niveau d'exigence ne dépend ni de la vigilance du moment ni de la bonne volonté de l'IA.
- **Une revue qui décide**. Rien n'entre sans un cycle fixe : analyse d'impact, proposition, validation explicite, implémentation, vérification. L'IA propose, je décide. Les décisions importantes sont consignées et indexées, pour que chaque « pourquoi » survive à celui qui l'a écrit.
- **Des audits qui dérangent**. À intervalles réguliers, je fais réexaminer tout le système de façon contradictoire : chaque constat est vérifié sur pièces, les faux positifs sont écartés, la remédiation est planifiée par vagues. C'est ce qui arrête la dérive lente qu'aucune revue au fil de l'eau ne détecte.

Je fais aujourd'hui travailler plusieurs agents de développement en même temps sur le même dépôt. Ils viennent de deux familles d'outils et chacun avance sur son chantier, dans sa propre copie du dépôt (un « arbre de travail ») ou, parfois, dans la même. Ce qui les tient ensemble, ce n'est pas leur coordination, c'est le référentiel commun, avec les mêmes règles écrites et les mêmes contrôles automatiques, ces « gardes » qui bloquent avant toute livraison ce qui n'est pas conforme. Si un agent renomme un bouton, une garde rappelle que l'aide, la recherche des réglages et le vocabulaire que LIA emploie pour se décrire doivent suivre. Comme pour le code, rien de leur travail n'est consolidé sur la foi d'un résumé. Chaque fichier est attribué à son auteur par son empreinte et par le journal de l'agent, chaque fusion est rejouée dans un arbre isolé puis vérifiée par tous les contrôles, et une sauvegarde précède chaque bascule. La livraison qui rassemble ces chantiers commence par l'inventaire de ce que chacun a réellement changé, jamais par ce qu'il annonce.

Dans le produit, une interface conversationnelle devient utile quand elle peut agir sur ses propres outils : demander « Passe mes réponses en HTML + cartes » doit retrouver le même réglage que le formulaire. La conversation offre un chemin plus simple, mais elle n'ajoute aucun droit ni aucune permission implicite. Quand LIA rend compte de ce qu'elle fait, préparer n'est pas accomplir : une demande en attente, une modification enregistrée et un conflit doivent être nommés chacun pour ce qu'ils sont. Les compagnons animés rendent ce travail visible, avec des designs originaux et des expressions qui suivent l'activité, sans faire passer une intention pour une action accomplie.

Le monde partagé donne à l'assistante des lieux : une bibliothèque pour les connaissances, une salle multimédia pour créer, un jardin à explorer à plusieurs. La vraie décision d'ingénierie porte sur ce qui franchit chaque frontière. Un avatar public exprime le choix d'une personne, sans exposer le contexte de son assistante ni sa maison privée. Une pièce ouvre un outil qui existe déjà, sans accorder de permission nouvelle. Les messages échangés entre humains ont leur propre durée de vie, limitée et distincte du reste. La traduction est un choix et elle est comptabilisée, alors que les déplacements et l'affichage de la scène n'appellent aucun modèle. Dans une partie, chaque coup est confirmé par le serveur, et l'adversaire joué par l'ordinateur est une recherche bornée, pas un modèle. Une photo est dessinée à partir de ce que la personne a choisi de montrer, jamais copiée depuis l'écran. Une interface plus riche reste gouvernable tant que ses coûts, sa propriété et ses confirmations gardent le même sens.

---

## 4. Les arbitrages

Voici trois décisions structurantes, parmi les 364 documentées.

La première porte sur la **souveraineté** : je ne voulais aucune dépendance irréversible envers un fournisseur. Les modèles d'IA (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity et des modèles locaux avec Ollama) passent tous par une même abstraction, si bien que chaque usage peut changer de fournisseur par simple configuration, coûts comparés. Côté services, Google, Apple et Microsoft sont interchangeables pour chaque catégorie, qu'il s'agisse de la messagerie, de l'agenda ou des contacts. L'auto-hébergement donne la maîtrise du serveur : les données du compte sont stockées sur l'instance et les identifiants des connecteurs sont chiffrés. Les services distants que la personne choisit reçoivent tout de même les données utiles à leur part de la demande.

La deuxième porte sur l'**économie** : j'ai traité le coût de chaque requête comme un critère de conception. Deux modes d'exécution coexistent. Un pipeline déterministe et économe traite les demandes courantes, un agent autonome prend en charge les demandes exploratoires. Sur les cas standards, à service rendu équivalent, l'écart de consommation mesuré va de 1 à 4-8. Chaque appel est compté au token, valorisé en euros, agrégé par utilisateur et par modèle, et soumis à des quotas.

Le coût se joue aussi dans les détails : une notification de deux phrases est demandée sans réflexion, parce qu'un modèle qui réfléchit par défaut facture sa réflexion dans le budget de sa réponse. Par défaut, l'agent autonome n'emporte que les outils que la question appelle, choisis par pertinence et non dans leur ordre d'arrivée : quatre-vingts descriptions d'outils pesaient l'essentiel de son premier appel, sans être comptées. Enfin, chaque appel est valorisé au prix que le fournisseur facture réellement, avec des tarifs relus sur ses pages, l'écriture en cache facturée à son vrai prix et les tarifs d'heures creuses selon le jour.

La troisième porte sur la **maîtrise du risque** : aucune action irréversible sans validation humaine. Plusieurs niveaux de contrôle humain s'échelonnent selon la sensibilité de l'action, de la question de clarification à la carte de confirmation avant d'agir. J'ai fait spécifier et tester ce qui se passe en cas d'interruption : une validation en attente survit à un redémarrage, sans perte ni double exécution. Quand une demande contient plusieurs actions, chacune est soumise à son tour, sur sa propre carte, et le compte rendu dit ce qui a été fait et pour qui.

Au téléphone, la carte de confirmation sert à protéger un tiers. Quand LIA appelle la personne elle-même, sur un numéro qu'elle a déclaré et vérifié par un code lu à voix haute, la personne joue elle-même le rôle de la carte. Pour ses appels, comme pour une session vocale live du navigateur ouverte sur sa propre clé Gemini, OpenAI ou ElevenLabs, c'est elle qui choisit le mode : soit la voix confie chaque demande au chat au moment où elle est dite, avec ses confirmations, soit elle lit seule et n'agit sur rien. Ce qui tourne sur sa clé personnelle est facturé par le fournisseur et montré une fois, mais n'est pas compté ici. Ce que la plateforme paie pour elle est en revanche inscrit à son compte, quel que soit le chemin : une carte consultée pendant un appel, la météo du briefing, une photo montrée.

Ce qu'un inconnu envoie, un e-mail ou sa pièce jointe, reste une donnée à lire et jamais une instruction à suivre. Un script écrit par l'assistante ne sort sur le web que par une seule porte, et les clés de la personne y sont échangées hors de portée du script ; pour un site que personne n'a autorisé, LIA demande d'abord à la personne, qui a trois réponses possibles : avec les données, sans elles, ou pas du tout. Quand l'agent autonome ne peut pas obtenir ce qu'on lui demande, il le dit, avec ce qu'il a tenté, au lieu de combler le vide. Ce qui doit être exact, comme un montant, une durée ou une conversion, est calculé par un outil, jamais estimé par le modèle. Ce qui part sans confirmation ne s'adresse qu'à la personne elle-même, un e-mail à soi ou un appel sur son numéro vérifié : le destinataire n'y est pas un paramètre, donc rien ne peut le détourner. Une compétence écrite ailleurs, tirée d'une bibliothèque publique ou d'un plugin, travaille à l'écart : elle n'accède jamais aux connecteurs de la personne et ne joint que les hôtes permis. Et une compétence que l'IA écrit n'entre dans l'espace de la personne que lorsque celle-ci clique.

## 5. L'exploitation

Je pilote ce système aux instruments.

- **Observabilité** : une trentaine de tableaux de bord couvrent la santé de l'application, les engagements de service, les coûts d'IA, le comportement des agents et l'infrastructure. Ils s'appuient sur plus de 600 métriques, des journaux structurés centralisés et un traçage distribué de bout en bout. Journaux, métriques et traces ne gardent que des faits, jamais les mots ni les noms des personnes. Plus de cinquante procédures d'exploitation sont écrites, pour le diagnostic, la remédiation et la restauration. Les instruments descendent jusqu'aux processus : chaque worker de l'API publie ce qu'il occupe en mémoire, si bien que le total d'un conteneur se lit processus par processus. Un instrument mesure aussi ce qu'il annonce : l'alerte de latence ne compte que les tours qu'une personne attend, et le rapport quotidien du serveur commence par ce que la supervision a enregistré, plutôt que par un instantané.
- **Autodiagnostic** : l'assistante lit elle-même cette télémétrie. Elle se contrôle à intervalles réguliers, garde la mémoire des incidents qu'elle a diagnostiqués à partir de ces procédures et contourne dans ses réponses une panne connue. Chaque diagnostic montre les preuves sur lesquelles il repose.
- **Livraison** : déploiement en conteneurs, migrations de schéma automatisées, images publiées pour deux architectures matérielles (amd64 et arm64).
- **Chaîne logicielle** : chaque brique du serveur est épinglée par son empreinte et inventoriée à chaque version. Une veille hebdomadaire lit les alertes de sécurité que publie chaque dépendance, y compris celles qu'aucune base publique ne relaie. Une mise à jour attend un délai de prudence et ne revient jamais en arrière, et chaque version est installée sur des machines vierges avant d'être publiée.
- **Coûts** : une infrastructure frugale par choix, avec environ 150 € de matériel, aucune licence et des briques open source dimensionnées au besoin réel.
- **Protection des données** : la sécurité est revue point d'accès par point d'accès, les identifiants des connecteurs et les clés des fournisseurs sont chiffrés, et chaque compte peut être exporté ou supprimé. Les obligations du RGPD dépendent aussi de la façon dont l'instance est exploitée et des fournisseurs choisis.

Le produit rend ces choix d'ingénierie visibles pour la personne qui s'en sert. La conversation suit quelqu'un d'un appareil à l'autre sans bousculer sa lecture. La radio démarre quand la personne choisit d'écouter ; elle nomme les nouvelles dont elle s'inspire et affiche ce qu'elle coûte. Un fichier généré a une durée de vie que la personne peut prolonger, si elle le décide. Le travail planifié et les vérifications de conditions ont chacun leur horloge. Ce sont des promesses qu'on peut observer, appuyées sur des sources, des limites et des tests, plutôt qu'une prétention à deviner ce que la personne veut.

La même règle vaut pour ce qui n'est pas encore au niveau. Le mot d'activation « Dis LIA » est un petit modèle entraîné hors ligne, puis mesuré sur un banc dont les seuils ont été publiés avant l'entraînement. Le modèle français ne les atteint pas encore : il est donc livré en **bêta**, et le produit le dit, plutôt que d'abaisser la barre pour pouvoir écrire « terminé ». Une session vocale qui s'endort sur un silence ne coûte rien, et seule la personne la termine.

Une présence visible doit rester un choix maîtrisé. L'avatar Simli, expérimental, reprend la voix existante et fonctionne sur la clé personnelle, avec une seule sortie audible. Quand on l'arrête, il indique si la fermeture est confirmée ou encore en attente. Une connexion ouverte peut consommer le forfait même dans le silence ; la mise en veille du mode Live la ferme. Les éléments flottants s'adaptent à la place disponible sans effacer l'emplacement choisi. La validation de l'avatar sur le fournisseur et sur de vrais appareils reste à faire, et c'est dit. La dépense, elle aussi, doit pouvoir se prouver : chaque tentative payante garde son tarif et l'usage connu, même après un échec ou une annulation.

## 6. La preuve

Le niveau annoncé dans ce document vient d'un audit technique complet. Les 24 périmètres sont notés, et chaque constat est vérifié dans le code puis contre-vérifié pour écarter les faux positifs. L'audit applique la méthode du projet : il est mené avec l'outillage IA, en posture contradictoire, et chaque conclusion s'appuie sur une preuve vérifiée sur pièces. La dernière évaluation, le 25 octobre 2026, donne **7,9/10** sur la version 3.6.0 telle qu'enregistrée dans le dépôt, avec un profil que j'assume. Elle fait suite à 7,3 en août, puis à 8,0 et à une contre-expertise à 7,8 le 22 octobre. Le rapport complet est public, avec la grille de notation, la méthode, les constats ouverts et le protocole pour le reproduire : [rapport d'audit complet](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md).

Le plan d'action est organisé en vagues, chacune avec des critères de sortie mesurables. La première a été livrée puis auditée : l'audit a confirmé l'essentiel de ce qui avait été livré et a rouvert un point. C'est ainsi que ce projet rend compte de lui-même, par un niveau mesuré, écarts compris, plutôt que par un niveau proclamé.

J'ai appris à mes dépens qu'une suite de tests verte ne prouve pas qu'une fonctionnalité marche. Elle prouve seulement que ce qui a été testé se comporte comme écrit. Les défauts qui passent les portes sont justement ceux qu'on ne leur a jamais demandé de voir : une capacité que personne n'appelle, un chiffre que personne n'additionne, une garde qui reconnaît un nom plutôt qu'un mécanisme. Ce ne sont presque jamais des erreurs de code, mais des questions que personne n'avait posées.

J'en ai tiré une règle de travail : rien n'est cru avant d'avoir tourné, sur des données réelles et par le chemin que prend l'utilisateur. Un composant peut être juste et sa page vide ; un compteur peut être exact et répondre à la mauvaise question. Chaque livraison se termine donc par une relecture adverse, menée à froid, dont le but n'est pas de dérouler les tests mais de prendre le travail en défaut là où ils ne regardent pas. Les parcours de l'interface tournent à chaque livraison sous Chromium, puis chaque semaine sous Firefox et WebKit, avec un contrôle automatique d'accessibilité, parce qu'un moteur de plus voit ce que les autres laissent passer. Et une fonction censée améliorer le comportement de LIA reste un pilote tant qu'une comparaison avant/après, sur un corpus tenu à part, ne l'a pas démontré.

Chaque défaut trouvé laisse derrière lui une **garde structurelle** : un contrôle au démarrage, un invariant vérifié en continu, ou un test qui échoue si toute la classe du problème réapparaît. C'est la seule forme de progrès qui survive à celui qui l'a écrite : un correctif protège une ligne, une garde protège la règle.

---

## 7. Convictions

Voici ce que cette expérience change dans ma façon de diriger.

- Le développement assisté par IA se déploie comme un **dispositif de management**, et non comme un outil. Les gains de productivité sont réels et importants, mais ils ne durent que si le cadre (référentiel, contrôles, revue, audit) est installé avant de généraliser. C'est dans cet ordre qu'il faut l'introduire dans une organisation.
- La **gouvernance économique** de l'IA se joue dès la conception des usages. Deux architectures qui rendent le même service peuvent différer d'un facteur 4 à 8 en consommation. Ce choix revient à la direction technique, en amont, car le contrôle de la facture arrive toujours trop tard.
- Entre l'interdiction générale et la confiance aveugle, il existe une **voie gouvernable**. Le contrôle humain gradué se spécifie, se teste et s'audite. C'est l'approche que dessinent les exigences réglementaires, et elle est opérationnelle dès maintenant.
- Un dirigeant qui pratique **arbitre mieux**. Faire ou faire faire, accepter une dette ou non, croire ou non à la promesse d'un fournisseur : ces décisions gagnent en justesse quand on a éprouvé la matière soi-même. Ce projet est ma façon de garder ce contact avec le terrain.

*Projet personnel, mené en dehors de toute activité professionnelle. Évaluation technique issue de l'audit du 25 octobre 2026, constats contre-vérifiés. Les comptes structurels suivent le dépôt ; les lignes de source ont été remesurées le 26 octobre 2026. Dépôt : [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*
