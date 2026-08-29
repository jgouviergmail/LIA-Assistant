# ============================================================================
# Execution distante detachee : le transport hors du chemin critique (ADR-250)
# ============================================================================
# Un deploiement dure ~11 minutes (mesure v1.37.0 : build 08:38:18Z ->
# readiness 08:49:12Z). Tant qu'il tient dans une session ssh bloquante, la
# survie du travail depend de la survie de la connexion -- et elle n'y survit
# pas : mesure du 2026-08-29, tuer le client fait mourir le script distant par
# SIGPIPE (exit 141) en ~6 s des qu'il ecrit sur le canal. Sur un des deux
# essais, aucun verdict n'a meme ete ecrit, le wrapper etant mort avec lui.
#
# Detache, le meme travail survit a la destruction de tous les clients ssh et
# rend son code exact. Le verdict cesse alors d'etre deduit d'un code de
# transport : il est LU dans un fichier que le distant a ecrit.
#
# Le detachement ne s'obtient pas naivement. Quatre formes ont echoue (nohup,
# +disown, setsid, setsid sans &) parce que `&` met la LISTE entiere en
# arriere-plan dans un sous-shell qui conserve le canal, tandis que la
# redirection ne couvre que la derniere commande. La forme retenue prepare de
# maniere synchrone, puis lance une commande isolee dont les trois flux sont
# rediriges.
# ============================================================================

# NO `Set-StrictMode` HERE — see the same note in `RemoteExit.ps1`. Dot-sourcing
# applies it to the CALLER's scope, and it took down a real deployment at step 5
# by turning the driver's `$IsWindows` compatibility read into an error. The
# strictness is set by `RemoteRun.Tests.ps1`, which also guards this file.

# Ecrit par le wrapper distant quand le verrou est deja tenu. Ce n'est pas un
# code de sortie : un deploiement refuse n'a pas echoue, il n'a pas eu lieu.
$script:DeployBusyMarker = "DEPLOY_BUSY"

# Ou vivent le verdict, le journal et le verrou -- HORS du repertoire de
# travail, et c'est structurel.
#
# `deploy.sh` termine par un `mv` du repertoire de staging sur le repertoire
# vivant (l'echange atomique d'ADR-215). Des artefacts ecrits dans le staging
# partent donc avec lui, exactement au moment ou le travail REUSSIT. Mesure du
# 2026-08-29 sur la production : `.rc` a 0, 17 conteneurs sains, et un pilote
# qui n'a jamais rien vu parce qu'il regardait un chemin qui n'existait plus.
#
# `$HOME` est resolu par le shell DISTANT : la chaine voyage encodee, aucun
# shell du trajet ne l'expanse avant lui.
$script:ArtifactDir = '$HOME/.lia-deploy'
$script:DefaultLockPath = '$HOME/.lia-deploy/deploy.lock'

