# Drive the public demonstrator on the production host, from a workstation.
#
# The demonstrator is a SEPARATE Compose project on the same machine as the
# production stack. `deploy:prod` ships its files but never starts it: putting
# an instance in front of the Internet is a decision, not a side effect of a
# deployment. This script is that decision, typed on purpose.
#
#   task demo:prod:status     what is running, and what the instance reports
#   task demo:prod:up         start it WITH the Cloudflare tunnel
#   task demo:prod:down       stop it (the tmpfs database dies with it)
#   task demo:prod:verify     surface + spend ceiling + host isolation
#   task demo:prod:harden     install the container->host firewall rules
#   task demo:prod:push-env   send the local secrets file, mode 600
#
# The host, port and user come from scripts/deploy/deploy.local.ps1 - the same
# gitignored file `deploy-prod.ps1` reads, so the address lives in exactly one
# place and never in the repository.
#
# Created: 2026-08-07 (live-demonstrator programme, production handover)

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("up", "down", "status", "verify", "harden", "provision", "push-env", "logs")]
    [string]$Action,

    [string]$SshHost = "your-server-ip",
    [int]$SshPort = 22,
    [string]$SshUser = "deploy",
    [string]$RemoteDir = "lia"
)

$ErrorActionPreference = "Stop"

$localConfig = Join-Path $PSScriptRoot "deploy.local.ps1"
if (Test-Path $localConfig) { . $localConfig }

# ADR-250: meme regle que deploy-prod.ps1, meme bibliotheque. `up -d --build
# --wait` construit les images SUR le Pi -- c'est une operation longue, donc
# exactement celle qu'une coupure de transport interrompt, et `exit $code` sur
# un 255 affirmait "remote command exited 255" alors que la commande distante
# n'avait peut-etre jamais rendu de code du tout.
$remoteExitLib = Join-Path $PSScriptRoot "lib/RemoteExit.ps1"
if (-not (Test-Path $remoteExitLib)) {
    Write-Host "ERR: bibliotheque introuvable: $remoteExitLib" -ForegroundColor Red
    exit 1
}
. $remoteExitLib

if ($SshHost -eq "your-server-ip") {
    Write-Host "ERR: no host configured." -ForegroundColor Red
    Write-Host "     Create scripts/deploy/deploy.local.ps1 with `$SshHost / `$SshPort / `$SshUser," -ForegroundColor Gray
    Write-Host "     exactly as deploy-prod.ps1 expects it." -ForegroundColor Gray
    exit 1
}

$SshOptions = "-o ServerAliveInterval=30 -o ServerAliveCountMax=5 -o ConnectTimeout=30"
$Target = "$SshUser@$SshHost"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# TWO settings name the same file, and they are not interchangeable.
#
#   --env-file             what Compose INTERPOLATES ${VAR} from. Without it,
#                          Compose reads the `.env` of the current directory,
#                          never a service's env_file (measured 2026-08-06).
#   DEMO_INSTANCE_ENV_FILE what the API service LOADS into the container. The
#                          envelope declares `env_file: ${DEMO_INSTANCE_ENV_FILE
#                          :-.env.demo-instance}`, so leaving it unset makes
#                          the service ask for the DEVELOPMENT file - which
#                          does not exist on the production host:
#                            env file <deploy dir>/.env.demo-instance not found
#                          (measured 2026-08-07, after the preflight had
#                          passed on the file that WAS there).
#
# Setting only the first is the trap; both name the same file here.
# Reference-seed digest, computed HERE from the repository the deployment
# shipped. The envelope asks for the bundle (`APPLY_SEEDS=true`) and refuses
# to apply it without a digest - so leaving it unset means a production
# instance whose pricing catalogue is the partial one, and a spend ceiling
# that reads zero. `task demo:up*` computes it for the local shape; nothing
# did for this one.
$seedDigest = ""
foreach ($py in @((Join-Path $ProjectRoot "apps\api\.venv\Scripts\python.exe"), "python")) {
    if ($py -ne "python" -and -not (Test-Path $py)) { continue }
    $seedDigest = & $py -c "import sys; sys.path.insert(0, r'$ProjectRoot'); from pathlib import Path; from scripts.install.seed_bundle import compute_seed_bundle_sha256; print(compute_seed_bundle_sha256(Path(r'$ProjectRoot')))" 2>$null
    if ($LASTEXITCODE -eq 0 -and $seedDigest) { break }
}
if (-not $seedDigest) {
    Write-Host "  ERR: digest du bundle de seeds incalculable - la pile demarrerait avec un catalogue partiel." -ForegroundColor Red
    exit 1
}
$seedDigest = $seedDigest.Trim()

$Compose = "DEMO_INSTANCE_ENV_FILE=.env.demo-instance.prod SEED_BUNDLE_SHA256=$seedDigest docker compose --env-file .env.demo-instance.prod -f docker-compose.demo-instance.yml"

