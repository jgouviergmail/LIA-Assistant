# Native Android & iOS Apps

## Is there a mobile app for Android or iPhone?
Yes — one official app per store, and it works with **any** self-hosted LIA server. At first launch you type your server's address (HTTPS required); the app then loads your server's own interface, so every web improvement reaches it instantly with no store update. The web app and the PWA keep working exactly as before — the apps are an addition, never a replacement.

## How does sign-in work in the app?
Google refuses OAuth inside embedded webviews, so the app opens your phone's real browser and returns automatically through a `lia://` link. That link carries a single-use code bound to a secret only the app holds, so an intercepted link is worthless. Wiring this path also closed a real flaw: signing in with Google used to skip the two-factor code entirely; the code step is now enforced everywhere.

## How do notifications work?
Natively, on both platforms — and deliberately differently. On **Android**, the app initialises Firebase at runtime with options your own server publishes: your notifications never leave your own Firebase project. On **iOS**, Apple only lets the app's publisher push, so a minimal **wake relay** wakes the phone with one fixed neutral sentence; the app then fetches the real content from your server. The relay stores nothing — the handle *is* the sealed device token — and never learns who was woken or why.

## What happens if my server is unreachable, or I mistype its address?
The app ships its own offline screen (in all six languages) with a retry button and, crucially, a "use a different server" way out. A mistyped address at first launch never means reinstalling the app.

## Do connected services (Gmail, calendars, MCP) work from the app?
Yes. Every authorization that leaves for the browser — connectors, MCP servers, sign-in — now returns to the right screen of the app when it completes, instead of stranding you in a browser tab.
