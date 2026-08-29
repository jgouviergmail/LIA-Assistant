# ============================================================================
# Execution distante detachee (ADR-250) -- noyau pur.
#
# Le transport ne doit plus etre sur le chemin critique du verdict. Trois
# mesures du 2026-08-29 sur l'hote reel fondent ce dessein :
#
#   1. Tuer le client ssh fait mourir le script distant par SIGPIPE (exit 141)
#      en ~6 s des qu'il ecrit sur le canal -- pas au bout des 6 min 15 de
#      keepalive, immediatement. Sur un des deux essais, AUCUN verdict n'a meme
#      ete ecrit : le wrapper est mort avec le script.
#   2. La meme charge lancee DETACHEE survit a la destruction de tous les
#      clients ssh, rend son code de sortie exact et son journal complet.
#   3. Le detachement ne s'obtient pas naivement : `nohup`, `setsid`, `disown`
#      ont tous echoue tant que la redirection ne couvrait pas le sous-shell
#      cree par `&` pour la liste entiere.
#
# Ce fichier teste ce qui peut l'etre sans reseau : la FORME de la charge (une
# regression y serait invisible autrement) et la machine a etats du verdict.
# ============================================================================
#Requires -Version 7.0

BeforeAll {
    # The strictness the library wants for itself: set HERE, where it
    # applies to the test scope, instead of at the library's file scope,
    # where dot-sourcing would impose it on every caller.
    Set-StrictMode -Version Latest
    . (Join-Path $PSScriptRoot "RemoteRun.ps1")
}

