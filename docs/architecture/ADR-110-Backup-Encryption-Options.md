# ADR-110: Backup Encryption — Options Analysis (Deferred)

**Status**: 🧊 DEFERRED (options analyzed 2026-07-08; implementation deliberately postponed — no urgency)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-109](ADR-109-PostgreSQL-Backup-Strategy.md) (backup strategy — lists off-site copy as the phase-2 gap), runbook [DATABASE_BACKUP_RESTORE.md](../runbooks/DATABASE_BACKUP_RESTORE.md)

## Context

ADR-109 shipped automated pg_dump backups with a proven restore, and recorded
as its main accepted gap that dumps share the production NVMe with the
database (no disk-failure protection, plaintext at rest in a chmod-700
directory). The follow-up question — *can we encrypt the backups on-site,
before the off-site phase 2?* — was analyzed the same day.

**The finding that shapes the answer**: the live database volume
(`postgres_data`) is itself plaintext on the same NVMe — Fernet covers PII
columns, not the datafiles. Encrypting *only the dumps on the same disk*
therefore adds almost nothing against disk theft or disposal: whoever has the
disk has the live database next to the dumps. The right question is "against
which threat?", and each threat has a different correct mechanism.

## Options analyzed

**A. rclone `crypt` to a local target (recommended path when implemented).**
A small sync job (systemd timer on the Pi, or a micro-container) reads
`backups/postgres` and writes encrypted copies (NaCl secretbox, filenames
encrypted too) to a second target — ideally a USB SSD plugged into the Pi,
which also buys real protection against NVMe death, the #1 ADR-109 limit.
Pros: does not touch the sidecar or its rotation; it *is* the phase-2
mechanism (going off-site later = swapping the rclone backend, config/runbook
unchanged); `.env`-parameterizable; plaintext local retention can then be
shortened. Cons: plaintext originals remain on the NVMe until retention is
tightened. Estimated at ~half a day including a real restore-from-encrypted
drill and an ADR.

**B. Asymmetric encryption at dump time (age recipient, private key off-host)
— rejected in this form.** Strongest property (a full Pi compromise cannot
read historical dumps), but the image's post-backup hooks fight its rotation
engine: daily/weekly/monthly are hardlinks to the same inode and the purge
matches on the `.sql.gz` suffix — encrypt-then-delete breaks both. Doing it
cleanly means the custom backup script already rejected in ADR-109. The
property itself (key material off-host) arrives with off-site rclone crypt in
the final phase 2.

**C. Device-level encryption (LUKS on the data disk) — separate decision.**
The only real answer to *physical theft or disposal*, because it covers the
live database and the dumps together. On a headless Pi it is a serious
operational project: unlock at boot (dropbear-initramfs SSH or USB keyfile),
migration of existing Docker volumes, and unattended-reboot recovery on a
host with a history of tunnel instability. To be treated as its own ADR if
physical theft enters the threat model — not as a backup tweak.

## Decision

**Defer.** No encryption mechanism is implemented now (explicit product
decision, 2026-07-08: no urgency). When the work is picked up, the path is
**option A**, which converts into the full off-site phase 2 by a backend
swap. Option B stays rejected in hook form; option C is a distinct decision
gated on the threat model.

## Consequences

- Until then: dumps remain plaintext, `chmod 700`, on the same NVMe as the
  database — exactly the ADR-109 posture, now with the encryption options and
  their threat models on record.
- Triggers to revisit: a USB medium available on the Pi (A, local), an
  off-site target chosen (A, full phase 2), or physical theft entering the
  threat model (C study).
