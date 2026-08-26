# Publier les apps LIA sur les stores (lot 4) — pas à pas, sans prérequis

> Ce guide suppose que vous n'avez **jamais** publié d'application. Il couvre
> tout le lot 4 : comptes, signature, fiches, formulaires, soumission, et ce
> qui recommence à chaque mise à jour. Les lots techniques (1 → 3) sont
> terminés et mergés ; rien dans ce guide ne demande d'écrire du code.
>
> Ce que vous publiez : **une seule app par store**, la coque de
> `apps/mobile/` — un client pour n'importe quel serveur LIA auto-hébergé,
> dont l'utilisateur saisit l'URL au premier lancement
> ([GUIDE_MOBILE_ANDROID](GUIDE_MOBILE_ANDROID.md),
> [GUIDE_MOBILE_IOS](GUIDE_MOBILE_IOS.md), ADR-246).

---

## 0. Décisions à prendre AVANT tout upload

Trois choix deviennent **irréversibles** au premier envoi :

1. **L'identifiant d'application** (`appId` dans
   `apps/mobile/capacitor.config.json`, aujourd'hui `com.lia.assistant`).
   Google Play le grave à jamais au premier upload ; Apple lie la clé APNs et
   l'app à ce bundle id. La convention est le nom de domaine inversé d'un
   domaine **que vous possédez** — si `assistant.lia` ne vous appartient pas,
   préférez par exemple `com.jeyswork.lia` et changez-le PARTOUT avant le
   premier envoi (le fichier config, `AndroidManifest.xml` package,
   `applicationId` Gradle via `prepare`, `APNS_TOPIC` du relais, et la garde
   `test_mobile_plugin_surface_guard.py` qui code le chemin Java).
2. **Compte individuel ou organisation.** L'individuel est plus simple (pas de
   numéro D-U-N-S chez Apple) mais votre **nom personnel** apparaît sur les
   fiches. Une organisation demande un D-U-N-S (gratuit, quelques jours de
   délai chez Apple).
3. **Le nom affiché** (« LIA » aujourd'hui, `appName` du même fichier). Les
   stores refusent les noms déjà pris ; vérifiez la disponibilité dans chaque
   console avant de vous y attacher.

### Matériel commun aux deux stores (préparez-le une fois)

| Élément | Contrainte | Où le produire |
|---|---|---|
| Icône | 512×512 (Play) et 1024×1024 (Apple), sans transparence pour Apple | l'identité « LIA Cosmos » du dépôt |
| Captures d'écran | Prises SUR l'app réelle ; chaque console impose ses tailles et vous les indique à l'upload | émulateur / simulateur, app pointée sur votre serveur |
| **URL de politique de confidentialité** | **Obligatoire sur les deux stores**, publique | une page du site LIA ; elle doit dire ce que fait l'app (rien collecté par l'éditeur ; l'URL du serveur reste sur l'appareil ; le relais de réveil voit « un appareil a été réveillé, quand, et l'IP du serveur » — reprendre la formulation d'ADR-246) |
| Texte court + description longue | Play : 80 / 4000 caractères ; Apple : sous-titre 30 | à rédiger dans l'esprit des vitrines existantes |
| **Accès pour les testeurs des stores** | Les reviewers DOIVENT pouvoir se connecter | donnez dans les notes de review l'URL du démonstrateur public + un compte de test — sans cela, refus quasi certain des deux côtés |

---

## 1. Android — Google Play, du compte à la publication

### 1.1 Le compte (une fois)

1. Allez sur `play.google.com/console` avec un compte Google.
2. Payez les frais d'inscription (25 $, une seule fois, à vie).
3. Passez la vérification d'identité (pièce d'identité ; quelques jours).
   Depuis 2023, un compte individuel doit aussi afficher une adresse et faire
   tester l'app par ≥ 20 testeurs pendant 14 jours avant la production — le
   canal « closed testing » ci-dessous sert exactement à cela.

### 1.2 La clé de signature (une fois — NE LA PERDEZ PAS)

Google Play signe l'app pour vous (« Play App Signing ») ; vous ne gérez que
la **clé d'upload** :

```bash
keytool -genkeypair -v -keystore lia-upload.keystore -alias lia-upload \
  -keyalg RSA -keysize 2048 -validity 10000
```

- Rangez `lia-upload.keystore` et ses deux mots de passe dans votre
  gestionnaire de mots de passe. **Jamais dans le dépôt** (le dépôt est
  public).
- Si vous la perdez : Play sait la réinitialiser (formulaire), car Google
  détient la clé d'app — c'est tout l'intérêt de Play App Signing.