Describe "New-DetachedLaunchPayload -- la forme qui detache reellement" {
    BeforeAll {
        $script:payload = New-DetachedLaunchPayload `
            -RemoteDir "~/lia.staging" -Command "./deploy.sh" `
            -RunId "20260829-162500-ab12" -LockPath "deploy.lock"
    }

    It "ne purge RIEN : chaque execution a ses propres artefacts" {
        # Defaut mesure le 2026-08-29 sur l'hote reel. La forme precedente
        # purgeait `run.rc`/`run.log` de maniere synchrone AVANT de tenter le
        # verrou. Un second lancement concurrent detruisait donc le journal du
        # deploiement EN VOL (3 lignes -> 0, le premier continuant d'ecrire
        # dans un inode delie) et posait DEPLOY_BUSY dans le `.rc` que le
        # premier allait ecraser -- verdict transitoirement faux pour un run
        # qui n'etait pas le sien.
        #
        # Des artefacts nommes par execution suppriment la classe entiere :
        # il n'y a plus de fichier partage a purger, donc plus rien a detruire.
        $payload | Should -Not -Match "rm -f"
    }

    It "nomme ses artefacts d'apres l'identifiant d'execution" {
        $payload | Should -Match "20260829-162500-ab12"
    }

    It "redirige les TROIS flux du processus detache" {
        # C'est la seule raison pour laquelle ssh rend la main : un descripteur
        # laisse ouvert sur le canal le maintient jusqu'a la fin du travail.
        $payload | Should -Match ">/dev/null"
        $payload | Should -Match "2>&1"
        $payload | Should -Match "</dev/null"
    }

    It "detache reellement (nohup + arriere-plan)" {
        $payload | Should -Match "nohup"
        $payload.TrimEnd() | Should -Match "&$"
    }

    It "capture le code de sortie du SCRIPT, pas celui du wrapper" {
        $payload | Should -Match ([regex]::Escape('echo $? > ')) 
        $payload | Should -Match "20260829-162500-ab12\.rc"
    }

    It "envoie le journal dans un FICHIER, jamais sur le canal" {
        # Ecrire sur le canal est precisement ce qui tue le distant par SIGPIPE.
        $payload | Should -Match ([regex]::Escape('./deploy.sh > ')) 
        $payload | Should -Match "20260829-162500-ab12\.log 2>&1"
    }

    It "prend un verrou non bloquant que le noyau libere a la mort du detenteur" {
        $payload | Should -Match "flock -n"
        $payload | Should -Match "deploy\.lock"
    }

    It "signale un deploiement deja en vol au lieu de le doubler" {
        $payload | Should -Match "DEPLOY_BUSY"
    }

    It "protege `$? du shell EXTERNE (sinon le verdict est toujours 0)" {
        # Defaut trouve a l'execution reelle le 2026-08-29, invisible a toute
        # verification de forme plus laxiste : l'interieur etait en guillemets
        # DOUBLES, si bien que le shell externe expansait `$?` avant de le
        # passer au shell interne. Celui-ci recevait `echo 0 > run.rc`, le 0
        # etant le code du `rm -f` qui precede -- le verdict valait donc
        # TOUJOURS 0, y compris pour un deploiement qui avait echoue.
        #
        # L'interieur doit etre en guillemets SIMPLES : le shell externe n'y
        # touche pas. Meme classe que la garde $(...) deja en place, appliquee
        # a $?.
        $payload | Should -Match ([regex]::Escape("sh -c '"))
        $payload | Should -Not -Match ([regex]::Escape('sh -c "'))
    }

    It "partage le VERROU entre executions -- sinon il ne garde rien" {
        # Le verrou doit etre au chemin FIXE : un verrou par execution serait
        # pris a tous les coups et n'empecherait aucune concurrence.
        $other = New-DetachedLaunchPayload -RemoteDir "~/lia.staging" `
            -Command "./deploy.sh" -RunId "20260829-170000-cd34" -LockPath "deploy.lock"
        $other | Should -Match "deploy\.lock"
        $other | Should -Not -Match "20260829-162500-ab12"
    }

    It "n'enferme aucun guillemet simple dans la charge a quotes simples" {
        # Un guillemet simple dans le corps terminerait la chaine et le reste
        # serait interprete par le shell externe. Les chemins qui composent la
        # charge sont valides ailleurs, mais la garde doit etre ici.
        $inner = [regex]::Match($payload, "sh -c '([^']*)'").Groups[1].Value
        $inner | Should -Not -BeNullOrEmpty
        $inner | Should -Not -Match "'"
    }
}

Describe "ConvertTo-RemotePayload -- l'encodage qui traverse trois shells" {
    It "ne laisse passer que des caracteres base64" {
        $enc = ConvertTo-RemotePayload -Payload 'echo $? > x.rc && cd "a b" || true'
        $enc | Should -Match "^[A-Za-z0-9+/=]+$"
    }

    It "protege le `$? que `sh -c` aurait expanse LOCALEMENT" {
        # La branche Linux/macOS passe la commande a `sh -c` : un `$?` non
        # protege y serait remplace par le code de la commande precedente du
        # poste. Meme classe que la garde $(...) deja en place.
        $enc = ConvertTo-RemotePayload -Payload 'echo $? > run.rc'
        $decoded = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($enc))
        $decoded | Should -Be 'echo $? > run.rc'
    }

    It "survit aux guillemets, qui ont deja casse une commande distante" {
        $tricky = 'sh -c "cd /tmp && echo ''hello'' > f"'
        $enc = ConvertTo-RemotePayload -Payload $tricky
        [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($enc)) | Should -Be $tricky
    }
}

