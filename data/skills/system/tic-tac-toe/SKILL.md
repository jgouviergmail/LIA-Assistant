---
name: tic-tac-toe
description: >
  Interactive tic-tac-toe (morpion) game for two players. Displays a playable
  3x3 grid where players take turns placing X and O marks. Includes win
  detection, draw detection, and replay functionality.
category: loisirs
priority: 45
outputs: [text, frame]
---

# Jeu du Morpion (Tic-Tac-Toe)

## Instructions

1. Appeler `run_skill_script` avec :
   - script : `render_game.py`
   - parameters : `{}` (aucun paramètre utilisateur requis)
2. Présenter la frame retournée avec une courte phrase d'introduction.
3. Les joueurs peuvent jouer directement dans l'interface : cliquer sur une case pour placer leur symbole (X ou O).
4. Le jeu détecte automatiquement les gagnants et les matchs nuls, et propose de rejouer.

## Format de sortie

### 🎮 Interface de jeu
- Grille 3x3 interactive
- Indication du tour actuel (X ou O)
- Bouton "Rejouer" pour recommencer une partie
- Message de victoire ou de match nul quand la partie se termine

## Ressources disponibles

- scripts/render_game.py — Génère l'interface interactive du morpion