### 1.3 Construire l'AAB de release

Play exige un **AAB** (pas l'APK de debug que produit
`task mobile:build:android`). Depuis `apps/mobile/`, après un
`task mobile:prepare:android` :

```bash
cd apps/mobile/android
./gradlew bundleRelease \
  -Pandroid.injected.signing.store.file=/chemin/vers/lia-upload.keystore \
  -Pandroid.injected.signing.store.password=MOT_DE_PASSE \
  -Pandroid.injected.signing.key.alias=lia-upload \
  -Pandroid.injected.signing.key.password=MOT_DE_PASSE
# → android/app/build/outputs/bundle/release/app-release.aab
```

Les mots de passe passent en propriétés d'invocation pour ne jamais exister
dans un fichier du dépôt — le projet `android/` est régénéré et **gitignoré**,
n'y éditez rien à la main (ADR : généré + surcouche `native/`).

Versionnage : `versionCode` (entier, doit croître à chaque upload) et
`versionName` (texte affiché). La version de la coque est **découplée** de
celle de LIA — ne l'ajoutez PAS à `scripts/release/version_surfaces.py`
(mémoire du programme : une release LIA n'envoie rien aux stores).

### 1.4 Créer l'app dans la console et remplir les formulaires

Console Play → « Créer une application » → nom, langue par défaut, gratuite.
Puis le tableau de bord vous liste les étapes obligatoires ; les réponses qui
demandent réflexion :

- **Sécurité des données (« Data safety »)** : l'éditeur ne collecte **rien**.
  L'URL du serveur est stockée localement ; les données de l'utilisateur vont
  à SON serveur, pas à vous. Le jeton de notification va au projet Firebase du
  serveur de l'utilisateur (Android) — déclarez « aucune donnée collectée par
  le développeur », et décrivez le reste dans la politique de confidentialité.
- **Classification du contenu** : questionnaire IARC ; LIA est un assistant
  généraliste — répondez selon l'usage réel (pas de contenu généré par
  d'autres UTILISATEURS visibles entre eux, etc.).
- **Public cible** : 18+ simplifie tout (pas de règles « famille »).
- **Accès à l'app** : « Tout ou partie des fonctionnalités est restreinte » →
  fournissez l'URL du démonstrateur + identifiants de test + la phrase : « app
  cliente d'un logiciel serveur auto-hébergé open source ; le testeur saisit
  l'URL fournie au premier écran ».

### 1.5 Tester puis publier

1. **Internal testing** : uploadez l'AAB, ajoutez votre propre adresse Gmail,
   installez depuis le lien — vérifiez le parcours complet sur VOTRE serveur.
2. **Closed testing** : vos ≥ 20 testeurs pendant 14 jours (obligation des
   comptes individuels récents).
3. **Production** : promotion du même AAB ; la review Google prend de quelques
   heures à quelques jours.

---

## 2. iOS — App Store, du compte à la publication

### 2.1 Le compte (annuel)

1. `developer.apple.com` → « Enroll » (Apple ID avec double facteur requis).
2. 99 $/an. **Si vous cessez de payer, l'app est retirée du store.**
3. Individuel : vérification rapide. Organisation : D-U-N-S requis.

### 2.2 Identifiants, capacité push, et LA clé APNs

Dans `developer.apple.com` → Certificates, Identifiers & Profiles :

1. **Identifiers** → « + » → App ID → le bundle id choisi en §0 → cochez la
   capability **Push Notifications**.
2. **Keys** → « + » → cochez **Apple Push Notifications service (APNs)** →
   téléchargez le fichier **`.p8`** — **téléchargeable UNE SEULE FOIS** ;
   notez le **Key ID** (10 caractères) et votre **Team ID** (visible dans
   Membership).

Cette clé `.p8` est ce qui fait de VOUS l'opérateur du relais de réveil
(ADR-246) : elle vaut pour toute votre équipe Apple et ne doit **jamais** être
distribuée. Sur le serveur qui opère le relais (le vôtre) :

```bash
PUSH_RELAY_ENABLED=true
PUSH_RELAY_SEAL_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
APNS_KEY_PATH=/chemin/securise/AuthKey_XXXXXXXXXX.p8
APNS_KEY_ID=XXXXXXXXXX
APNS_TEAM_ID=YYYYYYYYYY
APNS_TOPIC=com.lia.assistant        # le bundle id choisi en §0
```

L'API refuse de démarrer si l'un manque — c'est voulu. Les auto-hébergeurs
qui veulent des notifications iOS pointeront `PUSH_RELAY_URL` vers votre
serveur (guide iOS, section relais).

### 2.3 Construire et téléverser (macOS + Xcode obligatoires)

```bash
task mobile:prepare:ios          # régénère ios/ et pose native/ dessus
open apps/mobile/ios/App/App.xcodeproj
```

Dans Xcode :

1. Cible **App** → Signing & Capabilities → cochez « Automatically manage
   signing » et choisissez votre Team : Xcode crée certificats et profils tout
   seul (ne gérez jamais cela à la main).
2. Ajoutez la capability **Push Notifications** (bouton « + Capability »).
3. Sélectionnez « Any iOS Device (arm64) » → menu **Product → Archive**.
4. Fenêtre Organizer → **Distribute App → App Store Connect → Upload**.

### 2.4 App Store Connect : TestFlight puis soumission

1. `appstoreconnect.apple.com` → Apps → « + » → votre bundle id.
2. Le build uploadé apparaît sous **TestFlight** (~15 min de traitement) :
   installez-le sur un vrai iPhone via l'app TestFlight — c'est ici que vous
   validez push (via votre relais) et retour OAuth en conditions réelles.
3. Onglet **App Privacy** : mêmes réponses qu'au §1.4 (rien collecté par
   l'éditeur), avec une nuance : le relais — le VÔTRE — voit l'événement de
   réveil ; déclarez-le comme dans la politique de confidentialité.
4. Fiche : captures aux tailles demandées (la console liste les obligatoires),
   description, mots-clés, URL d'assistance.
5. **App Review Information** : compte de test + URL du démonstrateur + les
   notes du §2.5 — c'est le champ qui décide de la review.
6. « Add for Review » → soumission. Review : un à trois jours en général.

### 2.5 Le risque de review à connaître : la guideline 4.2

Apple refuse les apps « simple reconditionnement d'un site web ». Notre app
EST une coque WebView — assumée, mais défendable, et les notes de review
doivent le défendre AVANT le refus :

> « Cette app est le client officiel d'un logiciel serveur **auto-hébergé**
> open source (comme le sont les clients Home Assistant ou Nextcloud). Elle
> apporte des capacités impossibles au web sur iOS : notifications push
> natives via un relais (le Push API n'existe pas dans WKWebView),
> retour OAuth par le navigateur système (`lia://…`, exigé par Google),
> écran natif de configuration du serveur et écran hors-ligne natif.
> Serveur de test : https://…, compte : … »

En cas de refus 4.2 malgré tout : répondez dans Resolution Center avec les
mêmes arguments (un refus n'est pas définitif, la discussion aboutit souvent),
et en dernier recours le Review Board. Ne « gonflez » pas l'app de gadgets
natifs pour plaire — c'est le motif de refus suivant (4.2.2).

---

## 3. Ce qui recommence à chaque mise à jour de la coque

La coque ne se republie **que quand `apps/mobile/` change** — jamais pour une
release LIA (l'app charge le serveur distant : les évolutions web arrivent
toutes seules).

| Étape | Android | iOS |
|---|---|---|
| Incrémenter | `versionCode` (+1) | « Build » (auto via Xcode) |
| Construire | `./gradlew bundleRelease` (mêmes propriétés) | Product → Archive |
| Téléverser | Console Play → nouvelle release | Organizer → Upload |
| Re-tester | Internal testing | TestFlight |
| Notes de version | oui, dans la console | oui, dans App Store Connect |
| Review | oui (souvent < 24 h) | oui (1-3 jours) |

À l'année : la cotisation Apple (99 $), et les montées de « target API level »
que Google impose environ une fois l'an (une mise à jour de Capacitor suivie
de `task mobile:probe:android` et `task mobile:verify:android` — le banc
existe pour ça).

## 4. Checklist finale

- [ ] §0 tranché : bundle id définitif partout, type de compte, nom vérifié
- [ ] Politique de confidentialité en ligne (URL publique)
- [ ] Google : compte vérifié, keystore d'upload sauvegardé HORS dépôt
- [ ] Google : AAB en internal testing, parcours complet validé sur votre serveur
- [ ] Google : Data safety, IARC, accès testeurs remplis ; closed testing lancé
- [ ] Apple : compte actif, App ID + capability Push, **`.p8` téléchargé et rangé**
- [ ] Apple : relais opérationnel sur votre serveur (`PUSH_RELAY_ENABLED` + une
      notification de test reçue sur un iPhone TestFlight)
- [ ] Apple : App Privacy, fiche, notes de review 4.2 avec serveur + compte de test
- [ ] Les deux : captures réelles, description, publication 🎉
