# Lot 4 — ABANDONNÉ après vérification : les genres prévus existent déjà

**Spécification** : [design](../specs/2026-09-11-anticipated-moments-design.md) §5
**Décision** : 2026-09-11, avant toute ligne de code.
**Statut** : le lot ne sera pas livré. Ce document dit pourquoi, parce qu'un
lot abandonné sans raison écrite revient.

---

## Ce que le plan prévoyait

Trois genres de moment de plus : `deadline_eve` (une échéance qui tombe demain),
`counterparty_silence` (un interlocuteur muet depuis un palier) et
`return_from_absence`.

## Ce que la lecture du code établit

Les deux premiers **existent déjà**, servis par le heartbeat, avec leur
anti-harcèlement :

| Genre prévu | Ce qui le couvre aujourd'hui | Fenêtre | Cooldown |
|---|---|---|---|
| `deadline_eve` (boucle) | `fetch_open_loops_context` — `due_worthy` | 48 h avant l'échéance, et au-delà | 3 jours par boucle |
| `deadline_eve` (ticket) | `_nudge_reason` — `due_soon` / `overdue` | 24 h avant l'échéance | 2 jours par ticket |
| `counterparty_silence` | `fetch_open_loops_context` — `stale_worthy`, sur une boucle sans échéance | 7 jours sans mouvement | 3 jours par boucle |

Le tick tourne toutes les trente minutes à l'intérieur de la fenêtre horaire de
la personne, donc « la veille » et « le palier franchi » sont atteints par le
chemin existant dans l'heure.

## Ce que le lot aurait ajouté

Un second chemin vers la même relance. Et pas seulement du code en double :
**deux compteurs de cooldown à tenir en phase pour un seul objet**. Le lot 1 a
déjà dû câbler le partage des compteurs dans un sens ; en ouvrir un second
chemin, c'est accepter qu'un jour une personne soit relancée deux fois sur le
même ticket parce qu'un chemin a brûlé le cooldown et pas l'autre.

Le gain, en face : servir à l'instant précis plutôt que dans la demi-heure. Sur
une échéance qui tombe demain, cela ne se voit pas.

**Ce lot est donc annulé.** C'est un faux négatif de l'analyse initiale — croire
qu'une capacité manque alors qu'elle est là — et la doctrine du dépôt le nomme :
on étend le registre existant, on ne crée pas une seconde table à la main.

## Ce qui reste ouvert, et sous quelle condition

`return_from_absence` n'est couvert par rien. Il reste hors périmètre pour deux
raisons, pas une :

1. ADR-214 §5.4 le prévoit comme une **voie ambiante**, pas comme une
   notification, et il exige un seuil RELATIF (p90 des intervalles entre
   sessions × facteur, jamais un absolu) qu'il faudrait calibrer.
2. Ce qu'il dirait — « voilà ce qui s'est passé pendant ton absence » — est ce
   que le briefing produit déjà à l'ouverture de la page.

Il reviendra si une mesure montre que les gens reviennent sans ouvrir le
briefing. Pas avant.

## Conséquence sur le programme

Le registre des genres garde un seul membre, et c'est un résultat, pas un
inachèvement : il a été écrit pour rendre le second genre additif, et il a servi
à établir que le second genre n'était pas nécessaire. Le lot suivant (les
veilles) comble un manque réel et mesuré.
