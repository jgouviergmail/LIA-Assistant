# Assistive-Technology Manual Campaign (AC-002)

Versioned protocol for the periodic manual accessibility campaign that
complements the automated evidence (jsx-a11y ratchet at 0, the WCAG-AA
design-contrast unit guard, and the blocking axe scans in `apps/web/e2e/a11y/`
replayed weekly on Chromium/Firefox/WebKit by `.github/workflows/a11y-matrix.yml`).

Automated scans prove computed names, roles, states and contrast. They cannot
prove the *experience*: reading order, announcement quality, focus feel,
gesture support. That is what this campaign covers.

## Cadence and scope

- **Cadence**: once per release train that changes an interactive journey, and
  at minimum once per quarter.
- **Matrix**:

| Screen reader | Browser | OS |
|---|---|---|
| NVDA (latest) | Firefox | Windows 11 |
| VoiceOver | Safari | macOS |

- **Journeys** (mirror of the automated set, walked by ear):
  1. Login (form labels, error announcement, remember-me toggle).
  2. Dashboard (landmark navigation, briefing card headings order).
  3. Chat: send a message, follow the streamed answer, open/close an image
     lightbox, use a voice overlay session.
  4. Settings: change a preference, hear the confirmation toast. Navigate the
     page BY HEADINGS (h1 title -> h2 group -> h3 section): each section must
     announce its title once and only once, and the group labels must be
     reachable as headings (both were broken until v1.25.31). Scroll a few
     screens down and confirm the tab bar is still announced and reachable.
  5. Spaces: create a space, upload a document, follow upload progress.
  6. Admin (superuser): tab to Administration, edit a pricing row.

## Per-journey checklist

For each journey, record PASS/FAIL plus notes:

- [ ] Every interactive control announces a meaningful name, role and state.
- [ ] Focus order follows the visual/logical order; focus is always visible.
- [ ] Dialogs trap focus, announce their title, restore focus on close.
- [ ] Dynamic updates (toasts, streaming, progress) are announced without
      stealing focus.
- [ ] No keyboard trap; Escape/arrow conventions work where expected.
- [ ] At 200 % zoom and 320 CSS px the journey is still completable.

## Reporting

File one campaign report per run at `docs/a11y/reports/AT_<year>-<month>.md`
with: date, tester, versions (app/AT/browser/OS), the matrix above with
verdicts, and a defect list. Every FAIL becomes a tracked issue; a campaign
with open critical defects blocks the "accessibility evidence" claim in the
audit, exactly like a red gate.

## Honesty rule

This campaign is evidence, not certification. The public wording stays
"internal audit aligned with industry references" — never "WCAG certified"
(see docs/audit/README.md).
