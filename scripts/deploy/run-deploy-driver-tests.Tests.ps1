# The suite runner must isolate synthetic repositories from its caller's Git state.
#Requires -Version 7.0

Describe "Deployment test runner Git isolation" {
    It "removes inherited repository-local variables before invoking Pester" {
        $runnerPath = (Join-Path $PSScriptRoot "run-deploy-driver-tests.ps1").Replace("'", "''")
        $outerIndex = Join-Path $TestDrive "caller.index"
        [IO.File]::WriteAllText($outerIndex, "CALLER_INDEX_SENTINEL")
        $indexLiteral = $outerIndex.Replace("'", "''")
        $probe = @"
function global:Invoke-Pester {
    param([string]`$Path, [switch]`$PassThru)
    foreach (`$name in @(& git rev-parse --local-env-vars)) {
        if (Test-Path -LiteralPath "Env:`$name") { throw "Inherited Git variable: `$name" }
    }
    [pscustomobject]@{ PassedCount = 1; FailedCount = 0 }
}
[Environment]::SetEnvironmentVariable('GIT_INDEX_FILE', '$indexLiteral', 'Process')
[Environment]::SetEnvironmentVariable('GIT_WORK_TREE', '$indexLiteral', 'Process')
& '$runnerPath'
"@
        $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($probe))
        $engine = Join-Path $PSHOME $(if ($IsWindows) { "pwsh.exe" } else { "pwsh" })
        $result = & $engine -NoProfile -EncodedCommand $encoded 2>&1 | Out-String
        $LASTEXITCODE | Should -Be 0 -Because $result
        [IO.File]::ReadAllText($outerIndex) | Should -BeExactly "CALLER_INDEX_SENTINEL"
    }
}
