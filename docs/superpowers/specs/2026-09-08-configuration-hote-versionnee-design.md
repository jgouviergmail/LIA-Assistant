# Configuration de l'hôte versionnée — le dépôt devient autoritaire

> **2026-09-08.** Conçu après une mise à jour de `cloudflared` qui a mis au jour
> deux dérives silencieuses : le runbook annonçait un protocole que la
> configuration vivante avait cessé d'utiliser six semaines plus tôt, et le
> gabarit d'infrastructure du dépôt était un instantané figé depuis six mois,
> amputé d'un protocole, d'un réglage réseau et d'un ingress entier. Aucune
> garde ne pouvait les voir : les deux fichiers sont hors de git **et** hors de
> `lint:docs`.
>
> **Révisé le même jour** après auto-critique : la première version affirmait que
> l'hôte pouvait se contrôler seul, ce que son architecture rendait impossible ;
> elle fondait deux questions distinctes sous un seul mot ; elle faisait entrer
> le pare-feu dans un modèle qui ne lui convient pas ; et elle citait un compte
> faux.

## Le problème, mesuré

La configuration qui fait tourner la production n'existe qu'à un seul endroit :
l'hôte. Le dépôt en garde des copies, mais rien ne les relie au réel.

| Fait | Mesure |
|---|---|
| Le gabarit d'infra du dépôt datait de six mois | Il lui manquait `protocol`, un réglage de famille d'adresses, et un ingress complet |
| Le runbook affirmait le mauvais protocole | Écart de six semaines, invisible jusqu'à une lecture manuelle |
| Deux incidents de configuration en un an | Une ligne perdue lors d'une édition, une valeur non quotée refusée au démarrage |

Rejouer cette configuration sur un hôte neuf demande aujourd'hui de la
reconstituer de mémoire. C'est le problème à supprimer.

## Périmètre : trois classes d'objets, trois modèles

La première version traitait tout comme « un fichier à installer ». C'est faux
pour deux des trois classes, et cette confusion est la cause de la moitié de ses
défauts.

**1. Fichiers déclaratifs** — huit fichiers dont le contenu nous appartient : la
configuration du tunnel, l'unité du tunnel, le script du chien de garde réseau
avec son unité et sa minuterie, la désactivation de l'économie d'énergie WiFi,
la persistance du journal système, et la configuration du démon Docker.
**Sept des huit ne portent aucune valeur personnelle** et sont versionnés tels
quels ; seule la configuration du tunnel est un gabarit. Modèle : installation à
un chemin, avec une action déclarée après.

**2. Règles de pare-feu** — elles portent des valeurs personnelles et ne sont
**pas** un fichier installable. Modèle par convergence, décrit plus bas.

**3. Artefact épinglé** — le binaire du tunnel, désigné par une version et une
empreinte. Ni fichier du dépôt, ni règle : modèle d'acquisition vérifiée.

Le fichier d'identifiants du tunnel est un secret pur : jamais rendu, jamais
comparé, copié depuis le coffre quand il est absent.

**Hors périmètre** : l'installation du système, les paquets, l'utilisateur, le
matériel spécifique au boîtier, et tout service sans rapport avec LIA. Un hôte
vierge reste une opération manuelle ; ce document couvre ce qui vient après.

## Contraintes dures

1. **Aucune fuite.** Ni identifiant d'infrastructure, ni nom d'hôte interne, ni
   adresse, ni secret ne doit entrer dans git. Le dépôt est public.
2. **Aucune tâche récurrente pour l'exploitant.** Le contrôle se déclenche seul
   et la correction s'applique seule au déploiement.
3. **Le service ne peut pas rester à terre.** Toute application qui casse le
   tunnel se rétablit d'elle-même.

## Architecture

Le déchiffrement ne peut avoir lieu que sur le poste de développement : l'hôte
n'a ni `sops`, ni `age`, ni clé — et ce fait est structurant, pas accidentel. Y
déposer une clé reviendrait à ranger le coffre à côté de ce qu'il protège.

**Conséquence, et c'est le pivot de cette révision : l'hôte ne peut pas calculer
ce qu'il devrait contenir.** Il ne sait pas rendre les gabarits. Toute promesse
d'un contrôle autonome sur l'hôte doit donc s'appuyer sur autre chose que le
rendu.

```
Poste de dev                             Hôte
────────────                             ────
valeurs chiffrées ──sops──> valeurs
                              │
gabarits versionnés ──rendu───┤
                              │
                        paquet rendu ──scp──> dossier temporaire
                                                      │
                                          script d'application
                                                      │
                                        compare · valide · installe
                                                      │
                                        vérifie · restaure si besoin
                                                      │
                                          dépose les EMPREINTES
                                                      │
                                     (la minuterie quotidienne
                                      compare à ces empreintes)
```

### Arborescence