Describe "Get-DetachedVerdict -- ce que l'on sait, et rien de plus" {
    It "code 0 lu dans le .rc = succes" {
        $v = Get-DetachedVerdict -RcContent "0" -ProcessAlive $false -PollExhausted $false
        $v.Kind | Should -Be "Success"
        $v.ExitCode | Should -Be 0
    }

    It "code non nul lu dans le .rc = echec DISTANT, avec son code" {
        $v = Get-DetachedVerdict -RcContent "17" -ProcessAlive $false -PollExhausted $false
        $v.Kind | Should -Be "RemoteFailure"
        $v.ExitCode | Should -Be 17
    }

    It "tolere les espaces et le saut de ligne autour du code" {
        (Get-DetachedVerdict -RcContent "  42 `n" -ProcessAlive $false -PollExhausted $false).ExitCode | Should -Be 42
    }

    It "processus vivant, pas de .rc = toujours en cours" {
        $v = Get-DetachedVerdict -RcContent $null -ProcessAlive $true -PollExhausted $false
        $v.Kind | Should -Be "Running"
    }

    It "processus MORT sans .rc = interrompu, et on le dit" {
        # Le cas le plus dangereux : tue par l'OOM, un reboot, un SIGPIPE.
        # Ni succes ni echec distant -- le travail s'est arrete en chemin.
        $v = Get-DetachedVerdict -RcContent $null -ProcessAlive $false -PollExhausted $false
        $v.Kind | Should -Be "Interrupted"
    }

    It "budget epuise alors qu'il tourne encore = inconnu, JAMAIS echec" {
        $v = Get-DetachedVerdict -RcContent $null -ProcessAlive $true -PollExhausted $true
        $v.Kind | Should -Be "Unknown"
    }

    It "un .rc illisible ne devient pas un succes" {
        # Un `.rc` tronque ou pollue est une inconnue, pas un zero.
        (Get-DetachedVerdict -RcContent "bruit" -ProcessAlive $false -PollExhausted $false).Kind | Should -Be "Interrupted"
        (Get-DetachedVerdict -RcContent "" -ProcessAlive $false -PollExhausted $false).Kind | Should -Be "Interrupted"
    }

    It "le .rc PRIME sur l'etat du processus" {
        # Course normale : le script a fini et ecrit son code, le pgrep de la
        # meme seconde voit encore le wrapper. Le verdict ecrit gagne.
        $v = Get-DetachedVerdict -RcContent "0" -ProcessAlive $true -PollExhausted $false
        $v.Kind | Should -Be "Success"
    }

    It "un marqueur DEPLOY_BUSY est un refus, pas un echec du deploiement" {
        $v = Get-DetachedVerdict -RcContent "DEPLOY_BUSY" -ProcessAlive $false -PollExhausted $false
        $v.Kind | Should -Be "Busy"
    }
}

