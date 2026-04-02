# LIA — Politique de Confidentialite

> Vos donnees. Votre assistant. Vos regles.

**Version** : 1.0
**Date** : 2026-03-29
**Application** : LIA v1.14.1
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

Cette politique s'applique a l'instance hebergee de LIA. Si vous deployez votre propre instance (auto-hebergement), vous devenez responsable du traitement des donnees de cette instance et cette politique ne s'applique pas directement. Nous vous encourageons neanmoins a vous en inspirer pour votre propre conformite.

En utilisant LIA, vous reconnaissez avoir lu et compris la presente politique. Si vous n'acceptez pas les termes decrits, veuillez ne pas utiliser le service.

## 2. Donnees collectees

LIA collecte et traite les categories de donnees suivantes, strictement necessaires au fonctionnement du service :

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

**Donnees de connexion aux services tiers :**
- Jetons d'acces OAuth (Google Workspace, Apple iCloud, Microsoft 365)
- Jetons de rafraichissement pour le renouvellement automatique
- Ces jetons sont chiffres via Fernet (chiffrement symetrique AES-128-CBC) avant stockage

**Donnees d'utilisation :**
- Metriques d'utilisation anonymisees (nombre de requetes, temps de reponse)
- Compteurs de tokens LLM consommes par session
- Journaux d'erreurs techniques (sans donnees personnelles identifiantes)

**Donnees que LIA ne collecte PAS :**
- Donnees de geolocalisation
- Donnees biometriques
- Donnees de navigation en dehors de l'application
- Profils publicitaires ou donnees de ciblage

## 3. Bases legales du traitement

Conformement au Reglement General sur la Protection des Donnees (RGPD), chaque traitement de donnees repose sur une base legale specifique :

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

Lorsque vous interagissez avec LIA, certaines donnees sont transmises aux fournisseurs LLM pour le traitement du langage naturel. Ces fournisseurs peuvent avoir des serveurs localises en dehors de l'Union europeenne (notamment aux Etats-Unis). Voir la section "Fournisseurs LLM" pour plus de details.

Les connexions a Google Workspace, Apple iCloud et Microsoft 365 impliquent egalement des echanges avec les serveurs de ces fournisseurs, selon leurs propres politiques de confidentialite.

## 5. Securite des donnees

LIA met en oeuvre une architecture de securite multicouche concue pour proteger vos donnees a chaque etape :

**Architecture BFF (Backend-for-Frontend) :**
L'architecture BFF garantit que les jetons d'authentification et les credentials des services tiers ne transitent jamais par le navigateur. Toutes les operations sensibles sont effectuees cote serveur.

**Chiffrement des donnees sensibles :**
- Les jetons OAuth (Google, Apple, Microsoft) sont chiffres avec Fernet (AES-128-CBC + HMAC SHA256) avant stockage en base de donnees
- Les mots de passe sont haches avec bcrypt (facteur de cout adaptatif)
- Toutes les communications sont chiffrees en transit via TLS 1.2+

**Filtrage PII (Personally Identifiable Information) :**
Avant d'envoyer des donnees aux fournisseurs LLM, LIA applique un filtrage PII qui reduit les informations personnellement identifiables transmises. Ce mecanisme minimise l'exposition de vos donnees sensibles aux services tiers.

**Sessions et authentification :**
- Les sessions utilisateur sont stockees dans Redis avec expiration automatique
- L'authentification repose sur des cookies securises (HttpOnly, Secure, SameSite)
- Aucun jeton d'authentification n'est expose au JavaScript client

**Journalisation securisee :**
Les journaux techniques utilisent le format structure JSON (via structlog) et sont configures pour exclure les donnees personnelles identifiantes.

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
| Ollama | Local | Modeles executes localement (aucun transfert externe) |

**Ce qui est transmis aux fournisseurs LLM :**
- Le contenu de vos messages (apres filtrage PII)
- Le contexte conversationnel necessaire a la coherence des reponses
- Les resultats d'outils (resumes d'emails, details d'evenements, etc.)

**Ce qui n'est PAS transmis :**
- Vos jetons OAuth ou mots de passe
- Vos identifiants de compte
- Des donnees brutes non filtrees de vos services connectes

**Engagement des fournisseurs :**
Les principaux fournisseurs (OpenAI, Anthropic, Google) s'engagent contractuellement a ne pas utiliser les donnees API pour entrainer leurs modeles. Nous vous encourageons a consulter leurs politiques respectives pour plus de details.

Lorsque Ollama est configure, les requetes sont traitees localement et aucune donnee ne quitte votre infrastructure.

## 7. Conservation des donnees

Les durees de conservation sont definies selon la nature des donnees :

| Type de donnee | Duree de conservation | Justification |
|---|---|---|
| Compte utilisateur | Jusqu'a suppression du compte | Execution du contrat |
| Historique des conversations | Jusqu'a suppression par l'utilisateur ou du compte | Continuite du service |
| Jetons OAuth chiffres | Jusqu'a deconnexion du service ou suppression du compte | Acces aux services connectes |
| Sessions Redis | Expiration automatique (24h d'inactivite) | Securite |
| Journaux techniques | 30 jours glissants | Diagnostic et securite |
| Metriques d'utilisation | 90 jours glissants (anonymisees) | Amelioration du service |

**Suppression du compte :**
Lorsque vous demandez la suppression de votre compte, toutes vos donnees personnelles sont supprimees de maniere irreversible, y compris : profil utilisateur, conversations, checkpoints, jetons OAuth chiffres et preferences. Cette suppression est effective sous 30 jours maximum.

## 8. Vos droits

Conformement au RGPD, vous disposez des droits suivants :

- **Droit d'acces** (Art. 15) : Obtenir une copie de toutes les donnees personnelles que nous detenons a votre sujet.
- **Droit de rectification** (Art. 16) : Corriger des donnees personnelles inexactes ou incompletes.
- **Droit a l'effacement** (Art. 17) : Demander la suppression de vos donnees personnelles ("droit a l'oubli").
- **Droit a la limitation** (Art. 18) : Demander la restriction du traitement de vos donnees dans certaines circonstances.
- **Droit a la portabilite** (Art. 20) : Recevoir vos donnees dans un format structure, couramment utilise et lisible par machine.
- **Droit d'opposition** (Art. 21) : Vous opposer au traitement de vos donnees fonde sur l'interet legitime.
- **Droit de retirer votre consentement** : A tout moment, sans affecter la licéite du traitement effectue avant le retrait.

Pour exercer ces droits, contactez-nous a l'adresse indiquee dans la section Contact. Nous repondrons dans un delai de 30 jours conformement au RGPD.

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
- **Code source** : [GitHub](https://github.com/jgouville/lia) (AGPL-3.0)

**Responsable du traitement :**
LIA est exploitee par un developpeur independant agissant en qualite de responsable du traitement au sens du RGPD.

**Modifications de cette politique :**
Cette politique peut etre mise a jour pour refleter les evolutions du service ou de la reglementation. En cas de modification substantielle, vous serez informe(e) via l'application. La date de mise a jour en haut du document fait foi. Nous vous encourageons a consulter regulierement cette politique.

**Transparence open source :**
LIA etant un projet open source, vous pouvez a tout moment auditer le code source pour verifier exactement quelles donnees sont collectees, comment elles sont traitees et ou elles sont envoyees. Cette transparence radicale constitue un engagement fondamental du projet.
