# ADR-277 — Mes raccourcis : des sections de réglages épinglées, sur tous les écrans

**Statut :** Accepté — 2026-09-09
**Amende :** ADR-227 (réglages maître-détail : les tables de sections et leur
modèle), ADR-172 (recherche des réglages : les portes de disponibilité),
ADR-184 (ce qu'un système impose, il le publie), ADR-252 (le widget des yeux :
sa mécanique flottante)

---

## Contexte

La page des réglages compte cinquante-huit sections sous trois onglets et
douze groupes (ADR-227). Une personne en fréquente quatre ou cinq — celles de
son usage, jamais les mêmes d'un compte à l'autre — et chacune est à trois
gestes de n'importe quel écran : l'en-tête, la page, le rail. Le propriétaire a
demandé (2026-09-09) une section « Mes raccourcis » dans Réglages ›
Personnalisation, qui présente toutes les entrées des paramètres avec une case
à cocher, cinq au plus ; et, dès qu'une est cochée, sur TOUS les écrans de
l'application, un menu flottant fonctionnant comme l'avatar animé — déplaçable
et réductible, sans redimensionnement — qui présente les sections choisies avec
leurs icônes et emmène sur la page d'un clic.

Deux mécaniques existaient déjà et n'en font qu'une :

| Précédent | Ce qu'il apporte |
|---|---|
| Le widget des yeux (ADR-252, `useEyesDrag`) | un glisser au pointeur avec seuil, des flèches au clavier, une position en pourcentages du viewport persistée par appareil, un point de rappel quand il est réduit |
| Les raccourcis de chat (`users.chat_shortcuts`) | une liste par compte dans une colonne JSONB nullable, un schéma STRICT à l'écriture et un lecteur TOLÉRANT à la lecture, un remplacement complet, un plafond publié dans la réponse |

## Décision

**D1 — Ce qui est épinglé appartient au COMPTE ; où se trouve le menu
appartient à l'APPAREIL.** `users.settings_shortcuts` (JSONB, NULL = rien,
migration `89d81ad3b467`, classée « préférence conservée » dans
`user_data_map`) porte la liste ; la position du dock et son repli vivent dans
`localStorage` (`lia_shortcuts_dock_prefs`, hors du registre de purge SEC-035
pour la raison des yeux : une préférence d'affichage de l'appareil). Une liste
changée sur un appareil se voit sur tous ; un dock déplacé sur un téléphone ne
déplace pas celui du bureau.

**D2 — Le backend garde la FORME des jetons, jamais leur liste.** Le
vocabulaire des sections est celui du frontend (`SettingsSectionToken`,
`lib/settings-sections.ts`) : le backend valide un slug borné (≤ 64
caractères), l'unicité et le plafond, et le frontend écarte à la lecture un
jeton qu'il ne déclare plus — une section renommée depuis qu'elle a été
épinglée n'est pas un lien mort, elle disparaît. Une table serveur des
sections aurait dérivé à la première section ajoutée, et c'est précisément le
piège que le modèle du shell (ADR-227) a fermé côté frontend.

**D3 — Le plafond est un réglage, et il est PUBLIÉ** (ADR-184) :
`SETTINGS_SHORTCUTS_MAX_COUNT` (5 par défaut, 1 à 20), imposé par la route ET
par le lecteur tolérant, renvoyé par `GET /users/me/settings-shortcuts`
(`max_count`) pour que la section affiche « N / 5 » sans deviner une constante
serveur. La sixième case est `aria-disabled` et gardée par son gestionnaire —
jamais `disabled`, qui ferait tomber le focus d'un lecteur clavier sur
`<body>` — et le compteur dit pourquoi.

**D4 — La liste voyage avec le profil.** `UserBase.settings_shortcuts` est lue
par un validateur `before` qui est le lecteur tolérant lui-même : une entrée
malformée en base est écartée, jamais un 500 sur `/auth/me`. Le dock la lit
dans `useAuth().user` et ne fait AUCUNE requête : un écran ne coûte rien de
plus pour le porter. Après un enregistrement, le hook rafraîchit
l'utilisateur, et tous les écrans suivent.