# ============================================================================
# L'orchestrateur : la frontiere d'E/S est INJECTEE, la machine a etats est
# donc verifiable sans reseau, sans Pi et sans attente.
# ============================================================================
Describe "Invoke-RemoteDetached -- la machine a etats" {
    BeforeAll {
        # Executeur factice : rejoue une sequence de reponses distantes et
        # journalise les charges recues. Chaque reponse est @{ ExitCode; Output }.
        # Le faux executeur capture ses etats par CLOSURE, pas via `$script:` :
        # une closure creee dans un BeforeAll de Pester ne partage pas la
        # portee de script attendue, et `Set-StrictMode` transforme alors la
        # variable absente en erreur -- panne de harnais qui se lit comme une
        # panne du code teste.
        function New-FakeExecutor {
            param([object[]]$Responses)
            $calls = [System.Collections.Generic.List[string]]::new()
            $idx = [ref]0
            $block = {
                param([string]$Payload)
                $calls.Add($Payload)
                $r = $Responses[[Math]::Min($idx.Value, $Responses.Count - 1)]
                $idx.Value++
                return $r
            }.GetNewClosure()
            return @{ Block = $block; Calls = $calls }
        }
        function Poll([string]$Rc, [int]$Alive, [string]$Log = "") {
            @{ ExitCode = 0; Output = "RC=$Rc`nALIVE=$Alive`n---LOG---`n$Log" }
        }
    }

    It "rend Success quand le distant a ecrit 0" {
        $exec = New-FakeExecutor @(@{ ExitCode = 0; Output = "" }, (Poll "0" 0))
        $v = Invoke-RemoteDetached -RemoteDir "~/lia.staging" -Command "./deploy.sh" `
            -RemoteExecutor $exec.Block -PollIntervalSeconds 0 -BudgetSeconds 60 -Sleeper {}
        $v.Kind | Should -Be "Success"
        $v.ExitCode | Should -Be 0
    }

    It "rend RemoteFailure avec le code du serveur" {
        $exec = New-FakeExecutor @(@{ ExitCode = 0; Output = "" }, (Poll "23" 0))
        $v = Invoke-RemoteDetached -RemoteDir "~/d" -Command "./x.sh" `
            -RemoteExecutor $exec.Block -PollIntervalSeconds 0 -BudgetSeconds 60 -Sleeper {}
        $v.Kind | Should -Be "RemoteFailure"
        $v.ExitCode | Should -Be 23
    }

    It "patiente tant que le travail tourne, puis conclut" {
        $exec = New-FakeExecutor @(
            @{ ExitCode = 0; Output = "" },
            (Poll "" 1), (Poll "" 1), (Poll "0" 0)
        )
        $v = Invoke-RemoteDetached -RemoteDir "~/d" -Command "./x.sh" `
            -RemoteExecutor $exec.Block -PollIntervalSeconds 0 -BudgetSeconds 60 -Sleeper {}
        $v.Kind | Should -Be "Success"
    }

    It "un sondage qui NE SE CONNECTE PAS est reessaye, jamais converti en verdict" {
        # C'est le coeur du dispositif : une coupure reseau pendant la
        # scrutation ne dit rien du deploiement. La convertir en echec
        # reproduirait exactement le defaut que ce chantier supprime.
        $exec = New-FakeExecutor @(
            @{ ExitCode = 0; Output = "" },
            @{ ExitCode = 255; Output = "" },
            @{ ExitCode = 255; Output = "" },
            (Poll "0" 0)
        )
        $v = Invoke-RemoteDetached -RemoteDir "~/d" -Command "./x.sh" `
            -RemoteExecutor $exec.Block -PollIntervalSeconds 0 -BudgetSeconds 60 -Sleeper {}
        $v.Kind | Should -Be "Success"
    }

    It "rend Interrupted quand le travail est mort sans laisser de verdict" {
        $exec = New-FakeExecutor @(@{ ExitCode = 0; Output = "" }, (Poll "" 0))
        $v = Invoke-RemoteDetached -RemoteDir "~/d" -Command "./x.sh" `
            -RemoteExecutor $exec.Block -PollIntervalSeconds 0 -BudgetSeconds 60 -Sleeper {}
        $v.Kind | Should -Be "Interrupted"
    }

    It "rend Unknown quand le budget expire alors qu'il tourne encore" {
        $exec = New-FakeExecutor @(@{ ExitCode = 0; Output = "" }, (Poll "" 1))
        $v = Invoke-RemoteDetached -RemoteDir "~/d" -Command "./x.sh" `
            -RemoteExecutor $exec.Block -PollIntervalSeconds 0 -BudgetSeconds 0 -Sleeper {}
        $v.Kind | Should -Be "Unknown"
    }

    It "rend Busy sans rien casser quand un deploiement est deja en vol" {
        $exec = New-FakeExecutor @(@{ ExitCode = 0; Output = "" }, (Poll "DEPLOY_BUSY" 1))
        $v = Invoke-RemoteDetached -RemoteDir "~/d" -Command "./x.sh" `
            -RemoteExecutor $exec.Block -PollIntervalSeconds 0 -BudgetSeconds 60 -Sleeper {}
        $v.Kind | Should -Be "Busy"
    }

    It "signale LaunchFailed si le lancement lui-meme n'a pas abouti" {
        # Avant que quoi que ce soit ne demarre, un echec est un vrai echec :
        # rien ne tourne a distance, relancer est sans danger.
        $exec = New-FakeExecutor @(@{ ExitCode = 255; Output = "" })
        $v = Invoke-RemoteDetached -RemoteDir "~/d" -Command "./x.sh" `
            -RemoteExecutor $exec.Block -PollIntervalSeconds 0 -BudgetSeconds 60 -Sleeper {}
        $v.Kind | Should -Be "LaunchFailed"
    }

    It "diffuse le journal au fil de l'eau, sans jamais repeter une ligne" {
        $seen = [System.Collections.Generic.List[string]]::new()
        $exec = New-FakeExecutor @(
            @{ ExitCode = 0; Output = "" },
            (Poll "" 1 "etape 1`netape 2"),
            (Poll "0" 0 "etape 3")
        )
        $v = Invoke-RemoteDetached -RemoteDir "~/d" -Command "./x.sh" `
            -RemoteExecutor $exec.Block -PollIntervalSeconds 0 -BudgetSeconds 60 -Sleeper {} `
            -OnLogLine { param($l) $seen.Add($l) }
        $v.Kind | Should -Be "Success"
        $seen | Should -Be @("etape 1", "etape 2", "etape 3")
    }

    It "expose l'identifiant d'execution, pour que l'operateur retrouve ses artefacts" {
        $exec = New-FakeExecutor @(@{ ExitCode = 0; Output = "" }, (Poll "0" 0))
        $v = Invoke-RemoteDetached -RemoteDir "~/d" -Command "./x.sh" `
            -RemoteExecutor $exec.Block -PollIntervalSeconds 0 -BudgetSeconds 60 -Sleeper {}
        $v.RunId | Should -Not -BeNullOrEmpty
        $v.LogPath | Should -Match ([regex]::Escape($v.RunId))
    }

    It "sonde la vivacite par le VERROU, jamais par pgrep" {
        # `pgrep -f` matche sa propre ligne de commande : mesure du
        # 2026-08-29, deux diagnostics successifs se sont auto-comptes et une
        # commande de nettoyage s'est tuee elle-meme. Le verrou repond a la
        # meme question sans ce piege, et il est deja la.
        $exec = New-FakeExecutor @(@{ ExitCode = 0; Output = "" }, (Poll "0" 0))
        Invoke-RemoteDetached -RemoteDir "~/d" -Command "./x.sh" `
            -RemoteExecutor $exec.Block -PollIntervalSeconds 0 -BudgetSeconds 60 -Sleeper {} | Out-Null
        # La charge atteint l'executeur ENCODEE : la decoder est ce qui rend
        # l'assertion vraie sur ce que le Pi executera reellement.
        $pollPayload = [Text.Encoding]::UTF8.GetString(
            [Convert]::FromBase64String($exec.Calls[1]))
        $pollPayload | Should -Match "flock -n"
        $pollPayload | Should -Not -Match "pgrep"
    }
}

