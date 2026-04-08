# LIA — L'Assistant IA qui vous appartient

> **Your Life. Your AI. Your Rules.**

**Version** : 3.0
**Date** : 2026-04-08
**Application** : LIA v1.14.5
**Licence** : AGPL-3.0 (Open Source)

---

## Table des matières

1. [Le contexte](#1-le-contexte)
2. [Administration simple](#2-administration-simple)
3. [Ce que LIA sait faire](#3-ce-que-lia-sait-faire)
4. [Un serveur pour vos proches](#4-un-serveur-pour-vos-proches)
5. [Souverain et frugal](#5-souverain-et-frugal)
6. [Transparence radicale](#6-transparence-radicale)
7. [Profondeur émotionnelle](#7-profondeur-émotionnelle)
8. [Fiabilité de production](#8-fiabilité-de-production)
9. [Ouverture radicale](#9-ouverture-radicale)
10. [Vision](#10-vision)

---

## 1. Le contexte

L'ère des assistants IA agentiques est arrivée. ChatGPT, Gemini, Copilot, Claude — chacun propose un agent capable d'agir dans votre vie numérique : envoyer des emails, gérer votre agenda, rechercher sur le web, contrôler vos appareils.

Ces assistants sont remarquables. Mais ils partagent un modèle commun : vos données vivent sur leurs serveurs, l'intelligence est une boîte noire, et quand vous partez, tout reste derrière vous.

LIA prend un chemin différent. Pas un concurrent frontal des géants — un **assistant IA personnel que vous hébergez, que vous comprenez, et que vous contrôlez**. LIA orchestre les meilleurs modèles d'IA du marché, agit dans votre vie numérique, et le fait avec des qualités fondamentales qui le distinguent.

---

## 2. Administration simple

### 2.1. Un déploiement guidé, puis zéro friction

L'auto-hébergement a mauvaise réputation. LIA ne prétend pas éliminer toute étape technique : la mise en place initiale — configuration des clés API, paramétrage des connecteurs OAuth, choix de l'infrastructure — demande un peu de temps et quelques compétences de base. Mais chaque étape est **documentée en détail** dans un guide de déploiement pas à pas.

Une fois cette phase d'installation terminée, **tout le quotidien se gère depuis une interface web intuitive**. Plus besoin de terminal ni de fichiers de configuration.

### 2.2. Ce que chaque utilisateur peut configurer

Chaque utilisateur dispose de son propre espace de paramétrage, organisé en deux onglets :

**Préférences personnelles :**

- **Connecteurs personnels** : branchez vos comptes Google, Microsoft ou Apple en quelques clics via OAuth — email, calendrier, contacts, tâches, Google Drive. Ou connectez Apple via IMAP/CalDAV/CardDAV. Clés API pour les services externes (météo, recherche)
- **Personnalité** : choisissez parmi les personnalités disponibles (professeur, ami, philosophe, coach, poète...) — chacune influence le ton, le style et le comportement émotionnel de LIA
- **Voix** : configurez le mode vocal — mot-clé de détection, sensibilité, seuil de silence, lecture automatique des réponses
- **Notifications** : gérez les notifications push et les appareils enregistrés
- **Canaux** : reliez Telegram pour chatter et recevoir des notifications sur mobile
- **Génération d'images** : activez et configurez la création d'images par IA
- **Serveurs MCP personnels** : connectez vos propres serveurs MCP pour étendre les capacités de LIA
- **Apparence** : langue, fuseau horaire, thème (5 palettes, mode sombre/clair), police (9 choix), format d'affichage des réponses (cartes HTML, HTML, Markdown)
- **Debug** : accédez au panneau de debug pour inspecter chaque échange (si activé par l'administrateur)

**Fonctionnalités avancées :**

- **Psyche Engine** : ajustez les traits de personnalité (Big Five) qui modulent la réactivité émotionnelle de votre assistant
- **Mémoire** : consultez, éditez, épinglez ou supprimez les souvenirs de LIA — activez ou désactivez l'extraction automatique de faits
- **Journaux personnels** : configurez l'extraction d'introspections après chaque conversation et la consolidation périodique
- **Centres d'intérêt** : définissez vos sujets favoris, configurez la fréquence de notifications, les créneaux horaires et les sources (Wikipedia, Perplexity, réflexion IA)
- **Notifications proactives** : réglez la fréquence, la fenêtre horaire et les sources de contexte (calendrier, météo, tâches, emails, intérêts, mémoires, journaux)
- **Actions planifiées** : créez des automatisations récurrentes exécutées par l'assistant
- **Skills** : activez/désactivez des compétences expertes, créez vos propres Skills personnels
- **Espaces de connaissances** : chargez vos documents (PDF, Word, Excel, PowerPoint, EPUB, HTML et 15+ formats) ou synchronisez un dossier Google Drive — indexation automatique avec recherche hybride
- **Export de consommation** : téléchargez vos données de consommation LLM et API en CSV

### 2.3. Ce que l'administrateur contrôle

L'administrateur accède à un troisième onglet dédié à la gestion de l'instance :

**Utilisateurs et accès :**

- **Gestion des utilisateurs** : créer, activer/désactiver des comptes, visualiser les services connectés et les fonctionnalités activées par utilisateur
- **Limites d'usage** : définir des quotas par utilisateur (tokens LLM, appels API, générations d'images) avec suivi temps réel et blocage automatique
- **Messages broadcast** : envoyer des messages importants à tous les utilisateurs ou à une sélection, avec date d'expiration optionnelle
- **Export de consommation global** : exporter la consommation de tous les utilisateurs en CSV

**IA et connecteurs :**

- **Configuration LLM** : configurer les clés API des fournisseurs (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, Ollama), assigner un modèle par rôle dans le pipeline, gérer les niveaux de raisonnement — clés stockées chiffrées
- **Activation/désactivation de connecteurs** : activer ou désactiver les intégrations au niveau global (Google OAuth, Apple, Microsoft 365, Hue, météo, Wikipedia, Perplexity, Brave Search). La désactivation révoque les connexions actives et notifie les utilisateurs
- **Tarification** : gérer les prix par modèle LLM (coût par million de tokens), par API Google Maps (Places, Routes, Geocoding), et par génération d'image — avec historique des prix

**Contenu et extensions :**

- **Personnalités** : créer, éditer, traduire et supprimer les personnalités disponibles pour tous les utilisateurs — définir la personnalité par défaut
- **Skills système** : gérer les compétences expertes à l'échelle de l'instance — import/export, activation/désactivation, traduction
- **Espaces de connaissances système** : gérer la base de connaissances FAQ, surveiller l'état de l'indexation et les migrations de modèles
- **Voix globale** : configurer le mode TTS par défaut (standard ou HD) pour tous les utilisateurs
- **Debug système** : configuration des logs et du diagnostic

### 2.4. Un assistant, pas un projet technique

Le but de LIA n'est pas de vous transformer en administrateur système. C'est de vous offrir la puissance d'un assistant IA complet **avec la simplicité d'une application grand public**. L'interface est installable comme une application native sur ordinateur, tablette et smartphone (PWA), et tout est conçu pour être accessible sans compétence technique au quotidien.

---

## 3. Ce que LIA sait faire

LIA agit concrètement dans votre vie numérique grâce à 16 agents spécialisés qui couvrent l'ensemble des besoins du quotidien : gestion de vos données personnelles (emails, calendrier, contacts, tâches, fichiers), accès aux informations externes (recherche web, météo, lieux, itinéraires), création de contenu (images, diagrammes), contrôle de votre maison connectée, navigation web autonome, et anticipation proactive de vos besoins.

### 3.1. Conversation naturelle

Parlez à LIA comme à un assistant humain — pas de commandes à mémoriser, pas de syntaxe à respecter. LIA comprend et répond en 99+ langues, avec une interface disponible en 6 langues (français, anglais, allemand, espagnol, italien, chinois). Les réponses sont rendues en cartes visuelles HTML interactives, en HTML direct, ou en Markdown selon vos préférences.

### 3.2. Services connectés personnels

- **Email** : lire, rechercher, rédiger, envoyer, répondre, transférer — via Gmail, Outlook ou Apple Mail
- **Calendrier** : consulter, créer, modifier, supprimer des événements — via Google Calendar, Outlook Calendar ou Apple Calendar
- **Contacts** : rechercher, créer, modifier des contacts — via Google Contacts, Outlook Contacts ou Apple Contacts
- **Tâches** : gérer vos listes de tâches — via Google Tasks ou Microsoft To Do
- **Fichiers** : accéder à Google Drive pour rechercher et lire vos documents
- **Maison connectée** : contrôler votre éclairage Philips Hue — allumer/éteindre, luminosité, couleurs, scènes, gestion par pièce

### 3.3. Intelligence web et environnement

- **Recherche web** : recherche multi-sources (Brave Search, Perplexity, Wikipedia) pour des réponses complètes et sourcées
- **Météo** : conditions actuelles et prévisions à 5 jours, avec détection de changements (début/fin de pluie, chute de température, alertes vent)
- **Lieux et commerces** : recherche de lieux à proximité avec détails, horaires, avis
- **Itinéraires** : calcul d'itinéraires multi-modaux (voiture, marche, vélo, transports en commun) avec géolocalisation automatique

### 3.4. Voix

LIA propose un mode vocal complet :

- **Push-to-Talk** : maintenez le bouton microphone pour parler, optimisé pour le mobile
- **Mot-clé "OK Guy"** : détection mains-libres exécutée **entièrement dans votre navigateur** via Sherpa-onnx WASM — aucun son n'est transmis tant que le mot-clé n'est pas détecté
- **Synthèse vocale** : mode standard (Edge TTS, gratuit) ou HD (OpenAI TTS / Gemini TTS)
- **Messages vocaux Telegram** : envoyez des messages audio, LIA les transcrit et répond

### 3.5. Création et médias

- **Génération d'images** : créez des images par description textuelle, éditez des photos existantes
- **Schémas Excalidraw** : générez des diagrammes et schémas directement dans la conversation
- **Pièces jointes** : joignez photos et PDF — LIA analyse le contenu visuel et extrait le texte des documents
- **MCP Apps** : widgets interactifs directement dans le chat (formulaires, visualisations, mini-applications)

### 3.6. Proactivité et initiatives

LIA ne se contente pas de répondre — elle anticipe :

- **Notifications proactives** : LIA croise vos sources de contexte (calendrier, météo, tâches, emails, intérêts) et vous notifie quand c'est genuinement utile — avec un système anti-spam intégré (quota quotidien, fenêtre horaire, cooldown)
- **Initiative conversationnelle** : pendant un échange, LIA vérifie proactivement les informations connexes — si la météo annonce de la pluie samedi, elle consulte votre calendrier pour signaler d'éventuelles activités en extérieur
- **Centres d'intérêt** : LIA détecte progressivement les sujets qui vous passionnent et peut vous envoyer du contenu pertinent
- **Sous-agents** : pour les tâches complexes, LIA délègue à des agents éphémères spécialisés qui travaillent en parallèle

### 3.7. Navigation web autonome

Un agent de navigation (Playwright/Chromium headless) peut naviguer sur des sites web, cliquer, remplir des formulaires, extraire des données de pages dynamiques — à partir d'une simple instruction en langage naturel. Un mode d'extraction simplifié convertit n'importe quelle URL en texte exploitable.

### 3.8. Administration serveur (DevOps)

En installant Claude CLI (Claude Code) directement sur le serveur, les administrateurs peuvent diagnostiquer leur infrastructure en langage naturel depuis le chat de LIA : consulter les logs Docker, vérifier la santé des conteneurs, surveiller l'espace disque, analyser les erreurs. Cette fonctionnalité est réservée aux comptes administrateurs.

---

## 4. Un serveur pour vos proches

### 4.1. LIA est un serveur web partagé

Contrairement aux assistants cloud personnels (un compte = un utilisateur), LIA est conçu comme un **serveur centralisé** que vous déployez une fois et partagez avec votre famille, vos amis, ou votre équipe.

Chaque utilisateur dispose de son propre compte avec :

- Son profil, ses préférences, sa langue
- **Sa propre personnalité d'assistant** avec son humeur, ses émotions et sa relation unique — grâce au Psyche Engine, chaque utilisateur interagit avec un assistant qui développe un lien émotionnel distinct
- Sa mémoire, ses souvenirs, ses journaux personnels — totalement isolés
- Ses propres connecteurs (Google, Microsoft, Apple)
- Ses espaces de connaissances privés

### 4.2. Gestion d'usage par utilisateur

L'administrateur garde le contrôle de la consommation :

- **Limites d'usage** configurables par utilisateur : nombre de messages, tokens, coût maximum — par jour, par semaine, par mois, ou en cumul global
- **Quotas visuels** : chaque utilisateur voit sa consommation en temps réel avec des jauges claires
- **Activation/désactivation de connecteurs** : l'administrateur active ou désactive les intégrations (Google, Microsoft, Hue...) au niveau de l'instance

### 4.3. Votre IA de famille

Imaginez : un Raspberry Pi dans votre salon, et toute la famille qui profite d'un assistant IA intelligent — chacun avec son expérience personnalisée, ses souvenirs, son style de conversation, et un assistant qui développe sa propre relation émotionnelle avec lui. Le tout sous votre contrôle, sans abonnement cloud, sans données qui partent chez un tiers.

---

## 5. Souverain et frugal

### 5.1. Vos données restent chez vous

Quand vous utilisez ChatGPT, vos conversations vivent sur les serveurs d'OpenAI. Avec Gemini, chez Google. Avec Copilot, chez Microsoft.

Avec LIA, **tout reste dans votre PostgreSQL** : conversations, mémoire, profil psychologique, documents, préférences. Vous pouvez exporter, sauvegarder, migrer ou supprimer la totalité de vos données à tout moment. Le RGPD n'est pas une contrainte — c'est une conséquence naturelle de l'architecture. Les données sensibles sont chiffrées, les sessions isolées, et le filtrage automatique des informations personnelles identifiables (PII) est intégré.

### 5.2. Même un Raspberry Pi suffit

LIA tourne en production sur un **Raspberry Pi 5** — un ordinateur monocarte à 80 euros. 16 agents spécialisés, une stack d'observabilité complète, un système de mémoire psychologique, le tout sur un micro-serveur ARM. Les images Docker multi-architecture (amd64/arm64) permettent le déploiement sur n'importe quel matériel : NAS Synology, VPS à quelques euros par mois, serveur d'entreprise, ou cluster Kubernetes.

La souveraineté numérique n'est plus un privilège d'entreprise — c'est un droit accessible à tous.

### 5.3. Optimisé pour la frugalité

LIA ne se contente pas de tourner sur du matériel modeste — elle **optimise activement** sa consommation de ressources IA :

- **Filtrage de catalogue** : seuls les outils pertinents pour votre requête sont présentés au LLM, réduisant drastiquement le nombre de tokens consommés
- **Apprentissage de patterns** : les plans validés sont mémorisés et réutilisés sans rappeler le LLM
- **Message Windowing** : chaque composant ne voit que le contexte strictement nécessaire
- **Cache de prompts** : exploitation du cache natif des fournisseurs pour limiter les coûts récurrents

Ces optimisations combinées permettent une réduction significative de la consommation de tokens par rapport à une approche agentique naïve.

---

## 6. Transparence radicale

### 6.1. Pas de boîte noire

Quand un assistant cloud exécute une tâche, vous voyez le résultat. Mais combien d'appels IA ? Quels modèles ? Combien de tokens ? Quel coût ? Pourquoi cette décision ? Vous n'en savez rien.

LIA prend le parti inverse — **tout est visible, tout est auditable**.

### 6.2. Le panneau de debug intégré

Directement dans l'interface de chat, un panneau de debug expose en temps réel chaque conversation avec le détail de l'analyse d'intention (classification du message et score de confiance), du pipeline d'exécution (plan généré, appels outils avec entrées/sorties), du pipeline LLM (chaque appel IA avec modèle, durée, tokens et coût), du contexte injecté (souvenirs, documents RAG, journaux) et du cycle de vie complet de la requête.

### 6.3. Suivi des coûts au centime

Chaque message affiche son coût en tokens et en euros. L'utilisateur peut exporter sa consommation. L'administrateur dispose de dashboards temps réel avec jauges par utilisateur et quotas configurables.

Vous ne payez pas un abonnement qui masque les coûts réels. Vous voyez exactement ce que chaque interaction coûte, et vous pouvez optimiser : modèle économique pour le routage, plus puissant pour la réponse.

### 6.4. La confiance par la preuve

La transparence n'est pas un gadget technique. Elle change la relation avec votre assistant : vous **comprenez** ses décisions, vous **maîtrisez** vos coûts, vous **détectez** les problèmes. Vous faites confiance parce que vous pouvez vérifier — pas parce qu'on vous demande de croire.

---

## 7. Profondeur émotionnelle

### 7.1. Au-delà de la mémoire factuelle

Les grands assistants retiennent vos préférences et vos faits personnels. C'est utile, mais c'est plat. LIA va plus loin avec une compréhension **psychologique et émotionnelle** structurée.

Chaque souvenir porte un poids émotionnel (-10 à +10), un score d'importance, une nuance d'usage, et une catégorie psychologique. Ce n'est pas une simple base de données — c'est un profil qui comprend ce qui vous touche, ce qui vous motive, ce qui vous blesse.

### 7.2. Le Psyche Engine : une personnalité vivante

C'est le différenciateur le plus profond de LIA. ChatGPT, Gemini, Claude — tous ont une personnalité fixe. Chaque message est une page blanche émotionnelle. LIA est différente.

Le **Psyche Engine** donne à LIA un état psychologique dynamique qui évolue à chaque échange :

- **14 humeurs** qui fluctuent avec le ton de la conversation (sereine, curieuse, mélancolique, enjouée...)
- **16 émotions** qui se déclenchent et s'atténuent en réponse à vos mots
- **Une relation** qui s'approfondit message après message
- **Des traits de personnalité** (Big Five) hérités de la personnalité choisie
- **Des motivations** qui influencent la proactivité de l'assistant

Vous ne parlez pas à un outil — vous interagissez avec une entité dont le vocabulaire se réchauffe quand elle est touchée, dont les phrases raccourcissent sous la tension, dont l'humour surgit quand l'échange est léger. Et elle ne le dit jamais — elle le **montre**.

### 7.3. Les carnets de bord

LIA tient ses propres réflexions dans des **journaux personnels** : auto-réflexion, observations sur l'utilisateur, idées, apprentissages. Ces notes, rédigées à la première personne et colorées par la personnalité active, influencent organiquement les réponses futures.

C'est une forme d'introspection artificielle — l'assistant qui réfléchit sur ses interactions et développe ses propres perspectives. L'utilisateur garde le contrôle total : lecture, édition, suppression.

### 7.4. La sécurité émotionnelle

Quand un souvenir à forte charge émotionnelle négative est activé, LIA bascule automatiquement en mode protecteur : ne jamais plaisanter, ne jamais minimiser, ne jamais banaliser. L'assistant adapte son comportement à la réalité émotionnelle de la personne — pas un traitement uniforme pour tout le monde.

### 7.5. La connaissance de soi

LIA dispose d'une base de connaissances intégrée sur ses propres fonctionnalités, lui permettant de répondre aux questions sur ce qu'elle sait faire, comment elle fonctionne, et quelles sont ses limites.

---

## 8. Fiabilité de production

### 8.1. Le vrai défi de l'IA agentique

La grande majorité des projets d'IA agentique n'atteignent jamais la production. Coûts non maîtrisés, comportement non déterministe, absence de traces d'audit, coordination défaillante entre agents. LIA a résolu ces problèmes — et tourne en production 24/7 sur un Raspberry Pi.

### 8.2. Une stack d'observabilité professionnelle

LIA embarque une observabilité de grade production :

| Outil | Rôle |
| --- | --- |
| **Prometheus** | Métriques système et métier |
| **Grafana** | Dashboards de monitoring temps réel |
| **Tempo** | Traces distribuées de bout en bout |
| **Loki** | Agrégation de logs structurés |
| **Langfuse** | Tracing spécialisé des appels LLM |

Chaque requête est tracée de bout en bout, chaque appel LLM est mesuré, chaque erreur est contextualisée. Ce n'est pas du monitoring ajouté après coup — c'est une **décision architecturale fondamentale** documentée dans les Architecture Decision Records du projet.

### 8.3. Un pipeline anti-hallucination

Le système de réponse dispose d'un mécanisme anti-hallucination en trois couches : formatage des données avec limites explicites, directives imposant l'usage exclusif de données vérifiées, et gestion des cas limites. Le LLM est contraint de ne synthétiser que ce qui provient des résultats réels des outils.

### 8.4. Human-in-the-Loop à 6 niveaux

LIA ne refuse pas les actions sensibles — elle vous les **soumet** avec le niveau de détail adapté : approbation de plan, clarification, critique de brouillon, confirmation destructive, confirmation d'opérations en masse, review de modifications. Chaque approbation alimente l'apprentissage — le système s'accélère avec le temps.

---

## 9. Ouverture radicale

### 9.1. Zéro lock-in

ChatGPT vous lie à OpenAI. Gemini à Google. Copilot à Microsoft.

LIA vous connecte à **7 fournisseurs IA simultanément** : OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen, et Ollama (modèles locaux). Vous pouvez mixer : OpenAI pour la planification, Anthropic pour la réponse, DeepSeek pour les tâches de fond — tout configurable depuis l'interface d'administration, en un clic.

Si un fournisseur change ses tarifs ou dégrade son service, vous basculez instantanément. Aucune dépendance, aucun piège.

### 9.2. Standards ouverts

| Standard | Usage dans LIA |
| --- | --- |
| **MCP** (Model Context Protocol) | Connexion d'outils externes par utilisateur |
| **agentskills.io** | Skills injectables avec progressive disclosure |
| **OAuth 2.1 + PKCE** | Authentification pour tous les connecteurs |
| **OpenTelemetry** | Observabilité standardisée |
| **AGPL-3.0** | Code source complet, auditable, modifiable |

### 9.3. Extensibilité

Chaque utilisateur peut connecter ses propres serveurs MCP, étendant les capacités de LIA bien au-delà des outils intégrés. Les Skills (standard agentskills.io) permettent d'injecter des instructions expertes en langage naturel — avec un générateur de Skills intégré pour en créer facilement.

L'architecture de LIA est conçue pour faciliter l'ajout de nouveaux connecteurs, canaux, agents et fournisseurs IA. Le code est structuré avec des abstractions claires et des guides de développement dédiés (agent creation guide, tool creation guide) qui rendent l'extension accessible à tout développeur.

### 9.4. Multi-canal

L'interface web responsive est complétée par une intégration Telegram native (conversation, messages vocaux transcrits, boutons d'approbation inline, notifications proactives) et des notifications push Firebase. Votre mémoire, vos journaux, vos préférences vous suivent d'un canal à l'autre.

---

## 10. Vision

### 10.1. L'intelligence qui grandit avec vous

La combinaison mémoire psychologique + journaux introspectifs + apprentissage bayésien + Psyche Engine crée une forme d'intelligence émergente : au fil des mois, LIA développe une compréhension de plus en plus nuancée de qui vous êtes. Ce n'est pas de l'intelligence artificielle générale — c'est une intelligence **pratique, relationnelle et émotionnelle**, au service d'une personne spécifique.

### 10.2. Ce que LIA ne prétend pas être

LIA n'est pas un concurrent des géants du cloud et ne prétend pas rivaliser avec leurs budgets de recherche. En tant que chatbot conversationnel pur, les modèles utilisés via leur interface native seront probablement plus fluides. Mais LIA n'est pas un chatbot — c'est un **système d'orchestration intelligent** qui utilise ces modèles comme composants, sous votre contrôle total.

### 10.3. Pourquoi LIA existe

LIA existe parce que le monde manque d'un assistant IA qui soit **à vous**. Vraiment à vous. Simple à administrer au quotidien. Partageable avec vos proches, chacun avec sa propre relation émotionnelle. Hébergé sur votre serveur. Transparent sur chaque décision et chaque coût. Capable d'une profondeur émotionnelle que les assistants commerciaux n'offrent pas. Fiable en production. Et ouvert — ouvert sur les fournisseurs, les standards, et le code.

**Your Life. Your AI. Your Rules.**
