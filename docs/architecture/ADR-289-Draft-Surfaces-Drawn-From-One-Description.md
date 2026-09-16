# ADR-289 — Un brouillon et son résultat sont décrits une fois, dessinés par surface : carte `lia-card` dans le chat, Markdown sur le ticket

- **Statut** : Accepté
- **Date** : 2026-09-16
- **Amende** : ADR-276 lot 13 (le Markdown reste la forme d'une surface qui ne
  rend aucun balisage ; il n'est plus la SEULE forme), ADR-276 lot 14 (une
  seule autrice de la forme — c'est désormais la DESCRIPTION, et non plus un
  renderer Markdown, que toute surface dessine), ADR-274 (le renderer possède
  la forme, le modèle le sens), ADR-288 (la suite de brouillons s'ouvre sur ce
  que le tour a préparé), ADR-185 (un compte rendu dit ce qui a été fait, à
  qui, avec quoi — pas seulement un libellé)
- **Périmètre** : `domains/agents/drafts/card_spec.py` (nouveau),
  `domains/agents/drafts/card_html.py` (nouveau),
  `domains/agents/drafts/preview_renderer.py`,
  `domains/agents/drafts/result_renderer.py`,
  `domains/agents/services/hitl/interactions/draft_critique.py`,
  `domains/agents/nodes/hitl_dispatch_node.py`,
  `domains/agents/nodes/response_node.py`, `core/i18n_hitl.py`,
  `core/constants.py` (`DRAFT_RESULT_EXCERPT_MAX_CHARS`)

## Contexte

Trois retours du propriétaire sur la première suite de brouillons (ADR-288,
captures du 2026-09-16) :

1. **L'aperçu avait disparu.** La question groupée d'avant listait les deux
   e-mails avant de montrer le premier ; la suite ouvrait directement sur
   « Brouillon 1 sur 2 » et sa carte.
2. **La carte de brouillon était plate.** Titre gras, puces, paragraphes : du
   Markdown, alors que le chat dessine chaque donnée — e-mail, événement,
   contact — en carte `lia-card` avec en-tête, illustration, sections. Le
   lot 13 avait choisi le Markdown pour qu'un commentaire de ticket, texte
   échappé, puisse l'aplatir ; ce choix de surface était devenu la forme
   unique.
3. **Le compte rendu d'un lot ne disait que les libellés.** « ✅ Tout va bien »,
   « ✅ Penser à appeler Hua demain » : la personne qui venait d'approuver deux
   envois ne lisait, dans la réponse, ni à qui ni quoi. Le résultat d'un
   brouillon SEUL montrait déjà ses champs (destinataire, objet, corps, lien) ;
   celui d'un lot, non.

Les 27 renderers par type produisaient des lignes Markdown : la forme était
décidée là où le contenu l'était, et une seconde forme aurait été une seconde
autrice — exactement ce que le lot 14 interdit.

## Décision

1. **Une description, deux formes.** Les renderers par type décrivent la carte
   (`card_spec.py` : `Row`, `Note`, `Block`, `CardSpec`) ; `to_markdown_lines`
   la dessine dans la grammaire du lot 13, **au caractère près** — le filet
   « golden » `test_detailed_preview_characterization.py` n'a pas été
   régénéré, c'est la preuve ; `card_html.to_html_card` la dessine en
   `lia-card` avec les classes que les cartes de données utilisent déjà
   (`lia-card-top`, `lia-illus`, `lia-d-row`, `lia-sec`, `lia-desc-block`),
   chaque valeur échappée, les paragraphes d'un corps en `<br>`, une seule
   ligne pour voyager en un seul fragment de flux. Une `Row` porte la clé de
   son champ pour qu'une surface qui dessine des icônes en choisisse une.
