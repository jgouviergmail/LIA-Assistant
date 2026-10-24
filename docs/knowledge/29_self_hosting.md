# Self-hosting LIA

## Can I run LIA on my own server?

Yes. LIA is free software (AGPL-3.0) built to be self-hosted, and a guided installer sits at the root of the repository: clone it, then run `./install.sh`.

**🖥️ What the machine needs:**
• Linux, on a 64-bit x86 or ARM processor — a Raspberry Pi 5 is the reference production machine
• Docker with a recent Compose v2, and a recent Python 3 to run the installer itself
• at least 10 GiB of free disk space

The installer checks each of them and says what is missing.

Your conversations, memory, documents and encrypted keys live in your own database; the AI models and the services you connect still receive what each task needs.

To look before you leap, `./install.sh --check-only` checks the machine without installing anything, and `./install.sh --dry-run` generates the configuration without starting it. The manual installation described in the getting-started guide remains fully supported.

## What does the guided installer do?

It asks its questions — in English or French — then does the whole job in one pass:
• generates a private configuration and the folders it needs
• builds the application, or fetches prebuilt images, and validates the settings before starting anything
• starts the stack: the database is migrated and the reference data — personalities, model catalogue and prices, default configuration — is loaded in a single transaction, all or nothing
• creates your administrator account and stores your provider keys encrypted
• restarts the server so every process uses them, runs a verifier, and prints a report containing no secret

**❓ What it asks:** how LIA will be reached, your administrator e-mail and name, the application's default language, a DeepSeek and an OpenAI key (the shipped configuration uses both; every model can be changed afterwards), an optional Google Gemini key (memory recall, searches by meaning and image analysis run on it; the final report says what stays degraded without it), and whether to enable a few optional features — the monitoring stack, self-diagnostics, the script sandbox, the Live voice mode, the personal radio and the speaking avatar. Each stays off unless you answer yes. It also offers two optional pairs of keys, each given whole or left empty: a Google Maps browser key with its Cloud map ID, for interactive place maps, and — when LIA is reached on a public domain — a Cloudflare Turnstile site key and secret key, for an anti-robot check on sign-up, sign-in and password reset.

For an unattended install, the same answers can come from a file: `./install.sh --non-interactive --answers answers.env`. To change these choices later — how LIA is reached, the optional features — run `./install.sh --reconfigure`: each question shows the answer in force, which Enter keeps, and your data, keys, administrator and secrets stay as they are. Before anything changes, the settings your new answers would rewrite are listed with their current and new values, and nothing is applied unless you confirm; if the new configuration does not come back — or you interrupt it — the previous one is put back.

## How will people reach my instance?

That is the one choice worth thinking about. The installer offers three:
• **lan** — home or office network, no domain name: the web interface is published on port 3000 of the machine, in plain HTTP
• **proxy** — you already run a reverse proxy (nginx, Traefik, Caddy) on the same machine: nothing new is published, and your proxy serves HTTPS
• **caddy** — you have domain names and want HTTPS handled for you: certificates are obtained and renewed automatically. Point the DNS records of your web and API domains at the machine before installing

In every mode, browsers talk only to the web interface; the API never gets a port of its own.

The mobile apps need an HTTPS address: choose **proxy** or **caddy** if you want them.

## How do I know the installation really worked?

A server that answers is not yet a working installation, so the installer does not stop there. Once the stack is up, a verifier checks, without reading any secret:
• the database is on exactly the expected migration
• the reference data was applied in full, under the exact expected version
• your administrator account exists, is active and has administrator rights
• the stored provider keys can actually be decrypted
• every core role of the configuration points to a provider you gave a key for

Only then does the installer print its report: the address to open, your administrator account, how the instance is reached and where the database backups are written. Sign in there; **Settings › Administration › LLM Configuration** then lets you change any model or add an optional provider key.

## Are my secrets safe during installation?

Yes, by construction.
• **Your password and provider keys** are typed at a hidden prompt, handed to the server on its standard input and stored encrypted in the database — never written to the configuration file, the installer's state or its log, and never on a command line
• **The server's own secrets** — the encryption key, the session key, the database and cache passwords — are generated at random into a configuration file only your account can read
• **The resume state** keeps only non-secret facts and fingerprints
• **An answers file** for an unattended install is read once, never copied, and refused if other users can read it

Your administrator password must meet the instance's password policy; the installer states the rule when it asks. An administrator account is never reset by email: if you forget its password, set a new one from the server with the `set_password` command the self-hosting guide gives (it also signs the account out of every device).

One thing never to do: change the generated encryption key by hand. Everything encrypted with it would become unreadable.

## What if a step fails halfway?

The installer stops at the first failing step, names it, writes the details to its own log with every secret removed, and gives you the command to continue:
`./install.sh --resume`

