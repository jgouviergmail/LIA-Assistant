"""Interactive tic-tac-toe game — client-side gameplay, i18n, theme-aware."""

import json
import sys


_LABELS = {
    "fr": {
        "title": "Morpion",
        "turn": "Tour de : {p}",
        "x_wins": "🎉 X a gagné !",
        "o_wins": "🎉 O a gagné !",
        "draw": "🤝 Match nul !",
        "restart": "Rejouer",
        "x": "X",
        "o": "O",
    },
    "en": {
        "title": "Tic-Tac-Toe",
        "turn": "Turn: {p}",
        "x_wins": "🎉 X wins!",
        "o_wins": "🎉 O wins!",
        "draw": "🤝 Draw!",
        "restart": "Play again",
        "x": "X",
        "o": "O",
    },
    "es": {
        "title": "Tres en raya",
        "turn": "Turno: {p}",
        "x_wins": "🎉 ¡X gana!",
        "o_wins": "🎉 ¡O gana!",
        "draw": "🤝 ¡Empate!",
        "restart": "Jugar de nuevo",
        "x": "X",
        "o": "O",
    },
    "de": {
        "title": "Tic-Tac-Toe",
        "turn": "Zug: {p}",
        "x_wins": "🎉 X gewinnt!",
        "o_wins": "🎉 O gewinnt!",
        "draw": "🤝 Unentschieden!",
        "restart": "Neu spielen",
        "x": "X",
        "o": "O",
    },
    "it": {
        "title": "Tris",
        "turn": "Tocca a: {p}",
        "x_wins": "🎉 X vince!",
        "o_wins": "🎉 O vince!",
        "draw": "🤝 Pareggio!",
        "restart": "Rigioca",
        "x": "X",
        "o": "O",
    },
    "zh": {
        "title": "井字棋",
        "turn": "轮到：{p}",
        "x_wins": "🎉 X 赢了！",
        "o_wins": "🎉 O 赢了！",
        "draw": "🤝 平局！",
        "restart": "再玩一次",
        "x": "X",
        "o": "O",
    },
}


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    params = payload.get("parameters", {})
    lang = (params.get("_lang") or "fr").lower().split("-")[0]
    labels = _LABELS.get(lang, _LABELS["fr"])

    cfg = json.dumps(labels, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: #1f2937;
      padding: 24px 16px;
      text-align: center;
      background: transparent;
    }}
    h1 {{
      margin: 0 0 16px;
      font-size: 1.5rem;
      color: #374151;
    }}
    .status {{
      font-size: 1.1rem;
      font-weight: 600;
      margin-bottom: 16px;
      color: #4b5563;
    }}
    .board {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      max-width: 240px;
      margin: 0 auto 20px;
    }}
    .cell {{
      width: 72px;
      height: 72px;
      background: #f3f4f6;
      border: 2px solid #d1d5db;
      border-radius: 8px;
      font-size: 2rem;
      font-weight: 800;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.15s ease;
      user-select: none;
    }}
    .cell:hover {{
      background: #e5e7eb;
      border-color: #9ca3af;
    }}
    .cell.x {{
      color: #dc2626;
    }}
    .cell.o {{
      color: #2563eb;
    }}
    .cell.winner {{
      background: #fef3c7;
      border-color: #f59e0b;
    }}
    button {{
      border: none;
      border-radius: 999px;
      padding: 10px 22px;
      font-size: 0.95rem;
      font-weight: 600;
      background: linear-gradient(135deg, #6366f1, #4f46e5);
      color: white;
      cursor: pointer;
      font-family: inherit;
      box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
    }}
    button:hover {{
      filter: brightness(1.06);
    }}
    html[data-theme="dark"] body {{
      color: #e5e7eb;
    }}
    html[data-theme="dark"] h1 {{
      color: #f3f4f6;
    }}
    html[data-theme="dark"] .status {{
      color: #d1d5db;
    }}
    html[data-theme="dark"] .cell {{
      background: #374151;
      border-color: #4b5563;
    }}
    html[data-theme="dark"] .cell:hover {{
      background: #4b5563;
      border-color: #6b7280;
    }}
    html[data-theme="dark"] .cell.winner {{
      background: #78350f;
      border-color: #f59e0b;
    }}
  </style>
</head>
<body>
  <h1 id="title">{labels["title"]}</h1>
  <div class="status" id="status">{labels["turn"].format(p=labels["x"])}</div>
  <div class="board" id="board"></div>
  <button id="restart">{labels["restart"]}</button>
  <script>
    (function() {{
      var LABELS = {cfg};
      var board = Array(9).fill(null);
      var currentPlayer = 'x';
      var gameActive = true;

      var $board = document.getElementById('board');
      var $status = document.getElementById('status');
      var $restart = document.getElementById('restart');

      var winPatterns = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8], // rows
        [0, 3, 6], [1, 4, 7], [2, 5, 8], // columns
        [0, 4, 8], [2, 4, 6]             // diagonals
      ];

      function checkWin() {{
        for (var i = 0; i < winPatterns.length; i++) {{
          var p = winPatterns[i];
          var a = board[p[0]], b = board[p[1]], c = board[p[2]];
          if (a && a === b && a === c) {{
            return {{ winner: a, pattern: p }};
          }}
        }}
        if (board.every(function(c) {{ return c !== null; }})) {{
          return {{ draw: true }};
        }}
        return null;
      }}

      function render() {{
        $board.innerHTML = '';
        for (var i = 0; i < 9; i++) {{
          var $cell = document.createElement('div');
          $cell.className = 'cell';
          if (board[i]) {{
            $cell.classList.add(board[i]);
            $cell.textContent = board[i].toUpperCase();
          }}
          $cell.dataset.index = i;
          $cell.addEventListener('click', onCellClick);
          $board.appendChild($cell);
        }}
      }}

      function highlightWin(pattern) {{
        var cells = $board.querySelectorAll('.cell');
        for (var i = 0; i < pattern.length; i++) {{
          cells[pattern[i]].classList.add('winner');
        }}
      }}

      function onCellClick(e) {{
        if (!gameActive) return;
        var idx = parseInt(e.target.dataset.index, 10);
        if (board[idx]) return;

        board[idx] = currentPlayer;
        render();

        var result = checkWin();
        if (result) {{
          gameActive = false;
          if (result.winner) {{
            $status.textContent = result.winner === 'x' ? LABELS.x_wins : LABELS.o_wins;
            highlightWin(result.pattern);
          }} else if (result.draw) {{
            $status.textContent = LABELS.draw;
          }}
        }} else {{
          currentPlayer = currentPlayer === 'x' ? 'o' : 'x';
          $status.textContent = LABELS.turn.replace('{{p}}', LABELS[currentPlayer]);
        }}
      }}

      function restart() {{
        board = Array(9).fill(null);
        currentPlayer = 'x';
        gameActive = true;
        $status.textContent = LABELS.turn.replace('{{p}}', LABELS.x);
        render();
      }}

      $restart.addEventListener('click', restart);
      render();
    }})();
  </script>
</body>
</html>"""

    print(json.dumps({
        "text": labels["turn"].format(p=labels["x"]),
        "frame": {"html": html, "title": labels["title"], "aspect_ratio": 1.1},
    }))


if __name__ == "__main__":
    main()