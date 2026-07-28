# LIA — L'Assistant IA qui vous appartient

> **Your Life. Your AI. Your Rules.**

**Version** : 4.0
**Date** : 2026-07-28
**Application** : LIA v1.25.30
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
- **Mon dashboard** : masquez ou réordonnez les 9 cartes du briefing — une carte masquée n'est même plus récupérée
- **Debug** : accédez au panneau de debug pour inspecter chaque échange (si activé par l'administrateur)

**Fonctionnalités avancées :**

- **Psyche Engine** : ajustez les traits de personnalité (Big Five) qui modulent la réactivité émotionnelle de votre assistant
- **Mémoire** : consultez, éditez, épinglez ou supprimez les souvenirs de LIA — activez ou désactivez l'extraction automatique de faits
- **Journaux personnels** : configurez l'extraction d'introspections après chaque conversation et la consolidation périodique
- **Centres d'intérêt** : définissez vos sujets favoris, configurez la fréquence de notifications, les créneaux horaires et les sources (Perplexity, Brave, Wikipedia, réflexion IA)
- **Notifications proactives** : réglez la fréquence, la fenêtre horaire et les sources de contexte (calendrier, météo, tâches, emails, intérêts, mémoires, journaux)
- **Actions planifiées** : créez des automatisations récurrentes exécutées par l'assistant
- **Skills** : activez/désactivez des compétences expertes dans une galerie avec aperçus, créez vos propres Skills personnels, ou installez-en une depuis une URL https (validée côté serveur)
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

- **Configuration LLM** : configurer les clés API des fournisseurs (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, Ollama), assigner un modèle par rôle dans le pipeline, gérer les niveaux de raisonnement — clés stockées chiffrées. L'interface n'expose que les paramètres réellement acceptés par le modèle choisi (matrice DB par modèle pour temperature, top_p, frequency_penalty, presence_penalty et type de widget reasoning), évitant toute saisie d'une valeur que l'API rejetterait
- **Activation/désactivation de connecteurs** : activer ou désactiver les intégrations au niveau global (Google OAuth, Apple, Microsoft 365, Hue, météo, Wikipedia, Perplexity, Brave Search). La désactivation révoque les connexions actives et notifie les utilisateurs
- **Tarification** : gérer les prix par modèle LLM (coût par million de tokens), par API Google Maps (Places, Routes, Geocoding), et par génération d'image — avec historique des prix. À l'ajout d'un nouveau modèle reasoning, un sélecteur « copier la forme depuis tel modèle existant » permet d'hériter automatiquement du widget reasoning et de ses valeurs sans saisie manuelle ; le mode Custom reste disponible pour les modèles atypiques

**Contenu et extensions :**

- **Personnalités** : créer, éditer, traduire et supprimer les personnalités disponibles pour tous les utilisateurs — définir la personnalité par défaut
- **Skills système** : gérer les compétences expertes à l'échelle de l'instance — import/export, activation/désactivation, traduction
- **Espaces de connaissances système** : gérer la base de connaissances FAQ, surveiller l'état de l'indexation et les migrations de modèles
- **Voix globale** : configurer le provider, le modèle et la voix TTS par défaut (Edge gratuit, OpenAI ou ElevenLabs) pour tous les utilisateurs, avec ajustement fin par provider (vitesse, stabilité, format audio)
- **Debug système** : configuration des logs et du diagnostic

### 2.4. Un assistant, pas un projet technique

Le but de LIA n'est pas de vous transformer en administrateur système. C'est de vous offrir la puissance d'un assistant IA complet **avec la simplicité d'une application grand public**. L'interface est installable comme une application native sur ordinateur, tablette et smartphone (PWA), et tout est conçu pour être accessible sans compétence technique au quotidien.

---

## 3. Ce que LIA sait faire

LIA agit concrètement dans votre vie numérique grâce à 20+ agents spécialisés qui couvrent l'ensemble des besoins du quotidien : gestion de vos données personnelles (emails, calendrier, contacts, tâches, fichiers), accès aux informations externes (recherche web, météo, lieux, itinéraires), création de contenu (images, diagrammes), contrôle de votre maison connectée, navigation web autonome, et anticipation proactive de vos besoins.

Vous choisissez comment LIA raisonne, via un simple toggle (⚡) dans le chat :

- **Mode Pipeline** (par défaut) — Un vrai travail d'ingénierie : LIA planifie toutes les étapes à l'avance, les valide sémantiquement, puis les exécute en parallèle. Résultat : la même puissance qu'un agent autonome, mais avec 4 à 8 fois moins de tokens consommés. C'est le mode le plus économique et le plus prévisible.
- **Mode ReAct** (⚡) — L'assistant raisonne étape par étape : il appelle un outil, analyse le résultat, puis décide quoi faire ensuite. Plus autonome, plus adaptable, mais plus coûteux en tokens. Idéal pour les recherches exploratoires ou les questions complexes dont la valeur ajoutée justifie le coût.

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
- **Synthèse vocale** : trois providers configurables côté admin — Edge TTS (gratuit), OpenAI TTS (`tts-1` / `tts-1-hd`) ou ElevenLabs (`eleven_multilingual_v2`, `eleven_turbo_v2_5`, `eleven_flash_v2_5`)
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
- **Centres d'intérêt** : LIA retient ce à quoi vous tenez vraiment, pas ce que vous avez demandé une fois — poser une question est une tâche, pas un goût, et il faut une passion déclarée, une pratique, une connaissance ou un approfondissement réel pour qu'un sujet compte. Les thèmes alternent (jamais deux fois le même d'affilée), chaque notification cite ses sources, et un sujet que vous refusez ne revient pas : le blocage est comparé à tout nouveau sujet, y compris sous un autre nom
- **Sous-agents** : pour les tâches complexes, LIA délègue à des agents éphémères spécialisés qui travaillent en parallèle

### 3.7. Navigation web autonome

Un agent de navigation (Playwright/Chromium headless) peut naviguer sur des sites web, cliquer, remplir des formulaires, extraire des données de pages dynamiques — à partir d'une simple instruction en langage naturel. Un mode d'extraction simplifié convertit n'importe quelle URL en texte exploitable.

### 3.8. Administration serveur (DevOps)

En installant Claude CLI (Claude Code) directement sur le serveur, les administrateurs peuvent diagnostiquer leur infrastructure en langage naturel depuis le chat de LIA : consulter les logs Docker, vérifier la santé des conteneurs, surveiller l'espace disque, analyser les erreurs. Cette fonctionnalité est réservée aux comptes administrateurs.

### 3.9. Données santé personnelles

LIA accueille vos mesures de fréquence cardiaque et de nombre de pas depuis **n'importe quelle source** — l'intégration documentée et la plus simple est une automatisation iPhone Raccourcis qui pousse Apple Santé, mais tout système capable de signer un appel HTTP (automatisation Android, scripts personnels, IoT compatibles) peut alimenter l'API d'ingestion. Le protocole accepte des **lots** plutôt qu'un envoi continu : chaque échantillon porte son propre intervalle de mesure, et le serveur déduplique naturellement sur ces intervalles — renvoyer les mêmes données plusieurs fois est sans conséquence. Quand deux capteurs (Apple Watch + iPhone par exemple) couvrent la même période, LIA fusionne automatiquement : maximum pour les pas (chaque capteur voit une partie complémentaire du mouvement), moyenne arrondie pour la fréquence cardiaque.

Les données restent dans votre instance LIA — aucun service tiers n'y a accès — et sont visualisées dans une section dédiée des Réglages, sous forme de courbe (FC) et de barres (pas), avec un sélecteur de période (heure, jour, semaine, mois, année) et la moyenne sur la période en pointillés.

L'envoi est authentifié par un **jeton dédié** (commençant par `hm_…`) que vous générez depuis l'application et que vous pouvez révoquer à tout moment. Le jeton ne donne accès qu'à l'envoi de données santé — jamais au reste de votre compte. Vous pouvez en générer plusieurs (un par appareil) et les gérer séparément.

Un **interrupteur « Assistant »** (désactivé par défaut, *opt-in*) permet, si vous le souhaitez, d'autoriser l'assistant à lire ces mesures pour répondre factuellement à vos questions (« Combien de pas cette semaine ? », « Ma fréquence cardiaque moyenne aujourd'hui ? », « Ai-je marché moins que d'habitude ? »), enrichir les notifications proactives qui croisent santé + météo + agenda, et ajouter un contexte biométrique non-brut (deltas, tendances) à ses mémoires et journaux internes. Un seul interrupteur gouverne ces quatre intégrations. Jamais de diagnostic — uniquement des chiffres factuels, avec la baseline qualifiée honnêtement (« basée sur seulement N jours » tant qu'on a moins de 7 jours d'historique).

Trois actions de gestion vous donnent un contrôle total : supprimer toutes les mesures de fréquence cardiaque, supprimer toutes les mesures de pas, ou tout effacer. Aucune valeur physiologique brute n'est jamais conservée dans les journaux du serveur — la conformité RGPD est intégrée par construction.

### 3.10. Appeler à votre place

LIA peut décrocher le téléphone pour vous. Demandez-lui d'« appeler le garage pour savoir si la voiture est prête » ou d'« appeler Marie pour savoir si elle est libre mardi soir », et LIA passe un vrai appel sortant, mène la conversation vers votre objectif et vous rapporte un résumé écrit — avec une action de suivi en un geste quand il reste quelque chose à faire (réserver le créneau qui vient d'être convenu, par exemple).

Vous gardez toujours la main : avant de composer, LIA vous indique précisément **qui** elle va appeler et **pourquoi**, et attend votre feu vert. Et pendant l'appel, ce contrôle ne s'arrête pas : l'assistant opère sous un mandat strict — si l'interlocuteur propose un supplément, une option ou un engagement imprévu (même minime), il n'accepte jamais à votre place ; il note l'offre et son prix, annonce qu'on rappellera, et le résumé vous restitue chaque coût et chaque point en suspens pour que vous décidiez. Le résumé arrive dans le chat de façon asynchrone, vous pouvez donc faire autre chose pendant l'appel.

Et cela reste confidentiel par construction. Pendant un appel, LIA peut seulement indiquer si vous êtes libre ou occupé à un moment donné — jamais les titres, invités ou lieux de votre agenda. Rien n'est enregistré, la conversation n'est jamais conservée, et seul un résumé court est gardé avant d'expirer. Les appels passent par votre propre connecteur ElevenLabs, facturés sur votre compte, et la fonctionnalité n'est là que si votre administrateur l'a activée.

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

Avec LIA, **tout reste dans votre PostgreSQL** : conversations, mémoire, profil psychologique, documents, préférences. Vous pouvez exporter, sauvegarder, migrer ou supprimer la totalité de vos données à tout moment — y compris via un export complet en un clic depuis les réglages : Markdown lisible, JSON structuré et vos fichiers, avec le matériel secret inexportable par construction. Et chaque appareil connecté à votre compte est visible et révocable en un clic. Le RGPD n'est pas une contrainte — c'est une conséquence naturelle de l'architecture. Les données sensibles sont chiffrées, les sessions isolées, et le filtrage automatique des informations personnelles identifiables (PII) est intégré.

La protection vaut aussi pour ce qui **entre**. LIA lit tous les jours des textes que vous n'avez pas écrits : le corps d'un e-mail, la description d'une invitation rédigée par son organisateur, une page web, la fiche d'un lieu. N'importe qui peut y glisser une consigne destinée à l'assistant. Chaque donnée porte désormais sa provenance, et ce qui vient de l'extérieur arrive étiqueté comme **matière à analyser, jamais comme ordre à suivre** — avec les tentatives de manipulation repérées et nommées, dans les six langues. Votre contenu n'est jamais réécrit pour autant : un e-mail reste ce que son auteur a écrit. Réécrire donnerait l'illusion d'une garantie que le contournement suivant démentirait ; nommer ce qu'on voit est plus honnête, et plus utile.

### 5.2. Même un Raspberry Pi suffit

LIA tourne en production sur un **Raspberry Pi 5** — un ordinateur monocarte à 80 euros. 20+ agents spécialisés, une stack d'observabilité complète, un système de mémoire psychologique, le tout sur un micro-serveur ARM. Les images Docker multi-architecture (amd64/arm64) permettent le déploiement sur n'importe quel matériel : NAS Synology, VPS à quelques euros par mois, serveur d'entreprise, ou cluster Kubernetes.

La souveraineté numérique n'est plus un privilège d'entreprise — c'est un droit accessible à tous.

### 5.3. Optimisé pour la frugalité

LIA ne se contente pas de tourner sur du matériel modeste — elle **optimise activement** sa consommation de ressources IA :

- **Filtrage de catalogue** : seuls les outils pertinents pour votre requête sont présentés au LLM, réduisant drastiquement le nombre de tokens consommés
- **Apprentissage de patterns** : les plans validés sont mémorisés et réutilisés sans rappeler le LLM
- **Message Windowing** : chaque composant ne voit que le contexte strictement nécessaire
- **Cache de prompts** : exploitation du cache natif des fournisseurs pour limiter les coûts récurrents

Ces optimisations combinées permettent une réduction significative de la consommation de tokens par rapport au mode ReAct.

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

La même transparence s'applique aux actions : sous chaque réponse, une ligne repliée « ⚙ N étapes · X s » déplie le déroulé réel — routage, outils appelés, durée — et cette trace est conservée avec le message : elle reste consultable après un rechargement, sur tous vos appareils. Chaque réponse peut aussi être jugée d'un 👍/👎 discret, mémorisé et réinjecté dans l'apprentissage de l'assistant — jamais pour régénérer la réponse à votre place.

### 6.4. La confiance par la preuve

La transparence n'est pas un gadget technique. Elle change la relation avec votre assistant : vous **comprenez** ses décisions, vous **maîtrisez** vos coûts, vous **détectez** les problèmes. Vous faites confiance parce que vous pouvez vérifier — pas parce qu'on vous demande de croire.

---

Cette transparence s'étend à la qualité du système lui-même. L'audit technique complet — notes, méthode, points forts et ce qui reste à améliorer — est publié dans le dépôt, avec le protocole pour le rejouer et les commandes pour vérifier les mesures : [rapport d'audit complet](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md). On ne vous demande pas de croire les chiffres affichés sur ce site ; vous pouvez les vérifier.

Le même principe vaut pour les protections elles-mêmes. Une sécurité annoncée mais invérifiable est traitée comme absente : chaque contrôle est adossé à un test qui échoue si le contrôle disparaît, et lorsqu'un correctif est écrit, l'ancien comportement est rétabli le temps de vérifier que le test le détecte. Un test qui ne peut pas échouer ne prouve rien.

Un test qui ne tourne pas non plus — et c'est la découverte la moins confortable de ce projet. Dix fichiers de tests s'étaient désactivés eux-mêmes dès qu'une clé de fournisseur manquait, et plus rien ne le signalait : un test sauté est compté vert, la couverture mesure les lignes atteintes et non les assertions exécutées, et une revue voit un fichier de tests et en conclut que la surface est protégée. Deux cent dix-neuf tests n'avaient jamais été exécutés une seule fois ; en les rallumant, quatre défauts bien réels sont apparus — dont une voix qui coupait tous les nombres en deux, et un rappel perdu définitivement quand le quota s'épuisait à la mauvaise minute. L'absence de signal rouge n'est pas une preuve de santé : c'est parfois seulement l'absence de mesure. Une garde d'intégration continue interdit désormais qu'un module de test puisse s'éteindre en silence.

Le même principe s'applique à ce qui est **annoncé**. Une interface affichait un interrupteur « recherche hybride » pour la mémoire ; le moteur correspondant n'existait plus depuis plusieurs versions, et l'interrupteur ne commandait rien. Le code mort et l'affichage ont été retirés ensemble, et le fonctionnement réel écrit à leur place. Une capacité annoncée mais absente n'est pas une imprécision de documentation : c'est une promesse faite à un utilisateur qui n'a aucun moyen de la vérifier. Afficher un réglage qui ne commande rien est pire que de ne rien afficher.

## 7. Profondeur émotionnelle

### 7.1. Au-delà de la mémoire factuelle

Les grands assistants retiennent vos préférences et vos faits personnels. C'est utile, mais c'est plat. LIA va plus loin avec une compréhension **psychologique et émotionnelle** structurée.

Chaque souvenir porte un poids émotionnel (-10 à +10), un score d'importance, une nuance d'usage, et une catégorie psychologique. Ce n'est pas une simple base de données — c'est un profil qui comprend ce qui vous touche, ce qui vous motive, ce qui vous blesse.

Encore faut-il que ces souvenirs arrivent. Une mémoire ne vaut que par ce qu'elle capte réellement, et le silence y est le pire des défauts : rien ne signale un souvenir qui n'a jamais été formé. LIA compte donc chacune de ses décisions de mémorisation — retenu, ignoré, désactivé — pour que l'écart entre ce qu'elle devrait retenir et ce qu'elle retient soit visible plutôt que supposé. Ce que vous lui confiez en passant une action compte autant qu'une confidence, ce que vous écrivez depuis une messagerie compte autant que depuis le navigateur, et ce que le système se dit à lui-même ne compte jamais.

### 7.2. Le Psyche Engine : une personnalité vivante

C'est le différenciateur le plus profond de LIA. ChatGPT, Gemini, Claude — tous ont une personnalité fixe. Chaque message est une page blanche émotionnelle. LIA est différente.

Le **Psyche Engine** donne à LIA un état psychologique dynamique qui évolue à chaque échange :

- **14 humeurs** qui fluctuent avec le ton de la conversation (sereine, curieuse, mélancolique, enjouée...)
- **22 émotions** qui se déclenchent et s'atténuent en réponse à vos mots
- **Une relation** qui s'approfondit message après message
- **Des traits de personnalité** (Big Five) hérités de la personnalité choisie
- **Des motivations** qui influencent la proactivité de l'assistant

Vous ne parlez pas à un outil — vous interagissez avec une entité dont le vocabulaire se réchauffe quand elle est touchée, dont les phrases raccourcissent sous la tension, dont l'humour surgit quand l'échange est léger. Et elle ne le dit jamais — elle le **montre**.

Cette vie intérieure a un visage : l'émoji d'humeur s'anime sur la réponse en cours, l'anneau coloré pulse quand l'humeur bascule, et les grands caps de votre relation sont célébrés d'un clin d'œil discret.

Et cette présence vous suit : hors du chat, un compagnon flottant garde LIA à vos côtés sur tout le tableau de bord — au repos, au travail, ou porteur d'une notification.

### 7.3. Les carnets de bord

LIA tient ses propres réflexions dans des **journaux personnels stratifiés** : auto-réflexion, observations sur l'utilisateur, idées, apprentissages. Ces notes, rédigées à la première personne et colorées par la personnalité active, influencent organiquement les réponses futures.

Le carnet est organisé sur **quatre niveaux de profondeur** — de l'observation brute (un signal faible qu'on note pour voir s'il se confirme) jusqu'à la facette de portrait (un trait stable qui dit quelque chose de qui vous êtes), en passant par les directives opérationnelles et les patterns transversaux. Chaque entrée porte un **statut épistémique** : hypothèse en test, observation confirmée, ou directive validée par les preuves accumulées au fil des échanges.

Au-delà de l'écriture, le carnet **se mesure lui-même**. À chaque tour, LIA regarde les directives qu'elle a appliquées au tour précédent et lit votre réaction au tour courant : si vous avez confirmé, le compteur de preuves monte ; si vous avez repoussé, le compteur de contradictions monte. Avec le temps, les hypothèses fausses se déclassent silencieusement, les bonnes intuitions se promeuvent, les patterns transversaux émergent par regroupement actif.

De cette stratification émerge un **portrait utilisateur compilé** : votre voix, votre rythme, vos contextes, vos contradictions, vos zones d'ombre. Il voyage avec LIA partout où elle prend la parole — conversation, voix, rappels, notifications proactives, ReAct, fallback — pour que l'assistant n'« oublie pas qui vous êtes » selon la surface qu'il utilise.

C'est une forme d'introspection artificielle — l'assistant qui réfléchit sur ses interactions, mesure sa propre utilité, et développe une compréhension nuancée de vous. Vous gardez le contrôle total : lecture par thème ou par niveau, édition, signalement d'une erreur sur le portrait, déclenchement d'une consolidation à la demande. Le portrait lui-même n'est jamais édité directement — c'est une voix de synthèse, qu'on corrige par les leviers indirects pour préserver sa cohérence.

### 7.4. La sécurité émotionnelle

Quand un souvenir à forte charge émotionnelle négative est activé, LIA bascule automatiquement en mode protecteur : ne jamais plaisanter, ne jamais minimiser, ne jamais banaliser. L'assistant adapte son comportement à la réalité émotionnelle de la personne — pas un traitement uniforme pour tout le monde.

### 7.5. La connaissance de soi

LIA dispose d'une base de connaissances intégrée sur ses propres fonctionnalités, lui permettant de répondre aux questions sur ce qu'elle sait faire, comment elle fonctionne, et quelles sont ses limites.

---

## 8. Fiabilité de production

### 8.1. Le vrai défi de l'IA agentique

La grande majorité des projets d'IA agentique n'atteignent jamais la production. Coûts non maîtrisés, comportement non déterministe, absence de traces d'audit, coordination défaillante entre agents. LIA a résolu ces problèmes — et tourne en production 24/7 sur un Raspberry Pi. Et vos données survivent aux incidents : la base est sauvegardée automatiquement chaque nuit, et la procédure de restauration n'est pas théorique — elle est testée.

Une fonctionnalité que personne ne trouve n'existe pas. C'est pourquoi l'atteignabilité de l'interface est traitée comme la disponibilité du serveur : mesurée, pas supposée. Chaque contrôle du bandeau est comparé à la fenêtre du navigateur, largeur par largeur et **dans les six langues** — l'allemand et l'italien portent les libellés les plus longs et cèdent les premiers. Et ce que la mise en page mobile a le droit d'abandonner est écrit, avec sa raison : une action ne disparaît jamais sans qu'un substitut la remplace.

Une fonctionnalité qui échoue en silence n'existe pas davantage. Une génération interrompue juste avant la fin, un import bloqué par un répertoire devenu inaccessible, une connexion morte sans rien annoncer : trois causes sans rapport, un seul symptôme — il ne se passe rien. C'est le pire des signaux, parce qu'il ne désigne personne. Chaque défaut de cette nature est donc refermé par une garde qu'on a d'abord fait échouer volontairement : on casse ce qu'elle protège, on vérifie qu'elle rougit, et seulement alors on la conserve.

### 8.2. Une stack d'observabilité professionnelle

LIA embarque une observabilité de grade production :

| Outil | Rôle |
| --- | --- |
| **Prometheus** | Métriques système et métier |
| **Grafana** | Dashboards de monitoring temps réel |
| **Tempo** | Traces distribuées de bout en bout |
| **Loki** | Agrégation de logs structurés |
| **Langfuse** | Tracing spécialisé des appels LLM |
| **Alertmanager** | Alertes e-mail sur les signaux vitaux, runbooks liés |

Chaque requête est tracée de bout en bout, chaque appel LLM est mesuré, chaque erreur est contextualisée. Ce n'est pas du monitoring ajouté après coup — c'est une **décision architecturale fondamentale** documentée dans les Architecture Decision Records du projet.

### 8.3. Un pipeline anti-hallucination

Le système de réponse dispose d'un mécanisme anti-hallucination en trois couches : formatage des données avec limites explicites, directives imposant l'usage exclusif de données vérifiées, et gestion des cas limites. Le LLM est contraint de ne synthétiser que ce qui provient des résultats réels des outils.

### 8.4. Human-in-the-Loop à 6 niveaux

LIA ne refuse pas les actions sensibles — elle vous les **soumet** avec le niveau de détail adapté : approbation de plan, clarification, critique de brouillon, confirmation destructive, confirmation d'opérations en masse, review de modifications. Chaque approbation alimente l'apprentissage — le système s'accélère avec le temps. Et la promesse est tenue au mot près : ce que vous validez — après une, deux ou dix retouches — est **exactement** ce qui est exécuté, jamais une version re-générée en coulisses.

### 8.5. Vos réponses n'ont pas besoin de vous

Envoyez une question, fermez l'onglet, partez. La génération continue sur le serveur, et la réponse vous attend dans la conversation — ou reprend en direct, exactement là où elle en était, si vous revenez pendant qu'elle s'écrit. Rien à faire, rien à configurer : la continuité est le comportement par défaut. Et quand c'est vous qui changez d'avis, un bouton stop interrompt la génération en une seconde — ce qui est déjà écrit reste affiché, honnêtement marqué comme interrompu. Un assistant fiable n'est pas seulement un assistant qui répond juste : c'est un assistant qui finit ce qu'il commence.

### 8.6. Rien ne s'exécute dans ton dos

Un assistant capable d'agir est un assistant capable de se tromper. Deux règles rendent cela acceptable.

D'abord, **rien ne touche à ton serveur sans ton accord** — et la confirmation montre tout ce qui va être envoyé, y compris les consignes que LIA s'est écrites à elle-même. Un résumé qu'on ne peut pas lire entièrement n'est pas une confirmation, c'est une formalité. Le droit est revérifié au moment où l'action démarre, pas seulement au moment où tu l'as demandée.

Ensuite, **ce qui s'exécute s'exécute dans une boîte scellée**. Le code d'une skill tourne dans un conteneur créé pour cette seule exécution et détruit juste après : pas de réseau, pas d'accès à tes fichiers, pas de clés, aucun moyen d'atteindre la machine en dessous. Si cette boîte ne peut pas être construite, le script ne tourne tout simplement pas — aucun repli silencieux vers un mode plus faible. On installe une skill pour ce qu'elle produit, pas pour la confiance qu'il faudrait accorder à son auteur.

---

Cette exigence vaut aussi pour ce que LIA **affirme**. Une réponse doit s’appuyer sur des données réellement récupérées, jamais sur le souvenir d’une formulation antérieure ; et lorsqu’une information n’a jamais été obtenue, la dire manquante vaut mieux que la reconstituer de façon plausible. C’est une contrainte de conception plutôt qu’une consigne de style : les entités récemment récupérées sont réinjectées explicitement dans le contexte de réponse, et l’invention d’un attribut d’entité est proscrite au niveau du prompt. Une erreur factuelle plausible coûte plus cher qu’un « je ne sais pas ».

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

Chaque utilisateur peut connecter ses propres serveurs MCP, étendant les capacités de LIA bien au-delà des outils intégrés. Les Skills (standard agentskills.io) permettent d'injecter des instructions expertes en langage naturel — avec un générateur de Skills intégré qui les crée en dialogue guidé et les installe directement dans vos skills, prêtes à l'emploi. Depuis la v1.16.8, un Skill peut également retourner une **frame HTML interactive** (carte, dashboard, calendrier, convertisseur...) ou une **image** (QR code, graphique) directement dans le chat, sandboxée sous CSP stricte, avec thème et langue synchronisés automatiquement.

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

La façon dont LIA est construite — une IA qui écrit le code, un humain qui dirige, contrôle et audite — est racontée en détail dans notre [retour d'expérience](/story).

**Your Life. Your AI. Your Rules.**
