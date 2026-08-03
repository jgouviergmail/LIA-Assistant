# ADR-198 : une routine s'exécute au plus une fois par jour local

**Statut**: ✅ IMPLEMENTED (2026-08-03)
**Date**: 2026-08-03
**Décideurs**: Équipe LIA
**Complète**: [ADR-175](ADR-175-Routine-Condition-Triggers.md) (routines à condition), [ADR-185](ADR-185-Exact-CRM-Counts-And-Readable-Relayed-Messages.md) (un chiffre montré est une affirmation)

## Contexte

Le studio des routines affichait **une seule** prochaine exécution. La demande
était d'en montrer cinq. En instrumentant le planificateur pour les calculer,
un défaut de production est apparu — présent depuis toujours, invisible 364
jours par an.

### Ce que la mesure établit

Simulation différentielle contre APScheduler 3.11 — le moteur que l'exécuteur
utilise lui-même — sur les transitions 2026 de sept fuseaux, dont des décalages
à la demi-heure, un à 45 minutes, l'hémisphère sud, et Lord Howe dont le
changement d'heure vaut **30 minutes** :

- **Au passage à l'heure d'hiver, l'heure murale existe deux fois.** Le cron
  produit donc deux instants distincts pour le même jour local. Les dix sites
  de reprogrammation appellent tous `compute_next_trigger_utc` **sans
  référence**, c'est-à-dire « le prochain après maintenant » : à 00:30 UTC la
  routine s'exécute, puis **59 min 55 s plus tard** elle s'exécute encore.
  **54 doubles exécutions** sur les transitions 2026 des sept fuseaux.
- **L'heure touchée dépend du fuseau.** Santiago est frappé à **23:00**, pas à
  2 h du matin — un test qui n'aurait couvert que la nuit européenne aurait été
  faussement rassurant.
- **Au passage à l'heure d'été, l'heure murale peut ne pas exister.** Le
  déclencheur renvoie tout de même `02:30` portant l'**ancien** décalage :
  l'instant réel est `03:30` locale. Afficher le datetime rendu annoncerait une
  heure à laquelle la routine ne s'exécutera pas.

## Décision

**Le modèle n'autorise qu'une heure par jour** (`trigger_hour` +
`trigger_minute` uniques, plus les jours de la semaine). Cette propriété — et
non une intuition — rend sûre la règle : **au plus une exécution par jour
local**. Un second instant pour le même jour est l'artefact de la transition,
jamais une exécution demandée.

**Une exécution consommée n'est pas un test manuel.** `execute_single_action`
sert le planificateur ET le bouton « tester maintenant ». Appliquer la règle
aveuglément **supprimerait** l'exécution à venir : tester une routine de 08:00
à 07:00 la repousserait à demain. La reprogrammation distingue donc les deux
par `due_at <= now` — une échéance consommée d'un créneau encore à venir.

**L'affichage lit l'instant, jamais le datetime du déclencheur.** Les cinq
occurrences voyagent en instants UTC ; le client les rend avec `Intl` dans le
fuseau **de la routine** (publié à côté), pas celui du navigateur — un
utilisateur en déplacement lit les heures auxquelles la routine s'exécutera
réellement. Un changement de nom de fuseau entre deux occurrences est signalé :
l'heure murale ne bouge pas, l'instant si, et sans mention le lecteur ne verrait
aucune différence entre deux lignes.

**Une condition n'est pas une exécution.** Pour une routine à condition, les
mêmes occurrences sont présentées comme des **fenêtres d'évaluation** :
prétendre connaître la date à laquelle la condition deviendra vraie serait une
invention.

## Conséquences

**Non-régression prouvée par simulation, pas par raisonnement** : 15 036
scénarios de reprogrammation, **54 divergences — exactement les 54 doubles
exécutions**, et zéro ailleurs. Une première règle candidate avait été
**réfutée** de la même manière : elle décalait d'un jour même en UTC, où aucun
changement d'heure n'existe, parce que `get_next_fire_time` est inclusif et
qu'une référence tombant pile à l'heure planifiée était lue comme « déjà
servie ».

**Le calcul reste unique.** Rien n'est réinterprété dans le navigateur : une
seconde lecture du cron serait une seconde autorité, et les deux divergeraient
précisément aux transitions.

**Corollaire i18n corrigé au passage** : `format_schedule_display` alimente les
outils d'automatisation, donc son texte est lu par le modèle puis restitué à
l'utilisateur. Il ne servait que `fr` et `en` — les quatre autres langues
recevaient de l'**anglais**. Les libellés passent par `i18n_dates` et une table
de formulations compactes ; les abréviations de jours sont **déclarées** et non
tronquées (`"Mittwoch"[:3]` donne `Mit`, l'allemand écrit `Mi`).

## Alternatives écartées

**Corriger sur les dix sites d'appel.** Dix occasions d'oublier le prochain, et
la règle métier dispersée. La correction vit dans la fonction que tous
appellent.

**Dédupliquer à l'affichage seulement.** Aurait masqué la ligne en double sans
empêcher la seconde exécution — le symptôme retiré, la cause intacte.

**Ignorer le défaut** (une nuit par an). Le créneau est atteignable depuis le
formulaire (heures entières, minutes par pas de cinq), et une routine qui écrit
— envoie un message, crée un événement — le ferait deux fois.
