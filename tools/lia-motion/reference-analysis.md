# Référence de réalisation : GoLunch

Source : https://www.youtube.com/watch?v=0spNx1Uku38

Le fichier vidéo fourni ensuite par l’utilisateur a aussi été inspecté :
`11-10-2026 22-52-21 (modifié).mp4`, environ 76 secondes. Il contient une capture
du lecteur et permet d’examiner les déplacements et découpages localement.
La piste de ce fichier est silencieuse ; elle ne sert pas de référence sonore.

La reprise a été examinée dans le lecteur YouTube pendant sa lecture, avec
des captures successives et des retours sur les transitions. Les temps
ci-dessous sont des repères visuels, pas un relevé image par image ni une
analyse auditive de sa musique. Aucune image de GoLunch n’entre dans LIA.

| Repère | Observation | Application à LIA |
| --- | --- | --- |
| Début | L’horloge change d’échelle, les éléments arrivent autour d’elle, puis la marque occupe le cadre. | Partir d’une demande dans LIA ; faire évoluer le cadrage vers sa réponse. |
| Vers 13 s | Les chiffres et les cartes entrent en plusieurs temps. | Révéler progressivement les éléments réels du produit plutôt qu’afficher un tableau complet. |
| Vers 24 s | Les cartes de plats se détachent du navigateur ; profondeur et échelle guident le regard. | Extraire des pixels de vraies cartes capturées, avec leur provenance, sans reconstruire une interface. |
| Vers 27 s | Le téléphone prend la place du desktop ; un détail reste visible autour de lui. | Prévoir de vraies captures mobile quand elles sont disponibles, sans recadrer un desktop en faux téléphone. |
| Vers 31 s | Une action dans les filtres conduit au résultat. | Enregistrer les clics, sélections et résultats dans le frontend natif. |
| Vers 45–54 s | Les villes passent d’un éventail d’images à leur page, puis la carte remplit le plan. | Varier les échelles et relier les plans par un élément du produit. |
| Vers 58–66 s | La carte se rapproche d’une rue, puis un restaurant devient le point d’attention. | Zoomer vers le contrôle ou résultat utile, avec un temps suffisant pour le lire. |
| Vers 70 s | La couleur change avec la famille de contenu. | Utiliser des transitions distinctes, cohérentes avec les écrans natifs. |
| Conclusion | La marque et l’adresse arrivent sur une composition qui rappelle les plans précédents. | Conclure avec le compagnon natif, LIA, son adresse et le crédit musical. |

La reprise abandonne la grille répétée du premier montage. Les textes courts
ponctuent les enregistrements ; les coupures se calent sur les pulsations
mesurées du nouveau morceau. Un label de fonctionnalité, une capture de
réglages et une interaction exercée sont des preuves de portée différente :
la fiche de production doit les distinguer.

## Reprise V3 après rejet des deux premiers essais

Le plan de produit conserve un texte fort à gauche, la fenêtre à droite et un
fond clair éclairé très doucement. Les éléments du même écran se détachent puis
reviennent ; les actions et les résultats restent liés par ces objets. Le
montage n’utilise pas une suite de pages agrandies comme substitut à l’animation.

L’utilisateur autorise explicitement la reconstruction des écrans, sous réserve
de fidélité à l’UX et à l’UI. Les classes natives, les couleurs, les textes de
boutons et les états du chat/HITL sont les références. Le scénario garde le
DL de trois lignes du résultat réel ; il n’invente pas trois widgets de sources.

BIP est la mascotte demandée. Les originaux de son artwork, vérifiés contre le
manifest natif, permettent une mise en scène de grande taille sans agrandir
uniquement le WebP optimisé pour le petit avatar. Ses émotions suivent le
parcours et réutilisent les poses natives.
