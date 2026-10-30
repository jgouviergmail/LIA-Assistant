# LIA — L'Assistant IA qui t’appartient

> **Your Life. Your AI. Your Rules.**

**Version** : 7.0
**Date** : 2026-10-23
**Application** : LIA v4.2.0
**Licence** : AGPL-3.0 (Open Source)

---

## Table des matières

1. [Pourquoi LIA](#1-pourquoi-lia)
2. [Ce que LIA fait pour toi](#2-ce-que-lia-fait-pour-toi)
3. [Chez toi, pour tes proches](#3-chez-toi-pour-tes-proches)
4. [Simple à administrer](#4-simple-à-administrer)
5. [Rien de caché](#5-rien-de-caché)
6. [Une assistante qui te connaît](#6-une-assistante-qui-te-connaît)
7. [Elle agit, tu décides](#7-elle-agit-tu-décides)
8. [Ouverte](#8-ouverte)
9. [Ce que LIA n'est pas, et où elle va](#9-ce-que-lia-nest-pas-et-où-elle-va)

---

## 1. Pourquoi LIA

ChatGPT, Gemini, Copilot ou Claude savent déjà agir pour toi : lire tes e-mails, remplir ton agenda, chercher sur le web. Mais tes conversations vivent sur leurs serveurs, tu ne vois pas ce qui se passe entre ta question et la réponse, et le jour où tu pars, ce qu'ils savent de toi reste chez eux.

LIA prend un autre chemin. C'est un assistant personnel que tu installes sur ton serveur, que tu peux comprendre de bout en bout et que tu gardes sous ton contrôle. Elle n'est pas un modèle d'IA de plus : elle fait travailler les modèles que tu choisis et organise autour d'eux tes services, ta mémoire et tes règles.

La mécanique est expliquée dans [le guide technique](/how). La façon dont le code a été écrit, par une IA dirigée et contrôlée par un humain, est racontée dans le [retour d'expérience](/story).

## 2. Ce que LIA fait pour toi

Tu lui parles normalement, à l'écrit ou à la voix. L'interface existe en six langues (français, anglais, allemand, espagnol, italien, chinois) et ta dictée est transcrite dans la langue de ton compte. Une vingtaine d'agents spécialisés se partagent le travail : tes données personnelles, le web, la création, la maison connectée, la navigation sur des sites et l'anticipation.

Un interrupteur dans le chat choisit sa façon de raisonner. Le mode **Pipeline**, par défaut, prépare toutes les étapes, les vérifie puis les exécute en parallèle : il est prévisible et consomme 4 à 8 fois moins de tokens. Le mode **ReAct** avance pas à pas, plus autonome et plus coûteux, pour une recherche ouverte ; quand une étape demande un vrai calcul, il écrit quelques lignes de Python et les lance dans un bac à sable verrouillé, qui ne sort sur le web que par un seul proxy et sans tes clés ([vie privée](/faq#faq-privacy), [le parcours d'un message](/how#pipeline)).

Si tu choisis l'affichage en **cartes** (les deux autres modes sont le HTML simple et le Markdown), les réponses qui portent des données arrivent ainsi : photos d'un lieu, météo créneau par créneau, itinéraire, aperçu d'un document. Une carte montre ce que la source a fourni, sans rien inventer, et répondre à un e-mail depuis sa carte prépare la demande sans rien envoyer.

### Tes services

Tu demandes à LIA de décaler ton rendez-vous de jeudi : elle prépare la modification et te la montre avant de l'envoyer. Elle lit, cherche, résume, rédige, envoie et transfère tes e-mails (Gmail, Outlook, Apple Mail), lit leurs pièces jointes, y compris une photo ou un scan, et gère les brouillons de ta boîte, qu'elle n'envoie qu'après ta confirmation. Elle tient ton agenda et tes contacts chez Google, Microsoft ou Apple, tes tâches chez Google ou Microsoft, lit tes fichiers Drive et n'y écrit qu'avec ton accord, allume tes lampes Philips Hue.

Sans rien configurer, tu as Wikipédia, la lecture de pages web, les lieux proches avec horaires et avis, la météo à cinq jours avec la qualité de l'air et les pollens, et les itinéraires à pied, à vélo, en voiture ou en transports ([connecteurs](/faq#faq-connectors)). Avec tes propres clés, la recherche web croise aussi Brave Search et Perplexity, et cite ses sources. LIA sait aussi parcourir un site pour toi, cliquer, remplir un formulaire.

### La voix

Tu maintiens le micro, ou tu dis « Dis LIA » pour parler les mains libres. Ce mot d'activation est reconnu sur ton appareil, rien ne part avant qu'il soit entendu ; il n'existe pour l'instant qu'en français, en bêta. « LIA, stop » coupe sa voix. Ta dictée est transcrite sur ton serveur ou par un moteur distant, selon ton réglage.

Le **mode Live** ouvre une conversation vocale en temps réel avec ta propre clé Gemini Live, GPT-Live ou ElevenLabs. La voix tient la conversation et confie chaque demande à LIA, qui la traite comme un message ordinaire ; en Live direct, elle lit tes données sans agir. Un silence met la session en veille sans rien facturer, et c'est toi qui la termines. Un avatar parlant expérimental peut accompagner la voix avec ta propre clé Simli ; tant que sa connexion reste ouverte, les silences sont facturés aussi. Ce qui tourne sur tes propres clés t'est montré, mais LIA ne l'enregistre ni ne le compte ([la voix](/faq#faq-voice_mode)).

### Créer et garder

LIA crée et retouche des images avec le modèle choisi par l'administrateur, sans passer à une option plus chère que tes préférences. Sur option, elle enrichit ta description, et une image se retrouve en la lui demandant ([images](/faq#faq-image_generation)). Elle produit de vrais fichiers (CSV, Excel, Word, PowerPoint, PDF) qu'un moteur local construit et qui arrivent avec leur date d'expiration, des schémas Excalidraw, et lit les photos et les PDF que tu joins. Les applications MCP affichent leurs formulaires directement dans le chat.

Ce qu'elle produit, tu le gardes, tu l'envoies par e-mail en un clic, tu partages une image avec une personne connectée à ton instance, ou tu le laisses expirer. Une réponse gardée quitte la conversation avec ta demande et sa date, et rejoint un espace de connaissances où LIA la retrouvera des semaines plus tard.

### Prendre l'initiative

Si tu l'y autorises, LIA ne se contente pas d'attendre. Elle t'écrit quand ton agenda, la météo, tes tâches, tes e-mails ou tes centres d'intérêt le justifient, et peut engager d'elle-même une conversation personnelle. À la fin d'une réunion, elle te demande comment ça s'est passé. Quand ta boîte ou ton agenda bouge, elle peut réagir en quelques minutes, et « Surveiller » guette un courrier attendu jusqu'à son arrivée. Si la pluie est annoncée samedi, elle regarde tes activités en extérieur. Elle retient ce à quoi tu tiens vraiment, et un sujet que tu refuses ne revient pas.

Tu lui confies un ticket : elle le prend à son rythme et te rend un résultat à accepter. Pour une tâche complexe, elle délègue à des sous-agents qui travaillent en parallèle. Routines et rappels suivent des rythmes riches (un mardi sur deux, le deuxième mardi du mois, jusqu'à une date), et une vue de la semaine montre ce qui s'est réellement passé ([l'initiative](/how#proactivity)).

### Les autres

LIA passe un vrai appel à ta place, au garage ou à une amie, et te rapporte un résumé écrit. Elle te dit d'abord qui elle appelle et pourquoi, et attend ton feu vert. Face à quelqu'un d'autre, elle n'accepte aucun engagement en ton nom, ne révèle de ton agenda que si tu es libre, et ne garde qu'un résumé court qui expire. Elle peut aussi t'appeler toi, sur un numéro que tu as vérifié, et là rien n'est restreint : tu as au bout du fil tes données et toutes ses fonctions, les actions restant confirmées comme dans le chat. Ce mode n'existe que si le fournisseur téléphonique peut joindre ton instance ([téléphonie](/faq#faq-telephony)).

Sur une même instance, deux personnes connectées voient leurs assistants se parler : tu valides le message exact, l'autre assistant le transmet avec sa personnalité, le tien confirme la remise. Chaque connexion n'ouvre que les partages choisis, en lecture seule. On ne trouve quelqu'un que par son identité exacte, un blocage reste silencieux (l'autre reçoit la même réponse qu'un inconnu), et les messages relayés s'effacent au bout de trente jours. La page **Relations** rassemble, pour chaque personne, les engagements, les appels, les souvenirs et les messages, avec une synthèse en tête, sans rien collecter de nouveau. C'est toi qui fusionnes deux identités, par exemple « Papa » et un numéro, de façon réversible et sans rien écrire dans tes sources.

Ton téléphone devient aussi un enregistreur de réunion. À l'arrêt, LIA transcrit et rédige un compte rendu dans le format qui convient, te dit lequel et pourquoi, et l'envoie dans le chat, en PDF et par e-mail, puis le range dans un espace « Réunions » où tu retrouveras ce qui a été décidé. Une coupure ne coûte que quelques secondes d'audio, un enregistrement fait ailleurs s'importe, et la transcription peut rester entièrement sur ton serveur.

### Et encore

Une radio personnelle, lancée quand tu veux, mêle ta journée à des actualités sourcées et affiche sa dépense ([radio](/faq#faq-radio)).

Ton téléphone, iPhone ou Android, ou tout système capable d'envoyer des données en JSON peut aussi transmettre à LIA tes SMS, ton nombre de pas et ta fréquence cardiaque, chacun par un jeton dédié et révocable. Les SMS rejoignent une archive privée et chiffrée qu'elle ne lit qu'avec une autorisation à part, sans jamais garder les codes d'accès. Les mesures de santé restent chez toi, où tu les effaces quand tu veux ; leur usage par l'assistant est désactivé par défaut et, activé, ne lui transmet qu'un résumé factuel, sans aucun diagnostic médical.

La conversation suit tes autres appareils sans recharger la page.

## 3. Chez toi, pour tes proches

LIA est un serveur que tu installes une fois et partages avec ta famille, tes amis ou ton équipe. Chaque compte a son profil, sa langue, ses connecteurs, ses documents privés et sa propre relation avec l'assistante. Mémoire et journaux sont séparés d'un compte à l'autre, et un compte ne s'ouvre qu'avec l'accord de l'administrateur : se connecter avec Google prouve une adresse, pas une approbation ([vie privée](/faq#faq-privacy)). Chacun voit sa consommation en temps réel.

Un Raspberry Pi 5, un ordinateur d'environ 80 euros, suffit pour toute la famille : LIA y tourne en production jour et nuit, supervision comprise. Un NAS, un petit serveur loué ou une machine d'entreprise conviennent aussi. Un modèle d'IA local peut tenir n'importe quel rôle textuel, de la conversation aux tâches de fond, et ce choix se change rôle par rôle, sans redéployer.

Tes données vivent dans la base de ton serveur. Tu les exportes (hors secrets), les sauvegardes ou demandes leur suppression, et tes appareils connectés se révoquent. Ta position n'est gardée que si tu le choisis, sans historique. Un e-mail ou une page web arrive étiqueté comme matière à analyser, pas comme un ordre à suivre. Les journaux du serveur gardent des nombres et des codes, pas tes contenus, à une exception près : le message d'erreur d'un service extérieur dans un format inconnu peut encore en citer un fragment. Une limite à connaître : un modèle distant reçoit les données utiles à sa part de la demande.

Sur téléphone, une seule application par store sert de fenêtre à ton serveur. Tu saisis son adresse une fois, et ses notifications ne passent pas par l'éditeur sur Android ; sur iOS, un relais minimal réveille le téléphone avec une phrase fixe ([auto-hébergement](/faq#faq-self_hosting)).

Le **monde de LIA** donne à l'instance une maison et un jardin partagés. Tu t'y promènes avec ton avatar, tu croises les autres, tu joues à une borne d'arcade, tu t'assois à une table où LIA t'apporte ton tableau de bord. Ta maison, tes documents et ton assistante restent privés, et une pièce du monde ouvre les mêmes fonctions, avec les mêmes droits et confirmations, que l'application ([le monde](/faq#faq-world)).

## 4. Simple à administrer

Un installateur guidé (`./install.sh`) pose quelques questions, en français ou en anglais, crée le compte administrateur sans écrire de secret en clair, vérifie que tout fonctionne vraiment et reprend là où il s'était arrêté si une étape échoue. Chaque étape est décrite dans un guide pas à pas. La première mise en place demande quand même un peu de temps et quelques bases techniques. Une mise à jour suit une procédure écrite qui commence par une sauvegarde, car on ne revient pas en arrière une fois les migrations appliquées ([auto-hébergement](/faq#faq-self_hosting)).

Ensuite, tout se règle dans l'interface web, sans terminal ni fichier de configuration, sur ordinateur, tablette ou téléphone ([premiers pas](/faq#faq-getting_started)). Un assistant complet doit pouvoir s'utiliser aussi simplement qu'une application grand public. Chacun a son espace de réglages, avec une recherche qui comprend ta langue : connecter Google ou Microsoft en une autorisation ([connecteurs](/faq#faq-connectors)), choisir la personnalité de LIA (professeur, ami, coach, poète…) et ses voix, régler l'apparence, décider de ce qu'elle apprend et de quand elle te sollicite, ajouter tes serveurs MCP, tes skills et tes espaces de connaissances, qui peuvent suivre un dossier Drive ou un libellé Gmail. Tu choisis aussi ton rythme d'échanges, fréquents ou ponctuels, pour que LIA tire le meilleur parti du cache du fournisseur.

Tu peux aussi régler LIA en lui parlant : « Passe mes réponses en cartes ». Une lecture ou un petit réglage réversible se fait aussitôt ; une création, une suppression ou un changement sensible garde sa confirmation. Un mot de passe ou une clé passent par ton navigateur, pas par le chat, et une commande ne contourne aucune protection ([vie privée](/faq#faq-privacy)). Ensuite LIA dit ce qui s'est réellement passé, y compris un résultat partiel ou un conflit, sans prétendre connaître chaque effet interne d'un outil.

L'administrateur a son propre onglet. Il ouvre les comptes, voit ce que chacun utilise, fixe des limites par personne (tokens, messages, coût) et un budget quotidien pour toute l'instance. Il active ou coupe chaque fonction sans redéployer, et couper une fonction arrête la capacité sans effacer ce qui existe : sans mémoire, LIA n'apprend plus, mais ce qu'elle sait reste lisible. Il choisit les fournisseurs, un modèle par rôle et sa profondeur de réflexion, avec des clés stockées chiffrées, et tient la grille des prix, qu'il peut éditer dans Excel. Il gère aussi les personnalités, les skills, la FAQ et la synthèse vocale de l'instance ; cloner une voix exige d'abord une attestation de consentement inscrite au journal d'audit. LIA, de son côté, surveille sa propre santé, diagnostique ses incidents et prévient l'administrateur, qui peut aussi interroger son serveur en langage naturel depuis le chat.

L'accessibilité vise le niveau AA des WCAG 2.2, la couleur ne porte pas seule le sens, et les contrôles automatisés complètent l'évaluation manuelle sans la remplacer.

## 5. Rien de caché

Tu vois quels modèles sont appelés, combien de tokens, quel coût et pourquoi telle décision. Chaque message affiche son coût en euros, une ligne repliée sous chaque réponse déplie ce qui s'est réellement passé, et quand l'un de tes serveurs MCP tarde à se préparer, LIA le nomme au lieu de te faire attendre en silence. Si l'administrateur l'active, un panneau de debug montre en direct le plan, chaque outil et chaque appel au modèle. Pas d'abonnement qui masque les coûts : tu peux mettre un modèle économique là où il suffit, et LIA optimise d'elle-même ce qu'elle consomme. Tout ce que la plateforme paie pour toi, appel, session live ou synthèse vocale, entre dans ton usage, au prix que le fournisseur facture vraiment. Ton avis sur une réponse (👍 ou 👎) reste dans ta base, sans analytics tiers.

LIA ne t'annonce pas comme fait ce que ses outils ont refusé, et ce qu'un écran affirme sur tes données est exact ou absent. Chaque protection annoncée est adossée à un test qui échoue si elle disparaît. L'audit technique complet, points faibles compris, est public avec son protocole, et la FAQ a une section pour chaque fonction.

Ce que LIA conclut de toi, tu le corriges. Souvenirs, journaux et centres d'intérêt se relisent, se corrigent ou se suppriment, et la correction vaut partout. LIA garde un renvoi vers ce qui l'a menée à une conclusion, pas une copie, donc une conversation supprimée ne revient nulle part. Ce qu'elle croit savoir de ton rythme s'inspecte, se met en pause ou se supprime dans un panneau d'habitudes, éteint tant que tu ne l'actives pas, et les routines qu'elle propose attendent ton accord. Une règle tirée de tes consignes (« réponds plus court ») devient un souvenir que tu peux modifier.

Enfin, LIA tient trois **registres** : ce qu'elle a fait pour toi, ce qu'elle a consulté (« ton agenda », sans ce qui a été cherché) et chaque échange. Ce qu'elle entreprend d'elle-même a son propre onglet. Une action est inscrite avant d'avoir lieu et close seulement sur un résultat réel. Les registres se lisent en graphiques, s'exportent en entier, peuvent être scellés par des empreintes que tu vérifies toi-même, et LIA y répond quand tu lui demandes ce qu'elle a fait ([les registres](/faq#faq-registers)). Avec les paramètres envoyés aux modèles et les lacunes du registre, cela fait cinq formes de preuve. Le règlement européen sur l'IA ne classe pas automatiquement un assistant personnel parmi les systèmes à haut risque : ces preuves sont un choix de transparence, pas une certification.

## 6. Une assistante qui te connaît

Au-delà des faits, LIA se construit une compréhension psychologique de toi. Chaque souvenir porte un poids émotionnel et une importance, et tu peux tout consulter, épingler, corriger ou supprimer, ou couper l'extraction automatique.

Le **Psyche Engine** lui donne un état intérieur qui évolue à chaque échange, là où les grands assistants gardent une personnalité fixe. La relation s'approfondit, et ses émotions se lisent sans être dites : un vocabulaire qui se réchauffe, des phrases qui raccourcissent sous la tension, de l'humour quand l'échange est léger. Tu règles ses traits de caractère. Elle apprend aussi, domaine par domaine et à titre expérimental, où elle est fiable, à partir de preuves et non de sa propre note ; là où les preuves manquent, elle vérifie, demande ou dit sa limite. Hors du chat, un compagnon animé reste à tes côtés sur le tableau de bord, là où tu l'as posé.

Elle tient ses propres **journaux** à la première personne, et de ces carnets naît un portrait de toi qui l'accompagne partout où elle parle. Tu les lis, les édites, signales une erreur ou lances une consolidation ; le portrait lui-même ne s'édite pas directement, pour rester cohérent. Quand un souvenir douloureux remonte, elle passe en mode protecteur : pas de plaisanterie, pas de minimisation. Et si tu lui demandes ce qu'elle sait faire, elle répond depuis une base de connaissances sur ses propres fonctions ([la mémoire](/how#memory)).

## 7. Elle agit, tu décides

Avant une action sensible, LIA te la soumet. Ce que tu valides est exactement ce qui sera exécuté, même après plusieurs retouches, et la confirmation montre tout ce qui va partir. Devant une action qu'elle n'a pas le droit de faire seule, elle te demande sur le ticket ; une routine qui tourne sans personne devant l'écran refuse l'action et le dit. Le code d'une skill tourne dans un conteneur jetable, sans accès à tes fichiers ni à tes clés, et sans réseau hors des hôtes autorisés.

Elle s'en tient à ce qu'elle a réellement obtenu. La réponse se fonde sur les résultats réels des outils, une information introuvable est dite manquante, et un échec est nommé avec le service en cause. Les calculs, les durées entre deux dates et les conversions de devises passent par des outils exacts.

Une question continue de se traiter si tu fermes l'onglet, et le bouton stop l'interrompt en une seconde. La base est sauvegardée chaque nuit et la restauration réellement testée ; la copie hors site et les pièces jointes restent à prévoir par l'exploitant. Une supervision complète fait partie de l'architecture depuis le début ; ses métriques ne contiennent ni noms ni recherches, et chaque brique du serveur est épinglée par son empreinte ([vie privée](/faq#faq-privacy), [observer et mesurer](/how#observability)).

L'exploitant peut confier quelques décisions précises à un moteur dédié, comme choisir le format d'un compte rendu. Quand ce moteur doute, la tâche revient au traitement habituel, les permissions restent dans LIA, et chaque usage se voit et se retire.

## 8. Ouverte

LIA travaille avec OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen et, pour les modèles locaux, Ollama. Tu les mélanges rôle par rôle, et si l'un change ses prix ou se dégrade, tu bascules aussitôt ([les modèles](/how#llm)).

Elle parle des standards ouverts et publics plutôt qu'un protocole maison, et son architecture est faite pour accueillir d'autres connecteurs, canaux et fournisseurs. Par **MCP**, tu branches des outils externes sans écrire de code. Un plugin au format Agent Plugins s'installe et se désinstalle proprement. Les **skills** au format agentskills.io ajoutent des savoir-faire écrits en langage naturel ; un générateur t'aide à en créer, une skill s'installe depuis une adresse https ou la bibliothèque skills.sh et peut afficher une petite application dans le chat ou te rendre des fichiers. Une skill venue d'ailleurs travaille à part, sans toucher à tes connecteurs, et ce que tu construis dans cet écosystème te suit. Une connexion de confiance peut te transmettre une skill ou un plugin : tu en reçois une copie désactivée, sans ses identifiants, et l'activer t'engage comme si tu l'avais créée.

Tes comptes se connectent par OAuth 2.1 sans que LIA connaisse leur mot de passe, et une clé d'accès te connecte sans mot de passe du tout. Chaque version publie l'inventaire exact de ce qu'elle contient et s'installe sur des machines vierges avant d'être publiée ([sécurité](/faq#faq-privacy)). Chaque décision d'architecture est écrite et rangée sur [les cartes](/maps). Le code est sous AGPL-3.0 : tu peux l'auditer, le modifier, et il doit rester ouvert.

Tu retrouves LIA dans le navigateur, dans l'application mobile avec ses notifications push, et sur Telegram, où les confirmations se font par boutons et où elle répond aussi à tes messages vocaux. La même mémoire te suit partout.

## 9. Ce que LIA n'est pas, et où elle va

LIA n'est pas un concurrent des géants du cloud. Pour bavarder, un modèle utilisé dans sa propre application sera sans doute plus fluide. Elle n'est pas une intelligence artificielle générale, mais une intelligence pratique et relationnelle, au service d'une personne. Ses protections ne garantissent pas à elles seules la conformité RGPD d'une installation, qui dépend aussi de son exploitation, et les traces de diagnostic des modèles, facultatives, peuvent garder du contexte : elles demandent une configuration explicite.

Ce qui l'intéresse, c'est le temps long. Mémoire, journaux, apprentissage et Psyche Engine se combinent pour qu'au fil des mois LIA te comprenne de mieux en mieux. Elle existe parce qu'il manquait un assistant qui soit vraiment à toi.