function Invoke-Remote {
    param([string]$Command, [string]$Label, [switch]$Diagnose)

    Write-Host "`n[$Label]" -ForegroundColor Cyan
    Write-Host "  $Target : $Command" -ForegroundColor DarkGray

    # The command travels BASE64-ENCODED, and that is not a flourish.
    #
    # Interpolating it into a quoted ssh argument makes it cross three shells
    # that each own the quote character: PowerShell, ssh's argument
    # reassembly, and the remote shell. Any `"` inside becomes ambiguous, and
    # the failure is silent until it is not - measured 2026-08-07 on the
    # permission check, which reached the host as an unterminated string:
    #   bash: -c: ligne 1: fin de fichier (EOF) prematuree
    # Two other commands (the readiness probe, the surface check) carried the
    # same hazard and had simply not been run yet.
    #
    # Encoded, the ssh argument holds only [A-Za-z0-9+/=] and a fixed
    # pipeline: no shell on the path can misread it, and a command may then be
    # written naturally, with the quotes it actually needs.
    $payload = "cd ~/$RemoteDir && $Command"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))
    & ssh $SshOptions.Split(' ') -p $SshPort $Target "echo $encoded | base64 -d | sh"
    if ($LASTEXITCODE -ne 0) {
        $code = $LASTEXITCODE

        if ((Get-RemoteExitVerdict -ExitCode $code) -eq "ContactLost") {
            # 255 : la commande distante n'a peut-etre jamais rendu de code.
            # L'annoncer comme "remote command exited 255" attribuait au
            # serveur une reponse qu'il n'avait pas donnee. Les diagnostics
            # sont sautes : ils passent par la meme connexion, qui est morte.
            foreach ($line in Get-ContactLostExplanation) {
                Write-Host "  $line" -ForegroundColor Yellow
            }
            Write-Host "  Pour trancher : ssh -p $SshPort $Target `"cd ~/$RemoteDir && $Compose ps`"" -ForegroundColor Gray
            exit $code
        }

        Write-Host "  ERR: remote command exited $code" -ForegroundColor Red

        # An operator should not have to go and fetch the reason. A container
        # that fails its healthcheck says why in its own log, and the driver
        # is already connected to the machine that holds it.
        if ($Diagnose) {
            Write-Host "`n[Journaux de l API - 60 dernieres lignes]" -ForegroundColor Yellow
            $diag = "cd ~/$RemoteDir && $Compose logs --tail 60 demo-instance-api 2>&1 || true"
            $encodedDiag = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($diag))
            & ssh $SshOptions.Split(' ') -p $SshPort $Target "echo $encodedDiag | base64 -d | sh"
        }
        exit $code
    }
}