**D5 — Une seule mécanique flottante.** `useEyesDrag` est GÉNÉRALISÉ en
`useFloatingDrag(rootRef, position, setPosition)` : le hook ne possède aucun
store, chaque widget garde son emplacement, et les yeux le réutilisent tel
quel. Deux précisions gagnées au passage, parce qu'un dock est fait de liens :
une pression sur un contrôle interactif (bouton, lien, champ) n'est jamais un
glisser, et les flèches ne déplacent la surface que lorsqu'elle porte
ELLE-MÊME le focus — les flèches d'un lien sont au lien.

**D6 — Le sélecteur est le modèle du shell.** La section liste
`buildSettingsShellModel` sous `useSettingsAvailability` — extrait de la page
des réglages, lu désormais par le rail, la recherche et le sélecteur — de sorte
que le sélecteur ne peut pas offrir une section que le shell n'affiche pas ;
groupée comme le rail, avec les teintes de groupe (ADR-208 : la teinte marque
le GROUPE, jamais un état) ; la section s'exclut elle-même, un raccourci vers
l'endroit où l'on choisit les raccourcis n'aidant personne.

**D7 — Le dock ne dessine que ce que le compte peut ouvrir.** Une section
d'administration épinglée par un super-utilisateur qui ne l'est plus serait un
lien vers un panneau absent : filtrée sur `is_superuser`. Les autres portes
(drapeaux d'instance) restent celles du panneau — le dock ne consulte pas
`/config` pour ne pas doubler une requête sur chaque écran.

**D8 — Esthétique et cibles.** Une capsule verre (`bg-background/85
backdrop-blur-xl`, bord `border-border/60`), 44 px par lien, l'icône de la
section dans la teinte de son groupe, infobulle et nom accessible = titre de
la section, une poignée en tête, un bouton de repli en pied ; réduite, une
pastille de 44 px avec l'épingle. Bord droit à mi-hauteur par défaut — hors des
yeux (au-dessus du composeur) et du compagnon (en bas à gauche) — et z-30 comme
les yeux : sous les dialogues et les toasts, et déplaçable de toute façon.

## Conséquences

- Nouveau jeton `my-shortcuts` dans les quatre tables de sections
  (`SETTINGS_SECTIONS`, `SETTINGS_SEARCH_META`, `SETTINGS_SECTION_ICONS`,
  `SETTINGS_SECTION_REGISTRY`) : 58 sections, la garde de la recherche le
  compte ; icône `Pin`, unique parmi les cinquante-huit.
- Deux routes, `GET`/`PUT /users/me/settings-shortcuts`, ajoutées à la surface
  publique figée du démonstrateur.
- `useSettingsAvailability` remplace le `useMemo` de la page des réglages ;
  `useEyesDrag` devient une enveloppe de trois lignes.
- Locales ×6 (section, mots-clés de recherche, dock) dans le registre de
  l'application (vous / Sie / tú / tu / 您).

## Suites (2026-09-10, retours du propriétaire)

- **Le dock replié se déplace, et l'avatar réduit aussi.** La pastille de
  repli est un bouton, et `useFloatingDrag` écartait toute pression sur un
  élément interactif — y compris la surface elle-même. Seuls les DESCENDANTS
  interactifs sont désormais laissés à leur sémantique ; une surface qui est
  un bouton se déplace comme les autres, et le clic qu'un dépôt laisse
  derrière lui est avalé plutôt que lu comme « déplier » (`wasRecentDrag`).
  Le point de rappel des yeux suit la même règle et partage l'emplacement
  persistant du widget : les yeux reviennent là où le point a été laissé.
- **Le bouton de repli est au-dessus du premier raccourci**, la poignée au
  pied de la capsule : un pouce qui vise le haut de la capsule le trouve.
- **La capsule se déplie vers la place qu'elle a.** Dépliée depuis la moitié
  basse de l'écran elle grandit VERS LE HAUT — son pied est épinglé où était
  le pied du bouton replié, par un `bottom` CSS qui n'exige aucune mesure de
  hauteur — et l'emplacement mémorisé reste celui du bouton, si bien qu'un
  nouveau repli le remet exactement où il était ; depuis la moitié haute elle
  grandit vers le bas. Le sens est décidé AU DÉPLIAGE et jamais re-dérivé : une
  capsule montée puis glissée engage son vrai sommet et repousse vers le bas
  depuis là, donc reste où on l'a lâchée ; pendant qu'elle monte, le hook ne
  reçoit aucun emplacement et lit le rectangle réel pour ses flèches et son
  recadrage. Avant : dépliée près du bas, elle dépassait l'écran ou le
  recadrage déplaçait l'emplacement mémorisé, et le bouton replié sautait.

## Preuves

Mesurées le 2026-09-09 sur l'instantané livré, du plus proche au plus large :

- **Backend** — 55 tests ciblés (schéma strict, lecteur tolérant, DTO lu tel
  quel, les deux routes, complétude du profil, carte des données, surface du
  démonstrateur), puis 570 sur `users`, `shared`, `auth`, `api`, `chat` et
  les gardes AST, puis la suite unitaire rapide COMPLÈTE
  (`task test:backend:unit:fast`, 25 061 tests) — qui a rendu deux échecs
  hérités des lots 14–15 et invisibles aux suites ciblées, tous deux dans des
  tests : une adresse réelle copiée d'un exemple (garde anti-PII) et un libellé
  d'événement dérivé non déclaré à la garde des orphelins, corrigés et
  re-vérifiés ; `task lint:backend` vert (mypy strict, 1 514 fichiers) ;
  `task db:migrate:replay-check` OK sur une base vierge (`89d81ad3b467`) ;
  `task test:markers` OK (27 269 tests collectés) ; `task lint:hygiene` vert
  (les deux `.env` d'exemple portent le nouveau réglage).
- **Frontend** — 497 tests sur les onze suites du lot (hook générique, store,
  hook des raccourcis, sélecteur, dock, widget des yeux inchangé, les quatre
  gardes de tables), puis la suite complète : 622 fichiers, 7 907 tests verts ;
  `tsc` non incrémental propre ; `task lint:frontend` vert, les trois ratchets
  tenus — l'a11y et le texte atténué ont chacun refusé une première version
  (un harnais `div` sans rôle, un glyphe en `text-muted-foreground/70`), et
  c'est le code qui a bougé, jamais la base ; `task lint:i18n` : parité des
  six locales.
- **Navigateur réel** — `smoke/shortcuts-dock.spec.ts`, 4 parcours hermétiques
  sur le conteneur web : le dock nommé, ses liens vers les liens profonds, sa
  survie à la navigation, le repli et la restauration, l'absence tant que rien
  n'est épinglé, le sélecteur qui envoie la liste ENTIÈRE sur une seule case —
  et axe sans violation bloquante sur les deux états.
- **Runtime** — compte jetable créé dans l'instance de développement puis
  supprimé : `GET` avec le plafond, `PUT` stocke une nouvelle liste,
  `/auth/me` la porte, un de trop → 400, un jeton malformé ou un doublon →
  422 sans rien écrire, la liste vide dépingle tout ; puis une ligne poubelle
  écrite directement en base (`["theme", 1, "BAD ID", "theme"]`) lue par
  `/auth/me` et par la route comme `["theme"]`, jamais un 500. ALL PASS.
- **Documentation** — `task lint:docs:preview` sans dérive, index et
  décomptes réalignés par `task release:sync-counts`, `AGENTS.md` régénéré.
