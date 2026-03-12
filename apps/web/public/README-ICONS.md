# Favicon Guide for LIA

## Current Active Icon

**v3-lia-circle.svg** - Badge circulaire professionnel avec texte "LIA"
- Style classique et élégant
- Très professionnel
- Excellente lisibilité

## Available Variations

See [FAVICON-VARIATIONS.md](FAVICON-VARIATIONS.md) for all 10 design variations.

### Quick Access to Popular Styles:
- **v1-lia-letter.svg** - Lettre L stylisée
- **v3-lia-circle.svg** ⭐ (ACTIVE) - Badge circulaire
- **v7-lia-robot-cute.svg** - Robot mignon
- **v8-lia-hexagon.svg** - Hexagone tech
- **v9-lia-gradient-text.svg** - Texte gradient bold

## To Change the Icon

```bash
cp v7-lia-robot-cute.svg icon.svg  # Example: switch to robot design
```

Or update the metadata in `apps/web/src/app/[lng]/layout.tsx`

## Technical Notes

- Next.js automatically detects `icon.svg` in the public folder
- SVG format ensures crisp display at any size
- The icons use a blue-to-purple gradient matching the app theme (#2563eb to #7c3aed)
