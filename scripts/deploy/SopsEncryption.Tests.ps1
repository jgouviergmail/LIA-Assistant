# Native Windows PowerShell 5.1 regression: task deploy:prod uses this host,
# whose ANSI file reads and OEM stdout decoding can corrupt a SOPS MAC.
#Requires -Version 7.0

Describe "SOPS UTF-8 boundary under Windows PowerShell 5.1" -Skip:(-not $IsWindows) {
    BeforeAll {
        $script:WinPsExe = (Get-Command powershell.exe -ErrorAction Stop).Source
        $script:SopsExe = (Get-Command sops -CommandType Application -ErrorAction Stop).Source
        $script:FixtureBase = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../../.tmp/windows-sops-utf8"))
        $script:FixtureRoot = Join-Path $FixtureBase ([Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $FixtureRoot -Force | Out-Null
        $script:Utf8NoBom = New-Object Text.UTF8Encoding($false)
        $tokens = $null
        $parseErrors = $null
        $ast = [Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $PSScriptRoot "deploy-prod.ps1"), [ref]$tokens, [ref]$parseErrors)
        if ($parseErrors.Count) { throw "Deploy script must parse before the SOPS regression runs" }
        $script:EncryptFunction = $ast.Find({
                param($node)
                $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
                $node.Name -eq "Invoke-SopsEncryptDotenv"
            }, $true).Extent.Text

        # Deterministic all-zero test identity, NEVER a production key. Only the
        # temporary ignored key file holds its AGE encoding. The recipient was
        # independently derived from X25519 private bytes [0] * 32.
        $hrp = "age-secret-key-"
        $values = @($hrp.ToCharArray() | ForEach-Object { [int]$_ -shr 5 }) + @(0) +
            @($hrp.ToCharArray() | ForEach-Object { [int]$_ -band 31 }) + @(0) * 58
        $checksum = 1
        $generators = @(0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3)
        foreach ($value in $values) {
            $top = $checksum -shr 25
            $checksum = (($checksum -band 0x1ffffff) -shl 5) -bxor $value
            for ($i = 0; $i -lt 5; $i++) {
                if (($top -shr $i) -band 1) { $checksum = $checksum -bxor $generators[$i] }
            }
        }
        $checksum = $checksum -bxor 1
        $alphabet = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
        $suffix = -join (0..5 | ForEach-Object { $alphabet[($checksum -shr (5 * (5 - $_))) -band 31] })
        $script:TestIdentity = ($hrp + "1" + ("q" * 52) + $suffix).ToUpperInvariant()
        $script:TestRecipient = "age19ljhmg68e43yx9fgm2k9lwefquc0la5y4lzvlshdjzv47kxt8d6qr9vf4p"

        function Invoke-SopsFixture([string]$Name, [int]$InitialCodePage, [string]$Failure = "") {
            $directory = Join-Path $FixtureRoot $Name
            New-Item -ItemType Directory -Path $directory | Out-Null
            $source = Join-Path $directory ".env.prod"
            $output = Join-Path $directory ".env.prod.encrypted"
            $key = Join-Path $directory "test-age-key.txt"
            $unicode = "Été — 漢字 🎵"
            $sourceText = "# $unicode`r`nSECRET_KEY=synthetic-$unicode # removed inline comment`r`nPUBLIC_LABEL=$unicode`r`n"
            [IO.File]::WriteAllText($source, $sourceText, $Utf8NoBom)
            [IO.File]::WriteAllText($key, $TestIdentity + "`n", $Utf8NoBom)
            $rule = if ($Failure -eq "sops") { '^not-this-file$' } else { '^\.env\.prod$' }
            $config = "creation_rules:`n  - path_regex: '$rule'`n    encrypted_regex: '^SECRET_KEY$'`n    age: $TestRecipient`n"
            [IO.File]::WriteAllText((Join-Path $directory ".sops.yaml"), $config, $Utf8NoBom)
            if ($Failure -eq "writer") { $output = $directory }
            $qDirectory = $directory.Replace("'", "''")
            $qSource = $source.Replace("'", "''")
            $qOutput = $output.Replace("'", "''")
            $qKey = $key.Replace("'", "''")
            $qSops = $SopsExe.Replace("'", "''")
            $childScript = @"
`$ErrorActionPreference = 'Stop'
$EncryptFunction
function Write-Err { param([string]`$Message) }
Set-Location -LiteralPath '$qDirectory'
[Console]::OutputEncoding = [Text.Encoding]::GetEncoding($InitialCodePage)
`$originalEncoding = [Console]::OutputEncoding
`$utf8 = New-Object Text.UTF8Encoding(`$false)
`$before = [Convert]::ToBase64String([IO.File]::ReadAllBytes('$qSource'))
`$succeeded = `$false
`$threw = `$false
try {
    `$succeeded = Invoke-SopsEncryptDotenv -SourceEnv '$qSource' -OutputEnc '$qOutput' -AgeKeyFile '$qKey'
} catch { `$threw = `$true }
`$restored = [Console]::OutputEncoding.Equals(`$originalEncoding)
`$archiveExists = Test-Path -LiteralPath '$qOutput' -PathType Leaf
`$bom = `$false
`$crCount = 0
`$decryptExit = `$null
`$normalizedDecryptExit = `$null
`$unicodeValuesMatch = `$false
`$unicodeCommentMatches = `$false
if (`$archiveExists) {
    `$bytes = [IO.File]::ReadAllBytes('$qOutput')
    `$bom = `$bytes.Length -ge 3 -and `$bytes[0] -eq 239 -and `$bytes[1] -eq 187 -and `$bytes[2] -eq 191
    `$crCount = @(`$bytes | Where-Object { `$_ -eq 13 }).Count
    function Invoke-PrivateDecrypt([byte[]]`$Payload) {
        `$start = New-Object Diagnostics.ProcessStartInfo
        `$start.FileName = '$qSops'
        `$start.Arguments = 'decrypt --input-type dotenv --output-type dotenv --filename-override .env.prod'
        `$start.WorkingDirectory = '$qDirectory'
        `$start.UseShellExecute = `$false
        `$start.CreateNoWindow = `$true
        `$start.RedirectStandardInput = `$true
        `$start.RedirectStandardOutput = `$true
        `$start.RedirectStandardError = `$true
        `$start.StandardOutputEncoding = `$utf8
        `$start.StandardErrorEncoding = `$utf8
        `$start.EnvironmentVariables['SOPS_AGE_KEY_FILE'] = '$qKey'
        `$process = New-Object Diagnostics.Process
        `$process.StartInfo = `$start
        `$null = `$process.Start()
        `$stdoutTask = `$process.StandardOutput.ReadToEndAsync()
        `$stderrTask = `$process.StandardError.ReadToEndAsync()
        `$process.StandardInput.BaseStream.Write(`$Payload, 0, `$Payload.Length)
        `$process.StandardInput.Close()
        `$process.WaitForExit()
        `$privateResult = @{ ExitCode = `$process.ExitCode; Clear = `$stdoutTask.Result }
        `$null = `$stderrTask.Result
        `$process.Dispose()
        return `$privateResult
    }
    `$direct = Invoke-PrivateDecrypt `$bytes
    `$decryptExit = `$direct.ExitCode
    `$normalized = `$utf8.GetString(`$bytes).TrimStart([char]0xFEFF) -replace "``r``n?", "``n"
    `$decoded = Invoke-PrivateDecrypt (`$utf8.GetBytes(`$normalized))
    `$normalizedDecryptExit = `$decoded.ExitCode
    `$clearLines = `$decoded.Clear -split "``r?``n"
    `$unicodeValuesMatch = (`$clearLines -ccontains 'SECRET_KEY=synthetic-$unicode') -and
        (`$clearLines -ccontains 'PUBLIC_LABEL=$unicode')
    `$unicodeCommentMatches = `$clearLines -ccontains '# $unicode'
}
`$report = @{
    Succeeded = `$succeeded; Threw = `$threw; ArchiveExists = `$archiveExists
    Utf8Bom = `$bom; CrCount = `$crCount; DecryptExit = `$decryptExit
    NormalizedDecryptExit = `$normalizedDecryptExit; UnicodeValuesMatch = `$unicodeValuesMatch
    UnicodeCommentMatches = `$unicodeCommentMatches; EncodingRestored = `$restored
    SourceUnchanged = `$before -ceq [Convert]::ToBase64String([IO.File]::ReadAllBytes('$qSource'))
    TempRemoved = -not (Test-Path -LiteralPath '$qSource.sops.tmp')
}
[Console]::Write((`$report | ConvertTo-Json -Compress))
"@
            $start = New-Object Diagnostics.ProcessStartInfo
            $start.FileName = $WinPsExe
            $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($childScript))
            $start.Arguments = "-NoProfile -NonInteractive -EncodedCommand $encoded"
            $start.UseShellExecute = $false
            $start.CreateNoWindow = $true
            $start.RedirectStandardOutput = $true
            $start.RedirectStandardError = $true
            $process = New-Object Diagnostics.Process
            $process.StartInfo = $start
            try {
                $null = $process.Start()
                $stdoutTask = $process.StandardOutput.ReadToEndAsync()
                $stderrTask = $process.StandardError.ReadToEndAsync()
                $process.WaitForExit()
                if ($process.ExitCode -ne 0) { throw "WinPS SOPS fixture failed; private output suppressed" }
                $privateOutput = $stdoutTask.Result
                $null = $stderrTask.Result
                return ($privateOutput | ConvertFrom-Json)
            } finally {
                $process.Dispose()
            }
        }

        $script:OemResult = Invoke-SopsFixture "oem-success" 850
        $script:Utf8Result = Invoke-SopsFixture "utf8-success" 65001
        $script:SopsFailure = Invoke-SopsFixture "sops-failure" 850 "sops"
        $script:WriterFailure = Invoke-SopsFixture "writer-failure" 850 "writer"
    }

    AfterAll {
        if ($FixtureRoot -and (Test-Path -LiteralPath $FixtureRoot)) {
            $resolved = [IO.Path]::GetFullPath($FixtureRoot)
            if (-not $resolved.StartsWith($FixtureBase + [IO.Path]::DirectorySeparatorChar,
                    [StringComparison]::OrdinalIgnoreCase)) { throw "Fixture cleanup escaped its ignored directory" }
            Remove-Item -LiteralPath $FixtureRoot -Recurse -Force
        }
    }

    It "writes an archive directly readable by SOPS without BOM or CR" {
        $OemResult.Succeeded | Should -BeTrue
        $OemResult.Utf8Bom | Should -BeFalse
        $OemResult.CrCount | Should -Be 0
        $OemResult.DecryptExit | Should -Be 0
    }

    It "preserves a valid MAC when the caller uses OEM stdout decoding" {
        $OemResult.NormalizedDecryptExit | Should -Be 0
        $OemResult.UnicodeValuesMatch | Should -BeTrue
        $OemResult.UnicodeCommentMatches | Should -BeTrue
    }

    It "reads Unicode source values as UTF-8 even under WinPS default ANSI reads" {
        $Utf8Result.NormalizedDecryptExit | Should -Be 0
        $Utf8Result.UnicodeValuesMatch | Should -BeTrue
        $Utf8Result.UnicodeCommentMatches | Should -BeTrue
    }

    It "restores the caller encoding and leaves source bytes intact after success" {
        foreach ($result in @($OemResult, $Utf8Result)) {
            $result.EncodingRestored | Should -BeTrue
            $result.SourceUnchanged | Should -BeTrue
            $result.TempRemoved | Should -BeTrue
        }
    }

    It "cleans the plaintext copy and restores encoding when SOPS rejects its rule" {
        $SopsFailure.Succeeded | Should -BeFalse
        $SopsFailure.ArchiveExists | Should -BeFalse
        $SopsFailure.EncodingRestored | Should -BeTrue
        $SopsFailure.SourceUnchanged | Should -BeTrue
        $SopsFailure.TempRemoved | Should -BeTrue
    }

    It "cleans the plaintext copy and restores encoding when the archive write fails" {
        $WriterFailure.Threw | Should -BeTrue
        $WriterFailure.EncodingRestored | Should -BeTrue
        $WriterFailure.SourceUnchanged | Should -BeTrue
        $WriterFailure.TempRemoved | Should -BeTrue
    }
}