```
infrastructure/host/
  manifest.yaml           SUIVI    fichiers déclaratifs et actions
  firewall.yaml           SUIVI    règles, avec valeurs substituées
  artifacts.yaml          SUIVI    version et empreinte du binaire épinglé
  files/                  SUIVI    fichiers statiques et gabarits
  values.example.yaml     SUIVI    la forme des valeurs, exemples neutres
  values.enc.yaml         IGNORÉ   les valeurs réelles, chiffrées
  secrets/                IGNORÉ   les identifiants du tunnel, chiffrés
```

## Les deux questions

« Dérive » recouvrait deux questions différentes. Les confondre, c'est laisser un
seul prédicat répondre à deux interrogations — le motif que le projet combat
partout ailleurs.

| Question | Réponse possible où | Détectée par |
|---|---|---|
| **Quelqu'un a-t-il édité l'hôte à la main ?** | Sur l'hôte, sans clé | Comparaison aux empreintes déposées lors de la dernière application |
| **L'hôte est-il en retard sur le dépôt ?** | Là où le rendu est possible | Comparaison du rendu au réel, au déploiement |

Les empreintes sont écrites par l'application elle-même : elles disent « voici ce
que nous avons installé ». Toute divergence ultérieure est, par construction, une
édition manuelle. C'est la menace réelle, et elle devient détectable sans clé.

Ce qu'elles ne disent **pas** : si le dépôt a changé depuis. Une liste
d'empreintes fraîche sur un hôte en retard reste silencieuse — et c'est correct,
tant que les deux questions restent nommées séparément partout, y compris dans
les métriques.

## Le manifeste des fichiers déclaratifs

Chaque entrée déclare la source, la destination, le mode, le propriétaire, et
l'action qui suit : rien, rechargement du gestionnaire de services, ou
redémarrage d'un service nommé.

Un fichier présent dans `files/` mais absent du manifeste **fait échouer le
contrôle**. C'est la doctrine de complétude au démarrage déjà appliquée aux
registres du projet : un tableau silencieux sur une clé inconnue est la façon
dont une fonctionnalité meurt sans bruit.

## Le rendu

Sur le poste, dans un dossier temporaire détruit par un `trap`, jamais dans
l'arbre du dépôt.

Une variable absente du fichier de valeurs est une **erreur dure**. Jamais de
substitution vide : c'est ainsi qu'on déploie une configuration amputée sans
s'en apercevoir — exactement la classe de défaut que ce travail existe pour
supprimer.

## L'application

`--check` compare et sort en erreur sur divergence, sans rien toucher.

`--apply` sauvegarde, installe, et **saute les fichiers identiques** : aucun
redémarrage n'a lieu quand rien n'a changé. Les actions consécutives sont
groupées et dédupliquées. En fin de course, il dépose la liste d'empreintes qui
arme le contrôle autonome.

Deux protections viennent de la mise à jour du 2026-09-08 :

**Pré-vol avant toute installation.** La configuration rendue est validée par le
binaire cible avant d'être installée. Ce jour-là, cette étape a intercepté une
valeur numérique non quotée que le nouveau binaire refusait : installer d'abord
et valider ensuite aurait laissé le service mort. La leçon appartient au script,
pas à un runbook qu'on oublie de lire.

**Vérification puis restauration automatique.** Après un redémarrage du tunnel,
on attend l'établissement des connexions attendues. Absentes au bout du délai,
les sauvegardes sont restaurées, le service redémarré, et la commande sort en
erreur. L'absence d'exception n'est pas une preuve de succès.

## Le pare-feu : convergence, pas installation

Les règles ne sont pas un fichier qu'on écrit. Elles vivent dans un fragment
généré par l'outil, doublé d'un jumeau pour l'autre famille d'adresses qu'il faut
garder cohérent, et l'outil les régénère. Les installer à la main est fragile.

Modèle retenu : une liste de règles déclarée, avec ses valeurs substituées, et
une convergence — lire l'état courant, ajouter ce qui manque, retirer ce qui est
en trop, ne rien faire quand l'ensemble correspond déjà. Jamais de remise à zéro
suivie d'un rechargement : la fenêtre entre les deux est exactement le moment où
l'accès se perd.

**Minuterie d'annulation.** Le pare-feu est le seul élément du périmètre dont une
mauvaise application ne se rattrape pas à distance :

1. programmer la restauration de l'état précédent dans quelques minutes
2. converger vers les règles déclarées
3. le poste vérifie qu'il joint toujours l'hôte
4. si oui, annuler la minuterie ; sinon, ne rien faire — l'hôte se rétablit seul

## L'artefact épinglé

Le binaire du tunnel est désigné par une version et une empreinte. L'opération
n'est pas une installation de fichier : télécharger, **vérifier l'empreinte**,
valider la configuration existante avec le nouveau binaire, arrêter, remplacer en
conservant le précédent sous son numéro de version, redémarrer, vérifier, et
restaurer l'ancien si la vérification échoue.

