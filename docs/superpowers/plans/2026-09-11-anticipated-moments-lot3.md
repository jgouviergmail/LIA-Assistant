# Lot 3 — Ne pas interrompre quelqu'un qui est en réunion

**Spécification** : [2026-09-11-anticipated-moments-design.md](../specs/2026-09-11-anticipated-moments-design.md) §8
**Méthode** : TDD strict. Inline, aucun sous-agent, aucune action git.

---

## Le défaut, mesuré par lecture

Rien n'empêche le heartbeat d'interrompre quelqu'un pendant une réunion. La
seule garde voisine est le cooldown d'activité, et il répond à une autre
question : « cette personne vient-elle d'écrire ? ». Quelqu'un en réunion
n'écrit précisément pas — c'est le moment où la garde existante le croit le plus
disponible.

Ce lot est indépendant du reste du programme : il réduit le bruit de la
proactivité déjà livrée, moments ou pas.

---

## T3.1 — Le prédicat, pur

`moments/busy.py` : `is_in_meeting(events, now, user_tz) -> bool`.

Vrai quand un événement **avec au moins un participant autre que la personne**
est en cours à cet instant. Les mêmes exclusions que le score, pour la même
raison : un créneau solo n'est pas une réunion, une journée entière n'est pas
une occupation, un événement décliné n'est pas honoré.

**Tests, table de cas** : rien en cours ; réunion en cours ; créneau solo en
cours ; journée entière ; réunion déclinée ; réunion qui vient de finir ; qui
va commencer ; événement illisible (jamais une exception).

---

## T3.2 — La garde

Dans `HeartbeatProactiveTask.check_eligibility`, après le drapeau et **avant**
le report de rythme.

- lecture par le cache de l'agenda, jamais un appel de plus quand il est chaud ;
- fail-open intégral : ne pas savoir n'est pas une raison de se taire ;
- réglage `MOMENTS_BUSY_GUARD_ENABLED`, défaut **ON** — c'est une réduction de
  bruit, pas une capacité nouvelle ;
- **un moment n'est jamais différé par elle** : le bloc de contournement du lot 1
  la précède déjà, et un débrief se sert précisément quand la réunion vient de
  finir.

**Tests** : différé pendant une réunion ; pas différé sinon ; pas différé quand
le réglage est OFF ; pas différé pour un moment ; fail-open sur erreur de
lecture ; l'ordre des gardes (un moment sort avant d'atteindre celle-ci).

---

## T3.3 — La métrique

`heartbeat_ticks_deferred_total` existe avec un libellé `day_class`. Elle est
**étendue** d'un libellé `reason` (`rhythm` sur l'existant, `in_meeting` sur le
nouveau), pas dupliquée : deux métriques pour « ce tick n'a pas parlé » seraient
deux endroits où lire la même chose. Le panneau qui la lit est mis à jour.

---

## T3.4 — Portes

`task lint`, `task test:backend:unit:fast`, cliquets, `.env.example` × 2.
