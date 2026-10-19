# LIA — Le fil de ta journée

Film de présentation complet de 80 secondes, en français, 1920 × 1080, 60 images par seconde. Composition indépendante `LIA-Feature-Film` dans `index.tsx`. La version de 16 secondes n'est pas utilisée dans ce film.

La narration traverse neuf usages : briefing, comparaison des sources, validation d'un envoi, Live, mémoire modifiable, réunion et compte rendu, routine, Skill App interactive, radio et sources. Les bornes précises de montage viennent des attaques mesurées dans `public/audio/feature-film/score.json`. L'ouverture et la conclusion durent environ quatre secondes chacune ; chaque usage dispose d'environ huit secondes.

Les noms et informations sont fictifs. Les gestes et délais sont scénarisés. Le HTML des cartes e-mail/document/brouillon et leurs feuilles de style viennent des renderers actuels. Les primitives mémoire/réunion/Live et le visage BIP réutilisent les sources actuelles. Les surfaces liées aux hooks de compte sont adaptées pour le film sans montage de fournisseur ni opération réelle. Les fichiers de scènes documentent leurs sources. Aucun comportement réseau, envoi, enregistrement, facturation ou résultat de performance n'est démontré réellement.

La musique originale a été générée pour cette demande par Lyria. L'édition complète utilise la prise source, sans appel payant supplémentaire ni bande-son de l'ancien film. Les paramètres d'édition et empreintes sont conservés dans `score.json`. La mesure technique des attaques ne constitue pas une écoute humaine.

Depuis `tools/lia-motion` :

```powershell
npm run check
node scripts/render-feature-film.mjs stills
node scripts/render-feature-film.mjs all
# Ou reprendre seulement un chapitre, puis assembler :
node scripts/render-feature-film.mjs render radio
node scripts/render-feature-film.mjs assemble
node scripts/package-feature-film.mjs
```

Le paquet DEV utilise `http://localhost:3000` par défaut. Pour une prévisualisation
sur une autre origine, fournis `MOTION_PREVIEW_ORIGIN` au script de packaging ;
aucune adresse du réseau de l'exploitant n'est inscrite dans les sources.
Les [attributions des assets](../../public/film/ASSETS.md) et les
[conditions de la musique](../../public/audio/atlas-proof/LICENSE.md) restent
avec les sources éditables.

Les exports restent dans `exports/lia-motion/feature-film-80s/`. Le packaging crée un répertoire DEV ignoré et un override Compose local ; il ne change pas l'environnement de production. Le manifeste d'origine lu au début de l'intégration est conservé à côté. Les deux vidéos d'illustration indépendantes sont conservées après la nouvelle présentation, avec leurs fichiers et crédits inchangés. Le bouton Présentation pointe également vers ce film.

Publication du 17 octobre 2026 : le film remplace l'ancienne présentation sur l'origine média DEV configurée par l'opérateur et sur `https://github.com/jgouviergmail/LIA-Assistant/releases/download/v3.0.0` pour la production. Le DEV utilise de nouveau son environnement Compose habituel. Les deux manifestes publiés ont la même empreinte ; les sauvegardes, inventaires avant/après et contrôles HTTP sont conservés dans le dossier d'export. Le code de l'application et les autres assets de release ne sont pas modifiés par cette publication média.

Correction de diffusion du même jour : les rendus web sont réencodés depuis le master avec des GOP fermés de deux secondes, CRF 21, VBV et audio AAC 128 kbit/s. Ils conservent tous les timestamps, 4 800 images et 80 secondes. La version 1080p passe de 15,72 à 10,61 Mo ; la 720p de 8,46 à 6,82 Mo. Le master reste disponible dans l'export. `landing-beats.ts` choisit désormais des attaques espacées d'au moins 900 ms pour le compagnon de la landing : 80 gestes, contre 312 transitoires auparavant, sans modifier le montage ni la musique. Les accents de cette chorégraphie ne sont pas une détection de mesures musicales. Les rapports d'encodage, comparaisons et preuves de publication sont dans `optimization-candidates/` et `optimized-publication/` sous le dossier d'export.
