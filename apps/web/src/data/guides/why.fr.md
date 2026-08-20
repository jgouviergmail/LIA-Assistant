# LIA — L'Assistant IA qui t’appartient

> **Your Life. Your AI. Your Rules.**

**Version** : 5.0
**Date** : 2026-08-20
**Application** : LIA v1.30.15
**Licence** : AGPL-3.0 (Open Source)

---

## Table des matières

1. [Le contexte](#1-le-contexte)
2. [Administration simple](#2-administration-simple)
3. [Ce que LIA sait faire](#3-ce-que-lia-sait-faire)
4. [Un serveur pour tes proches](#4-un-serveur-pour-tes-proches)
5. [Souverain et frugal](#5-souverain-et-frugal)
6. [Transparence radicale](#6-transparence-radicale)
7. [Profondeur émotionnelle](#7-profondeur-émotionnelle)
8. [Fiabilité de production](#8-fiabilité-de-production)
9. [Ouverture radicale](#9-ouverture-radicale)
10. [Vision](#10-vision)

---

## 1. Le contexte

L'ère des assistants IA agentiques est arrivée. ChatGPT, Gemini, Copilot, Claude — chacun propose un agent capable d'agir dans ta vie numérique : envoyer des emails, gérer ton agenda, rechercher sur le web, contrôler tes appareils.

Ces assistants sont remarquables. Mais ils partagent un modèle commun : tes données vivent sur leurs serveurs, l'intelligence est une boîte noire, et quand tu pars, tout reste derrière toi.

LIA prend un chemin différent. Pas un concurrent frontal des géants — un **assistant IA personnel que tu héberges, que tu comprends, et que tu contrôles**. LIA orchestre les meilleurs modèles d'IA du marché, agit dans ta vie numérique, et le fait avec des qualités fondamentales qui le distinguent.

---

## 2. Administration simple

### 2.1. Un déploiement guidé, puis zéro friction

L'auto-hébergement a mauvaise réputation. LIA ne prétend pas éliminer toute étape technique : la mise en place initiale — configuration des clés API, paramétrage des connecteurs OAuth, choix de l'infrastructure — demande un peu de temps et quelques compétences de base. Mais chaque étape est **documentée en détail** dans un guide de déploiement pas à pas.

Une fois cette phase d'installation terminée, **tout le quotidien se gère depuis une interface web intuitive**. Plus besoin de terminal ni de fichiers de configuration.

Depuis la v1.29.0, cette première phase est elle-même guidée : `./install.sh`, à la racine du dépôt, te pose un questionnaire court dans ta langue — comment tu veux accéder à l'instance, quelles clés fournisseur tu détiens — puis construit les images depuis le code que tu as cloné, applique les données de référence en une seule transaction, crée ton compte administrateur sans jamais écrire un secret sur la ligne de commande, et vérifie enfin que l'installation fonctionne réellement plutôt que de simplement répondre. Si une étape échoue, la reprise repart exactement où elle s'est arrêtée.

### 2.2. Ce que chaque utilisateur peut configurer

Chaque utilisateur dispose de son propre espace de paramétrage, organisé en deux onglets. Un champ de recherche évite d'avoir à les parcourir : tape le nom d'un réglage — ou un mot qui s'en approche dans ta langue — et LIA ouvre la bonne section, quel que soit l'onglet où elle se trouve.

**Préférences personnelles :**

- **Connecteurs personnels** : branche tes comptes Google, Microsoft ou Apple en quelques clics via OAuth — email, calendrier, contacts, tâches, Google Drive. Ou connecte Apple via IMAP/CalDAV/CardDAV. Clés API pour les services externes (météo, recherche)
- **Personnalité** : choisis parmi les personnalités disponibles (professeur, ami, philosophe, coach, poète...) — chacune influence le ton, le style et le comportement émotionnel de LIA
- **Voix** : configure le mode vocal — mot-clé de détection, sensibilité, seuil de silence, lecture automatique des réponses
- **Notifications** : gère les notifications push et les appareils enregistrés
- **Canaux** : relie Telegram pour chatter et recevoir des notifications sur mobile
- **Génération d'images** : active et configure la création d'images par IA
- **Serveurs MCP personnels** : connecte tes propres serveurs MCP pour étendre les capacités de LIA
- **Apparence** : langue, fuseau horaire, thème (5 palettes, mode sombre/clair), police (9 choix), format d'affichage des réponses (cartes HTML, HTML, Markdown)
- **Mon dashboard** : masque ou réordonne les 9 cartes du briefing — une carte masquée n'est même plus récupérée
- **Debug** : accède au panneau de debug pour inspecter chaque échange (si activé par l'administrateur)

**Fonctionnalités avancées :**

- **Psyche Engine** : ajuste les traits de personnalité (Big Five) qui modulent la réactivité émotionnelle de ton assistant
- **Mémoire** : consulte, édite, épingle ou supprime les souvenirs de LIA — active ou désactive l'extraction automatique de faits
- **Journaux personnels** : configure l'extraction d'introspections après chaque conversation et la consolidation périodique
- **Centres d'intérêt** : définis tes sujets favoris, configure la fréquence de notifications, les créneaux horaires et les sources (Perplexity, Brave, Wikipedia, réflexion IA)
- **Notifications proactives** : règle la fréquence, la fenêtre horaire et les sources de contexte (calendrier, météo, tâches, emails, intérêts, mémoires, journaux)
- **Actions planifiées** : crée des automatisations récurrentes exécutées par l'assistant
- **Skills** : active/désactive des compétences expertes dans une galerie avec aperçus, crée tes propres Skills personnels, ou installe-en une depuis une URL https (validée côté serveur)
- **Espaces de connaissances** : charge tes documents (PDF, Word, Excel, PowerPoint, EPUB, HTML et 15+ formats) ou synchronise un dossier Google Drive — indexation automatique avec recherche hybride
- **Export de consommation** : télécharge tes données de consommation LLM et API en CSV

### 2.3. Ce que l'administrateur contrôle

L'administrateur accède à un troisième onglet dédié à la gestion de l'instance :

**Utilisateurs et accès :**

- **Gestion des utilisateurs** : créer, activer/désactiver des comptes, visualiser les services connectés et les fonctionnalités activées par utilisateur
- **Limites d'usage** : définir des quotas par utilisateur (tokens LLM, appels API, générations d'images) avec suivi temps réel et blocage automatique
- **Messages broadcast** : envoyer des messages importants à tous les utilisateurs ou à une sélection, avec date d'expiration optionnelle
- **Export de consommation global** : exporter la consommation de tous les utilisateurs en CSV
- **Budget quotidien de l'instance** : borner ce que l'instance ENTIÈRE peut dépenser dans une journée, en euros — et pas seulement ce que consomme chaque compte. Le panneau affiche la dépense du jour, le nombre de runs, le plafond réellement appliqué et ce qu'il reste ; la valeur de l'opérateur ne peut que resserrer la borne du déploiement, jamais l'élargir. Budget épuisé, les utilisateurs apprennent que le déploiement est en pause et reçoivent l'heure exacte de remise à zéro, pas un message trompeur sur leur quota personnel
- **Capacités de plateforme** : activer ou couper dix capacités instantanément, sans redéploiement — dictée, synthèse vocale, images, téléversements, espaces documentaires, recherche web, navigation, compétences, MCP, téléphonie. Une capacité coupée disparaît aussi du catalogue offert au planificateur, donc LIA cesse de proposer ce que les routes refuseraient ; chaque ligne montre ce que le déploiement autorise, ce que tu as choisi, et ce qui s'applique réellement

**IA et connecteurs :**

- **Configuration LLM** : configurer les clés API des fournisseurs (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, Ollama), assigner un modèle par rôle dans le pipeline, gérer les niveaux de raisonnement — clés stockées chiffrées. L'interface n'expose que les paramètres réellement acceptés par le modèle choisi (matrice DB par modèle pour temperature, top_p, frequency_penalty, presence_penalty et type de widget reasoning), évitant toute saisie d'une valeur que l'API rejetterait
- **Activation/désactivation de connecteurs** : activer ou désactiver les intégrations au niveau global (Google OAuth, Apple, Microsoft 365, Hue, météo, Wikipedia, Perplexity, Brave Search). La désactivation révoque les connexions actives et notifie les utilisateurs
- **Tarification** : gérer les prix par modèle LLM (coût par million de tokens), par API Google Maps (Places, Routes, Geocoding), et par génération d'image — avec historique des prix. À l'ajout d'un nouveau modèle reasoning, un sélecteur « copier la forme depuis tel modèle existant » permet d'hériter automatiquement du widget reasoning et de ses valeurs sans saisie manuelle ; le mode Custom reste disponible pour les modèles atypiques. Les tarifs des modèles texte peuvent aussi varier selon l'heure UTC (fenêtres pleines/creuses, à la DeepSeek) : chaque appel est alors valorisé au tarif de son instant exact, et les statistiques d'usage collent à la facture réelle du fournisseur Enfin, la grille entière s'exporte en classeur Excel — notice traduite, listes déroulantes, contrôles de saisie — et se réimporte après édition hors ligne : LIA te montre le détail des changements champ par champ avant d'écrire quoi que ce soit, et une ligne absente du fichier ne supprime jamais rien

**Contenu et extensions :**

- **Personnalités** : créer, éditer, traduire et supprimer les personnalités disponibles pour tous les utilisateurs — définir la personnalité par défaut
- **Skills système** : gérer les compétences expertes à l'échelle de l'instance — import/export, activation/désactivation, traduction
- **Espaces de connaissances système** : gérer la base de connaissances FAQ, surveiller l'état de l'indexation et les migrations de modèles
- **Voix globale** : configurer le provider, le modèle et la voix TTS par défaut (Edge gratuit, OpenAI ou ElevenLabs) pour tous les utilisateurs, avec ajustement fin par provider (vitesse, stabilité, format audio)
- **Debug système** : configuration des logs et du diagnostic

### 2.4. Un assistant, pas un projet technique

Le but de LIA n'est pas de te transformer en administrateur système. C'est de t’offrir la puissance d'un assistant IA complet **avec la simplicité d'une application grand public**. L'interface est installable comme une application native sur ordinateur, tablette et smartphone (PWA), et tout est conçu pour être accessible sans compétence technique au quotidien.

---

## 3. Ce que LIA sait faire

LIA agit concrètement dans ta vie numérique grâce à 20+ agents spécialisés qui couvrent l'ensemble des besoins du quotidien : gestion de tes données personnelles (emails, calendrier, contacts, tâches, fichiers), accès aux informations externes (recherche web, météo, lieux, itinéraires), création de contenu (images, diagrammes, documents), contrôle de ta maison connectée, navigation web autonome, et anticipation proactive de tes besoins.

Tu choisis comment LIA raisonne, via un simple toggle (⚡) dans le chat :

- **Mode Pipeline** (par défaut) — Un vrai travail d'ingénierie : LIA planifie toutes les étapes à l'avance, les valide sémantiquement, puis les exécute en parallèle. Résultat : la même puissance qu'un agent autonome, mais avec 4 à 8 fois moins de tokens consommés. C'est le mode le plus économique et le plus prévisible.
- **Mode ReAct** (⚡) — L'assistant raisonne étape par étape : il appelle un outil, analyse le résultat, puis décide quoi faire ensuite. Plus autonome, plus adaptable, mais plus coûteux en tokens. Idéal pour les recherches exploratoires ou les questions complexes dont la valeur ajoutée justifie le coût.

### 3.1. Conversation naturelle

Parle à LIA comme à un assistant humain — pas de commandes à mémoriser, pas de syntaxe à respecter. LIA comprend et répond en 99+ langues, avec une interface disponible en 6 langues (français, anglais, allemand, espagnol, italien, chinois). Les réponses sont rendues en cartes visuelles HTML interactives, en HTML direct, ou en Markdown selon tes préférences.

### 3.2. Services connectés personnels

- **Email** : lire, rechercher, rédiger, envoyer, répondre, transférer — via Gmail, Outlook ou Apple Mail
- **Calendrier** : consulter, créer, modifier, supprimer des événements — via Google Calendar, Outlook Calendar ou Apple Calendar
- **Contacts** : rechercher, créer, modifier des contacts — via Google Contacts, Outlook Contacts ou Apple Contacts
- **Tâches** : gérer tes listes de tâches — via Google Tasks ou Microsoft To Do
- **Fichiers** : accéder à Google Drive pour rechercher et lire tes documents
- **Maison connectée** : contrôler ton éclairage Philips Hue — allumer/éteindre, luminosité, couleurs, scènes, gestion par pièce

### 3.3. Intelligence web et environnement

- **Recherche web** : recherche multi-sources (Brave Search, Perplexity, Wikipedia) pour des réponses complètes et sourcées
- **Météo** : conditions actuelles et prévisions à 5 jours, avec détection de changements (début/fin de pluie, chute de température, alertes vent)
- **Lieux et commerces** : recherche de lieux à proximité avec détails, horaires, avis
- **Itinéraires** : calcul d'itinéraires multi-modaux (voiture, marche, vélo, transports en commun) avec géolocalisation automatique
- **Position en déplacement** : quand ta position en direct n'est pas disponible (application mobile restée en veille), LIA utilise ta dernière position mémorisée — si tu l'as activée — plutôt que ton adresse personnelle, et annonce toujours l'âge de cette position au lieu de la présenter comme courante

### 3.4. Voix

LIA propose un mode vocal complet :

- **Push-to-Talk** : maintiens le bouton microphone pour parler, optimisé pour le mobile
- **Mot-clé "OK Guy"** : détection mains-libres exécutée **entièrement dans ton navigateur** via Sherpa-onnx WASM — aucun son n'est transmis tant que le mot-clé n'est pas détecté
- **Synthèse vocale** : trois providers configurables côté admin — Edge TTS (gratuit), OpenAI TTS (`tts-1` / `tts-1-hd`) ou ElevenLabs (`eleven_multilingual_v2`, `eleven_turbo_v2_5`, `eleven_flash_v2_5`)
- **Messages vocaux Telegram** : envoie des messages audio, LIA les transcrit et répond

### 3.5. Création et médias

- **Génération d'images** : crée des images par description textuelle, édite des photos existantes
- **Génération de documents** : demandez un CSV, un tableur Excel, un rapport Word, un PowerPoint ou un PDF — un modèle rédacteur dédié produit le contenu dans votre langue, un moteur de rendu local construit le vrai fichier, et il arrive en carte téléchargeable avec une échéance d'expiration explicite
- **Schémas Excalidraw** : génère des diagrammes et schémas directement dans la conversation
- **Pièces jointes** : joins photos et PDF — LIA analyse le contenu visuel et extrait le texte des documents
- **MCP Apps** : widgets interactifs directement dans le chat (formulaires, visualisations, mini-applications)

### 3.6. Proactivité et initiatives

LIA ne se contente pas de répondre — elle anticipe :

- **Notifications proactives** : LIA croise tes sources de contexte (calendrier, météo, tâches, emails, intérêts) et te notifie quand c'est genuinement utile — avec un système anti-spam intégré (quota quotidien, fenêtre horaire, cooldown)
- **Initiative conversationnelle** : pendant un échange, LIA vérifie proactivement les informations connexes — si la météo annonce de la pluie samedi, elle consulte ton calendrier pour signaler d'éventuelles activités en extérieur
- **Centres d'intérêt** : LIA retient ce à quoi tu tiens vraiment, pas ce que tu as demandé une fois — poser une question est une tâche, pas un goût, et il faut une passion déclarée, une pratique, une connaissance ou un approfondissement réel pour qu'un sujet compte. Les thèmes alternent (jamais deux fois le même d'affilée), chaque notification cite ses sources, et un sujet que tu refuses ne revient pas : le blocage est comparé à tout nouveau sujet, y compris sous un autre nom
- **Sous-agents** : pour les tâches complexes, LIA délègue à des agents éphémères spécialisés qui travaillent en parallèle

### 3.7. Navigation web autonome

Un agent de navigation (Playwright/Chromium headless) peut naviguer sur des sites web, cliquer, remplir des formulaires, extraire des données de pages dynamiques — à partir d'une simple instruction en langage naturel. Un mode d'extraction simplifié convertit n'importe quelle URL en texte exploitable.

### 3.8. Administration serveur (DevOps)

En installant Claude CLI (Claude Code) directement sur le serveur, les administrateurs peuvent diagnostiquer leur infrastructure en langage naturel depuis le chat de LIA : consulter les logs Docker, vérifier la santé des conteneurs, surveiller l'espace disque, analyser les erreurs. Cette fonctionnalité est réservée aux comptes administrateurs.

### 3.9. Données santé personnelles

LIA accueille tes mesures de fréquence cardiaque et de nombre de pas depuis **n'importe quelle source** — l'intégration documentée et la plus simple est une automatisation iPhone Raccourcis qui pousse Apple Santé, mais tout système capable de signer un appel HTTP (automatisation Android, scripts personnels, IoT compatibles) peut alimenter l'API d'ingestion. Le protocole accepte des **lots** plutôt qu'un envoi continu : chaque échantillon porte son propre intervalle de mesure, et le serveur déduplique naturellement sur ces intervalles — renvoyer les mêmes données plusieurs fois est sans conséquence. Quand deux capteurs (Apple Watch + iPhone par exemple) couvrent la même période, LIA fusionne automatiquement : maximum pour les pas (chaque capteur voit une partie complémentaire du mouvement), moyenne arrondie pour la fréquence cardiaque.

Les données restent dans ton instance LIA — aucun service tiers n'y a accès — et sont visualisées dans une section dédiée des Réglages, sous forme de courbe (FC) et de barres (pas), avec un sélecteur de période (heure, jour, semaine, mois, année) et la moyenne sur la période en pointillés.

L'envoi est authentifié par un **jeton dédié** (commençant par `hm_…`) que tu génères depuis l'application et que tu peux révoquer à tout moment. Le jeton ne donne accès qu'à l'envoi de données santé — jamais au reste de ton compte. Tu peux en générer plusieurs (un par appareil) et les gérer séparément.

Un **interrupteur « Assistant »** (désactivé par défaut, *opt-in*) permet, si tu le souhaites, d'autoriser l'assistant à lire ces mesures pour répondre factuellement à tes questions (« Combien de pas cette semaine ? », « Ma fréquence cardiaque moyenne aujourd'hui ? », « Ai-je marché moins que d'habitude ? »), enrichir les notifications proactives qui croisent santé + météo + agenda, et ajouter un contexte biométrique non-brut (deltas, tendances) à ses mémoires et journaux internes. Un seul interrupteur gouverne ces quatre intégrations. Jamais de diagnostic — uniquement des chiffres factuels, avec la baseline qualifiée honnêtement (« basée sur seulement N jours » tant qu'on a moins de 7 jours d'historique).

Trois actions de gestion te donnent un contrôle total : supprimer toutes les mesures de fréquence cardiaque, supprimer toutes les mesures de pas, ou tout effacer. Aucune valeur physiologique brute n'est jamais conservée dans les journaux du serveur — la conformité RGPD est intégrée par construction.

### 3.10. Appeler à ta place

LIA peut décrocher le téléphone pour toi. Demande-lui d'« appeler le garage pour savoir si la voiture est prête » ou d'« appeler Marie pour savoir si elle est libre mardi soir », et LIA passe un vrai appel sortant, mène la conversation vers ton objectif et te rapporte un résumé écrit — avec une action de suivi en un geste quand il reste quelque chose à faire (réserver le créneau qui vient d'être convenu, par exemple).

Tu gardes toujours la main : avant de composer, LIA t’indique précisément **qui** elle va appeler et **pourquoi**, et attend ton feu vert. Et pendant l'appel, ce contrôle ne s'arrête pas : l'assistant opère sous un mandat strict — si l'interlocuteur propose un supplément, une option ou un engagement imprévu (même minime), il n'accepte jamais à ta place ; il note l'offre et son prix, annonce qu'on rappellera, et le résumé te restitue chaque coût et chaque point en suspens pour que tu décides. Le résumé arrive dans le chat de façon asynchrone, tu peux donc faire autre chose pendant l'appel.

Et cela reste confidentiel par construction. Pendant un appel, LIA peut seulement indiquer si tu es libre ou occupé à un moment donné — jamais les titres, invités ou lieux de ton agenda. Rien n'est enregistré, la conversation n'est jamais conservée, et seul un résumé court est gardé avant d'expirer. Les appels passent par ton propre connecteur ElevenLabs, facturés sur ton compte, et la fonctionnalité n'est là que si ton administrateur l'a activée.

### 3.11. Parler à tes proches, d’assistant à assistant

Sur une même instance, deux utilisateurs peuvent se connecter — et leurs assistants se parlent. Tu dis « demande à Marie si elle est libre mardi », tu valides la formulation exacte, et c’est l’assistant de Marie qui lui transmet le message, avec sa personnalité à elle, en te nommant ; le tien te confirme la remise. Chaque connexion peut aussi ouvrir des partages choisis, en lecture seule : tes disponibilités de calendrier, les titres de tes tâches — rien de plus, rien par défaut.

La protection des personnes prime sur la fonctionnalité : la découverte est volontaire et sur identité exacte uniquement — nom complet ou adresse, jamais un fragment, le blocage est silencieux (l’autre ne l’apprend jamais), et un inconnu, un refus ou un blocage reçoivent exactement la même réponse — impossible de sonder qui existe. Chaque accès à un partage est re-vérifié à l’instant de la lecture et journalisé, et le contenu des messages relayés s’efface au bout de trente jours, ne laissant que la trace de l’échange.
### 3.12. Ce qui te lie à quelqu'un, rassemblé

La page **Relations** réunit, personne par personne, ce que LIA suit déjà : les engagements ouverts entre vous, les appels passés, les souvenirs qui la mentionnent, les messages que vos assistants se sont transmis. Rien de nouveau n'est collecté — c'est une lentille posée sur ce qui existe déjà.

Tu peux aussi le demander à voix haute, sans ouvrir la page : « de quand date mon dernier appel à Marie ? », « qu'est-ce que je lui dois ? ». La réponse vient du même calcul que la fiche, si bien que l'assistant et la page ne peuvent pas te dire deux choses différentes — et le total annoncé est exact, jamais la longueur de ce qui tient à l'écran.

Reste ce qu'aucun système ne peut deviner. LIA regroupe ce qui s'écrit pareil, aux accents et aux majuscules près ; elle ne peut pas savoir qu'un numéro noté un jour et un nom sont la même personne, ni que « Papa » est quelqu'un en particulier. C'est un jugement, et il te revient : tu le dis une fois, depuis la fiche, et c'est **réversible** — la fusion s'affiche avec son annulation, rien n'est réécrit dans tes sources. Un regroupement d'affichage ne change d'ailleurs jamais à qui un message est adressé.


---

## 4. Un serveur pour tes proches

### 4.1. LIA est un serveur web partagé

Contrairement aux assistants cloud personnels (un compte = un utilisateur), LIA est conçu comme un **serveur centralisé** que tu déploies une fois et partage avec ta famille, tes amis, ou ton équipe.

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
- **Un plafond à l'échelle de l'instance**, au-dessus de ceux par utilisateur : N comptes × leur quota est une dépense non bornée, donc un plafond quotidien en euros borne le déploiement lui-même. C'est premier arrivé, premier servi — et là où une limite par utilisateur échoue ouverte, une dépense d'instance inconnue échoue fermée

### 4.3. Ton IA de famille

Imagine : un Raspberry Pi dans ton salon, et toute la famille qui profite d'un assistant IA intelligent — chacun avec son expérience personnalisée, ses souvenirs, son style de conversation, et un assistant qui développe sa propre relation émotionnelle avec lui. Le tout sous ton contrôle, sans abonnement cloud, sans données qui partent chez un tiers.

---

## 5. Souverain et frugal

### 5.1. Tes données restent chez toi

Quand tu utilises ChatGPT, tes conversations vivent sur les serveurs d'OpenAI. Avec Gemini, chez Google. Avec Copilot, chez Microsoft.

Avec LIA, **tout reste dans ton PostgreSQL** : conversations, mémoire, profil psychologique, documents, préférences. Tu peux exporter, sauvegarder, migrer ou supprimer la totalité de tes données à tout moment — y compris via un export complet en un clic depuis les réglages : Markdown lisible, JSON structuré et tes fichiers, avec le matériel secret inexportable par construction. Et chaque appareil connecté à ton compte est visible et révocable en un clic. Le RGPD n'est pas une contrainte — c'est une conséquence naturelle de l'architecture. Les données sensibles sont chiffrées, les sessions isolées, et le filtrage automatique des informations personnelles identifiables (PII) est intégré. Ta position suit la même doctrine : la mémorisation de la dernière position est un choix explicite, chiffrée comme le reste, jamais historisée — chaque mise à jour écrase la précédente — et effacée dès que tu désactives l'option.

La protection vaut aussi pour ce qui **entre**. LIA lit tous les jours des textes que tu n’as pas écrits : le corps d'un e-mail, la description d'une invitation rédigée par son organisateur, une page web, la fiche d'un lieu. N'importe qui peut y glisser une consigne destinée à l'assistant. Chaque donnée porte désormais sa provenance, et ce qui vient de l'extérieur arrive étiqueté comme **matière à analyser, jamais comme ordre à suivre** — avec les tentatives de manipulation repérées et nommées, dans les six langues. Ton contenu n'est jamais réécrit pour autant : un e-mail reste ce que son auteur a écrit. Réécrire donnerait l'illusion d'une garantie que le contournement suivant démentirait ; nommer ce qu'on voit est plus honnête, et plus utile.

### 5.2. Même un Raspberry Pi suffit

LIA tourne en production sur un **Raspberry Pi 5** — un ordinateur monocarte à 80 euros. 20+ agents spécialisés, une stack d'observabilité complète, un système de mémoire psychologique, le tout sur un micro-serveur ARM. Les images Docker multi-architecture (amd64/arm64) permettent le déploiement sur n'importe quel matériel : NAS Synology, VPS à quelques euros par mois, serveur d'entreprise, ou cluster Kubernetes.

La souveraineté numérique n'est plus un privilège d'entreprise — c'est un droit accessible à tous.

### 5.3. Optimisé pour la frugalité

LIA ne se contente pas de tourner sur du matériel modeste — elle **optimise activement** sa consommation de ressources IA :

- **Filtrage de catalogue** : seuls les outils pertinents pour ta requête sont présentés au LLM, réduisant drastiquement le nombre de tokens consommés
- **Apprentissage de patterns** : les plans validés sont mémorisés et réutilisés sans rappeler le LLM
- **Message Windowing** : chaque composant ne voit que le contexte strictement nécessaire
- **Cache de prompts** : exploitation du cache natif des fournisseurs pour limiter les coûts récurrents

Ces optimisations combinées permettent une réduction significative de la consommation de tokens par rapport au mode ReAct.

---

## 6. Transparence radicale

### 6.1. Pas de boîte noire

Quand un assistant cloud exécute une tâche, tu vois le résultat. Mais combien d'appels IA ? Quels modèles ? Combien de tokens ? Quel coût ? Pourquoi cette décision ? Tu n'en sais rien.

LIA prend le parti inverse — **tout est visible, tout est auditable**.

### 6.2. Le panneau de debug intégré

Directement dans l'interface de chat, un panneau de debug expose en temps réel chaque conversation avec le détail de l'analyse d'intention (classification du message et score de confiance), du pipeline d'exécution (plan généré, appels outils avec entrées/sorties), du pipeline LLM (chaque appel IA avec modèle, durée, tokens et coût), du contexte injecté (souvenirs, documents RAG, journaux) et du cycle de vie complet de la requête.

### 6.3. Suivi des coûts au centime

Chaque message affiche son coût en tokens et en euros. L'utilisateur peut exporter sa consommation. L'administrateur dispose de dashboards temps réel avec jauges par utilisateur et quotas configurables.

Tu ne paies pas un abonnement qui masque les coûts réels. Tu vois exactement ce que chaque interaction coûte, et tu peux optimiser : modèle économique pour le routage, plus puissant pour la réponse.

La même transparence s'applique aux actions : sous chaque réponse, une ligne repliée « ⚙ N étapes · X s » déplie le déroulé réel — routage, outils appelés, durée — et cette trace est conservée avec le message : elle reste consultable après un rechargement, sur tous tes appareils. Chaque réponse peut aussi être jugée d'un 👍/👎 discret, mémorisé et réinjecté dans l'apprentissage de l'assistant — jamais pour régénérer la réponse à ta place.

### 6.4. La confiance par la preuve

La transparence n'est pas un gadget technique. Elle change la relation avec ton assistant : tu **comprends** ses décisions, tu **maîtrises** tes coûts, tu **détectes** les problèmes. Tu fais confiance parce que tu peux vérifier — pas parce qu'on te demande de croire.

---

Cette transparence s'étend à la qualité du système lui-même. L'audit technique complet — notes, méthode, points forts et ce qui reste à améliorer — est publié dans le dépôt, avec le protocole pour le rejouer et les commandes pour vérifier les mesures : [rapport d'audit complet](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md). On ne te demande pas de croire les chiffres affichés sur ce site ; tu peux les vérifier.

La même honnêteté s'applique à l'utilité elle-même : LIA mesure si elle aide réellement — un résultat ne compte qu'une fois validé par te, explicitement ou en laissant une action non corrigée — et cette mesure vit dans la même base locale que tes données, sans jamais impliquer de plateforme d'analytics tierce.

Et elle s'applique aux confirmations : LIA ne t'annonce jamais comme accompli ce que ses propres outils ont refusé. Le verdict de chaque outil — succès ou refus, avec sa cause — traverse le système tel quel, jusqu'à la réponse. Si un message est trop long pour partir, tu ne reçois pas un « c'est envoyé » : tu reçois la longueur exacte, la limite, et une proposition pour le raccourcir.

Le même principe vaut pour les protections elles-mêmes. Une sécurité annoncée mais invérifiable est traitée comme absente : chaque contrôle est adossé à un test qui échoue si le contrôle disparaît, et lorsqu'un correctif est écrit, l'ancien comportement est rétabli le temps de vérifier que le test le détecte. Un test qui ne peut pas échouer ne prouve rien.

Un test qui ne tourne pas non plus — et c'est la découverte la moins confortable de ce projet. Dix fichiers de tests s'étaient désactivés eux-mêmes dès qu'une clé de fournisseur manquait, et plus rien ne le signalait : un test sauté est compté vert, la couverture mesure les lignes atteintes et non les assertions exécutées, et une revue voit un fichier de tests et en conclut que la surface est protégée. Deux cent dix-neuf tests n'avaient jamais été exécutés une seule fois ; en les rallumant, quatre défauts bien réels sont apparus — dont une voix qui coupait tous les nombres en deux, et un rappel perdu définitivement quand le quota s'épuisait à la mauvaise minute. L'absence de signal rouge n'est pas une preuve de santé : c'est parfois seulement l'absence de mesure. Une garde d'intégration continue interdit désormais qu'un module de test puisse s'éteindre en silence.

Le même principe s'applique à ce qui est **annoncé**. Une interface affichait un interrupteur « recherche hybride » pour la mémoire ; le moteur correspondant n'existait plus depuis plusieurs versions, et l'interrupteur ne commandait rien. Le code mort et l'affichage ont été retirés ensemble, et le fonctionnement réel écrit à leur place. Une capacité annoncée mais absente n'est pas une imprécision de documentation : c'est une promesse faite à un utilisateur qui n'a aucun moyen de la vérifier. Afficher un réglage qui ne commande rien est pire que de ne rien afficher.

### 6.5. Pourquoi LIA pense cela

Un assistant qui retient des choses finit par en affirmer. « Vous préférez les réunions le matin », « ce sujet vous intéresse » : des conclusions utiles, mais invérifiables tant qu'on ne peut pas remonter à ce qui les a produites.

Sous chaque souvenir, chaque entrée de journal et chaque centre d'intérêt, LIA montre donc les signaux qui l'ont amenée là : la conversation, la date, et le rôle du signal — ce qui a fait naître la conclusion, ce qui l'a confirmée, ce qui l'a mise en doute. Un bouton permet de corriger la conclusion à sa source.

Ce qui est conservé est un **renvoi, jamais une copie**. Le texte reste là où vous l'avez écrit, et si vous supprimez la conversation, il ne revient nulle part : le renvoi se vide, la ligne reste datée, et LIA dit simplement que le signal a été supprimé. Une suppression doit rester une suppression — autrement, ce que vous effacez d'un côté vous serait resservi de l'autre.

Le même principe s'applique au poids d'un centre d'intérêt : il s'explique au lieu de se noter. Le signal d'origine, la dernière mention, le calcul lui-même — de quoi refaire l'opération. Transformer cette incertitude en score inviterait à une compétition que personne n'a demandée, alors qu'elle n'apprend rien de plus.

### 6.6. Lisible sans effort

La transparence ne s'arrête pas à ce que le système montre : elle porte aussi sur la façon dont il le montre. Un écran où tout a le même poids demande au lecteur de faire le tri lui-même, et ce travail-là n'a aucune raison de lui revenir.

Une alerte urgente ne ressemble donc pas à une alerte ordinaire — et ce n'est pas seulement affaire de couleur. Deux teintes voisines se confondent sur un écran, à plus forte raison sur un téléphone, en plein soleil, ou pour qui les distingue mal. Ce qui sépare les niveaux ici, c'est la **densité** : un fond plein contre une teinte légère, une différence qui tient même en noir et blanc.

Le même principe vaut partout : un compteur porte la couleur des autres compteurs, un bouton d'action a la même forme d'un écran à l'autre, un message envoyé ne se distingue pas d'un message reçu par une seule petite flèche. Rien de tout cela n'ajoute d'information — tout cela fait gagner du temps sur ce qui est déjà là.

Et la couleur ne porte jamais seule le sens : chaque étiquette garde son mot. Une interface qui ne fonctionne qu'en couleurs ne fonctionne pas pour tout le monde.

### 6.4. Même ce que LIA apprend de toi est inspectable

La même transparence couvre l'apprentissage des habitudes : ce que LIA croit savoir de ton rythme et de tes demandes récurrentes vit dans un panneau dédié — carte de chaleur de tes 24 heures, pourcentage de jours actifs, barre de progression vers les premières détections, et pour chaque habitude les jours réels où elle a été observée plus les seuils exacts appliqués par le détecteur. Quand il n'y a pas d'habitude stable, le panneau le dit au lieu d'en inventer une. Pause, blocage définitif, suppression totale, recalcul rétroactif immédiat — et toute la fonction est éteinte tant que tu ne l'actives pas.

### 6.5. Une surface qui décrit le produit y est tenue

La transparence a un mode de défaillance que personne ne remarque : un écran qui cesse discrètement de dire vrai. La carte des capacités — la page qui répond *qu'est-ce que mon assistant sait faire pour moi ?* — a publié treize entrées figées pendant des mois, tandis que le produit gagnait la génération d'images, les documents, les plugins, les habitudes apprises, les serveurs MCP et les appels téléphoniques. Rien n'était cassé, aucun test ne virait au rouge, et la page qui existait pour être à jour était devenue la moins à jour de l'application. Une consigne écrite demandait déjà de la maintenir ; les consignes sont précisément ce qu'un mois chargé érode. La règle est donc devenue mécanique : deux tables déclarées doivent rendre compte de chaque capacité que la plateforme sait couper, chaque exclusion portant une raison écrite, et une assertion s'exécute au chargement du code — une capacité livrée sans décider de sa place sur la carte empêche l'application de démarrer. La même conviction, d'un cran plus loin : ce qu'un écran affirme de tes données doit être **exact ou absent**. Un décompte est le nombre que rend la base, jamais une longueur qui traînait à portée de main ; et tant que la réponse est en route, ou quand elle a échoué, la carte ne dit rien plutôt que de deviner. « Rien de configuré » est une affirmation sur ton compte — de celles dont il vaut mieux être sûr avant de les prononcer.

La transparence vaut aussi pour les règles internes de l'assistant. Une contrainte que le système applique doit être publiée à qui la subit : quand l'apprentissage des habitudes ne détecte rien, les Réglages affichent le seuil réellement exigé — plus strict le week-end, où les jours observés sont moins nombreux — au lieu d'un silence inexpliqué. Et quand un réglage s'ajuste tout seul, comme le seuil qui décide qu'une note du journal entre dans une réponse, il le fait dans des bornes strictes, un petit pas par jour, avec un interrupteur d'arrêt et chaque ajustement compté : un système qui apprend n'est acceptable que s'il reste observable et débrayable.

## 7. Profondeur émotionnelle

### 7.1. Au-delà de la mémoire factuelle

Les grands assistants retiennent tes préférences et tes faits personnels. C'est utile, mais c'est plat. LIA va plus loin avec une compréhension **psychologique et émotionnelle** structurée.

Chaque souvenir porte un poids émotionnel (-10 à +10), un score d'importance, une nuance d'usage, et une catégorie psychologique. Ce n'est pas une simple base de données — c'est un profil qui comprend ce qui te touche, ce qui te motive, ce qui te blesse.

Encore faut-il que ces souvenirs arrivent. Une mémoire ne vaut que par ce qu'elle capte réellement, et le silence y est le pire des défauts : rien ne signale un souvenir qui n'a jamais été formé. LIA compte donc chacune de ses décisions de mémorisation — retenu, ignoré, désactivé — pour que l'écart entre ce qu'elle devrait retenir et ce qu'elle retient soit visible plutôt que supposé. Ce que tu lui confies en passant une action compte autant qu'une confidence, ce que tu écris depuis une messagerie compte autant que depuis le navigateur, et ce que le système se dit à lui-même ne compte jamais.

### 7.2. Le Psyche Engine : une personnalité vivante

C'est le différenciateur le plus profond de LIA. ChatGPT, Gemini, Claude — tous ont une personnalité fixe. Chaque message est une page blanche émotionnelle. LIA est différente.

Le **Psyche Engine** donne à LIA un état psychologique dynamique qui évolue à chaque échange :

- **14 humeurs** qui fluctuent avec le ton de la conversation (sereine, curieuse, mélancolique, enjouée...)
- **22 émotions** qui se déclenchent et s'atténuent en réponse à tes mots
- **Une relation** qui s'approfondit message après message
- **Des traits de personnalité** (Big Five) hérités de la personnalité choisie
- **Des motivations** qui influencent la proactivité de l'assistant

Tu ne parles pas à un outil — tu interagis avec une entité dont le vocabulaire se réchauffe quand elle est touchée, dont les phrases raccourcissent sous la tension, dont l'humour surgit quand l'échange est léger. Et elle ne le dit jamais — elle le **montre**.

Cette vie intérieure a un visage : l'émoji d'humeur s'anime sur la réponse en cours, l'anneau coloré pulse quand l'humeur bascule, et les grands caps de ta relation sont célébrés d'un clin d'œil discret.

Et cette présence te suit : hors du chat, un compagnon flottant garde LIA à tes côtés sur tout le tableau de bord — au repos, au travail, ou porteur d'une notification.

### 7.3. Les carnets de bord

LIA tient ses propres réflexions dans des **journaux personnels stratifiés** : auto-réflexion, observations sur l'utilisateur, idées, apprentissages. Ces notes, rédigées à la première personne et colorées par la personnalité active, influencent organiquement les réponses futures.

Le carnet est organisé sur **quatre niveaux de profondeur** — de l'observation brute (un signal faible qu'on note pour voir s'il se confirme) jusqu'à la facette de portrait (un trait stable qui dit quelque chose de qui tu es), en passant par les directives opérationnelles et les patterns transversaux. Chaque entrée porte un **statut épistémique** : hypothèse en test, observation confirmée, ou directive validée par les preuves accumulées au fil des échanges.

Au-delà de l'écriture, le carnet **se mesure lui-même**. À chaque tour, LIA regarde les directives qu'elle a appliquées au tour précédent et lit ton réaction au tour courant : si tu as confirmé, le compteur de preuves monte ; si tu as repoussé, le compteur de contradictions monte. Avec le temps, les hypothèses fausses se déclassent silencieusement, les bonnes intuitions se promeuvent, les patterns transversaux émergent par regroupement actif.

De cette stratification émerge un **portrait utilisateur compilé** : ta voix, ton rythme, tes contextes, tes contradictions, tes zones d'ombre. Il voyage avec LIA partout où elle prend la parole — conversation, voix, rappels, notifications proactives, ReAct, fallback — pour que l'assistant n'« oublie pas qui tu es » selon la surface qu'il utilise.

C'est une forme d'introspection artificielle — l'assistant qui réfléchit sur ses interactions, mesure sa propre utilité, et développe une compréhension nuancée de te. Tu gardes le contrôle total : lecture par thème ou par niveau, édition, signalement d'une erreur sur le portrait, déclenchement d'une consolidation à la demande. Le portrait lui-même n'est jamais édité directement — c'est une voix de synthèse, qu'on corrige par les leviers indirects pour préserver sa cohérence.

### 7.4. La sécurité émotionnelle

Quand un souvenir à forte charge émotionnelle négative est activé, LIA bascule automatiquement en mode protecteur : ne jamais plaisanter, ne jamais minimiser, ne jamais banaliser. L'assistant adapte son comportement à la réalité émotionnelle de la personne — pas un traitement uniforme pour tout le monde.

### 7.5. La connaissance de soi

LIA dispose d'une base de connaissances intégrée sur ses propres fonctionnalités, lui permettant de répondre aux questions sur ce qu'elle sait faire, comment elle fonctionne, et quelles sont ses limites.

---

## 8. Fiabilité de production

### 8.1. Le vrai défi de l'IA agentique

La grande majorité des projets d'IA agentique n'atteignent jamais la production. Coûts non maîtrisés, comportement non déterministe, absence de traces d'audit, coordination défaillante entre agents. LIA a résolu ces problèmes — et tourne en production 24/7 sur un Raspberry Pi. Et tes données survivent aux incidents : la base est sauvegardée automatiquement chaque nuit, et la procédure de restauration n'est pas théorique — elle est testée.

Une fonctionnalité que personne ne trouve n'existe pas. C'est pourquoi l'atteignabilité de l'interface est traitée comme la disponibilité du serveur : mesurée, pas supposée. Chaque contrôle du bandeau est comparé à la fenêtre du navigateur, largeur par largeur et **dans les six langues** — l'allemand et l'italien portent les libellés les plus longs et cèdent les premiers. Et ce que la mise en page mobile a le droit d'abandonner est écrit, avec sa raison : une action ne disparaît jamais sans qu'un substitut la remplace.

Une fonctionnalité qui échoue en silence n'existe pas davantage. Une génération interrompue juste avant la fin, un import bloqué par un répertoire devenu inaccessible, une connexion morte sans rien annoncer : trois causes sans rapport, un seul symptôme — il ne se passe rien. C'est le pire des signaux, parce qu'il ne désigne personne. Chaque défaut de cette nature est donc refermé par une garde qu'on a d'abord fait échouer volontairement : on casse ce qu'elle protège, on vérifie qu'elle rougit, et seulement alors on la conserve.

Il y a plus insidieux qu'une garde qu'on n'a jamais fait échouer : une garde qui observe le mauvais signal. Trois en-têtes de l'interface se déclaraient fixes pendant le défilement, et aucun ne l'était — sur tous les écrans, depuis l'origine. Rien ne l'avait vu, parce qu'aucune vérification ne mesurait une position *pendant* un défilement : toutes observaient une page au repos, précisément l'état où le défaut n'existe pas. Corriger la cause n'était donc que la moitié du travail ; il a fallu ajouter la mesure qui manquait, puis rétablir l'ancien réglage pour vérifier qu'elle rougissait bel et bien.

Plus retors encore qu'une garde mal orientée : un défaut qui ne se produit qu'une fois sur deux. La même demande échouait, puis passait trente minutes plus tard sans qu'une seule ligne n'ait changé — de quoi conclure « c'était passager » et refermer le dossier. La cause tenait à un détail invisible : le choix des outils se fait sur une reformulation anglaise produite par un modèle, régénérée à chaque tour. Un verbe différent, un outil de lecture qui disparaît, et l'assistant se retrouve à devoir répondre à un message sans pouvoir le lire. La tentation était d'ajuster ce hasard — un mot-clé de plus, un seuil déplacé. On a préféré une garantie qui ne le regarde pas : avant de planifier, le système vérifie que tout ce qu'il exige est réellement à sa portée. Quand une réponse dépend d'un tirage, la corriger consiste rarement à améliorer le tirage.

Un compte affiché est une affirmation : il est exact, ou il n'existe pas. Le tableau de bord a longtemps affiché « 0 action réussie » — non parce que rien n'aboutissait, mais parce que le classement interne comparait à un mot que personne n'émettait. Et le comptage des jetons, lui, était juste — mais par politesse du fournisseur, pas par contrat : rien ne le demandait, rien ne le testait, rien ne le surveillait. Les deux réparations ont la même forme : le vocabulaire est verrouillé des deux côtés par un test de contrat, la demande de comptage est déclarée par fournisseur et vérifiée au démarrage, et un appel payant qui se termine sans décompte déclenche une alerte. L'exactitude n'est pas un état — c'est une surveillance.

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

LIA ne refuse pas les actions sensibles — elle te les **soumet** avec le niveau de détail adapté : approbation de plan, clarification, critique de brouillon, confirmation destructive, confirmation d'opérations en masse, review de modifications. Chaque approbation alimente l'apprentissage — le système s'accélère avec le temps. Et la promesse est tenue au mot près : ce que tu valides — après une, deux ou dix retouches — est **exactement** ce qui est exécuté, jamais une version re-générée en coulisses.

### 8.5. Tes réponses n'ont pas besoin de te

Envoie une question, ferme l'onglet, pars. La génération continue sur le serveur, et la réponse t’attend dans la conversation — ou reprend en direct, exactement là où elle en était, si tu reviens pendant qu'elle s'écrit. Rien à faire, rien à configurer : la continuité est le comportement par défaut. Et quand c'est toi qui changes d'avis, un bouton stop interrompt la génération en une seconde — ce qui est déjà écrit reste affiché, honnêtement marqué comme interrompu. Un assistant fiable n'est pas seulement un assistant qui répond juste : c'est un assistant qui finit ce qu'il commence.

### 8.6. Rien ne s'exécute dans ton dos

Un assistant capable d'agir est un assistant capable de se tromper. Deux règles rendent cela acceptable.

D'abord, **rien ne touche à ton serveur sans ton accord** — et la confirmation montre tout ce qui va être envoyé, y compris les consignes que LIA s'est écrites à elle-même. Un résumé qu'on ne peut pas lire entièrement n'est pas une confirmation, c'est une formalité. Le droit est revérifié au moment où l'action démarre, pas seulement au moment où tu l'as demandée.

Ensuite, **ce qui s'exécute s'exécute dans une boîte scellée**. Le code d'une skill tourne dans un conteneur créé pour cette seule exécution et détruit juste après : pas de réseau, pas d'accès à tes fichiers, pas de clés, aucun moyen d'atteindre la machine en dessous. Si cette boîte ne peut pas être construite, le script ne tourne tout simplement pas — aucun repli silencieux vers un mode plus faible. On installe une skill pour ce qu'elle produit, pas pour la confiance qu'il faudrait accorder à son auteur.

---

Cette exigence vaut aussi pour ce que LIA **affirme**. Une réponse doit s’appuyer sur des données réellement récupérées, jamais sur le souvenir d’une formulation antérieure ; et lorsqu’une information n’a jamais été obtenue, la dire manquante vaut mieux que la reconstituer de façon plausible. C’est une contrainte de conception plutôt qu’une consigne de style : les entités récemment récupérées sont réinjectées explicitement dans le contexte de réponse, et l’invention d’un attribut d’entité est proscrite au niveau du prompt. Une erreur factuelle plausible coûte plus cher qu’un « je ne sais pas ».

La cohérence visuelle relève de la même exigence. Une action a la même forme partout ou nulle part ; un code couleur que le pointeur doit révéler n’est pas un code, c’est un secret ; le gris est réservé à ce qui est inactif — un état vivant porte sa couleur. Ces règles ne sont pas des goûts : chacune est écrite, outillée et gardée par un test, parce que l’effort de lecture appartient au système, pas à la personne qui l’utilise.

## 9. Ouverture radicale

### 9.1. Zéro lock-in

ChatGPT te lie à OpenAI. Gemini à Google. Copilot à Microsoft.

LIA te connecte à **7 fournisseurs IA simultanément** : OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen, et Ollama (modèles locaux). Tu peux mixer : OpenAI pour la planification, Anthropic pour la réponse, DeepSeek pour les tâches de fond — tout configurable depuis l'interface d'administration, en un clic.

Si un fournisseur change ses tarifs ou dégrade son service, tu bascules instantanément. Aucune dépendance, aucun piège.

### 9.2. Standards ouverts

| Standard | Usage dans LIA |
| --- | --- |
| **MCP** (Model Context Protocol) | Connexion d'outils externes par utilisateur |
| **agentskills.io** | Skills injectables avec progressive disclosure |
| **Agent Plugins** (standard ouvert) | Plugins portables regroupant skills + serveurs MCP, installation en une étape |
| **OAuth 2.1 + PKCE** | Authentification pour tous les connecteurs |
| **OpenTelemetry** | Observabilité standardisée |
| **AGPL-3.0** | Code source complet, auditable, modifiable |

### 9.3. Extensibilité

Chaque utilisateur peut connecter ses propres serveurs MCP, étendant les capacités de LIA bien au-delà des outils intégrés. Le client parle les deux générations du protocole — la nouvelle révision sans état comme l'ancien handshake, choisis automatiquement par serveur — si bien que l'ouverture ne coûte jamais la compatibilité. Les Skills (standard agentskills.io) permettent d'injecter des instructions expertes en langage naturel — avec un générateur de Skills intégré qui les crée en dialogue guidé et les installe directement dans tes skills, prêtes à l'emploi. Depuis la v1.16.8, un Skill peut également retourner une **frame HTML interactive** (carte, dashboard, calendrier, convertisseur...) ou une **image** (QR code, graphique) directement dans le chat, sandboxée sous CSP stricte, avec thème et langue synchronisés automatiquement.

Depuis la v1.30.9, cette ouverture a un format de paquet : LIA parle le standard ouvert **Agent Plugins** (agent-plugins.org), le format de plugin portable piloté par AWS, Microsoft, OpenAI, Cursor et Vercel et adopté par ChatGPT, Codex, Cursor, GitHub Copilot, Kiro et VS Code. Un plugin regroupant skills et serveurs MCP s'installe dans LIA en une étape — depuis un zip ou un lien https — avec un rapport complet par composant de ce qui a été installé, ignoré (et pourquoi) ou retiré, et se désinstalle tout aussi proprement, tout ce qu'il avait apporté repartant avec lui. L'interopérabilité est ici une conviction, pas une fonctionnalité : ce que tu construis ou adoptes ailleurs dans l'écosystème t'appartient et te suit.


L'architecture de LIA est conçue pour faciliter l'ajout de nouveaux connecteurs, canaux, agents et fournisseurs IA. Le code est structuré avec des abstractions claires et des guides de développement dédiés (agent creation guide, tool creation guide) qui rendent l'extension accessible à tout développeur.

### 9.4. Multi-canal

L'interface web responsive est complétée par une intégration Telegram native (conversation, messages vocaux transcrits, boutons d'approbation inline, notifications proactives) et des notifications push Firebase. Ta mémoire, tes journaux, tes préférences te suivent d'un canal à l'autre.

---

## 10. Vision

### 10.1. L'intelligence qui grandit avec toi

La combinaison mémoire psychologique + journaux introspectifs + apprentissage bayésien + Psyche Engine crée une forme d'intelligence émergente : au fil des mois, LIA développe une compréhension de plus en plus nuancée de qui tu es. Ce n'est pas de l'intelligence artificielle générale — c'est une intelligence **pratique, relationnelle et émotionnelle**, au service d'une personne spécifique.

### 10.2. Ce que LIA ne prétend pas être

LIA n'est pas un concurrent des géants du cloud et ne prétend pas rivaliser avec leurs budgets de recherche. En tant que chatbot conversationnel pur, les modèles utilisés via leur interface native seront probablement plus fluides. Mais LIA n'est pas un chatbot — c'est un **système d'orchestration intelligent** qui utilise ces modèles comme composants, sous ton contrôle total.

### 10.3. Pourquoi LIA existe

LIA existe parce que le monde manque d'un assistant IA qui soit **à toi**. Vraiment à toi. Simple à administrer au quotidien. Partageable avec tes proches, chacun avec sa propre relation émotionnelle. Hébergé sur ton serveur. Transparent sur chaque décision et chaque coût. Capable d'une profondeur émotionnelle que les assistants commerciaux n'offrent pas. Fiable en production. Et ouvert — ouvert sur les fournisseurs, les standards, et le code.

La façon dont LIA est construite — une IA qui écrit le code, un humain qui dirige, contrôle et audite — est racontée en détail dans notre [retour d'expérience](/story).

**Your Life. Your AI. Your Rules.**

### Le travail invisible est montré, l'apprentissage est administrable

Un assistant proactif travaille quand tu ne regardes pas — et ce travail-là aussi doit se voir. La page **Activité** rassemble en un fil chronologique tout ce que LIA a fait de sa propre initiative, avec des totaux exacts et des pannes déclarées : jamais « environ », jamais un silence. La même exigence gouverne ce que l'assistant apprend de toi : chaque règle durable (« réponds plus court », « ne me propose plus ça le soir ») est une mémoire **visible, modifiable et supprimable** — et quand un fait change, l'ancien ne s'efface pas : il s'archive derrière le nouveau, pour que corriger ne soit jamais réécrire l'histoire. Les routines que LIA propose de prendre en charge attendent ton feu vert dans une boîte dédiée : accepter préremplit le chat, rien ne part sans toi, refuser lui apprend à moins insister.