function New-DetachedLaunchPayload {
    <#
        .SYNOPSIS
        Construit la charge shell qui lance un travail long, detache.

        .DESCRIPTION
        Trois proprietes, chacune payee par une mesure :

        1. ARTEFACTS PAR EXECUTION, donc AUCUNE purge. La forme precedente
           purgeait un `.rc`/`.log` partage avant de tenter le verrou : mesure
           du 2026-08-29, un second lancement concurrent detruisait le journal
           du deploiement EN VOL (3 lignes -> 0, le premier continuant
           d'ecrire dans un inode delie) et posait un marqueur dans le `.rc`
           que le premier allait ecraser. Nommer les artefacts d'apres
           l'execution supprime la classe : il n'y a plus de fichier partage.

        2. TROIS FLUX REDIRIGES. `>/dev/null 2>&1 </dev/null` sur la commande
           lancee -- et sur elle seule, pas sur une liste `&&`. Un descripteur
           laisse ouvert sur le canal maintient ssh jusqu'a la fin du travail,
           ce qui annule tout le benefice.

        3. JOURNAL DANS UN FICHIER. Ecrire sur le canal est exactement ce qui
           tue le distant par SIGPIPE quand le client disparait.

        Le verrou est pris PAR le processus detache et tenu pendant toute sa
        vie : `flock` est gere par le noyau, donc libere meme si le processus
        est tue -- il n'existe pas de verrou fantome a nettoyer a la main.
    #>
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true)][string]$RemoteDir,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][string]$LockPath
    )

    # Artefacts nommes PAR EXECUTION : il n'y a donc rien a purger, et rien
    # qu'un lancement concurrent puisse detruire. Le verrou, lui, reste au
    # chemin FIXE -- un verrou par execution serait pris a tous les coups et
    # ne garderait rien. Tous trois vivent hors du repertoire de travail, que
    # le deploiement renomme (voir $script:ArtifactDir).
    $RcPath = "$($script:ArtifactDir)/deploy.$RunId.rc"
    $LogPath = "$($script:ArtifactDir)/deploy.$RunId.log"

    # Le corps detache : verrou, puis travail, puis verdict. `exec 9>` ouvre le
    # descripteur pour toute la duree ; `flock -n` echoue immediatement si un
    # autre deploiement le tient deja.
    $inner = "exec 9>$LockPath; " +
             "if ! flock -n 9; then echo $($script:DeployBusyMarker) > $RcPath; exit 0; fi; " +
             "cd $RemoteDir && $Command > $LogPath 2>&1; " +
             'echo $? > ' + $RcPath

    # GUILLEMETS SIMPLES autour du corps, et c'est structurel. En guillemets
    # doubles, le shell EXTERNE expanse `$?` avant de passer la chaine au shell
    # interne : celui-ci recoit `echo 0 > run.rc`, le 0 etant le code du
    # `rm -f` qui precede. Le verdict valait alors TOUJOURS 0 -- y compris pour
    # un deploiement qui avait echoue. Mesure a l'execution reelle le
    # 2026-08-29 : script sortant en 23, `.rc` portant 0.
    #
    # Aucune verification de forme ne l'aurait vu ; il a fallu executer.
    if ($inner.Contains("'")) {
        throw ("New-DetachedLaunchPayload: le corps contient un guillemet simple, " +
               "qui terminerait la chaine et livrerait le reste au shell externe.")
    }

    # `mkdir` et `cd` synchrones : un repertoire d'artefacts impossible a creer
    # ou un repertoire de travail absent doivent faire echouer le LANCEMENT tout
    # de suite, pas silencieusement dans un processus detache.
    return ("mkdir -p $($script:ArtifactDir) && cd $RemoteDir && " +
            "nohup sh -c '$inner' >/dev/null 2>&1 </dev/null &")
}

function New-DeployRunId {
    <#
        .SYNOPSIS
        Un identifiant d'execution lisible et unique.

        .DESCRIPTION
        Horodatage pour que l'operateur reconnaisse ses artefacts d'un coup
        d'oeil, suffixe aleatoire pour que deux lancements de la meme seconde
        ne se marchent pas dessus.
    #>
    [OutputType([string])]
    param()

    $stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
    $suffix = -join ((48..57) + (97..122) | Get-Random -Count 4 | ForEach-Object { [char]$_ })
    return "$stamp-$suffix"
}

function ConvertTo-RemotePayload {
    <#
        .SYNOPSIS
        Encode une charge shell en base64 pour la faire traverser trois shells.

        .DESCRIPTION
        La commande traverse PowerShell, le reassemblage d'arguments de ssh,
        puis le shell distant. Chacun revendique le guillemet, et `sh -c` --
        la branche Linux/macOS du pilote -- expanserait en plus `$?` et
        `$(...)` LOCALEMENT. Encodee, la charge ne contient que
        [A-Za-z0-9+/=] : aucun shell du trajet ne peut la relire de travers.

        C'est la parade que demo-prod.ps1 employait deja depuis qu'une
        commande distante a atteint l'hote sous forme de chaine non terminee
        (mesure du 2026-08-07) ; elle est ici partagee plutot que recopiee.
    #>
    [OutputType([string])]
    param([Parameter(Mandatory = $true)][string]$Payload)

    return [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Payload))
}