2. **La surface est décidée par le run, jamais devinée par un appelant.**
   `card_surface()` rend sans balisage (`PLAIN`, la forme Markdown) dans trois
   cas : un run de ticket (son origine hors-tour le dit ; le commentaire est
   aplati ensuite par `markdown_to_plain_text`), un canal externe (le
   gestionnaire Telegram déclare `plain_surface_ctx` autour de tout le flux —
   son formateur coupe tout HTML dès le premier `<div`, une carte y aurait
   tronqué la question et vidé le compte rendu), et une personne qui a choisi
   l'affichage `markdown` (elle a demandé du texte). Tout le reste est le chat
   (`CHAT`). La question de critique et le nœud de réponse la demandent ; le
   défaut de `render_confirmation_card` et de `render_execution_result` reste
   `PLAIN`.
3. **La suite s'ouvre sur ce que le tour a préparé, sans clic de plus.** La
   première présentation du premier brouillon porte `sequence_drafts` (tous
   les brouillons, dans l'ordre) ; la question s'ouvre sur « N brouillons à
   relire » (six langues) et une ligne par brouillon, chacune dans le
   vocabulaire de SON type (`format_hitl_item_preview`), puis la position et
   la carte. Une re-présentation après une modification ou une clarification,
   et les interruptions suivantes, ne répètent rien. La confirmation
   reste une par brouillon : la v1.14.5 avait retiré l'approbation de plan
   parce qu'elle doublait les confirmations, et « ne jamais poser deux fois la
   même question » est écrit.
4. **Le résultat est décrit lui aussi** (`describe_execution_result` →
   `ResultSpec`, `ResultItem`) et dessiné par surface (`to_html_result`).
   Chaque entrée d'un lot porte les champs clés que le registre d'affichage
   déclare pour son type (`detail_fields`), moins ce que la ligne dit déjà
   (son libellé, sa date), le premier champ texte devenant un **extrait** d'une
   ligne, borné par `DRAFT_RESULT_EXCERPT_MAX_CHARS`, entre « ». Un e-mail dit
   son destinataire et le début de son corps ; un événement son lieu et sa
   date ; un contact son e-mail et son téléphone. Le résultat d'un brouillon
   seul est inchangé en Markdown (mêmes lignes, décrites) et devient une carte
   dans le chat. L'extrait est cité avec les guillemets de la langue
   (`EXCERPT_QUOTES` : « » en français, espagnol et italien, “ ” en anglais et
   en chinois, „ “ en allemand).

5. **Le modèle garde les mots d'une carte de brouillon.** Le filtre de
   contexte réduit une réponse HTML à sa prose d'en-tête pour que le modèle ne
   ré-émette jamais de balisage ; appliqué à la question et au compte rendu,
   il aurait effacé de la mémoire de la conversation ce qui a été envoyé et à
   qui (une carte de résultat s'ouvre sur son balisage : sa prose est vide).
   `message_filters._prose_of_html_answer` aplatit une carte `lia-draft*` en
   texte ; une carte de donnée garde la réduction historique.

## Conséquences

- Dans le chat, un brouillon à confirmer et le résultat de son exécution
  ressemblent enfin à la carte de donnée qu'ils annoncent — tous domaines,
  d'un coup, sans CSS ni front nouveaux : la feuille de style et le
  sanitiseur connaissaient déjà ces classes.
- Sur un ticket, rien ne change : le commentaire reste le Markdown aplati.
- Ajouter un type de brouillon reste un renderer qui DÉCRIT ; il obtient les
  deux formes.
- Les tests qui appelaient les renderers privés sérialisent désormais la
  description avant d'affirmer sur du texte.

## Ce que ce n'est pas

- La carte d'action du front (`HitlActionCard`, boutons et aperçu compact
  e-mail) n'a pas bougé : elle est un composant, pas une surface de rendu du
  serveur.
- L'extrait ne remplace pas le corps : le résultat d'un brouillon seul montre
  toujours le texte entier ; l'extrait est la forme d'une LIGNE de lot.