C'est la procédure exécutée à la main le 2026-09-08 ; elle est reprise ici parce
qu'elle a prouvé sa valeur le jour même en interceptant un défaut avant
installation.

## Le démon Docker : un cas à part

Modifier sa configuration impose de recharger ou redémarrer le démon — l'action
la plus perturbatrice du périmètre, puisqu'elle touche tout ce qui tourne. La
configuration actuelle déclare vouloir préserver les conteneurs au redémarrage du
démon, mais **cette propriété doit être vérifiée avant qu'on s'y fie**, sur un
hôte jetable et jamais sur la production.

En attendant cette vérification, ce fichier est déclaré en **contrôle seul** :
une divergence est signalée, jamais appliquée automatiquement. Le passage en
application automatique est une décision distincte, prise sur preuve.

## Déclenchement

- **Au déploiement** : rendu, comparaison au réel, et **application** de ce qui
  diverge — le dépôt est autoritaire.
- **Quotidiennement sur l'hôte** : une minuterie systemd qui **contrôle et
  alerte, sans jamais appliquer**. Une minuterie qui annule silencieusement à
  trois heures du matin le correctif d'urgence qu'un humain vient de poser est un
  automate qui se bat contre son exploitant. Elle porte un **jitter** — la règle
  du projet l'impose à tout travail périodique, parce que des périodes partageant
  un diviseur s'alignent pour la vie du processus.

## Observabilité

Deux questions, donc deux séries distinctes : l'une pour l'édition manuelle
détectée sur l'hôte, l'autre pour le retard sur le dépôt constaté au
déploiement. Les fondre donnerait un chiffre dont personne ne saurait dire ce
qu'il faut faire.

Elles sont exposées par le collecteur textfile de l'exporteur de nœud, qui n'est
pas activé aujourd'hui ; l'activer fait partie du travail. La règle du projet
interdit une métrique que personne ne peut voir, donc un panneau et une alerte
les accompagnent, et l'expression du panneau prévoit le cas où la série n'a
jamais été émise — une série jamais produite s'affiche « pas de données » là où un
exploitant attend un zéro vert.

## Ce qui rend la contrainte « aucune fuite » vérifiable

Un test échoue si un fichier suivi contient une valeur issue du fichier de
valeurs. C'est le filet décisif : il ne dépend ni de la vigilance d'un auteur ni
d'une ligne de `.gitignore`, et il attrape le cas réel — une vraie valeur collée
dans un gabarit « juste pour essayer ». Il couvre les trois déclarations, pas
seulement les gabarits, puisque les règles de pare-feu portent elles aussi des
valeurs personnelles.

Il s'accompagne d'une garde de complétude sur les règles d'exclusion : tout
chemin déclaré ignoré doit l'être effectivement, vérifié en interrogeant git
plutôt qu'en relisant le fichier d'exclusion.

## Le sens de la vérité

Après la capture initiale, **le dépôt est autoritaire**. Il n'existera pas de
mode « recapturer depuis l'hôte » : ce serait transformer la dérive en source de
vérité, c'est-à-dire supprimer le seul signal que ce système existe pour donner.

La capture initiale est une opération unique, vérifiée en comparant le rendu au
réel jusqu'à égalité stricte.

## Tests

| Objet | Nature |
|---|---|
| Rendu des gabarits | Unitaire : substitution, et échec dur sur variable manquante |
| Complétude manifeste ↔ fichiers | Garde, à l'image des assertions de registre du projet |
| Absence de fuite | Garde : aucune valeur du coffre dans une déclaration suivie |
| Convergence du pare-feu | Unitaire : ajout, retrait, et cas déjà conforme sans action |
| Idempotence | Deux applications consécutives : la seconde ne redémarre rien |
| Empreintes | Une édition manuelle simulée doit être détectée sans clé |
| Restauration | Une configuration volontairement fautive doit déclencher le retour arrière |
| Preuve d'exécution | Contrôle en 0 sur l'hôte réel après la capture initiale |

L'idempotence, les empreintes et la restauration ne sont pas vérifiables par des
simulacres : elles demandent un hôte. Elles seront prouvées en mode contrôle
d'abord, puis sur une application réelle observée.

## Étapes

1. Structure, les trois déclarations, valeurs chiffrées, gardes anti-fuite
2. Rendu et son test unitaire
3. Contrôle seul, prouvé sans rien modifier
4. Application des fichiers déclaratifs : sauvegarde, pré-vol, vérification,
   restauration, dépôt des empreintes
5. Convergence du pare-feu et sa minuterie d'annulation
6. L'artefact épinglé
7. Câblage au déploiement, minuterie de contrôle, métriques, panneau, alerte
8. Capture initiale et preuve d'égalité stricte avec le réel
9. Vérification du comportement du démon Docker sur hôte jetable, puis décision
   sur son passage en application automatique