function Get-DetachedVerdict {
    <#
        .SYNOPSIS
        Traduit l'etat observe du distant en verdict, sans jamais deviner.

        .DESCRIPTION
        Cinq etats, et la distinction entre les trois derniers est tout
        l'interet du dispositif :

          Success       le `.rc` porte 0
          RemoteFailure le `.rc` porte un code non nul -- il VIENT du serveur
          Busy          un deploiement etait deja en vol ; celui-ci n'a pas eu lieu
          Running       pas de `.rc`, processus vivant
          Interrupted   pas de `.rc`, processus mort -- tue en chemin
          Unknown       budget de scrutation epuise alors qu'il tournait encore

        `Interrupted` et `Unknown` ne sont PAS des echecs et ne doivent jamais
        etre presentes comme tels : dans le premier cas le travail s'est arrete
        quelque part, dans le second on a cesse de regarder. Les confondre avec
        un echec est le diagnostic invente que tout ce chantier supprime.

        Le `.rc` PRIME sur l'etat du processus : a la fin du travail, le
        verdict est ecrit une fraction de seconde avant que le wrapper ne
        disparaisse, et un sondage de la meme seconde voit encore le processus.
        L'ecrit gagne sur l'observe.
    #>
    [OutputType([hashtable])]
    param(
        [AllowNull()][AllowEmptyString()][string]$RcContent,
        [Parameter(Mandatory = $true)][bool]$ProcessAlive,
        [Parameter(Mandatory = $true)][bool]$PollExhausted
    )

    $rc = if ($null -eq $RcContent) { "" } else { $RcContent.Trim() }

    if ($rc -eq $script:DeployBusyMarker) {
        return @{ Kind = "Busy"; ExitCode = $null }
    }

    if ($rc -ne "") {
        # Un `.rc` illisible (tronque, pollue) n'est pas un zero : on ne
        # transforme pas une inconnue en succes.
        $parsed = 0
        if ([int]::TryParse($rc, [ref]$parsed)) {
            return @{
                Kind     = if ($parsed -eq 0) { "Success" } else { "RemoteFailure" }
                ExitCode = $parsed
            }
        }
        return @{ Kind = "Interrupted"; ExitCode = $null }
    }

    if ($ProcessAlive) {
        return @{ Kind = if ($PollExhausted) { "Unknown" } else { "Running" }; ExitCode = $null }
    }

    return @{ Kind = "Interrupted"; ExitCode = $null }
}


function New-DetachedPollPayload {
    <#
        .SYNOPSIS
        La charge de scrutation : verdict, vivacite et journal en UN aller-retour.

        .DESCRIPTION
        Un seul appel distant par sondage. Trois blocs, dans cet ordre, parce
        que le lecteur les consomme dans cet ordre.

        La vivacite est sondee par le VERROU, pas par `pgrep`. `pgrep -f`
        matche sa propre ligne de commande -- mesure du 2026-08-29 : deux
        diagnostics se sont auto-comptes, et une commande de nettoyage s'est
        tuee elle-meme. Le verrou repond a la meme question sans ce piege, et
        il est deja pris par le travail.

        AUCUN `cd`, et c'est une correction, pas une simplification. La forme
        precedente commencait par `cd <repertoire de travail> || exit 0` : quand
        `deploy.sh` a renomme ce repertoire, le sondage sortait SANS RIEN DIRE,
        et une reponse vide est indistinguable de "pas encore de verdict". Un
        deploiement reussi restait donc invisible jusqu'a epuisement du budget.
        Les chemins sont absolus et les deux lignes sont toujours imprimees :
        "le fichier n'est pas la" est une reponse, pas un silence.

        L'ordre "verdict d'abord" n'est pas cosmetique : le `.rc` est ecrit
        AVANT que le shell ne rende le verrou, donc verrou libre implique
        verdict deja ecrit. Lire le `.rc` en premier evite d'observer un etat
        intermediaire.
    #>
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true)][string]$RemoteDir,
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][string]$LockPath,
        [Parameter(Mandatory = $true)][int]$FromLine
    )

    $rc = "$($script:ArtifactDir)/deploy.$RunId.rc"
    $log = "$($script:ArtifactDir)/deploy.$RunId.log"
    return "printf 'RC=%s
' `"`$(cat $rc 2>/dev/null)`"; " +
           "if flock -n $LockPath -c true 2>/dev/null; then echo ALIVE=0; else echo ALIVE=1; fi; " +
           "echo ---LOG---; " +
           "tail -n +$FromLine $log 2>/dev/null"
}

