# Envoyer les SMS d’un iPhone vers LIA

LIA reçoit les messages que ton automatisation lui transmet. Elle n’accède pas directement à l’app Messages et ne récupère pas tout l’historique du téléphone. Le texte transmis peut aussi provenir d’iMessage : LIA ne vérifie pas le protocole d’origine et cette intégration ne collecte pas les pièces jointes.

## Préparer LIA

Dans Paramètres → Mes SMS, juste après Réunions, crée un jeton pour le téléphone puis confirme l’action. Copie le secret affiché une seule fois dans le navigateur d’origine. Garde un jeton par appareil et ne place jamais ce secret dans l’URL, une capture ou une discussion.

Pour renouveler un jeton du même téléphone, réutilise sa source d’ingestion. Une nouvelle source représente un autre émetteur ; elle n’hérite pas automatiquement de ses décisions de déduplication.

Trois choix restent indépendants :

- Réception : autoriser l’enregistrement des SMS transmis par le téléphone.
- Assistant : autoriser les lectures nécessaires aux réponses et synthèses ; cet accès commence désactivé.
- Push de réception : recevoir une notification générique dès l’arrivée d’un nouveau SMS accepté, à toute heure.

Les notifications proactives utiles ont aussi leur source Mes SMS dans les réglages proactifs. Elles suivent leurs propres plages et quotas. Désactiver la push de réception ne remplace pas ce réglage proactif.

## Construire l’appel Raccourcis

Adresses cibles, après mise à jour du serveur :

| Environnement | URL |
|---|---|
| Développement | https://192.168.0.29.nip.io:8000/api/v1/ingest/message |
| Production | https://lia.jeyswork.com/api/v1/ingest/message |

Dans Raccourcis, préparer un dictionnaire puis utiliser Obtenir le contenu de l’URL avec la méthode POST, un corps JSON et ces en-têtes :

~~~http
Authorization: Bearer <jeton affiché dans LIA>
Content-Type: application/json
~~~

Exemple fictif d’un message dont l’heure de réception est réellement disponible :

~~~json
{
  "schema_version": 1,
  "event_id": "812a2280-6047-4af3-9422-27e2581ec37b",
  "sender": "Alice",
  "date": "2026-10-19T09:30:00+02:00",
  "date_kind": "received",
  "body": "Le rendez-vous est déplacé à 10h30.",
  "o": "iphone"
}
~~~

Remplacer sender et body par les valeurs fournies par l’automatisation. Utiliser une date ISO 8601 avec fuseau ou décalage. Si seule la date d’exécution est disponible, utiliser cette date et date_kind: captured. Ne présenter une date comme received que si elle vient réellement du message.

Créer l’UUID une seule fois pour cet événement, avant la requête, puis garder ce dictionnaire identique pour toute reprise. Générer un nouvel UUID ou remplacer la date à chaque tentative peut créer une autre entrée. Sans event_id, LIA déduplique le contenu canonique complet, date comprise ; cela ne remplace pas une identité stable.

Le réseau de l’iPhone doit joindre l’adresse choisie. En développement, il faut notamment pouvoir atteindre l’adresse locale et faire confiance au certificat HTTPS valide utilisé par l’environnement. Ne désactive pas la vérification TLS pour contourner une erreur.

## Relier l’automatisation Messages

Créer une automatisation personnelle de réception d’un message et choisir les critères disponibles sur ta version d’iOS. Apple documente les critères d’expéditeur et de texte ; plusieurs critères se cumulent. Vérifie le périmètre réellement offert sur le téléphone : ce guide ne promet pas un déclenchement sans filtre pour tous les messages.

Utiliser les données d’entrée de cette automatisation pour construire l’appel ci-dessus et accorder les autorisations demandées par iOS. Vérifier sur l’appareil les possibilités d’exécution immédiate et le comportement lorsque l’écran est verrouillé.