# ============================================================================
# A library must not change the strictness of the script that loads it.
# ============================================================================
# `Set-StrictMode` is scope-based and dot-sourcing runs a file's statements in
# the CALLER's scope, so the line makes the LOADER strict — all of it.
#
# Cost, measured on a real deployment on 2026-08-29: `deploy-prod.ps1` died at
# step 5 reading `($null -eq $IsWindows)`, its own Windows PowerShell 5.1
# compatibility idiom (`$IsWindows` does not exist on 5.1). Production was
# untouched — the driver had not reached the remote step — and SEC-040 scrubbed
# the decrypted secret on the way out, which is the safety net doing its job on
# its first real failure.
#
# The guard probes the CLASS rather than that symptom. Asserting on `$IsWindows`
# would pass here forever: this suite runs under pwsh 7, where it is defined.
# Reading a name that is undefined by construction fails on every edition.
Describe "the library does not make its loader strict" {
    It "leaves an undefined variable readable in the caller's scope" {
        $probe = {
            # Start from a NON-strict scope, which is the driver's situation:
            # `BeforeAll` above made this suite strict on purpose, and without
            # this reset the probe would throw whatever the library does.
            Set-StrictMode -Off
            . (Join-Path $PSScriptRoot "RemoteRun.ps1")
            # Undefined by construction. Without a strict-mode leak this is
            # $null; with one, it throws — which is exactly what took the
            # deployment down, one scope away.
            $null -eq $lia_probe_variable_that_is_never_defined
        }
        { & $probe } | Should -Not -Throw
    }

    It "does not call Set-StrictMode at file scope" {
        # The readable half of the same rule: a reviewer adding the line back
        # should be told why it cannot live here.
        $source = Get-Content (Join-Path $PSScriptRoot "RemoteRun.ps1") -Raw
        $source | Should -Not -Match "(?m)^Set-StrictMode"
    }
}