function Invoke-RemoteDetached {
    <#
        .SYNOPSIS
        Lance un travail long a distance, puis LIT son verdict au lieu de le
        deduire du transport (ADR-250).

        .DESCRIPTION
        La frontiere d'E/S est injectee (`-RemoteExecutor`) : la machine a
        etats se verifie sans reseau, sans Pi et sans attente. C'est aussi ce
        qui permet de tester le cas decisif -- un sondage qui ne se connecte
        pas -- sans debrancher quoi que ce soit.

        L'executeur recoit DEUX arguments : la charge encodee, puis la phase
        (`launch` ou `poll`) en clair. La charge est opaque par construction --
        c'est tout l'interet de l'encodage -- si bien que sans cette seconde
        valeur la trace du pilote, le journal d'un harnais et la table des
        processus de l'hote n'affichent qu'un bloc de base64 de 400 caracteres.
        Un executeur qui l'ignore reste valide : PowerShell passe l'argument
        surnumeraire a `$args` sans erreur.

        Regle cardinale : un sondage en echec est REESSAYE. Le convertir en
        verdict reproduirait exactement le defaut que ce chantier supprime,
        puisqu'une coupure pendant la scrutation ne dit rien du travail.

        Six issues : Success, RemoteFailure, Busy, Interrupted, Unknown et
        LaunchFailed. Ce dernier porte le code rendu par l'executeur, et
        l'appelant DOIT le classer avant de conclure : un lancement qui echoue
        sur une coupure de transport (255) a pu forker le travail avant de
        perdre le canal. Seul un code non ambigu autorise a dire que rien n'a
        demarre -- affirmer l'inverse rendrait a un relancement sans danger
        apparent ce que tout ce module existe pour supprimer.
    #>
    [OutputType([hashtable])]
    param(
        [Parameter(Mandatory = $true)][string]$RemoteDir,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][scriptblock]$RemoteExecutor,
        [string]$RunId = (New-DeployRunId),
        [string]$LockPath = $script:DefaultLockPath,
        [int]$PollIntervalSeconds = 5,
        [int]$BudgetSeconds = 2700,
        [scriptblock]$OnLogLine = $null,
        [scriptblock]$Sleeper = { param($s) Start-Sleep -Seconds $s }
    )

    $rcPath = "$($script:ArtifactDir)/deploy.$RunId.rc"
    $logPath = "$($script:ArtifactDir)/deploy.$RunId.log"

    $launch = New-DetachedLaunchPayload -RemoteDir $RemoteDir -Command $Command `
        -RunId $RunId -LockPath $LockPath
    $launchResult = & $RemoteExecutor (ConvertTo-RemotePayload -Payload $launch) "launch"

    if ($launchResult.ExitCode -ne 0) {
        # Le lancement n'a pas abouti localement. C'est a l'appelant de dire si
        # cela prouve que rien n'a demarre : le code est rendu tel quel.
        return @{
            Kind = "LaunchFailed"; ExitCode = $launchResult.ExitCode
            RunId = $RunId; LogPath = $logPath; RcPath = $rcPath
        }
    }

    $fromLine = 1
    $elapsed = 0
    $verdict = @{ Kind = "Running"; ExitCode = $null }

    while ($true) {
        $poll = New-DetachedPollPayload -RemoteDir $RemoteDir -RunId $RunId `
            -LockPath $LockPath -FromLine $fromLine
        $res = & $RemoteExecutor (ConvertTo-RemotePayload -Payload $poll) "poll"

        if ($res.ExitCode -eq 0) {
            $rc = ""
            $alive = $true
            $logPart = ""
            $inLog = $false
            foreach ($line in ($res.Output -split "`r?`n")) {
                if ($inLog) { $logPart += "$line`n"; continue }
                if ($line -eq "---LOG---") { $inLog = $true; continue }
                if ($line -like "RC=*") { $rc = $line.Substring(3).Trim() }
                elseif ($line -like "ALIVE=*") { $alive = ($line.Substring(6).Trim() -eq "1") }
            }

            foreach ($l in ($logPart -split "`n")) {
                if ($l -ne "") {
                    $fromLine++
                    if ($OnLogLine) { & $OnLogLine $l }
                }
            }

            $exhausted = ($elapsed -ge $BudgetSeconds)
            $verdict = Get-DetachedVerdict -RcContent $rc -ProcessAlive $alive -PollExhausted $exhausted
            if ($verdict.Kind -ne "Running") { break }
        }
        # Sondage en echec : on ne sait rien de plus qu'avant. On reessaye.

        if ($elapsed -ge $BudgetSeconds) {
            $verdict = @{ Kind = "Unknown"; ExitCode = $null }
            break
        }

        & $Sleeper $PollIntervalSeconds
        $elapsed += [Math]::Max($PollIntervalSeconds, 1)
    }

    return @{
        Kind = $verdict.Kind; ExitCode = $verdict.ExitCode
        RunId = $RunId; LogPath = $logPath; RcPath = $rcPath
    }
}
