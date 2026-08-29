# ============================================================================
# Ce qu'un code de sortie ssh dit -- et surtout ce qu'il ne dit pas (ADR-250)
# ============================================================================
# `ssh` propage fidelement le code de la commande distante pour TOUTE valeur
# sauf 255, qu'il emploie aussi pour ses propres echecs de transport. Sur 255,
# et sur lui seul, l'appelant ne sait rien de ce qui s'est passe sur le
# serveur : ni succes, ni echec.
#
# Ce n'est pas theorique. `task deploy:prod` se termine sur une session SSH
# reinitialisee alors meme que le deploiement a REUSSI -- le skill
# lia-deploy-prod le documente sous "the exit code lies" et demande a
# l'operateur d'ignorer le message d'erreur. Une consigne ecrite qui demande a
# un humain d'ignorer une erreur EST le piege.
#
# Et l'inverse est vrai aussi : mesure du 2026-08-29, tuer le client ssh en
# cours d'execution fait mourir le script distant par SIGPIPE (exit 141) en
# quelques secondes. Un 255 peut donc aussi signaler un deploiement interrompu
# en plein milieu -- raison pour laquelle on ne devine dans aucun sens.
#
# Cette bibliotheque est le SEUL endroit ou la regle est ecrite. Deux pilotes
# la consomment (deploy-prod.ps1, demo-prod.ps1) ; deux copies auraient diverge.
# ============================================================================

Set-StrictMode -Version Latest

function Get-RemoteExitVerdict {
    <#
        .SYNOPSIS
        Classe un code de sortie ssh en Success / ContactLost / RemoteFailure.

        .DESCRIPTION
        Seul 255 est ambigu et devient `ContactLost`. Tout autre code non nul
        VIENT du serveur : ssh l'a propage tel quel, on peut donc parler
        d'echec distant sans rien inventer.

        Les codes hors plage (negatifs, > 255) sont traites comme des echecs
        distants : ils ne peuvent pas etre le 255 de ssh, et les inventer
        "coupure" serait exactement le diagnostic invente que cette
        bibliotheque existe pour supprimer.
    #>
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    if ($ExitCode -eq 0) { return "Success" }
    if ($ExitCode -eq 255) { return "ContactLost" }
    return "RemoteFailure"
}

function Get-ContactLostExplanation {
    <#
        .SYNOPSIS
        La prose commune aux deux pilotes quand le contact est perdu.

        .DESCRIPTION
        Rendue sous forme de lignes, pour que chaque appelant l'imprime avec
        SES propres helpers d'affichage : les deux scripts n'ont pas la meme
        palette, et un `Write-Host` brut se lirait comme une anomalie.

        L'ordre est delibere : ce qui s'est passe, ce qu'on ignore, puis
        l'avertissement -- parce qu'un operateur qui lit trois lignes en
        diagonale doit avoir vu "ne pas relancer" avant de decider.
    #>
    [OutputType([string[]])]
    param()

    return @(
        "ADR-250: contact perdu avec le serveur (ssh a rendu 255).",
        "Le verdict du deploiement est INCONNU : ce code signale une coupure de",
        "transport, pas un echec distant. Le deploiement peut encore etre EN",
        "COURS sur le serveur.",
        "",
        "NE PAS relancer le deploiement tant que le doute persiste : il",
        "effacerait le repertoire de staging sous un build en vol."
    )
}
