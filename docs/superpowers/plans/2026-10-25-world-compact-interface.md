# Compact world interface and conversations

## Accepted direction

The scene stays the main surface. Use the existing LIA typography, theme tokens,
buttons, menus, voice controls and account lifetimes. Keep 44px hit targets,
translated accessible names and keyboard paths. Do not add a rendering engine,
provider, audio session owner or separate notification transport.

## Ordered implementation

1. Reproduce the phone bypass and mixed conversation feed with behavioral tests.
   Add a phone landing panel with deliberate Call and SMS actions, plus distinct
   session notification badges. Reuse native SMS workspaces and call drafts.
2. Make the HUD compact across portrait, short landscape, tablet and desktop.
   Group place discovery and peer actions behind the functions menu. Keep LIA,
   conversations, home colours, settings and leave directly reachable.
3. Reuse the native voice selector with an explicit embedded-workspace handoff.
   Spoken comments, delegated Live and direct Live retain their native availability,
   exclusivity, quota and microphone behavior. Add the existing theme control.
4. Replace the aggregate private message feed with a conversation directory:
   public participant identity, safe translated preview, per-person unread counts,
   retained per-recipient drafts, offline history and deterministic selection.
   Opening the directory must never mark every conversation read. Pending or
   uncertain sends cannot be silently retargeted. Use a sidebar on wide docks
   and a list/detail flow on phones; avoid rendering untranslated originals in
   directory previews.
5. Keep only visible home palette controls. Stop reading memories and interests
   for decoration. Read legacy preference documents safely, retain revision/CAS
   and explicit corruption reset, and normalize new writes to colours only.
6. Review code and actual browser screenshots, including dark mode, enlarged fonts,
   virtual keyboard bounds, touch, multiple conversations and error paths. Run
   relevant unit/integration coverage and static ratchets without weakening them.
   Publish reviewed sources to the existing preview with rollback/source parity
   evidence; remove only the disposable resources created for this iteration.

## Acceptance limits

No paid call, SMS, translation or Live supplier session is triggered by automation.
Use hermetic API fixtures for those boundaries and real disposable storage for
persistence semantics. Browser emulation does not certify physical phone/Pi
performance. All work is inline in the existing external worktree.


## Execution record

Implemented inline. The [qualification ledger](../qualification/2026-10-25-world-house-refinement.md)
records the delivered behavior, red/green findings, real-browser and storage
verification, measured ratchets, publication parity and resource handover.
Physical hardware and audible supplier sessions remain outside this software
iteration's automated acceptance boundary.
