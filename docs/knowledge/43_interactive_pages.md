# Interactive pages

## What can I ask LIA to make?

Ask for something you will use: "Make me a Halloween tic-tac-toe", "Create a quiz on European capitals", "Build a mortgage calculator", "Make a countdown to Christmas". LIA writes the page and it appears in the conversation, ready to use, with its `.html` file below the answer.

## And if I only want the code?

Ask for the code: "Give me the HTML code for a tic-tac-toe". LIA writes it in its answer, with a Copy button that gives the whole file. On a page that is already running, the **Code** button at the top of the page shows its source; the page keeps running behind it, so a game in progress is not lost.

## Is it safe to run a page LIA wrote?

The page runs in an isolated frame. It cannot reach your account, your data, your cookies or the rest of the conversation. It cannot open a window or leave the frame, and it can reach no site of its choosing. A link in a page opens nothing.

A page that fails says so under its frame, in plain text.

## Why do I have to press Start when I come back?

A page starts by itself only in the answer that made it. Everywhere else — after a reload, on another device, in your history — it waits for **Start**. A page with a fault could freeze the tab, and it must never stop you from opening your conversation again. If that ever happens during the first run, reload: the page will wait for you.

## Can I change a page, or keep it?

Ask for the change: "Make the board bigger", "Add a score". LIA rewrites the page it just made, and you get the new version.

Its file is a generated document like the others, under the same rules: download it from the card below the answer and open it in any browser, keep it past its deadline from **Settings**, or find it among your generated files. **Restart**, at the top of the page, runs it again from the beginning.

What a page saves stays in memory: it lasts until the page restarts, and nothing is kept once you leave.

## Why can't a page load an image, a font or a library from the web?

For the reason above: a page reaches nothing outside itself. LIA writes everything into the page, and refuses to show one that depends on an external script, because it would load and do nothing. For the same reason a page has no access to your calendar, your mail or anything else: to put your data in a page, ask for it in the same request and LIA writes it in.

## What does it cost, and who can turn it off?

Writing or changing a page uses the model your administrator set on the **Interactive Page** line of the LLM configuration, and its cost shows on the answer like any other. Showing a page or its code again costs nothing.

The administrator can turn pages off in two places:
• **Settings › Administration › Platform capabilities** › **Interactive pages** — immediate, no redeploy. Pages already in a conversation stay there.
• the server configuration (`INTERACTIVE_PAGE_ENABLED=false` in the instance's environment file).

There is no per-user switch.
