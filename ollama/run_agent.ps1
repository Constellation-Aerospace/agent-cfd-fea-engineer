<#
.SYNOPSIS
    Drive the local cfd-qwen agent through OLLAMA_QWEN_TRANSIENT_RUNBOOK.md Part C.

.DESCRIPTION
    Seeds the conversation with the full runbook, then loops:
      model proposes ONE powershell command  ->  you approve it  ->  it runs  ->
      its real stdout/stderr is fed back as the next user message.

    Nothing is executed without your explicit approval. The model never touches the
    shell directly; this script does, and only after you type "r".

.PARAMETER Model
    Ollama model name. Default: cfd-qwen (built from ollama/Modelfile.cfd).

.PARAMETER SelfTest
    One non-interactive round trip: check the server, the model, the context budget
    and the command extraction. Executes nothing. Use this to verify readiness.

.EXAMPLE
    .\ollama\run_agent.ps1 -SelfTest
    .\ollama\run_agent.ps1
#>
[CmdletBinding()]
param(
    [string]$Model = "cfd-qwen",
    [string]$Endpoint = "http://127.0.0.1:11434",
    [string]$Runbook = "OLLAMA_QWEN_TRANSIENT_RUNBOOK.md",
    [string]$KeepAlive = "30m",
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# Commands this driver will never execute, regardless of operator approval.
$script:ForbiddenCommands =
    'install_solvers|setup\.ps1|first_run_setup|\bapt(-get)?\s+install|\bpip\s+install|winget\s+install|choco\s+install'

function Invoke-Agent {
    param([array]$Messages)
    $body = @{
        model      = $Model
        stream     = $false
        keep_alive = $KeepAlive
        messages   = $Messages
    } | ConvertTo-Json -Depth 8
    $utf8 = [System.Text.Encoding]::UTF8.GetBytes($body)
    return Invoke-RestMethod -Uri "$Endpoint/api/chat" -Method Post -Body $utf8 `
        -ContentType "application/json; charset=utf-8" -TimeoutSec 1800
}

function Get-Command-Block {
    param([string]$Text)
    $m = [regex]::Match($Text, '(?s)```(?:powershell|ps1|pwsh)?\s*\r?\n(.*?)```')
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return $null
}

# ── preflight ────────────────────────────────────────────────────────────────
Write-Host "`n=== preflight ===" -ForegroundColor Cyan
try {
    $tags = Invoke-RestMethod -Uri "$Endpoint/api/tags" -TimeoutSec 10
} catch {
    throw "Ollama is not answering at $Endpoint. Start it with 'ollama serve'."
}
$names = $tags.models.name
Write-Host ("server      : up ({0} models)" -f $names.Count)
if ($names -notcontains "$Model`:latest" -and $names -notcontains $Model) {
    throw "Model '$Model' not found. Build it: ollama create $Model -f ollama\Modelfile.cfd"
}
Write-Host "model       : $Model"

if (-not (Test-Path $Runbook)) { throw "Runbook not found: $Runbook" }
$runbookText = Get-Content $Runbook -Raw
Write-Host ("runbook     : {0} ({1:N0} chars, ~{2:N0} tokens)" -f `
    $Runbook, $runbookText.Length, [math]::Round($runbookText.Length / 3.7))

$seed = @"
Here is the full runbook. Execute Part C.

$runbookText

Start with C0. One powershell command per turn, nothing else.
"@

$messages = @( @{ role = "user"; content = $seed } )

# ── self test ────────────────────────────────────────────────────────────────
if ($SelfTest) {
    Write-Host "`n=== self test (executes nothing) ===" -ForegroundColor Cyan
    $t0 = Get-Date
    $r = Invoke-Agent -Messages $messages
    $secs = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
    $ctx = (ollama show $Model | Select-String 'num_ctx' | Out-String).Trim()
    Write-Host ("prompt      : {0:N0} tokens" -f $r.prompt_eval_count)
    Write-Host ("context     : {0}" -f $ctx)
    if ($r.prompt_eval_count -gt 24000) {
        Write-Warning "Runbook alone uses >24k tokens; little headroom for the run."
    }
    Write-Host ("latency     : ${secs}s at {0:N1} tok/s" -f ($r.eval_count / ($r.eval_duration / 1e9)))
    $cmd = Get-Command-Block $r.message.content
    Write-Host "`n--- model reply ---" -ForegroundColor DarkGray
    Write-Host $r.message.content
    Write-Host "--- extracted command ---" -ForegroundColor DarkGray
    if ($cmd) { Write-Host $cmd -ForegroundColor Green } else { Write-Warning "No powershell block found." }
    if ($cmd -match $script:ForbiddenCommands) {
        Write-Warning "Model proposed an INSTALL command at C0. It would be refused, but review the prompt."
    } elseif ($cmd -match 'check_environment\.py') {
        Write-Host "`nPASS: model started at C0 with the read-only environment check." -ForegroundColor Green
    } else {
        Write-Warning "Model did not start with C0. Review the reply above."
    }

    # adversarial check: hand it the stale setup_report.json and confirm the block holds
    Write-Host "`n=== install-guard test (stale setup_report.json) ===" -ForegroundColor Cyan
    $m2 = $messages + @{ role = "assistant"; content = $r.message.content }
    $m2 += @{ role = "user"; content = (Get-Content (Join-Path $repo "setup_report.json") -Raw) }
    $r2 = Invoke-Agent -Messages $m2
    $cmd2 = Get-Command-Block $r2.message.content
    Write-Host $r2.message.content
    if ($cmd2 -match $script:ForbiddenCommands) {
        Write-Host "model proposed an installer -> DRIVER REFUSES IT (never executed)" -ForegroundColor Yellow
        Write-Host "PASS: hard block is the effective guard." -ForegroundColor Green
    } else {
        Write-Host "PASS: model declined to install on its own." -ForegroundColor Green
    }
    return
}

# ── interactive loop ─────────────────────────────────────────────────────────
Write-Host "`n=== agent loop — nothing runs without your approval ===" -ForegroundColor Cyan
Write-Host "  r = run it    s = skip (type your own note)    q = quit`n"

while ($true) {
    $r = Invoke-Agent -Messages $messages
    $reply = $r.message.content
    $messages += @{ role = "assistant"; content = $reply }

    Write-Host "`n--- agent ---" -ForegroundColor Cyan
    Write-Host $reply
    Write-Host ("[context: {0:N0} tokens used]" -f $r.prompt_eval_count) -ForegroundColor DarkGray
    if ($r.prompt_eval_count -gt 28000) {
        Write-Warning "Approaching the 32k context limit. Consider restarting with a state summary."
    }

    $cmd = Get-Command-Block $reply
    if (-not $cmd) {
        $note = Read-Host "`nNo command proposed. Your reply (or 'q')"
        if ($note -eq 'q') { break }
        $messages += @{ role = "user"; content = $note }
        continue
    }

    # Hard block: installers are never executed, not even with approval. A 7b model
    # will propose one if it is shown anything that looks like evidence the stack is
    # missing (e.g. the stale setup_report.json). Prose in the system prompt is not
    # sufficient to prevent this; this check is.
    if ($cmd -match $script:ForbiddenCommands) {
        Write-Host "`n--- REFUSED (not executed) ---" -ForegroundColor Red
        Write-Host $cmd -ForegroundColor Red
        Write-Host "This command installs software. The toolchain is already built." -ForegroundColor Red
        $messages += @{ role = "user"; content = @"
REFUSED - that command was not executed and never will be.

The solver stack is ALREADY INSTALLED AND VERIFIED: WSL Ubuntu, OpenFOAM v2412 with
the chtMultiRegion solvers, CalculiX 2.21, Gmsh 4.14.0-git, and every required Python
package. check_environment.py prints "READY: full CFD/FEA toolchain available."

If you were shown JSON with "ready": false or "openfoam": null, that is the stale
setup_report.json described in C0. It is a leftover artifact, not evidence, and it
does not override check_environment.py.

Do not propose an installer again. State which runbook step you are on and issue the
next command in the Part C sequence.
"@ }
        continue
    }

    Write-Host "`n--- proposed command ---" -ForegroundColor Yellow
    Write-Host $cmd -ForegroundColor Yellow
    $choice = Read-Host "`n[r]un / [s]kip / [q]uit"
    if ($choice -eq 'q') { break }
    if ($choice -ne 'r') {
        $note = Read-Host "Message to send instead"
        $messages += @{ role = "user"; content = $note }
        continue
    }

    Write-Host "`n--- output ---" -ForegroundColor DarkGray
    $out = try {
        (Invoke-Expression $cmd 2>&1 | Out-String)
    } catch {
        "COMMAND FAILED: $($_.Exception.Message)"
    }
    Write-Host $out

    # keep the feedback message bounded so long solver logs cannot blow the context
    $trimmed = $out
    if ($trimmed.Length -gt 6000) {
        $trimmed = $trimmed.Substring(0, 3000) + "`n...[middle truncated]...`n" +
                   $trimmed.Substring($trimmed.Length - 3000)
    }
    $messages += @{ role = "user"; content = $trimmed }
}

Write-Host "`nSession ended. $($messages.Count) messages." -ForegroundColor Cyan
