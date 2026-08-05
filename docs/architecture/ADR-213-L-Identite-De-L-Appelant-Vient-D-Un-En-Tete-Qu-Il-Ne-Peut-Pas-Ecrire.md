# ADR-213 : l'identité de l'appelant vient d'un en-tête qu'il ne peut pas écrire

**Statut** : ✅ IMPLEMENTED (2026-08-05)
**Contexte** : audit des logs de production API sur 7 jours (2026-07-29 → 2026-08-05)

## Contexte

Trois endroits répondaient indépendamment à la question « qui appelle ? » — le
rate limit global (`core/middleware`), l'enrichissement GeoIP (même middleware)
et le limiteur d'authentification (`domains/auth/dependencies`) — et tous trois
lisaient `scope["client"]`, c'est-à-dire l'adresse du pair telle qu'uvicorn l'a
résolue.

La production tourne avec `--proxy-headers --forwarded-allow-ips "*"`, ce qui
fait qu'uvicorn **réécrit** ce pair depuis `X-Forwarded-For`. Tous les sauts
étant déclarés dignes de confiance, il retient l'entrée **la plus à gauche** — et
Cloudflare **ajoute** l'adresse réelle au lieu de remplacer l'en-tête. L'entrée la
plus à gauche est donc celle que le visiteur a écrite.

Reproduit en conteneur isolé le 2026-08-05, en rejouant la topologie de
production :

```
curl -H "X-Forwarded-For: 127.0.0.1, 198.51.100.42" .../whoami
-> {"resolved_client": "127.0.0.1", "xff_header": "127.0.0.1, 198.51.100.42"}
```

Deux conséquences, toutes deux observées. Le plafond de 300 requêtes/minute
compartimente sur une valeur que l'appelant choisit : **la faire tourner suffit à
obtenir un budget neuf à chaque requête**. Et la piste d'audit est empoisonnée —
les 2600 avertissements de rate limit du scan du 2026-07-30 portent tous
`geo_country=local`, parce que le scanner s'était déclaré en loopback.

Le docstring du résolveur d'authentification affirmait précisément l'inverse
(« lire X-Forwarded-For ici rouvrirait le spoofing »), ce qui a fait tenir le
défaut pour impossible.

## Décision

**Un seul point de résolution, préférant l'en-tête que l'appelant ne peut pas
écrire** (`src/core/client_ip.py`).

1. `CF-Connecting-IP` est préféré : il porte exactement une adresse, et
   Cloudflare l'**écrase** si le visiteur en envoie une.
2. Lui faire confiance est fondé sur la même raison que le déploiement documente
   déjà pour `forwarded-allow-ips` : le port publié est lié à la loopback
   (`127.0.0.1:8000:8000`), donc les seuls pairs capables d'atteindre uvicorn
   sont cloudflared, le healthcheck interne et les services du réseau compose.
   Hors de cette topologie l'en-tête est simplement absent.
3. La valeur est **analysée avant d'être crue**. Un en-tête illisible est ignoré,
   jamais accepté : une clé de compartiment de rate limit et une entrée GeoIP ne
   doivent jamais être du texte arbitraire fourni par l'appelant.
4. Le résolveur **ne lève jamais**. Il s'exécute dans la chaîne de middleware :
   un scope malformé retombe sur l'adresse du pair, exactement comme un en-tête
   absent. Il ne peut pas être la raison d'un échec de requête.

## Conséquences

- Le plafond plafonne réellement, et les données géographiques redeviennent
  dignes de confiance.
- En développement et pour tout appel direct, `CF-Connecting-IP` est absent : le
  comportement retombe sur l'adresse du pair, soit exactement ce qui existait.
- La confiance accordée à l'en-tête **dépend de la topologie**. Exposer un jour
  l'API sans Cloudflare devant invaliderait cette hypothèse : c'est écrit dans le
  module, à côté du code qui en dépend.

## Preuves

`apps/api/tests/unit/core/test_client_ip_resolution.py` (18 tests) : la topologie
de production exacte, l'insensibilité à la casse, l'IPv6, le repli sans
Cloudflare, les valeurs malformées (texte, liste, hors plage) qui ne gagnent
jamais, et la robustesse aux scopes incomplets.

## Écartés

- **Lire `X-Forwarded-For` en prenant l'entrée la plus à droite** : dépend du
  nombre de sauts, silencieusement faux si la topologie change.
- **Retirer `--forwarded-allow-ips "*"`** : cloudflared joint via docker-proxy
  avec une adresse de bridge variable, il n'y a pas de pair fixe à déclarer.
- **Signer l'identité côté proxy** : coût sans bénéfice tant que le port reste
  lié à la loopback, où seul un pair de confiance peut écrire l'en-tête.