function Push-DemoEnv {
    <#
        Send the demonstrator's secrets file and lock it to 600.

        Called by `up` on every start, not only by `push-env`: a start that
        refused and told the operator to run a SECOND command was a chore this
        script invented for itself (measured 2026-08-07 - three failed starts
        in a row, each ending in an instruction rather than an instance).
        Pushing every time also removes drift: the host runs the file the
        workstation holds, or the start refuses.

        It never travels in the PROD bundle: it carries a DIFFERENT set of
        credentials from the production instance, and the bundle is a
        directory that lingers on the workstation.
    #>
    $source = Join-Path $ProjectRoot ".env.demo-instance.prod"
    if (-not (Test-Path $source)) {
        Write-Host "  ERR: $source introuvable sur ce poste." -ForegroundColor Red
        Write-Host "       Le creer depuis .env.demo-instance.prod.example, puis relancer." -ForegroundColor Gray
        exit 1
    }

    $content = Get-Content $source -Raw
    if ($content -match '(?m)^(FRONTEND_URL|APP_URL_SERVER)=.*localhost') {
        Write-Host "  ERR: ce fichier pointe sur localhost : forme de DEVELOPPEMENT." -ForegroundColor Red
        Write-Host "       Envoyer celui-la casserait le lien de verification." -ForegroundColor Gray
        exit 1
    }
    foreach ($key in @("DEMO_INSTANCE_TUNNEL_TOKEN", "DEEPSEEK_API_KEY", "SECRET_KEY", "FERNET_KEY")) {
        if ($content -notmatch "(?m)^$key=.") {
            Write-Host "  ERR: $key est vide. Instance non demarrable." -ForegroundColor Red
            exit 1
        }
    }

    Write-Host "`n[Fichier de secrets]" -ForegroundColor Cyan
    Write-Host "  $source -> ${Target}:~/$RemoteDir/" -ForegroundColor DarkGray
    & scp -P $SshPort $source "${Target}:~/$RemoteDir/.env.demo-instance.prod"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERR: scp a echoue ($LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    # 600 dans la foulee : un fichier cree par scp herite du umask.
    Invoke-Remote "chmod 600 .env.demo-instance.prod" "Permissions 600"
}

switch ($Action) {
    "status" {
        Invoke-Remote "$Compose ps" "Containers"
        Invoke-Remote "$Compose exec -T demo-instance-api python -c `"import urllib.request,json;print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8000/ready',timeout=10)),indent=1))`" || true" "Readiness"
    }

    "up" {
        # The tunnel profile is what puts the instance on the Internet, and the
        # token is what the profile needs. Checked on the HOST, where the file
        # actually is.
        # Everything that must be true before this instance faces the
        # Internet, checked on the host and refusing with the cause AND the
        # command that fixes it. In a script, not a quoted string: the first
        # version of this check reached the host unterminated, and the second
        # blamed permissions for a file that was simply not there.
        Push-DemoEnv
        # The digest travels WITH the preflight: it is what turns "these
        # seeds are not the ones you just described" into a refusal on the
        # host, BEFORE any migration runs, instead of a bare 64-hex
        # mismatch raised inside the container afterwards (2026-08-19).
        Invoke-Remote "SEED_BUNDLE_SHA256=$seedDigest sh scripts/deploy/preflight-demo-prod.sh" "Preflight"

        # `--build`, and it is the difference between serving the code that was
        # shipped and serving yesterday's. `deploy:prod` builds the three
        # PRODUCTION envelopes and deliberately does not start the
        # demonstrator, so its image is built HERE or nowhere. Without this
        # flag the start reused whatever image already existed: measured
        # 2026-08-07 on the public instance, an API container recreated minutes
        # earlier and healthy, running a source file dated 23 July -- a visitor
        # had switched the debug panel on and it stayed empty, with no error
        # anywhere to say why. Docker's layer cache makes an unchanged rebuild
        # cheap; a start that lies about which code it runs is not.
        Invoke-Remote "$Compose --profile tunnel up -d --build --wait" "Start (with tunnel)" -Diagnose

        # The step that creates the garbage takes it out. Building on every
        # start makes this driver a producer of build cache: measured on the
        # host the same day, 50.38 GB of it, 12.12 GB reclaimable, on a disk
        # shared with the production stack, its backups and its metrics
        # retention. Bounded by AGE, not emptied: `prune -a` would drop the
        # warm layers too and turn the next start into a cold rebuild.
        # Non-fatal - a full disk is a problem, a failed prune is not.
        Invoke-Remote "docker builder prune -f --filter until=168h || true" "Purge du cache de build (> 7 jours)"

        # HERE, and not in `deploy:prod`: the rules are written against the
        # demonstrator's SUBNETS, and those subnets do not exist until the
        # networks do. A deployment ships the instance without starting it, so
        # the hardening step there finds nothing and only warns - which meant
        # that following the documented path produced a PUBLIC instance with
        # no host isolation at all. Starting it is the moment the rules can be
        # written, so it is the moment they are.
        Invoke-Remote "sh scripts/deploy/harden-demo-host.sh" "Host isolation (iptables)"

        # The tmpfs database is empty at every start: the marker that authorizes
        # the nightly purge must be re-written, and provisioning refuses a model
        # this catalogue cannot price.
        Invoke-Remote "$Compose exec -T -w /app demo-instance-api python -m src.infrastructure.provisioning.cli" "Provision"

        # And the isolation is MEASURED before the instance is called started:
        # installing a rule and trusting it is how this gap appeared in the
        # first place. The probe opens real connections from inside the API
        # container and fails if the host answers.
        Invoke-Remote "$Compose exec -T -w /app demo-instance-api python scripts/ops/probe_host_isolation.py" "Host isolation (measured)"

        Write-Host "`nStarted, isolated and measured. Run 'task demo:prod:verify' before announcing the link." -ForegroundColor Green
    }

    "down" {
        Invoke-Remote "$Compose --profile tunnel down" "Stop"
        Write-Host "`nStopped. The tmpfs database died with it, by design." -ForegroundColor Green
    }

    "provision" {
        Invoke-Remote "$Compose exec -T -w /app demo-instance-api python -m src.infrastructure.provisioning.cli" "Provision"
    }

    "push-env" {
        Push-DemoEnv
        Invoke-Remote "SEED_BUNDLE_SHA256=$seedDigest sh scripts/deploy/preflight-demo-prod.sh" "Preflight"
        Write-Host "`nFichier en place. Lancer ensuite: task demo:prod:up" -ForegroundColor Green
    }

    "logs" {
        Invoke-Remote "$Compose logs --tail 120 --no-log-prefix demo-instance-api" "Journaux API"
    }

    "harden" {
        Invoke-Remote "sh scripts/deploy/harden-demo-host.sh" "Host isolation (iptables)"
    }

    "verify" {
        Invoke-Remote "$Compose exec -T -w /app demo-instance-api python -m src.infrastructure.provisioning.cli --verify" "Spend ceiling"
        Invoke-Remote "$Compose exec -T -w /app demo-instance-api python scripts/ops/probe_host_isolation.py" "Host isolation (measured)"
        Invoke-Remote "sh scripts/deploy/harden-demo-host.sh --check" "Host isolation (rules)"
        Invoke-Remote "sh scripts/deploy/verify-demo-surface.sh" "Closed surface"
    }
}
