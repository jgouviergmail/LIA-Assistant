# Native Android & iOS Apps

## Is there a mobile app for Android or iPhone?
Yes — one official app per store, and it works with **any** self-hosted LIA server. At first launch you type your server's address (HTTPS required); the app then loads your server's own interface, so every web improvement reaches it instantly with no store update. The web app and the app installed from the browser keep working — the native apps are an addition, never a replacement.

## How do I sign in from the mobile app?

With the same account as on the web. Signing in with your e-mail and password happens right in the app.

**🔐 With Google:** Google refuses sign-in inside an app's built-in browser, so the app opens your phone's own browser, then brings you back automatically once you are signed in. The return link carries a single-use code that only your app can redeem: intercepted, it is worthless.

**🔢 Your second step still applies:** if you set up an authenticator app in **Settings › Preferences › Security › Strong authentication**, its code is asked here too — signing in with Google never skips it, in the app or on the web.

## How do notifications work?
Natively, on both platforms — and deliberately differently. On **Android**, the app initialises Firebase at runtime with options your own server publishes: your notifications never leave your own Firebase project. On **iOS**, Apple only lets the app's publisher push, so a minimal **wake relay** wakes the phone with one fixed neutral sentence; the app then fetches the real content from your server. The relay stores nothing — the handle *is* the sealed device token — and never learns who was woken or why.

## What happens if my server is unreachable, or I mistype its address?
The app ships its own offline screen (in all six languages) with a retry button and, crucially, a "use a different server" way out. A mistyped address at first launch never means reinstalling the app.

## Do connected services (Gmail, calendars, MCP) work from the app?
Yes. Every authorization that leaves for the browser — connectors, MCP servers, sign-in — returns to the right screen of the app when it completes, instead of stranding you in a browser tab.

## How does browser installation differ from the native app?

In a compatible browser, use the offered installation option or add the site to your home screen: LIA then opens like an app, without the browser's bars. The native apps add features of their own on top, such as notifications delivered by the phone's own system. Both show your own server's interface, and both need the network; sharing and notifications from an installed browser app depend on your browser, system and permissions.

## Does LIA work without a connection once installed?

No — LIA runs on your server, and what you install is a window onto it. Conversations, answers, actions and synchronisation all need the network.

**📴 When the connection drops:**
• installed from the browser, LIA shows its own offline page, in your language, with a **Try again** button instead of a browser error
• the mobile app shows its offline screen, with a retry and a way to choose a different server — handy if the address was mistyped

**🔒 Nothing personal is kept for offline reading:** at most the application's own files are stored on the device; your conversations and data stay on the server.

When you reconnect, the open conversation catches up with what happened in the meantime.
