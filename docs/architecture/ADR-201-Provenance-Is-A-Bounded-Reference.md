# ADR-201 : la provenance est une référence bornée, et une suppression laisse une pierre tombale

- **Statut** : accepté
- **Date** : 2026-08-04
- **Portée** : `domains/shared` (nouveau), `domains/journals`, `domains/agents/services`, `domains/interests`, `domains/users`, réglages frontend

## Contexte

LIA écrit des souvenirs, des entrées de journal et des centres d'intérêt à
partir de ce que le lecteur lui dit. Jusqu'ici, **rien ne reliait la conclusion
au signal qui l'a produite**. Un souvenir affirmait « vous préférez les
réunions le matin » sans que personne — pas même le lecteur — puisse savoir
d'où cela venait, ni corriger la conclusion à sa source.

Deux réponses naïves sont disponibles, et toutes deux sont mauvaises :

- **recopier le message d'origine** dans le souvenir. La conclusion devient
  alors une archive permanente de la conversation : supprimer la conversation
  ne supprime plus rien, puisque son contenu survit ailleurs. C'est une fuite
  de données déguisée en fonctionnalité ;
- **ne rien conserver** et régénérer l'explication par le modèle à la demande.
  L'explication devient alors une reconstruction plausible — exactement le
  diagnostic inventé qu'ADR-182 a retiré du produit.

## Décision

**Une provenance est une référence, pas une copie.** La table
`provenance_references` porte l'identifiant du sujet (journal, souvenir ou
centre d'intérêt), l'identifiant de la conversation et du message d'origine, et
un `outcome` parmi trois valeurs — `origin` (ce qui a produit la conclusion),
`evidence` (ce qui l'a confirmée), `contradiction` (ce qui l'a mise en doute).
Aucun texte n'est dupliqué.

**Une suppression laisse une pierre tombale, jamais une résurrection.** Les
clés vers le sujet sont en `ON DELETE CASCADE` : supprimer un souvenir supprime
sa provenance. Les clés vers la conversation et le message sont en
`ON DELETE SET NULL` : supprimer une conversation **vide la référence sans
détruire la ligne**. Le lecteur voit alors « ce signal a été supprimé » plutôt
qu'une trace de ce qu'il a effacé. Le contraire — `CASCADE` sur la conversation
— aurait fait disparaître la mention même de l'existence d'une source, ce qui
se lit comme « LIA a inventé cela ».

**La provenance est bornée par construction.** Cinq références au plus par
sujet (`PROVENANCE_MAX_REFERENCES_PER_SUBJECT`), les plus anciennes étant
élaguées à l'écriture. Une provenance non bornée est une seconde copie de
l'historique, qui grossit exactement au rythme de l'usage.

**La borne est publiée avec la réponse.** `ProvenanceResponse` porte
`kept_at_most` : ce que le système applique, il le dit (ADR-184). Une limite
appliquée en silence n'est pas un contrat, c'est un piège.

**Une contrainte `CHECK` interdit une ligne sans sujet ou à deux sujets.**
`(journal_entry_id IS NOT NULL)::int + (memory_id IS NOT NULL)::int +
(interest_id IS NOT NULL)::int = 1`. Une provenance orpheline est une ligne que
personne ne purgera jamais.

## Conséquences

**Ce que le lecteur gagne.** Sous chaque souvenir et chaque entrée de journal,
un bloc replié « Pourquoi LIA pense cela ? » liste les signaux, leur date et
leur rôle, avec un lien vers la conversation encore présente et une mention
explicite pour celle qui ne l'est plus. Le bouton « Corriger » ouvre le flux
d'édition existant du sujet — on corrige la conclusion, pas la trace.

**Ce que la suppression de compte doit faire.** `provenance_references` est
classée `_PURGED_FULL` dans `user_data_map.py` et purgée **explicitement avant
ses sujets** dans `build_purge_statements`. Sans cet ordre, la cascade aurait
suffi, mais l'inventaire RGPD n'aurait pas listé la table — et ce que
l'inventaire ne liste pas, personne ne vérifie.

**Ce qui reste ouvert.** Les trois producteurs (extraction de journal,
extraction de souvenir, application d'action d'intérêt) écrivent leur
provenance via un seul module (`shared/provenance_capture.py`). Un quatrième
producteur qui l'oublierait n'échouerait pas : sa provenance serait simplement
vide. Ce trou est acceptable aujourd'hui parce que les trois sujets sont
exhaustifs ; il ne le restera pas si un quatrième apparaît.

## Alternatives écartées

**Un champ JSON `sources` sur chaque sujet.** Trois schémas à maintenir en
miroir, aucune contrainte référentielle, et la pierre tombale devient du code
applicatif au lieu d'une règle du schéma — donc oubliable.

**Regénérer l'explication par le modèle.** Coût par lecture, non
déterministe, et invérifiable : c'est précisément la classe de bug qu'ADR-182 a
supprimée.

## Références

- ADR-182 — un diagnostic inventé est pire qu'une absence de diagnostic
- ADR-184 — une contrainte appliquée doit être publiée
- ADR-185 — un compte affiché est exact, ou il n'existe pas
