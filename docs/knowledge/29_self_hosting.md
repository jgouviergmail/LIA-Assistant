# Self-hosting LIA

## Can I run LIA on my own machine?
Yes. LIA is free software (AGPL-3.0) and is designed to be self-hosted — that
is the point of the project, not an afterthought. A guided installer lives at
the root of the repository: `./install.sh`.

Nothing about running it requires a cloud account, a subscription, or sending
your data to a third party. A Raspberry Pi is enough for a household.

## What does the installer actually do?
It asks a short questionnaire in your language, then does the work:

1. **Questions** — how you want to reach the instance (local network, your own
   reverse proxy, or managed HTTPS), and which provider keys you hold.
2. **Preflight** — it checks the host before touching anything: Docker, disk,
   ports, and whether the source it was launched from is complete.
3. **Build** — it builds the API and Web images **from the source you cloned**.
   This is the default on purpose: an artifact nobody qualified has no place in
   an installation.
4. **Reference data** — personalities, model pricing, the LLM catalogue and the
   default configuration are applied in **one transaction**. A half-seeded
   installation does not exist: either everything lands, or nothing does.
5. **Bootstrap** — your administrator account and your provider keys are
   created from a single document read on standard input, in one transaction.
6. **Verification** — see the next question.
7. **Report** — a non-secret summary, naming any capability that will run
   degraded because its key was not provided.

## How do I know the installation actually worked?
Because `/ready` is checked, and then deliberately not trusted on its own.

A health endpoint proves that the server started. It does not prove that the
installation is correct. So a separate verifier runs afterwards and checks, with
no access to your secrets:

- there is exactly **one** database migration head;
- the reference-data marker is present and exact;
- the reference data satisfies its own postconditions (the expected rows exist);
- an **active** administrator account exists;
- the stored provider keys can actually be decrypted;
- provider coverage holds **on the configuration that is effective after the
  reference data was applied** — the one your first message will really use,
  not the code defaults that the reference data just overrode.

If any of these fail, the installer says which one, and stops.

## Are my secrets safe during installation?
Secrets never travel through the command line. They are read on standard
input and go straight into an encrypted column, in the same transaction that
creates the administrator. There is no default password: the password you
choose goes through the same strength validation as any account on the
running instance.

The resume state — what lets an interrupted install continue — stores only
non-secret facts plus SHA-256 fingerprints. If a fingerprint no longer
matches, the installer stops **before** changing anything rather than guessing.

## What if a step fails halfway through?
Run `./install.sh --resume`. It picks up exactly where it stopped and will not
re-ask for what is already done — except the three ephemeral secrets (your
administrator password and provider keys), which are never stored anywhere and
must be typed again if the bootstrap step itself did not complete.

To change how the instance is reached later — switching from local network to
a domain name, for example — use `./install.sh --reconfigure`. The identity of
the installation stays fixed; only the routing changes.

## Are prebuilt images available instead of building locally?
Only under a strict condition, and this is deliberate. Prebuilt mode accepts
**only** image references pinned by digest (`repository@sha256:...`) that come
from a release manifest explicitly marked as qualified. A mutable tag such as
`:latest` is never an input the installer will accept.

Until a release has passed its clean-machine qualification, local build stays
the default. That is why the local path is the one described first: it always
works, and it never depends on trusting a label.

## What is NOT covered by the installer?
Version upgrades, database downgrades, and destructive reinstalls are outside
its scope for now. It installs a working instance; it does not migrate one.

## How do I move my installation to a newer release?
There is no upgrade command, but there is a written procedure — seven steps in
`docs/guides/GUIDE_SELF_HOSTING.md`, section "Upgrading to a newer release".

The shape of it: back up the database first (migrations run automatically when
the new container starts, and there is no downgrade path), download and verify
the new bundle's SHA-256, stop the application, overwrite the files the release
owns while keeping your own `.env` and overlay, regenerate the image pins from
the new manifest, then start again and let the migrations run. Rolling back the
code means restoring the previous pins, which takes seconds; rolling back a
migration means restoring the dump, which is why the dump comes first.

Never set `APPLY_SEEDS=true` on an upgrade: the seed bundle deletes before it
inserts and exists for a fresh install only. And `./install.sh --resume` is not
the upgrade path — it is fail-closed and will refuse once the files change,
which is the guard working as intended.

Script skills, which execute code, require an extra opt-in overlay because they
need access to the Docker socket. A generic installation runs without it.

## My deployment ended on an error — did it fail?
Read the closing message rather than the exit code, and since v1.38.0 the message tells you which of six things happened. Only one of them is a failed deployment: the one where the server itself returned a non-zero code, and the driver then points you at the remote log. "Already in progress" means your deployment did not happen at all and nothing changed remotely; "interrupted" means it stopped mid-flight without writing a verdict; "watching budget exhausted" means it is still running and you stopped watching — re-run with a larger `-DeployBudgetSeconds`, or simply wait; "contact lost" means the connection dropped while launching, and the server may have started the work anyway. On all four, do not re-run: the driver would wipe the staging directory under a build still in flight. It prints the three commands that settle the question instead.

Before v1.38.0 the deployment ran inside the SSH session, so closing your laptop or losing Wi-Fi killed it within seconds. It now runs on the server, independently of your terminal.

## Does the deployment leave my production secrets on my machine?
No, not since v1.38.0. Building the bundle decrypts your production environment file in clear on your own machine. That copy — along with the encryption keys and the encrypted archive — is now removed on every exit path, including every error path, not only when the deployment succeeds. The bundle itself is left in place after a failure so you can inspect it. A simulation run (`-DryRun`) never touches anything.