# ============================================================================
# The verdict must survive the job renaming its own directory.
# ============================================================================
# `deploy.sh` ends on ADR-215's atomic swap: `mv "$STAGING_DIR" "$LIVE_DIR"`.
# Artifacts written inside the staging directory therefore MOVE at the exact
# moment the work succeeds.
#
# Measured on the real production deployment, 2026-08-29: `.rc` = 0, seventeen
# containers up, v1.38.0 running — and the driver saw none of it. Its poll began
# with `cd ~/lia.staging 2>/dev/null || exit 0`, so from the swap onward it
# exited silently with no output, and an empty answer is indistinguishable from
# "no verdict yet". A fully successful deployment would have been reported
# `Unknown` forty-five minutes later.
#
# Two properties, and neither had a test before this incident.
Describe "the verdict outlives the atomic swap (ADR-250)" {
    BeforeAll {
        $script:swapLaunch = New-DetachedLaunchPayload `
            -RemoteDir "~/lia.staging" -Command "./deploy.sh" `
            -RunId "20260829-231431-46il" -LockPath '$HOME/.lia-deploy/deploy.lock'
        $script:swapPoll = New-DetachedPollPayload `
            -RemoteDir "~/lia.staging" -RunId "20260829-231431-46il" `
            -LockPath '$HOME/.lia-deploy/deploy.lock' -FromLine 1
    }

    It "writes the verdict OUTSIDE the directory the deployment renames" {
        $swapLaunch | Should -Match ([regex]::Escape('$HOME/.lia-deploy/deploy.20260829-231431-46il.rc'))
        $swapLaunch | Should -Not -Match ([regex]::Escape('> deploy.20260829-231431-46il.rc'))
    }

    It "writes the log there too, so the operator can still read it after the swap" {
        $swapLaunch | Should -Match ([regex]::Escape('$HOME/.lia-deploy/deploy.20260829-231431-46il.log'))
    }

    It "holds the lock outside it as well, so exclusion survives the swap" {
        $swapLaunch | Should -Match ([regex]::Escape('exec 9>$HOME/.lia-deploy/deploy.lock'))
    }

    It "creates the artifact directory synchronously, before detaching" {
        # A directory it cannot create must fail the LAUNCH, where the caller
        # still gets an exit code — not silently inside a detached process.
        $swapLaunch | Should -Match ([regex]::Escape('mkdir -p $HOME/.lia-deploy && cd ~/lia.staging'))
    }

    It "polls WITHOUT changing directory" {
        # The `cd` was the defect: it made the answer depend on a path the job
        # is free to rename underneath it.
        $swapPoll | Should -Not -Match "cd "
    }

    It "never exits silently: a missing file is an answer, not a silence" {
        # `|| exit 0` produced an empty response that the parser read as
        # "still running". Both lines are now unconditional.
        $swapPoll | Should -Not -Match ([regex]::Escape("exit 0"))
        $swapPoll | Should -Match "printf 'RC=%s"
        $swapPoll | Should -Match "ALIVE=0"
        $swapPoll | Should -Match "ALIVE=1"
    }

    It "reads the artifacts by absolute path" {
        $swapPoll | Should -Match ([regex]::Escape('$HOME/.lia-deploy/deploy.20260829-231431-46il.rc'))
        $swapPoll | Should -Match ([regex]::Escape('$HOME/.lia-deploy/deploy.20260829-231431-46il.log'))
    }
}
