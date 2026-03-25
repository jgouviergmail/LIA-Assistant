# LIA — L'Assistant IA Personnel Souverain

> **Your Life. Your AI. Your Rules.**

**Version** : 2.0
**Date** : 2026-03-24
**Application** : LIA v1.11.5
**Licence** : AGPL-3.0 (Open Source)

---

## Table des matières

1. [Le monde a changé](#1-le-monde-a-changé)
2. [La thèse de LIA](#2-la-thèse-de-lia)
3. [Souveraineté : reprendre le contrôle](#3-souveraineté--reprendre-le-contrôle)
4. [Transparence radicale : voir ce que l'IA fait et ce qu'elle coûte](#4-transparence-radicale--voir-ce-que-lia-fait-et-ce-quelle-coûte)
5. [La profondeur relationnelle : au-delà de la mémoire](#5-la-profondeur-relationnelle--au-delà-de-la-mémoire)
6. [L'orchestration qui fonctionne en production](#6-lorchestration-qui-fonctionne-en-production)
7. [Le contrôle humain comme philosophie](#7-le-contrôle-humain-comme-philosophie)
8. [Agir dans votre vie numérique](#8-agir-dans-votre-vie-numérique)
9. [La proactivité contextuelle](#9-la-proactivité-contextuelle)
10. [La voix comme interface naturelle](#10-la-voix-comme-interface-naturelle)
11. [L'ouverture comme stratégie](#11-louverture-comme-stratégie)
12. [L'intelligence qui s'auto-optimise](#12-lintelligence-qui-sauto-optimise)
13. [Le tissu : comment tout s'entrelace](#13-le-tissu--comment-tout-sentrelace)
14. [Ce que LIA ne prétend pas être](#14-ce-que-lia-ne-prétend-pas-être)
15. [Vision : vers où va LIA](#15-vision--vers-où-va-lia)

---

## 1. Le monde a changé

### 1.1. L'ère agentique est là

Nous sommes en mars 2026. Le paysage de l'intelligence artificielle n'a plus rien à voir avec celui d'il y a deux ans. Les grands modèles de langage ne sont plus de simples générateurs de texte — ils sont devenus des **agents capables d'agir**.

**ChatGPT** dispose désormais d'un mode Agent qui combine navigation web autonome (héritée d'Operator), recherche approfondie et connexion à des applications tierces (Outlook, Slack, Google apps). Il peut analyser des concurrents et créer des présentations, planifier des courses et les commander, briefer un utilisateur sur ses réunions à partir de son calendrier. Ses tâches s'exécutent sur un ordinateur virtuel dédié, et les utilisateurs payants accèdent à un véritable écosystème d'applications intégrées.

**Google Gemini Agent** s'est intégré profondément dans l'écosystème Google : Gmail, Calendar, Drive, Tasks, Maps, YouTube. Chrome Auto Browse permet à Gemini de naviguer sur le web de manière autonome — remplir des formulaires, faire des achats, exécuter des workflows multi-étapes. L'intégration native avec Android via AppFunctions étend ces capacités à l'échelle du système d'exploitation.

**Microsoft Copilot** s'est transformé en plateforme agentique d'entreprise avec plus de 1 400 connecteurs, le support du protocole MCP, une coordination multi-agents, et Work IQ — une couche d'intelligence contextuelle qui connaît votre rôle, votre équipe et votre entreprise. Copilot Studio permet de créer des agents autonomes sans code.

**Claude** d'Anthropic propose Computer Use pour interagir avec des interfaces graphiques, et un écosystème MCP riche pour connecter des outils, des bases de données, des systèmes de fichiers. Claude Code agit comme un agent de développement complet.

Le marché des agents IA atteint 7,84 milliards de dollars en 2025 avec une croissance de 46 % par an. Gartner prévoit que 40 % des applications d'entreprise intégreront des agents IA spécifiques d'ici fin 2026.

### 1.2. Mais le monde a un problème

Derrière cette effervescence se cache une réalité plus nuancée.

**Seuls 10 à 15 % des projets IA agentiques atteignent la production.** Le taux d'échec de coordination entre agents est de 35 %. Gartner prévient que plus de 40 % des projets d'IA agentique seront annulés d'ici fin 2027, faute de maîtrise des coûts et des risques. Les coûts LLM explosent dans les boucles agentiques non contrôlées, le comportement non déterministe rend le debugging cauchemardesque, et les traces d'audit sont souvent absentes.

Et surtout : **ces assistants puissants sont tous des services cloud propriétaires.** Vos emails, votre agenda, vos contacts, vos documents — tout transite par les serveurs de Google, Microsoft ou OpenAI. La contrepartie de la commodité, c'est la cession de vos données les plus intimes à des entreprises dont le modèle économique repose sur l'exploitation de ces données. Le prix de l'abonnement n'est pas le vrai prix : **vos données personnelles sont le produit.**

Et quand vous changez d'avis, quand vous voulez partir ? Votre mémoire, vos préférences, votre historique — tout reste prisonnier de la plateforme. Le lock-in est total.

### 1.3. Une question fondamentale

C'est dans ce contexte que LIA pose une question simple mais radicale :

> **Est-il possible de bénéficier de la puissance des agents IA sans renoncer à sa souveraineté numérique ?**

La réponse est oui. Et c'est toute la raison d'être de LIA.

---

## 2. La thèse de LIA

### 2.1. Ce que LIA n'est pas

LIA n'est pas un concurrent frontal de ChatGPT, Gemini ou Copilot. Prétendre rivaliser avec les budgets de recherche de Google, Microsoft ou OpenAI serait une imposture.

LIA n'est pas non plus un wrapper — une interface qui masque un LLM unique derrière une jolie façade.

### 2.2. Ce que LIA est

LIA est un **assistant IA personnel souverain** : un système complet, open source, auto-hébergeable, qui orchestre intelligemment les meilleurs modèles d'IA du marché pour agir dans votre vie numérique — sous votre contrôle total, sur votre propre infrastructure.

C'est une thèse en cinq points :

1. **La souveraineté** : vos données restent chez vous, sur votre serveur, y compris un simple Raspberry Pi
2. **La transparence** : chaque décision, chaque coût, chaque appel LLM est visible et auditable
3. **La profondeur relationnelle** : une compréhension psychologique et émotionnelle qui dépasse la simple mémoire factuelle
4. **La fiabilité en production** : un système qui a résolu les problèmes que 90 % des projets agentiques ne surmontent pas
5. **L'ouverture radicale** : aucun lock-in, 7 fournisseurs IA interchangeables, standards ouverts

Ces cinq points ne sont pas des features marketing. Ce sont des **choix architecturaux profonds** qui traversent chaque ligne de code, chaque décision de conception, chaque compromis technique documentés dans 59 Architecture Decision Records.

### 2.3. Le sens profond

La conviction derrière LIA est que l'avenir de l'IA personnelle ne passera pas par la soumission à un géant du cloud, mais par l'**appropriation** : l'utilisateur doit pouvoir posséder son assistant, comprendre son fonctionnement, maîtriser ses coûts, et le faire évoluer selon ses besoins.

L'IA la plus puissante du monde ne sert à rien si vous ne pouvez pas lui faire confiance. Et la confiance ne se décrète pas — elle se construit par la transparence, le contrôle et l'expérience répétée.

---

## 3. Souveraineté : reprendre le contrôle

### 3.1. L'auto-hébergement comme acte fondateur

LIA tourne en production sur un **Raspberry Pi 5** — un ordinateur monocarte à 80 euros. C'est un choix délibéré, pas une contrainte. Si un assistant IA complet avec 15 agents spécialisés, une stack d'observabilité, et un système de mémoire psychologique peut fonctionner sur un micro-serveur ARM, alors la souveraineté numérique n'est plus un privilège d'entreprise — c'est un droit accessible à tous.

Les images Docker multi-architecture (amd64/arm64) permettent le déploiement sur n'importe quelle infrastructure : un NAS Synology, un VPS à 5 euros par mois, un serveur d'entreprise, ou un cluster Kubernetes.

### 3.2. Vos données, votre base de données

Quand vous utilisez ChatGPT, vos conversations sont stockées sur les serveurs d'OpenAI. Quand vous activez la mémoire de Gemini, vos souvenirs vivent chez Google. Quand Copilot indexe vos fichiers, ils transitent par Microsoft Azure.

Avec LIA, tout vit dans **votre** PostgreSQL :

- Vos conversations et leur historique
- Votre mémoire long-terme et votre profil psychologique
- Vos espaces de connaissances (RAG)
- Vos journaux personnels
- Vos préférences et configurations

Vous pouvez à tout moment exporter, sauvegarder, migrer ou supprimer la totalité de vos données. Le RGPD n'est pas une contrainte pour LIA — c'est une conséquence naturelle de l'architecture.

### 3.3. La liberté du choix d'IA

ChatGPT vous lie à OpenAI. Gemini à Google. Copilot à Microsoft.

LIA vous connecte à **7 fournisseurs simultanément** : OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen, et Ollama. Et vous pouvez mixer : utiliser OpenAI pour la planification, Anthropic pour la réponse, DeepSeek pour les tâches de fond — en configurant chaque nœud du pipeline indépendamment depuis une interface d'administration.

Cette liberté n'est pas seulement une question de coût ou de performance. C'est une **assurance contre la dépendance** : si un fournisseur change ses tarifs, dégrade son service, ou ferme son API, vous basculez en un clic.

---

## 4. Transparence radicale : voir ce que l'IA fait et ce qu'elle coûte

### 4.1. Le problème de la boîte noire

Quand ChatGPT Agent exécute une tâche, vous voyez le résultat. Mais combien d'appels LLM ont été nécessaires ? Quels modèles ont été utilisés ? Combien de tokens ? Quel coût ? Pourquoi cette décision plutôt qu'une autre ? Vous n'en savez rien. Le système est une boîte noire.

Cette opacité n'est pas neutre. Un abonnement à 20 ou 200 dollars par mois crée l'illusion de la gratuité : vous ne voyez jamais le coût réel de vos interactions. Cela encourage l'usage sans discernement et prive l'utilisateur de tout levier d'optimisation.

### 4.2. La transparence comme valeur fondamentale

LIA prend le parti inverse : **tout est visible, tout est auditable**.

**Le panneau de debug** — accessible dans l'interface de chat — expose en temps réel pour chaque conversation :

| Catégorie                | Ce que vous voyez                                                                                            |
| ------------------------ | ------------------------------------------------------------------------------------------------------------ |
| **Analyse d'intention**  | Comment le routeur a classifié votre message, avec le score de confiance                                     |
| **Pipeline d'exécution** | Le plan généré, les vagues d'exécution parallèle, les appels outils avec leurs entrées/sorties               |
| **Pipeline LLM**         | Chaque appel LLM et embedding dans l'ordre chronologique : modèle, durée, tokens (entrée/cache/sortie), coût |
| **Contexte et mémoire**  | Quels souvenirs ont été injectés, quels documents RAG, quel profil d'intérêts                                |
| **Intelligence**         | Les hits de cache, les patterns appris, les expansions sémantiques                                           |
| **Journaux personnels**  | Les notes injectées avec leur score de pertinence, les extractions en arrière-plan                           |
| **Cycle de vie**         | Le timing exact de chaque phase de la requête                                                                |

**Le suivi des coûts** est granulaire au centime : chaque message affiche son coût en tokens et en euros. L'utilisateur peut exporter sa consommation en CSV. L'administrateur dispose de dashboards temps réel avec jauges par utilisateur, quotas configurables (tokens, messages, coût) par période et globaux.

### 4.3. Pourquoi ça change tout

La transparence n'est pas un gadget pour techniciens. Elle change la relation fondamentale entre l'utilisateur et son assistant :

- Vous **comprenez** pourquoi LIA a choisi telle approche plutôt qu'une autre
- Vous **maîtrisez** vos coûts et pouvez optimiser (modèle moins cher pour le routage, plus puissant pour la réponse)
- Vous **détectez** les problèmes (un plan qui boucle, un cache qui ne fonctionne pas, une mémoire qui pollue)
- Vous **faites confiance** parce que vous pouvez vérifier, pas parce qu'on vous demande de croire

---

## 5. La profondeur relationnelle : au-delà de la mémoire

### 5.1. Ce que font les autres

Les grands assistants disposent tous de systèmes de mémoire qui progressent rapidement. ChatGPT retient les faits importants, organise automatiquement les souvenirs par priorité, et GPT-5 comprend désormais le ton et l'intention émotionnelle. Gemini Personal Intelligence (gratuit depuis mars 2026) accède à Gmail, Photos, Docs et YouTube pour construire un contexte riche. Copilot utilise Work IQ pour comprendre votre rôle, votre équipe et vos habitudes professionnelles.

Ces systèmes sont puissants et en constante amélioration. Mais leur approche de la mémoire reste essentiellement **factuelle et contextuelle** : ils retiennent vos préférences, vos faits personnels, et vos patterns d'interaction. La compréhension émotionnelle de GPT-5, par exemple, est implicite — elle émerge du modèle — mais elle n'est pas structurée, pondérée ni exploitable de manière programmatique.

### 5.2. Ce que fait LIA

LIA construit quelque chose de fondamentalement différent : un **profil psychologique** de l'utilisateur.

Chaque souvenir n'est pas une simple paire clé-valeur. Il porte :

- Un **poids émotionnel** (-10 à +10) : ce sujet est-il source de joie, d'anxiété, de douleur ?
- Un **score d'importance** : à quel point cette information est-elle structurante pour la personne ?
- Une **nuance d'usage** : comment utiliser cette information de manière bienveillante et appropriée ?
- Une **catégorie psychologique** : préférence, fait personnel, relation, sensibilité, pattern comportemental

Ce n'est pas de la psychologie de comptoir. C'est un système d'extraction automatique qui analyse chaque conversation à travers le prisme de la personnalité active de l'assistant, identifie les informations psychologiquement significatives, et les stocke avec leur contexte émotionnel.

**Exemple concret** : si vous mentionnez en passant que votre mère est malade, LIA ne stocke pas simplement "mère malade". Elle enregistre une sensibilité avec un poids émotionnel fort négatif, une nuance d'usage qui prescrit de ne jamais aborder le sujet légèrement, et une catégorie "relation/famille" qui structure l'information dans votre profil.

### 5.3. La sécurité émotionnelle

LIA intègre une **directive de danger émotionnel**. Quand un souvenir associé à une forte charge émotionnelle négative (poids <= -5) est activé, le système bascule en mode protecteur avec quatre interdictions absolues :

1. Ne jamais plaisanter sur le sujet
2. Ne jamais minimiser
3. Ne jamais comparer avec d'autres situations
4. Ne jamais banaliser

À notre connaissance, ce type de mécanisme de protection émotionnelle adaptative n'est pas courant dans les assistants IA grand public, qui traitent généralement tous les sujets avec la même neutralité. LIA adapte son comportement à la réalité émotionnelle de la personne qu'elle accompagne.

### 5.4. Les carnets de bord : quand l'assistant réfléchit

LIA intègre un mécanisme original : ses **carnets de bord** (Personal Journals).

L'assistant tient ses propres réflexions, organisées en quatre thèmes : auto-réflexion, observations sur l'utilisateur, idées et analyses, apprentissages. Ces notes sont rédigées à la première personne, colorées par la personnalité active, et influencent concrètement les réponses futures.

Ce n'est pas une mémoire de plus. C'est une forme d'**introspection artificielle** — l'assistant qui réfléchit sur ses interactions, note ses propres apprentissages, développe ses propres perspectives. Quand il a écrit "l'utilisateur préfère les explications concises sur les sujets techniques", cette observation influence organiquement ses réponses futures, sans règle codée en dur.

Les journaux sont déclenchés par deux mécanismes : extraction post-conversation (après chaque échange) et consolidation périodique (toutes les 4 heures, révision et réorganisation des notes). L'utilisateur garde un contrôle total : lecture, édition, suppression, activation/désactivation.

### 5.5. Le système d'intérêts

En parallèle, LIA développe un **système d'apprentissage des centres d'intérêt** : par analyse bayésienne des requêtes, elle détecte progressivement les sujets qui vous importent et peut, à terme, vous envoyer proactivement des informations pertinentes — un article, une actualité, une analyse — sur ces sujets.

### 5.6. La recherche hybride

L'ensemble de ce système de mémoire s'appuie sur une **recherche hybride** combinant similarité sémantique (pgvector) et correspondance de mots-clés (BM25). Cette approche duale offre une précision supérieure à chacune des méthodes prises isolément : le sémantique comprend le sens, le BM25 capture les noms propres et termes exacts.

---

## 6. L'orchestration qui fonctionne en production

### 6.1. Le vrai défi de l'IA agentique

La promesse agentique est séduisante : un assistant qui planifie, exécute, et synthétise. La réalité est brutale : 35 % de taux d'échec de coordination, coûts explosifs par boucles non contrôlées, debugging quasi impossible du fait du non-déterminisme.

LIA ne prétend pas avoir résolu l'IA agentique en général. Mais elle a résolu **son** problème spécifique : orchestrer 15 agents spécialisés de manière fiable, économique et observable en production, sur du hardware modeste.

### 6.2. Comment ça fonctionne

Quand vous envoyez un message, il traverse un pipeline en 5 phases :

**Phase 1 — Comprendre** : Le routeur analyse votre message en quelques centaines de millisecondes et décide s'il s'agit d'une conversation simple ou d'une demande nécessitant des actions. L'analyseur de requête identifie les domaines concernés (email, calendrier, météo...) et un routeur sémantique affine la détection grâce à des embeddings locaux (+48 % de précision).

**Phase 2 — Planifier** : Pour les demandes complexes, un planificateur intelligent génère un plan d'exécution structuré — un arbre de dépendances avec des étapes, des conditions, des itérations. Si un plan similaire a déjà été validé par le passé, un apprentissage bayésien permet de le réutiliser directement (bypass du LLM, économies massives).

**Phase 3 — Valider** : Le plan est soumis à validation sémantique puis, si nécessaire, à votre approbation via le système Human-in-the-Loop (voir section 7).

**Phase 4 — Exécuter** : Les étapes du plan sont exécutées en parallèle quand c'est possible, en séquence quand il y a des dépendances. Chaque agent spécialisé gère son domaine (contacts, emails, calendrier...) et les résultats alimentent les étapes suivantes.

**Phase 5 — Répondre** : Un système de synthèse anti-hallucination en trois couches produit une réponse fidèle aux données réelles, sans invention ni extrapolation.

En arrière-plan, trois processus fire-and-forget s'exécutent sans impacter la latence : extraction mémoire, extraction journal, détection d'intérêts.

### 6.3. La maîtrise des coûts

Là où la plupart des systèmes agentiques voient leurs coûts exploser, LIA a développé un ensemble de mécanismes d'optimisation qui réduisent la consommation de tokens de 89 % :

- **Filtrage de catalogue** : seuls les outils pertinents pour votre requête sont présentés au LLM (96 % de réduction)
- **Apprentissage de patterns** : les plans validés sont mémorisés et réutilisés (bypass LLM si confiance > 90 %)
- **Message Windowing** : chaque nœud ne voit que les N derniers messages nécessaires (5/10/20 selon le nœud)
- **Context Compaction** : résumé LLM des anciens messages quand le contexte dépasse le seuil
- **Prompt Caching** : exploitation du cache natif OpenAI/Anthropic (90 % de réduction)
- **Embeddings locaux** : embeddings E5 exécutés localement (zéro coût API, ~50 ms)

### 6.4. L'observabilité comme filet de sécurité

LIA dispose d'une observabilité native de grade production : 350+ métriques Prometheus, 18 dashboards Grafana, traces distribuées (Tempo), logging structuré (Loki), et tracing LLM spécialisé (Langfuse). 59 Architecture Decision Records documentent chaque choix de conception.

Dans un écosystème où 89 % des déploiements d'agents IA en production implémentent une forme d'observabilité, LIA va plus loin avec un debug panel embarqué qui rend ces métriques accessibles directement dans l'interface utilisateur, pas dans un outil de monitoring séparé.

---

## 7. Le contrôle humain comme philosophie

### 7.1. Ce que font les autres

Gemini Agent "demande confirmation avant les actions critiques, comme envoyer un email ou faire un achat". ChatGPT Operator "refuse d'effectuer certaines tâches pour des raisons de sécurité, comme envoyer des emails et supprimer des événements". C'est une approche binaire : soit l'action est autorisée, soit elle est refusée.

### 7.2. Le Human-in-the-Loop de LIA : 6 niveaux de nuance

LIA ne refuse pas les actions sensibles — elle vous les **soumet** avec le niveau de détail adapté :

| Niveau                       | Déclencheur                                | Ce que vous voyez                              |
| ---------------------------- | ------------------------------------------ | ---------------------------------------------- |
| **Approbation de plan**      | Actions destructrices ou sensibles         | Le plan complet avec chaque étape détaillée    |
| **Clarification**            | Ambiguïté détectée                         | Une question précise pour lever l'ambiguïté    |
| **Critique de brouillon**    | Email, événement, contact à créer/modifier | Le brouillon complet, éditable avant envoi     |
| **Confirmation destructive** | Suppression de 3+ éléments                 | Avertissement explicite d'irréversibilité      |
| **Confirmation FOR_EACH**    | Opérations en masse                        | Nombre d'opérations et nature de chaque action |
| **Review de modification**   | Modifications suggérées par l'IA           | Comparaison avant/après avec surlignage        |

### 7.3. La nuance qui change tout

La critique de brouillon illustre cette philosophie. Quand vous demandez à LIA d'envoyer un email, elle ne l'envoie pas directement (comme le ferait un agent autonome) et ne refuse pas non plus (comme le ferait ChatGPT Operator). Elle vous montre le brouillon complet avec des templates markdown adaptés au domaine (email, événement, contact, tâche), des emojis de champs, une comparaison before/after pour les modifications, et un avertissement d'irréversibilité pour les suppressions. Vous pouvez modifier, approuver ou rejeter.

C'est la différence entre un agent qui agit à votre place et un assistant qui vous **propose** et vous laisse décider. La confiance ne vient pas de l'absence de risque — elle vient de la **visibilité** sur ce qui va se passer.

### 7.4. Le feedback implicite

Chaque approbation ou rejet alimente le système d'apprentissage de patterns. Si vous approuvez systématiquement un type de plan, LIA apprend et propose avec plus de confiance. Le HITL n'est pas qu'un garde-fou — c'est un mécanisme de **calibration continue** de l'intelligence du système.

---

## 8. Agir dans votre vie numérique

### 8.1. Trois écosystèmes, une interface

LIA se connecte aux trois grands écosystèmes bureautiques du marché :

**Google Workspace** (OAuth 2.1 + PKCE) : Gmail, Google Calendar, Google Contacts (14+ schémas), Google Drive, Google Tasks — avec couverture CRUD complète.

**Microsoft 365** (OAuth 2.0 + PKCE) : Outlook, Calendar, Contacts, To Do — comptes personnels et professionnels (Azure AD multi-tenant).

**Apple iCloud** (IMAP/SMTP, CalDAV, CardDAV) : Apple Mail, Apple Calendar, Apple Contacts — pour ceux qui vivent dans l'écosystème Apple.

Un principe d'exclusivité mutuelle garantit la cohérence : un seul fournisseur actif par catégorie (email, calendrier, contacts, tâches). Vous pouvez avoir Google pour le calendrier et Microsoft pour les emails.

### 8.2. Maison connectée

LIA contrôle votre éclairage Philips Hue par commande en langage naturel : allumer/éteindre, ajuster la luminosité et les couleurs, gérer les pièces et les scènes. Connexion locale (même réseau) ou cloud (OAuth2 Philips Hue).

### 8.3. Navigation web et extraction

Un agent de navigation autonome (Playwright/Chromium headless) peut naviguer sur des sites web, cliquer, remplir des formulaires, extraire des données de pages JavaScript complexes — à partir d'une simple instruction en langage naturel. Un mode d'extraction plus simple convertit n'importe quelle URL en texte Markdown exploitable.

### 8.4. Pièces jointes

Images (analyse par modèle de vision) et PDF (extraction de texte) sont supportés en pièces jointes, avec compression côté client et isolation stricte par utilisateur.

### 8.5. Espaces de connaissances (RAG Spaces)

Créez des bases documentaires personnelles en chargeant vos documents (15+ formats : PDF, DOCX, PPTX, XLSX, CSV, EPUB...). Synchronisation automatique de dossiers Google Drive avec détection incrémentale. Recherche hybride sémantique + mots-clés. Et une base de connaissances système (119+ Q/A) permet à LIA de répondre aux questions sur ses propres fonctionnalités.

---

## 9. La proactivité contextuelle

### 9.1. Au-delà de la notification

La proactivité de LIA n'est pas un système d'alertes configuré manuellement. C'est un **jugement LLM contextualisé** qui agrège en parallèle 7 sources de contexte — calendrier, météo (avec détection de changements : début/fin de pluie, chute de température, alerte vent), tâches, emails, intérêts, mémoires, journaux — et laisse un modèle de langage décider s'il y a quelque chose de genuinement utile à communiquer.

Le système en deux phases sépare la **décision** (modèle économique, température basse, sortie structurée : "notifier" ou "ne pas notifier") de la **génération** (modèle expressif, personnalité de l'assistant, langue de l'utilisateur).

### 9.2. Anti-spam par conception

Quota quotidien configurable (1-8/jour), fenêtre horaire personnalisable, cooldown entre notifications, anti-redondance par injection de l'historique récent dans le prompt de décision, skip si l'utilisateur est en conversation active. La proactivité est opt-in, chaque paramètre est modifiable, et la désactivation préserve les données.

### 9.3. Initiative conversationnelle

Pendant une conversation, LIA ne se contente pas de répondre à la question posée. Après chaque exécution, un **agent d'initiative** analyse les résultats et vérifie proactivement les informations connexes — si la météo annonce de la pluie samedi, l'initiative consulte le calendrier pour signaler d'éventuelles activités en extérieur. Si un email mentionne un rendez-vous, elle vérifie la disponibilité. Entièrement piloté par prompt (pas de logique codée en dur), limité aux actions de lecture, enrichi par la mémoire et les centres d'intérêt de l'utilisateur.

### 9.4. Actions planifiées

Au-delà des notifications, LIA exécute des actions récurrentes programmées avec gestion de fuseau horaire, retry automatique, et désactivation après échecs consécutifs. Les résultats sont notifiés via push (FCM), SSE, et Telegram.

---

## 10. La voix comme interface naturelle

### 10.1. Entrée vocale

**Push-to-Talk** : maintenez le bouton microphone pour parler. Optimisé mobile avec anti-long-press, gestion des gestes tactiles, annulation par glissement.

**Mot-clé "OK Guy"** : détection mains-libres exécutée **entièrement dans votre navigateur** via Sherpa-onnx WASM — aucun son n'est transmis à un serveur tant que le mot-clé n'est pas détecté. La transcription utilise Whisper (99+ langues, offline) avec respect de votre langue préférée.

**Optimisations latence** : réutilisation du flux micro, pré-connexion WebSocket, setup parallèle — le délai entre détection du mot-clé et début d'enregistrement est de ~50-100 ms.

### 10.2. Sortie vocale

Deux modes : Standard (Edge TTS, gratuit, haute qualité) et HD (OpenAI TTS ou Gemini TTS, premium). Bascule automatique HD vers Standard en cas d'échec.

---

## 11. L'ouverture comme stratégie

### 11.1. Standards ouverts, pas de lock-in

| Standard                         | Usage dans LIA                                                                              |
| -------------------------------- | ------------------------------------------------------------------------------------------- |
| **MCP** (Model Context Protocol) | Connexion d'outils externes par utilisateur, avec OAuth 2.1, prévention SSRF, rate limiting |
| **agentskills.io**               | Skills injectables avec progressive disclosure (L1/L2/L3), générateur intégré               |
| **OAuth 2.1 + PKCE**             | Authentification déléguée pour tous les connecteurs                                         |
| **OpenTelemetry**                | Observabilité standardisée                                                                  |
| **AGPL-3.0**                     | Code source complet, auditable, modifiable                                                  |

### 11.2. MCP : l'extensibilité sans limites

Chaque utilisateur peut connecter ses propres serveurs MCP, étendant les capacités de LIA bien au-delà des outils intégrés. Les descriptions de domaine sont générées automatiquement par LLM pour un routage intelligent. Les MCP Apps permettent d'afficher des widgets interactifs (comme Excalidraw pour les diagrammes) directement dans le chat. Le **mode itératif (ReAct)** permet aux serveurs à API complexe d'être gérés par un agent dédié qui lit d'abord la documentation puis appelle les outils avec les bons paramètres — au lieu de tout pré-calculer dans le plan statique.

### 11.3. Skills : des compétences sur mesure

Les Skills (standard agentskills.io) permettent d'injecter des instructions expertes. Un Skill de "briefing matinal" peut coordonner calendrier, météo, emails et tâches en une seule commande déterministe. Le générateur intégré vous guide dans la création de Skills en langage naturel.

### 11.4. Multi-canal

L'interface web responsive est complétée par une intégration Telegram native (conversation textuelle, messages vocaux transcrits, boutons HITL inline, notifications proactives) et des notifications push Firebase.

---

## 12. L'intelligence qui s'auto-optimise

### 12.1. L'apprentissage bayésien des plans

À chaque plan validé et exécuté avec succès, LIA enregistre le pattern. Un scoring bayésien calcule la confiance dans chaque pattern. Au-dessus de 90 % de confiance, le plan est réutilisé directement sans appel LLM — économies massives de tokens et de latence. Le système est amorcé avec 50+ "golden patterns" prédéfinis et s'enrichit continuellement.

### 12.2. Le routage sémantique local

Des embeddings multilingues E5 (100+ langues) exécutés localement en ~50 ms permettent un routage sémantique qui améliore la précision de détection d'intention de 48 % par rapport au routage purement LLM — à coût zéro.

### 12.3. L'anti-hallucination en trois couches

Le nœud de réponse dispose d'un système anti-hallucination en trois couches : formatage des données avec limites explicites, directives système imposant l'usage exclusif de données vérifiées, et gestion explicite des cas limites (rejet, erreur, absence de résultats). Le LLM est contraint de ne synthétiser que ce qui provient des résultats réels des outils.

---

## 13. Le tissu : comment tout s'entrelace

La puissance de LIA ne réside pas dans la somme de ses fonctionnalités. Elle réside dans leur **intrication** — la manière dont chaque sous-système renforce les autres pour créer quelque chose qui dépasse la somme des parties.

### 13.1. Mémoire + Proactivité + Journaux

LIA ne se contente pas de savoir que vous avez une réunion demain. Grâce à sa mémoire, elle connaît votre anxiété par rapport à ce sujet. Grâce à ses journaux, elle a noté que les présentations courtes fonctionnent mieux avec cet interlocuteur. Grâce à son système d'intérêts, elle a repéré un article pertinent. La notification proactive intègre toutes ces dimensions dans un message personnalisé, cohérent et utile — pas une alerte générique.

### 13.2. HITL + Pattern Learning + Coûts

Chaque interaction HITL alimente l'apprentissage. Votre approbation d'un plan l'inscrit dans la mémoire bayésienne. La prochaine fois, il sera réutilisé sans appel LLM : meilleure expérience (plus rapide), moindre coût (moins de tokens), confiance accrue (plan déjà validé). Le HITL ne ralentit pas le système — il l'**accélère** avec le temps.

### 13.3. RAG + Réponse

Vos espaces de connaissances enrichissent directement les réponses de LIA. Si vous avez chargé les procédures de votre entreprise et posez une question sur le processus de validation, LIA recherche dans vos documents et intègre les informations pertinentes dans sa réponse. Les coûts d'embedding sont tracés par document et par requête, visibles dans le chat et le dashboard.

### 13.4. Routage sémantique + Filtrage de catalogue + Transparence

Le routage sémantique local détecte les domaines pertinents. Le filtrage de catalogue réduit les outils présentés au LLM de 96 %. Le debug panel vous montre exactement cette sélection. Résultat : des plans plus précis, moins chers, que vous pouvez comprendre et auditer.

### 13.5. Voix + Telegram + Web + Souveraineté

La même intelligence est accessible via trois canaux qui se complètent : le web pour les opérations complexes, Telegram pour la mobilité, la voix pour le mains-libres. Votre mémoire, vos journaux, vos préférences vous suivent d'un canal à l'autre — et tout reste sur votre serveur.

---

## 14. Ce que LIA ne prétend pas être

### 14.1. LIA n'est pas le "meilleur chatbot"

En tant que générateur de texte conversationnel, GPT-5.4 ou Claude Opus 4.6 utilisés via leur interface native seront probablement plus fluides que LIA — parce que LIA n'est pas un chatbot. C'est un système d'orchestration qui utilise ces modèles comme composants.

### 14.2. LIA n'a pas les ressources des GAFAM

L'équipe d'intégration de Gemini avec Google Workspace a des milliers d'ingénieurs et un accès direct aux APIs internes. LIA utilise les mêmes APIs publiques que n'importe quel développeur. La couverture fonctionnelle ne sera jamais identique.

### 14.3. LIA n'est pas "plug and play"

L'auto-hébergement a un prix : la configuration initiale, la maintenance du serveur, la gestion des mises à jour. LIA a un système de setup simplifié (`task setup` puis `task dev`), mais ce n'est pas aussi simple que de s'inscrire sur chatgpt.com.

### 14.4. Pourquoi cette honnêteté compte

Parce que la confiance se construit sur la vérité, pas sur le marketing. LIA excelle là où elle a choisi d'exceller : la souveraineté, la transparence, la profondeur relationnelle, la fiabilité en production, et l'ouverture. Sur le reste, elle s'appuie sur les meilleurs LLM du marché — qu'elle orchestre plutôt que de chercher à remplacer.

---

## 15. Vision : vers où va LIA

### 15.1. L'intelligence émergente

La combinaison mémoire psychologique + journaux introspectifs + apprentissage bayésien + intérêts + proactivité crée les conditions d'une forme d'**intelligence émergente** : au fil des mois, LIA développe une compréhension de plus en plus nuancée de qui vous êtes, ce dont vous avez besoin, et comment vous le présenter. Ce n'est pas de l'intelligence artificielle générale. C'est une intelligence **pratique et relationnelle**, au service d'une personne spécifique.

### 15.2. L'architecture extensible

Chaque composant est conçu pour l'extension sans réécriture :

- **Nouveaux connecteurs** (Slack, Notion, Trello) via l'abstraction par protocole
- **Nouveaux canaux** (Discord, WhatsApp) via l'architecture BaseChannel
- **Nouveaux agents** sans modifier le cœur du système
- **Nouveaux fournisseurs IA** via la factory LLM
- **Nouveaux outils MCP** par simple connexion utilisateur

### 15.3. La convergence

La vision à long terme de LIA est celle d'un **système nerveux numérique personnel** : un point unique qui orchestre l'ensemble de votre vie numérique, avec la mémoire d'un assistant qui vous connaît depuis des années, la proactivité d'un collaborateur attentif, la transparence d'un outil que vous comprenez, et la souveraineté d'un système que vous possédez.

Dans un monde où l'IA sera partout, la question ne sera plus "quelle IA utiliser ?" mais "**qui contrôle mon IA ?**". LIA répond : vous.

---

## Conclusion : pourquoi LIA existe

LIA n'existe pas parce que le monde manque d'assistants IA. Il en déborde. ChatGPT, Gemini, Copilot, Claude — chacun est remarquable à sa manière.

LIA existe parce que le monde manque d'un assistant IA qui soit **à vous**. Vraiment à vous. Sur votre serveur, avec vos données, sous votre contrôle, avec une transparence totale sur ce qu'il fait et ce qu'il coûte, une compréhension psychologique qui va au-delà des faits, et la liberté de choisir quel modèle d'IA l'anime.

Ce n'est pas un chatbot. Ce n'est pas une plateforme cloud. C'est un **compagnon numérique souverain** — et c'est précisément ce qui manquait.

**Your Life. Your AI. Your Rules.**

---

*Document rédigé sur la base du code source de LIA v1.11.5, de 190+ documents techniques, de 63 ADRs, du changelog complet, et d'une analyse du paysage concurrentiel IA de mars 2026. Toutes les fonctionnalités décrites sont implémentées et vérifiables dans le code. Les données de marché proviennent de Gartner, IBM, et des publications officielles d'OpenAI, Google, Microsoft et Anthropic.
