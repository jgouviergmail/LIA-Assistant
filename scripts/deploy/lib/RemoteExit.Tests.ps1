# ============================================================================
# Classification d'un code de sortie ssh (ADR-250).
#
# La regle tient en une phrase -- 255 ne dit rien du distant -- et c'est
# exactement pour cela qu'elle ne doit exister qu'a UN endroit : deux pilotes
# la portaient sur le point d'etre ecrits chacun de leur cote, et une regle
# dupliquee diverge.
#
# Mesures du 2026-08-29 sur l'hote reel, qui fondent la table ci-dessous :
#   commande distante `exit 7`   -> ssh rend 7
#   commande distante `exit 1`   -> ssh rend 1
#   commande distante `exit 255` -> ssh rend 255
#   hote injoignable             -> ssh rend 255
#   ProxyCommand casse           -> ssh rend 255
# ============================================================================
#Requires -Version 7.0

BeforeAll {
    . (Join-Path $PSScriptRoot "RemoteExit.ps1")
}

Describe "Get-RemoteExitVerdict" {
    It "classe 0 en succes" {
        Get-RemoteExitVerdict -ExitCode 0 | Should -Be "Success"
    }

    It "classe <Code> en echec DISTANT (ssh a propage le code du serveur)" -ForEach @(
        @{ Code = 1 }, @{ Code = 2 }, @{ Code = 5 }, @{ Code = 7 }
        @{ Code = 125 }, @{ Code = 130 }, @{ Code = 141 }, @{ Code = 254 }
    ) {
        Get-RemoteExitVerdict -ExitCode $Code | Should -Be "RemoteFailure"
    }

    It "classe 255 en contact perdu, et LUI SEUL" {
        Get-RemoteExitVerdict -ExitCode 255 | Should -Be "ContactLost"
        # Le voisinage immediat ne doit pas glisser dans la meme categorie :
        # 254 est un vrai code distant, 256 n'existe pas mais ne doit pas
        # etre traite comme une coupure par un modulo malencontreux.
        Get-RemoteExitVerdict -ExitCode 254 | Should -Be "RemoteFailure"
        Get-RemoteExitVerdict -ExitCode 256 | Should -Be "RemoteFailure"
    }

    It "n'invente rien sur un code negatif (PowerShell peut en produire)" {
        Get-RemoteExitVerdict -ExitCode -1 | Should -Be "RemoteFailure"
    }
}

Describe "Get-ContactLostExplanation" {
    BeforeAll { $script:lines = Get-ContactLostExplanation }

    It "rend plusieurs lignes de prose, pas une seule phrase compacte" {
        $lines.Count | Should -BeGreaterThan 3
    }

    It "dit que le verdict est inconnu, jamais qu'il y a eu echec" {
        ($lines -join " ") | Should -Match "(?i)inconnu"
        ($lines -join " ") | Should -Not -Match "(?i)echec du deploiement"
    }

    It "avertit que le distant peut encore tourner" {
        ($lines -join " ") | Should -Match "(?i)(en cours|peut encore)"
    }

    It "coupe le reflexe de relancer, qui est la vraie manoeuvre dangereuse" {
        # Relancer efface le repertoire de staging SOUS un build en vol.
        ($lines -join " ") | Should -Match "(?i)ne pas relancer"
    }

    It "porte le marqueur ADR-250, tracable par grep" {
        ($lines -join " ") | Should -Match "ADR-250"
    }
}
