# LIA — Politique de Confidentialite

> Vos donnees. Votre assistant. Vos regles.

**Version** : 1.0
**Date** : 2026-10-05
**Licence** : AGPL-3.0 (Open Source)

---

## Table des matieres

1. [Introduction](#introduction)
2. [Donnees collectees](#data_collected)
3. [Bases legales du traitement](#legal_basis)
4. [Hebergement et localisation](#hosting)
5. [Securite des donnees](#security)
6. [Fournisseurs LLM](#llm_providers)
7. [Conservation des donnees](#retention)
8. [Vos droits](#rights)
9. [Cookies](#cookies)
10. [Contact](#contact)

---

## 1. Introduction

La presente politique de confidentialite decrit comment LIA, un assistant personnel IA open source, collecte, utilise et protege vos donnees personnelles. LIA est developpee et exploitee par un developpeur independant dans le cadre d'un projet open source sous licence AGPL-3.0.

LIA est actuellement en phase beta et est proposee gratuitement pendant cette periode. L'application est accessible a l'adresse [https://lia.jeyswork.com](https://lia.jeyswork.com). Le code source complet est disponible publiquement, ce qui vous permet d'auditer le traitement de vos donnees a tout moment.

Cette politique s'applique à l'instance hébergée de LIA. Si vous déployez votre propre instance (auto-hébergement), vous maîtrisez son exploitation et devez évaluer les obligations de protection des données applicables à votre usage ; cette politique ne s'applique pas directement. Nous vous encourageons néanmoins à vous en inspirer pour cette évaluation.

En utilisant LIA, vous reconnaissez avoir lu et compris la presente politique. Si vous n'acceptez pas les termes decrits, veuillez ne pas utiliser le service.

## 2. Donnees collectees

LIA traite les catégories de données suivantes pour fournir le service et les fonctions facultatives que vous choisissez d'utiliser :

**Donnees de compte utilisateur :**
- Adresse email (identifiant unique)
- Nom et prenom
- Mot de passe (hache via bcrypt, jamais stocke en clair)
- Preferences linguistiques et fuseau horaire
- Role utilisateur (standard ou administrateur)

**Donnees de conversation :**
- Messages echanges entre vous et l'assistant
- Plans d'execution generes par le systeme de planification
- Resultats des actions effectuees par les agents (recherche d'emails, creation d'evenements, etc.)
- Historique des conversations, sauvegarde sous forme de checkpoints dans PostgreSQL
- Souvenirs, préférences, documents et autres contenus que vous fournissez pour personnaliser l'assistant

**Donnees de connexion aux services tiers :**
- Jetons d'accès et de rafraîchissement des services utilisant OAuth, notamment Google Workspace et Microsoft 365
- Mots de passe d'application ou autres identifiants de connecteurs comme Apple iCloud, et clés API des fournisseurs que vous configurez
- Ces secrets stockés sont chiffrés avec Fernet (AES-128-CBC avec authentification HMAC-SHA256)

**Données des fonctions facultatives :**
- Une adresse de domicile que vous enregistrez, et la position du navigateur si vous en autorisez l'accès ; mémoriser la dernière position connue nécessite aussi une activation volontaire. Ces champs de localisation sont chiffrés, la position mémorisée remplace la précédente sans constituer d'historique, et désactiver cette option l'efface
- Audio, transcriptions et images ou documents utilisés dans une demande vocale, une réunion ou une demande multimodale
- Mesures de santé si vous choisissez de connecter une source et d'utiliser ces fonctions

**Donnees d'utilisation :**
- Métriques opérationnelles agrégées (nombre de requêtes, temps de réponse) et relevés d'utilisation par compte
- Compteurs de tokens LLM consommes par session
- Journaux d'erreurs techniques avec des contrôles pour masquer les secrets et contenus personnels ; les traces de diagnostic facultatives ont une portée distincte, décrite ci-dessous

**Donnees que LIA ne collecte PAS :**
- Gabarits biométriques d'authentification conservés par votre appareil lorsque vous utilisez une clé d'accès
- Donnees de navigation en dehors de l'application
- Profils publicitaires ou donnees de ciblage

## 3. Bases legales du traitement

Le tableau suivant indique les bases légales utilisées pour le service hébergé au titre du Règlement général sur la protection des données (RGPD) :

| Traitement | Base legale | Justification |
|---|---|---|
| Creation et gestion du compte | Execution du contrat (Art. 6.1.b) | Necessaire pour fournir le service |
| Conversations avec l'assistant | Execution du contrat (Art. 6.1.b) | Fonction principale du service |
| Connexion aux services tiers (Google, Apple, Microsoft) | Consentement explicite (Art. 6.1.a) | Vous choisissez activement de connecter chaque service |
| Envoi de donnees aux fournisseurs LLM | Execution du contrat (Art. 6.1.b) | Necessaire au fonctionnement de l'assistant |
| Journaux techniques et metriques | Interet legitime (Art. 6.1.f) | Maintien de la securite et de la fiabilite du service |
| Cookie de preference linguistique | Consentement (Art. 6.1.a) | Memorisation de votre choix de langue |

Vous pouvez retirer votre consentement a tout moment pour les traitements fondes sur celui-ci, sans que cela affecte la licéite des traitements effectues avant le retrait.

## 4. Hebergement et localisation

**Infrastructure de l'instance hebergee :**

L'instance officielle de LIA est auto-hebergee sur un serveur physique administre par le developpeur. Les donnees sont stockees en France.

- **Base de donnees** : PostgreSQL pour le stockage persistant (comptes, conversations, checkpoints)
- **Cache** : Redis pour les sessions et le cache temporaire
- **Proxy inverse** : Cloudflare Tunnel pour l'acces HTTPS securise
- **Certificats TLS** : Geres automatiquement par Cloudflare

**Transferts internationaux de donnees :**

Lorsque vous interagissez avec LIA, les données utiles à votre demande peuvent être transmises à des fournisseurs de modèles, de voix, d'avatar, de recherche ou d'autres services, selon les fonctions et la configuration utilisées. Ces fournisseurs peuvent avoir des serveurs situés hors de l'Union européenne (notamment aux États-Unis et en Chine). Voir la section « Fournisseurs LLM » pour plus de détails.

Les connexions a Google Workspace, Apple iCloud et Microsoft 365 impliquent egalement des echanges avec les serveurs de ces fournisseurs, selon leurs propres politiques de confidentialite.

## 5. Securite des donnees

LIA met en oeuvre une architecture de securite multicouche concue pour proteger vos donnees a chaque etape :

**Architecture BFF (Backend-for-Frontend) :**
La session applicative utilise un cookie HttpOnly, et les identifiants permanents des connecteurs ainsi que les secrets API des modèles ou de l'avatar sont gérés côté serveur. Certaines connexions vocales ou d'avatar utilisent des accès de session temporaires dans le navigateur. Les cartes Google Maps interactives reçoivent aussi une clé API destinée au navigateur après activation authentifiée ; cette clé nécessite des restrictions chez le fournisseur et des quotas adaptés.

**Chiffrement des donnees sensibles :**
- Les identifiants stockés des connecteurs, secrets fournisseurs et champs de localisation désignés sont chiffrés avec [Fernet](https://cryptography.io/en/latest/fernet/) (AES-128-CBC + authentification HMAC-SHA256)
- Les mots de passe sont haches avec bcrypt (facteur de cout adaptatif)
- L'accès à l'application hébergée utilise HTTPS ; la protection des connexions internes et des sauvegardes dépend du déploiement

Ce chiffrement par champ ne chiffre pas toutes les colonnes de la base. Le serveur peut lire les conversations pour les traiter ; elles ne sont pas chiffrées de bout en bout. Un opérateur disposant de la base et des clés de chiffrement peut accéder aux données stockées ; la sécurité de cet accès et des sauvegardes dépend aussi de l'exploitation de l'instance.

**Informations personnelles et diagnostics :**
Des contrôles de masquage protègent les journaux techniques ; ils n'anonymisent pas automatiquement le contexte envoyé à un modèle. Vos messages et les contenus utiles des services connectés peuvent contenir les informations personnelles nécessaires à votre demande. Si le suivi des appels LLM est activé, les outils de diagnostic peuvent aussi conserver les entrées et sorties des modèles et des métadonnées rattachées au compte. Leur accès, hébergement et conservation doivent être configurés par l'opérateur.

**Sessions et authentification :**
- Les sessions utilisateur sont stockees dans Redis avec expiration automatique
- L'authentification repose sur des cookies securises (HttpOnly, Secure, SameSite)
- Le JavaScript client ne peut pas lire le cookie HttpOnly de la session applicative ; les accès temporaires des sessions vocales ou d'avatar activées dans le navigateur ont un autre rôle

**Journalisation securisee :**
Les journaux techniques utilisent le format JSON structuré (via structlog), avec des règles pour omettre les propos de l'utilisateur et masquer les secrets et informations personnelles reconnus. Ces contrôles ne rendent pas chaque stockage de diagnostic anonyme.

## 6. Fournisseurs LLM

LIA utilise plusieurs fournisseurs de modeles de langage (LLM) pour traiter vos requetes. Le choix du fournisseur depend de la configuration de votre instance et du type de tache :

| Fournisseur | Siege | Utilisation dans LIA |
|---|---|---|
| OpenAI | Etats-Unis | Modeles GPT pour la conversation et la planification |
| Anthropic | Etats-Unis | Modeles Claude pour la conversation et l'analyse |
| Google (Gemini) | Etats-Unis | Modeles Gemini pour le traitement multimodal |
| DeepSeek | Chine | Modeles de raisonnement avance |
| Qwen (Alibaba) | Chine | Modeles de traitement linguistique |
| Perplexity | Etats-Unis | Recherche web augmentee |
| Ollama | Selon le point d'accès configuré | Inférence sur un serveur local lorsqu'il est configuré ainsi |

**Ce qui est transmis aux fournisseurs LLM :**
- Le contenu de vos messages
- Le contexte conversationnel necessaire a la coherence des reponses
- Les résultats d'outils utiles (contenu d'emails, détails d'événements, documents, etc.), qui peuvent contenir des données personnelles

Les parcours vocaux, de réunion, d'image et d'avatar parlant facultatif peuvent également transmettre l'audio, le texte ou les images utiles à leurs fournisseurs respectifs. Les fonctions choisies et leur routage déterminent les services destinataires.

**Utilisation des identifiants :**
Les identifiants des connecteurs et les clés fournisseurs servent à s'authentifier auprès du service concerné ; ils ne sont pas ajoutés aux prompts des modèles comme contenu de conversation. Évitez de mettre des mots de passe ou d'autres secrets dans vos messages : les contenus que vous fournissez peuvent être inclus dans une demande envoyée à un fournisseur.

**Engagement des fournisseurs :**
L'utilisation pour l'entraînement, la conservation et les autres traitements dépendent du fournisseur, du produit, des réglages du compte et du contrat ou de la politique de confidentialité applicables. Consultez ces conditions pour chaque service activé ; LIA ne peut pas garantir universellement l'absence d'entraînement à leur place.

Choisir un point d'accès Ollama hébergé localement conserve l'inférence du modèle choisi sur ce serveur. Cela ne rend pas les autres intégrations locales : comptes connectés, recherche web, voix ou avatar distants peuvent toujours échanger des données avec leurs fournisseurs.

## 7. Conservation des donnees

Les durees de conservation sont definies selon la nature des donnees :

| Type de donnee | Duree de conservation | Justification |
|---|---|---|
| Compte utilisateur | Les contenus personnels sont purgés à la suppression ; la ligne du compte et les relevés de facturation restent jusqu'à leur étape d'effacement ou échéance de conservation applicable | Exploitation, facturation et obligations légales applicables |
| Historique des conversations | Jusqu'a suppression par l'utilisateur ou du compte | Continuite du service |
| Identifiants chiffrés des connecteurs | Jusqu'à déconnexion du service ou suppression du compte | Accès aux services connectés |
| Position mémorisée du navigateur | Remplacée à chaque mise à jour et effacée à la désactivation ; sa fraîcheur limite son utilisation | Demandes liées au lieu sans historique de déplacements |
| Sessions Redis | Expiration automatique selon les réglages de session et de maintien de connexion | Sécurité |
| Journaux techniques et traces de diagnostic facultatives | Conservation configurée pour chaque stockage de diagnostic | Diagnostic et sécurité |
| Métriques d'utilisation | Conservation configurée pour le stockage des métriques ; les relevés par compte suivent leur cycle de vie documenté | Suivi de consommation et exploitation du service |

**Suppression du compte :**
Vous pouvez demander la suppression du compte à l'administrateur. L'étape de suppression purge les contenus personnels tels que conversations, souvenirs, documents, checkpoints et identifiants stockés des connecteurs, mais conserve la ligne du compte, notamment le nom et l'email, et les relevés de facturation. L'étape d'effacement suivante retire la ligne de compte restante. Les journaux d'audit, stockages de diagnostic distincts, sauvegardes et données déjà reçues par les fournisseurs demandent leurs propres procédures de conservation et d'effacement ; aucune de ces étapes n'efface instantanément chaque copie. L'opérateur doit traiter les demandes d'effacement applicables sur ces stockages.

## 8. Vos droits

Conformement au RGPD, vous disposez des droits suivants :

- **Droit d'acces** (Art. 15) : Obtenir une copie de toutes les donnees personnelles que nous detenons a votre sujet.
- **Droit de rectification** (Art. 16) : Corriger des donnees personnelles inexactes ou incompletes.
- **Droit a l'effacement** (Art. 17) : Demander la suppression de vos donnees personnelles ("droit a l'oubli").
- **Droit a la limitation** (Art. 18) : Demander la restriction du traitement de vos donnees dans certaines circonstances.
- **Droit a la portabilite** (Art. 20) : Recevoir vos donnees dans un format structure, couramment utilise et lisible par machine.
- **Droit d'opposition** (Art. 21) : Vous opposer au traitement de vos donnees fonde sur l'interet legitime.
- **Droit de retirer votre consentement** : A tout moment, sans affecter la licéite du traitement effectue avant le retrait.

Pour exercer ces droits, contactez-nous à l'adresse indiquée dans la section Contact. Nous répondrons sans retard indu et normalement dans le mois suivant la réception de votre demande, toute prolongation justifiée étant communiquée selon l'[article 12 du RGPD](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng).

Si vous estimez que vos droits ne sont pas respectes, vous avez le droit d'introduire une reclamation aupres de la CNIL (Commission Nationale de l'Informatique et des Libertes) ou de toute autre autorite de controle competente.

## 9. Cookies

LIA utilise un nombre minimal de cookies, exclusivement fonctionnels :

| Cookie | Finalite | Duree | Type |
|---|---|---|---|
| `NEXT_LOCALE` | Memorise votre preference de langue (fr, en, de, es, it, zh) | 1 an | Fonctionnel |
| Cookie de session | Maintient votre session d'authentification | Duree de la session | Strictement necessaire |

**Ce que LIA n'utilise PAS :**
- Aucun cookie de pistage (tracking)
- Aucun cookie publicitaire
- Aucun cookie tiers d'analyse (Google Analytics, etc.)
- Aucun pixel de suivi
- Aucune empreinte numerique (fingerprinting)

Les cookies utilises par LIA sont strictement necessaires au fonctionnement du service ou relevent de votre choix explicite (preference de langue). Conformement a la directive ePrivacy, les cookies strictement necessaires ne requierent pas de consentement prealable.

## 10. Contact

Pour toute question relative a la protection de vos donnees personnelles, l'exercice de vos droits ou la presente politique, vous pouvez nous contacter :

- **Email** : liamyassistant@gmail.com
- **Site web** : [https://lia.jeyswork.com](https://lia.jeyswork.com)
- **Code source** : [GitHub](https://github.com/jgouviergmail/LIA-Assistant) (AGPL-3.0)

**Responsable du traitement :**
LIA est exploitee par un developpeur independant agissant en qualite de responsable du traitement au sens du RGPD.

**Modifications de cette politique :**
Cette politique peut etre mise a jour pour refleter les evolutions du service ou de la reglementation. En cas de modification substantielle, vous serez informe(e) via l'application. La date de mise a jour en haut du document fait foi. Nous vous encourageons a consulter regulierement cette politique.

**Transparence open source :**
LIA etant un projet open source, vous pouvez a tout moment auditer le code source pour verifier exactement quelles donnees sont collectees, comment elles sont traitees et ou elles sont envoyees. Cette transparence radicale constitue un engagement fondamental du projet.