On a first installation, a failure only stops the containers it started: your configuration, data, backups and log stay in place. Resuming keeps your answers and the generated configuration, asks again only for the secrets it never stores — your administrator password and your provider keys, the optional one included — then runs the deployment steps again.

Resuming is deliberately cautious: if the files it generated changed in the meantime, it stops before touching anything rather than guessing. If you interrupt an installation yourself, the same command picks it up; an interrupted `--reconfigure` puts the previous configuration back instead — just run it again.

## Prebuilt images or a local build?

The installer follows a rule, never a guess:
• from a **clone of the repository**, it builds the images from your source — the default, and the path that always works
• from an **official release** whose manifest is marked as qualified, it uses prebuilt images, each pinned by its digest — never a moving tag such as "latest"
• from a release whose manifest is missing or not qualified, it builds locally from the release's own verified source

`./install.sh --local-build` forces a local build in any case.

**Limits of the prebuilt images:** browser push notifications are not available (notifications arrive in the app), and changing a public setting that is built into the web interface requires a local build.

## What does the installer not do?

It installs a working instance. A few things stay deliberate, separate acts:
• **Upgrades**: moving to a newer release is a written procedure (next question)
• **Wiping and starting over**: it never removes your data volumes; deleting data is always a command you type yourself
• **Taking over an existing installation**: if it finds a configuration it did not create, it refuses to touch it
• **Changing provider keys**: done later, signed in, in **Settings › Administration › LLM Configuration**
• **Google and Microsoft**: their sign-in and connectors are set up after installation, following the getting-started guide
• **Searches by meaning** (memory recall, knowledge spaces, the journal) run on a Google Gemini key: the installer asks for it but lets you skip it, and they stay unavailable until you add it in **Settings › Administration › LLM Configuration**

The installer itself runs on Linux only.

## How do I move my installation to a newer release?

There is no upgrade command, on purpose: each step should be one you can see, stop and reverse. The self-hosting guide writes the procedure out ("Upgrading to a newer release"); its shape:
• **back up first**: a fresh database dump, your configuration and the current image pins — migrations run by themselves when the new version starts, and there is no way back down
• download the new release and check its SHA-256 checksum
• stop the application; your data stays
• copy the release's files over your installation, keeping your own configuration, overlay and installer state
• pin the images to the new release, start, and let the migrations run
• check the version and the services' health, then send one message

Rolling back the code means restoring the previous pins, in seconds; undoing a migration means restoring the dump — which is why it comes first.

Never set `APPLY_SEEDS=true` for an upgrade: the reference data deletes before it inserts. And `./install.sh --resume` is not an upgrade path — it refuses once the release files change, by design. The procedure is written for an installation running a release's prebuilt images.

## Can I run LIA without any cloud AI provider?

Partly. Here is exactly where the line is.

**✅ On your own hardware:** every model role — routing, planning, answering, agents — can run on a model served by your own Ollama server, set role by role in **Settings › Administration › LLM Configuration**. Dictation is transcribed on the server itself.

**☁️ Still online:**
• the guided installer asks for a DeepSeek and an OpenAI key, because the shipped configuration uses them; you can move every role to Ollama afterwards
• searches by meaning — memory recall, knowledge spaces, the journal — use Google's embedding service
• spoken answers come from online voice services, the default one free and without a key
• web search, weather, maps and the connectors you link are online services by nature

A fully offline installation is therefore not possible; one whose conversations are written by models on your own hardware is.

## Can the mobile apps connect to my own server?

Yes: the official Android and iPhone apps work with any self-hosted LIA. What your server needs:
• **an HTTPS address**: the apps refuse plain HTTP, so an installation reached in **lan** mode is for browsers only — choose **proxy** or **caddy**
• **on iPhone**, web and API addresses under the same domain (for example lia.example.org and api.example.org): Apple's browser engine blocks the sign-in cookie across different domains
• **notifications**: on Android, through a Firebase project you own and configure on the server; on iPhone, Apple lets only the app's publisher push, so your server must be given a wake relay's address — it carries one fixed sentence with no content, and without it the iPhone app receives no push

## What does the script sandbox need, and what if Docker refuses it?

Script skills and the scripts LIA writes run in throwaway containers, which needs the opt-in skill-sandbox overlay — the installer's "script sandbox" question — because the server must be allowed to start containers. A generic installation runs without it.

If Docker refuses to start the sandbox, the operation is reported as unavailable rather than run outside the isolated runner. Check the Docker permissions and the deployment configuration.

## How do I make interactive Position maps available?

The operator configures an explicit **Google Maps browser key** and a valid **Cloud map ID**. Restrict the browser key to the intended sites and Maps APIs in Google Cloud. The server key is never exposed as a fallback. The card can appear without interactive configuration, with its place list; paid activation remains a user click with cost disclosure and quota checks. A development demonstration ID is not valid production configuration.