Références Apple : [déclencheurs de communication](https://support.apple.com/guide/shortcuts/communication-triggers-apdd711f9dff/ios) et [requête d’API dans Raccourcis](https://support.apple.com/guide/shortcuts/request-your-first-api-apd58d46713f/ios). Choisir la version d’iOS correspondante dans ces pages.

## Vérifier puis reprendre sans doublon

1. Envoyer un message fictif non sensible avec un UUID neuf : l’accusé doit annoncer inserted et le verdict stored ; le message apparaît dans Mes SMS.
2. Réenvoyer exactement le même dictionnaire : duplicate, sans autre message ni nouvelle occurrence de notification.
3. Vérifier le fuseau du compte, le regroupement par jour et le nom de l’expéditeur. Une résolution ambiguë ou incomplète conserve la valeur reçue.
4. Tester les push selon les permissions du navigateur/appareil. Le relais iOS natif existant transmet un réveil générique sans corps SMS ; il ne garantit pas une bannière SMS personnalisée ou son lien profond.
5. Vérifier séparément le consentement Assistant, une recherche dans la discussion et, si activées, les notifications proactives utiles.

Pour une requête unitaire, stored répond normalement 201 ; duplicate ou un message ignoré, 200. Un conflit 409 signifie que le même événement porte un contenu différent. Un 422 demande de corriger le format. En lot, inspecter les verdicts de chaque élément, pas seulement le statut HTTP.

Une erreur réseau, un délai dépassé ou une erreur de stockage ne prouve pas que l’écriture a échoué. Garder l’UUID et les données ; respecter Retry-After lorsqu’il est fourni. Ne pas contourner un conflit avec un nouvel UUID.

Un raccourci élémentaire ne garantit pas une reprise persistante après fermeture, perte de réseau ou refus d’iOS. Conserver un événement en attente est une responsabilité du raccourci ; LIA ne peut pas récupérer un SMS qu’il n’a jamais envoyé. La validation physique sur ton iPhone reste nécessaire.

## Données sensibles, conservation et suppression

Les secrets d’accès reconnus — OTP, mots de passe, récupération et liens de connexion/réinitialisation identifiables — sont exclus avant stockage, tout comme les expéditeurs bloqués. C’est une détection déterministe limitée : elle ne reconnaît pas toute information privée. Les autres SMS médicaux ou bancaires ne sont pas automatiquement exclus.

Les SMS restent dans LIA jusqu’à leur suppression manuelle. Dans le détail d’un SMS, la poubelle en bas à droite le supprime directement, sans fenêtre de confirmation. Les suppressions d’un expéditeur, d’un jour, d’une période ou de tous les messages, ainsi que le blocage d’un expéditeur, conservent leur confirmation. Un blocage concerne les arrivées suivantes et n’efface pas l’historique.

Un SMS supprimé n’est pas recréé par le renvoi du même événement : une trace technique sans son contenu conserve la décision de réception. Il faut réutiliser le même identifiant d’événement et le même contenu pour les tentatives suivantes. Sans identifiant, le contenu complet, y compris la date, doit rester identique. Un nouvel identifiant, une autre source ou une date modifiée sans identifiant peut être interprété comme un nouveau SMS.

L’export des données personnelles contient les SMS lisibles. Un effacement invalide les exports encore hébergés ; il ne rappelle pas une copie téléchargée, une ancienne discussion ni une connaissance gardée séparément à partir de cette discussion. Les reçus techniques sans texte empêchent les reprises de recréer un ancien événement de la même source.

L’accès Assistant permet l’envoi des extraits nécessaires au modèle configuré, avec les politiques habituelles de quotas, coûts et traçage LLM. La réception seule ne déclenche pas de modèle ni d’apprentissage autonome. Une utilisation ultérieure dans une discussion suit les réglages et les contrats de mémoire habituels de LIA.

[Référence technique](../technical/SMS_INGESTION.md) · [Reprise opérateur](../runbooks/SMS_INGESTION_RECOVERY.md)
