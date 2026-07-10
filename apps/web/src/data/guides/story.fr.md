# Diriger une IA qui code

> Retour d'expérience — un système complet, de la conception à la production.

**Version** : 1.0
**Date** : 2026-07-10
**Application** : LIA v1.23.5
**Licence** : AGPL-3.0 (Open Source)

---

## 1. L'essentiel

LIA est un assistant IA multi-agents complet — connecteurs métier, voix, mémoire, six langues — conçu, développé et exploité en production en continu, en projet personnel.

La quasi-totalité du code a été écrite par une IA, sous direction humaine : référentiel d'ingénierie écrit, contrôles automatiques bloquants, revue systématique, audits récurrents. Le résultat est mesuré : **8,4/10** à l'audit technique sur 24 périmètres. Le dépôt est open-source ; les conclusions de l'audit — points forts comme faiblesses — sont assumées et résumées dans ce document.

| Indicateur | Valeur |
| --- | --- |
| Code écrit par une IA — dirigée, encadrée, contrôlée | **≈ 100 %** |
| Lignes de code (hors tests) — 31 domaines fonctionnels | **420 000** |
| Tests automatisés, exécutés à chaque commit et livraison | **10 000+** |
| Décisions d'architecture documentées (ADR) | **100+** |
| Versions livrées à rythme régulier | **120+** |
| Langues, parité vérifiée automatiquement | **6** |
| Audit technique sur 24 périmètres | **8,4/10** |

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

Trois décisions structurantes, parmi les 100+ documentées :

**Souveraineté & réversibilité — aucune dépendance fournisseur irréversible.** Les modèles d'IA (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, modèles locaux via Ollama) sont placés derrière une abstraction unique : chaque usage peut changer de fournisseur par configuration, avec comparaison de coût. Même principe côté métier : Google, Apple et Microsoft sont interchangeables par catégorie fonctionnelle. L'hébergement est intégralement maîtrisé ; les données personnelles sont chiffrées et restent sur l'infrastructure.

**Économie de l'IA — le coût par requête est un critère de conception.** Deux modes d'exécution coexistent : un pipeline déterministe et économe pour les demandes courantes, un mode agent autonome pour les demandes exploratoires — l'écart de consommation mesuré va de 1 à 4-8, à service rendu équivalent sur les cas standards. Chaque appel est compté au token, valorisé en euros, agrégé par utilisateur et par modèle, gouverné par quotas.

**Maîtrise du risque — aucune action irréversible sans validation humaine.** Six niveaux de contrôle humain, gradués selon la sensibilité de l'action — de la clarification à la confirmation des opérations destructives. Le comportement en cas d'interruption est spécifié et testé : une validation en attente survit aux redémarrages, sans perte ni double exécution.

## 5. L'exploitation

Un système qu'on pilote aux instruments :

- **Observabilité** : une vingtaine de tableaux de bord — santé applicative, engagements de service, coûts d'IA, comportement des agents, infrastructure. Près de 400 métriques ; journaux structurés centralisés avec filtrage des données personnelles ; traçage distribué de bout en bout. Plus de 30 procédures d'exploitation écrites — diagnostic, remédiation, restauration.
- **Livraison** : déploiement conteneurisé, migrations de schéma automatisées, images publiées pour deux architectures matérielles (amd64/arm64).
- **Coûts** : infrastructure frugale par choix — environ 150 € de matériel, zéro licence, briques open-source dimensionnées au besoin réel.
- **Conformité** : sécurité revue point d'accès par point d'accès ; chiffrement des données personnelles ; cycle de vie des comptes aligné sur le RGPD.

## 6. La preuve

Le niveau annoncé dans ce document résulte d'un audit technique complet : 24 périmètres notés, chaque constat vérifié dans le code et contre-vérifié pour éliminer les faux positifs. L'audit applique la méthode du projet lui-même — conduit avec l'outillage IA, en posture contradictoire, chaque conclusion ancrée dans une preuve vérifiée sur pièces. Dernière évaluation : **8,4/10**, avec un profil assumé. Le rapport complet — grille de notation, méthode, constats ouverts et protocole de reproduction — est public : [rapport d'audit complet](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md).

**Points forts confirmés :**

- Couche de données solide : intégrité référentielle complète, migrations sans rupture, accès concurrents maîtrisés.
- Observabilité et outillage qualité complets, et réellement utilisés au quotidien.
- Traçabilité des décisions et discipline de livraison tenues sur toute la durée.

**Ce qu'il reste à faire — connu, planifié :**

- Chaîne d'alerte temps réel et sauvegardes automatisées à remettre au niveau du reste.
- Couverture de tests du frontend à construire — le backend en concentre aujourd'hui l'essentiel.
- Décomposition des composants centraux les plus denses ; levée du principal frein de montée en charge.

Le plan d'action est organisé en vagues, chacune avec des critères de sortie mesurables. C'est la façon de rendre compte de ce projet : pas un niveau proclamé, un niveau mesuré — écarts compris.

## 7. Convictions

Ce que cette expérience change dans une pratique de direction :

- **Le développement assisté par IA se déploie comme un dispositif de management, pas comme un outil.** Les gains de productivité sont réels et importants ; ils ne durent que si le cadre — référentiel, contrôles, revue, audit — est installé avant la généralisation. C'est dans cet ordre qu'il faut l'introduire dans une organisation.
- **La gouvernance économique de l'IA se joue à la conception des usages.** Deux architectures rendant le même service peuvent différer d'un facteur 4 à 8 en consommation : ce choix appartient à la direction technique, en amont — le contrôle de la facture arrive toujours trop tard.
- **Entre l'interdiction générale et la confiance aveugle, il existe une voie gouvernable.** Le contrôle humain gradué se spécifie, se teste et s'audite ; c'est l'approche que dessinent les exigences réglementaires, et elle est opérationnelle dès maintenant.
- **Un dirigeant qui pratique arbitre mieux.** Faire ou faire faire, dette acceptable ou non, promesse fournisseur crédible ou non — ces décisions gagnent en justesse quand on a éprouvé la matière. Ce projet est une façon d'entretenir cette proximité avec le terrain.

*Projet personnel, mené en dehors de toute activité professionnelle. Chiffres issus de l'audit technique de juillet 2026 — tests exécutés, mesures effectuées sur le code, constats contre-vérifiés. Dépôt : [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*
