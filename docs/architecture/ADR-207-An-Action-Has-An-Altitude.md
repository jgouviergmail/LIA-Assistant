# ADR-207 : une action a une altitude, et l'altitude choisit la forme

- **Statut** : accepté (arbitrage propriétaire 2026-08-05)
- **Portée** : boutons et étiquettes de toute l'application — relations, hub
  Alertes, réglages (mémoire, intérêts, journaux, skills, raccourcis du chat,
  météo, localisation), espaces, export de consommation, sections
  d'administration (pricing ×3, RAG, config LLM, skills)

## Contexte

Le propriétaire a constaté, écran par écran, que des actions de même nature ne
portaient pas la même forme : « Écrire un message » en contour quand
« + Ajouter » des serveurs MCP est plein ; « Exporter » en contour dans les
journaux quand « Générer » un jeton santé est plein ; deux boutons de
suppression de ligne gris jusqu'au survol dans les raccourcis du chat quand les
passkeys portent leur rouge au repos ; cinq « Télécharger CSV » à cinq hauteurs
différentes ; des étiquettes de skills toutes grises.

ADR-205 avait conclu « un bouton d'action prend `outline` » sur un comptage de
137 sites — mais ce comptage mélangeait **toutes les altitudes** : annulations
de dialogue, préréglages de filtre, secondaires de formulaire et CTA de
section dans un seul total. Re-mesuré à l'altitude CTA seulement, la convention
majoritaire du code était déjà l'inverse : MCP, actions programmées, passkeys,
jetons santé, diffusion admin, import de skills, téléchargements CSV — tous
pleins. Les déviants étaient l'exception, pas la règle.

## Décision

**Quatre altitudes, quatre formes — et rien d'autre.**

1. **Le CTA de section** — créer, importer, exporter, consolider, écrire,
   appeler, suivre, un raccourci de hub — est **plein et thémé**
   (`variant="default"`). Il est reconnaissable partout parce qu'il est le
   même partout.
2. **La destruction de masse** — « tout supprimer » — est **pleine et rouge**
   (`variant="destructive"`), à la **même taille** que ses voisines de barre :
   deux poids égaux dans une même rangée portent la même géométrie.
3. **L'action de ligne** — l'icône dans une rangée de liste — reste discrète
   (`variant="ghost" size="icon"`), et la suppression y porte **son rouge au
   repos** (`text-destructive`), jamais seulement au survol : un code couleur
   que le pointeur doit révéler n'est pas un code, c'est un secret. Modèle :
   les passkeys.
4. **La secondaire vraie** — annuler, fermer, préréglage de filtre, retry d'un
   error-boundary, le lien de remédiation d'un bandeau d'alerte — garde
   `outline`. C'est désormais sa seule signification.

**Une étiquette est tonée par sa table, jamais par l'écran.** Les traits de
skill rejoignent `status-tone.ts` (`skillTraitTone`) : l'identité (catégorie)
en teinte primaire, le coût permanent (`always_loaded`) en ambre, les
capacités neutres. La galerie utilisateur et la section admin avaient déjà
divergé sur les mêmes libellés — c'est la dérive qu'une table unique interdit.

**Une grille d'actions aligne ses actions.** Les cinq cartes d'export CSV
étaient cinq copies à la main dont le bouton flottait sous une description de
longueur variable ; elles deviennent une carte unique (`flex flex-col` +
`mt-auto`) instanciée cinq fois — la ligne d'action est droite quelle que soit
la prose au-dessus, côté utilisateur comme côté admin (même composant).

## Conséquences

- « + Nouvelle entrée » (journaux) devient « + Ajouter », aligné mot pour mot
  sur la mémoire et les intérêts dans les six locales (l'espagnol des intérêts,
  qui disait « Agregar » quand la mémoire disait « Añadir », est aligné aussi).
- Les surcharges locales de géométrie (`h-9` des journaux, `gap-1.5` des
  skills) disparaissent : une barre = une taille = la taille de base du
  variant.
- Le bouton admin qui supprime une clé de fournisseur LLM gagne un nom
  accessible (`providers.deleteKey`, 6 locales) — il était une icône muette.
- `text-red-500` (localisation domicile) rejoint `text-destructive` : le seul
  rouge de l'app est celui du thème.
- **Remplace** la conséquence « les actions de la fiche relation et les
  raccourcis du hub prennent `outline` » d'ADR-205. Le reste d'ADR-205 (tons
  de statut, densité, `alert` solide) est inchangé.

## Alternatives écartées

**Tout `outline` (ADR-205, conservé tel quel).** Le comptage qui le fondait
additionnait des altitudes différentes ; à altitude égale, il contredisait la
majorité du code et l'œil du propriétaire.

**Rougir toutes les suppressions, y compris les icônes de ligne en plein
`destructive`.** Dix-huit boutons rouges pleins dans une liste diluent le
signal que le rouge existe pour porter ; la ligne reste discrète, le rouge au
repos suffit à la coder.

## Références

- ADR-205 — un statut nomme un ton, il n'écrit pas ses couleurs
- ADR-206 — une primitive porte son contrat
