"""
Wake relay for the published iOS shell.

One app is published per store, so one Apple Developer team owns its bundle
identifier — and only that team's APNs key may notify it. A self-hosted LIA
server therefore cannot reach an iPhone running the published app, however
correctly it is configured.

This subsystem is the deployment that CAN, lending that reachability to the
ones that cannot. It is disabled by default: exactly one deployment — the one
that publishes the app — turns it on.

What it deliberately does not do is carry the notification. It emits a fixed,
localised sentence; the shell then fetches the real content from its OWN server
over the user's own session. The relay never learns who the user is, which
server woke them, or what about.
"""
