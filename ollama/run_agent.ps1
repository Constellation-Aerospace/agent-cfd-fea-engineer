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

.PARAMETER AutoApprove
    Unattended mode for environments with no interactive console (Read-Host would
    otherwise block forever): every proposed command is executed without a keystroke.
    The installer hard-block (see $ForbiddenCommands) still applies unconditionally --
    this switch removes the approval prompt, not the safety guard. Supervision moves
    from per-command approval to reviewing -TranscriptPath afterward (or tailing it
    live) plus the runbook's own verification gates. Stops after -MaxTurns turns, or
    immediately if the model proposes no command for two turns in a row (treated as
    "done or stuck", since there's no operator to type a note and continue it).

.PARAMETER MaxTurns
    Safety cap on turns in -AutoApprove mode. Default 200 -- generous headroom for a
    ~9-step runbook with 8 restart segments, but bounded so a confused model can't loop
    forever unattended.

.PARAMETER TranscriptPath
    In -AutoApprove mode, append every turn (model reply, proposed command, real
    output) to this file as it happens, in addition to the console. Omit to log to
    console only.

.EXAMPLE
    .\ollama\run_agent.ps1 -SelfTest
    .\ollama\run_agent.ps1
    .\ollama\run_agent.ps1 -AutoApprove -Runbook OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_ETP_COPPER.md -TranscriptPath ollama\transcripts\run1.log
#>
[CmdletBinding()]
param(
    [string]$Model = "cfd-qwen",
    [string]$Endpoint = "http://127.0.0.1:11434",
    [string]$Runbook = "OLLAMA_QWEN_TRANSIENT_RUNBOOK.md",
    [string]$KeepAlive = "30m",
    [switch]$SelfTest,
    [switch]$AutoApprove,
    [int]$MaxTurns = 200,
    [string]$TranscriptPath = ""
)

function Write-Transcript {
    param([string]$Text)
    if (-not $TranscriptPath) { return }
    # A concurrent reader (e.g. a `tail -f`-style monitor) can transiently lock the
    # file on Windows. Retry rather than letting $ErrorActionPreference="Stop" abort
    # the whole unattended run over a log-write race.
    for ($i = 0; $i -lt 5; $i++) {
        try {
            Add-Content -Path $TranscriptPath -Value $Text -ErrorAction Stop
            return
        } catch {
            Start-Sleep -Milliseconds 200
        }
    }
    Write-Warning "Could not write to transcript after 5 retries: $TranscriptPath"
}

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# Commands this driver will never execute, regardless of operator approval.
$script:ForbiddenCommands =
    'install_solvers|setup\.ps1|first_run_setup|\bapt(-get)?\s+install|\bpip\s+install|winget\s+install|choco\s+install'

# Command output patterns that are documented, expected, non-fatal warnings on this
# repo's CAD family -- a small model reliably misreads these as "something to fix"
# and invents nonexistent remediation scripts instead of proceeding (observed 3x on
# the checkMesh warning specifically). Rather than let it discover that the hard way
# and then try to nudge it back afterward, inject the clarification into the SAME
# turn's output, before the model ever forms an opinion about what to do next.
$script:KnownBenignWarnings = @(
    @{
        Pattern = 'checkMesh reported failures'
        Note    = @"
[DRIVER NOTE -- read before deciding the next step] This checkMesh WARNING (ok: false,
high-aspect-ratio and/or non-orthogonality flags, but no FOAM FATAL ERROR) is a known,
already-documented, EXPECTED result for this CAD file (a ~3e-9 m^2 sliver face -- see
the runbook's own C-FPE / mesh notes). It is not a new problem. Do not fix, refine,
regenerate, or inspect the mesh further because of it -- there is no
fix_mesh_regions.py, refine_mesh.py, or smooth_mesh.py in this repo, and none is
needed. Proceed immediately to the NEXT DIFFERENT command that is explicitly written
in the runbook's Part C.
"@
    }
)

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
    if (-not $m.Success) { return $null }
    $block = $m.Groups[1].Value.Trim()
    # The model sometimes echoes the bare runbook step id as its own line inside the
    # fenced block (e.g. "C0" before the real command) instead of only in prose.
    # $ErrorActionPreference="Stop" turns "C0" into a terminating "not recognized"
    # error that aborts the whole block before the real command ever runs -- strip a
    # leading bare step-id line. Anchored to require a digit/slash/dash right after
    # "C" so real commands starting with C (Copy-Item, ...) are never touched.
    $block = $block -replace '(?s)^C(\d+[\w/-]*|-[A-Za-z]+)\s*\r?\n', ''
    $block = $block.Trim()

    # The model sometimes writes a plain-English acknowledgment/description INSIDE
    # the fenced block instead of only in prose outside it (e.g. "The checkMesh
    # WARNING is expected, proceed." or "Restage to the exact 40000m dwell state."
    # as the first line, with the real command below it). PowerShell then tries to
    # run that sentence as a command -- best case "term not recognized", worst case
    # an unterminated string (an apostrophe like "file's" starts a string literal
    # that's never closed) -- either way the real command on the next line never
    # executes. Strip leading lines that look like English sentences rather than
    # PowerShell code, stopping at the first line that looks like real code.
    $isCodeLine = {
        param($l)
        $l -match '[$\\]|--\w|\.(py|exe|ps1|json)\b|^\s*[&#]|^\s*(Get|Set|New|Copy|Remove|Select|Test|Invoke|Write|Import|Export|Move|Rename|Start|Stop|Add|Join)-\w'
    }
    $lines = $block -split "`r?`n"
    $start = 0
    while ($start -lt $lines.Count) {
        $l = $lines[$start].Trim()
        if ($l -eq '') { $start++; continue }
        if (& $isCodeLine $l) { break }
        if ($l -match '^[A-Z][a-z]') { $start++; continue }  # looks like an English sentence
        break  # anything else (e.g. a bare identifier) -- stop stripping, don't guess further
    }
    if ($start -ge $lines.Count) {
        $block = ''  # the whole block was prose, no command in it -- correctly "no command"
    } elseif ($start -gt 0) {
        $block = ($lines[$start..($lines.Count - 1)] -join "`n").Trim()
    }

    # Windows PowerShell 5.1 strips embedded double-quotes from single-quoted
    # arguments when it reconstructs argv for a NATIVE executable (a documented 5.1
    # quirk, fixed in PS7's $PSNativeCommandArgumentPassing='Standard' but that
    # preference doesn't exist in 5.1). '--solver '{"mode":"transient"}'' silently
    # arrives at python.exe as {mode:transient} -- invalid JSON, and the resulting
    # traceback's first stderr line becomes a terminating NativeCommandError under
    # $ErrorActionPreference="Stop", masking the real cause. Every runbook in this
    # repo writes JSON args this way (--bc/--overrides/--solver), so auto-escape
    # embedded quotes inside single-quoted {...} argument segments before execution,
    # regardless of how the model itself formatted them.
    $block = [regex]::Replace($block, "'(\{[^']*\})'", {
        param($m)
        $inner = $m.Groups[1].Value -replace '(?<!\\)"', '\"'
        "'$inner'"
    })
    return $block
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

# ── unattended loop ──────────────────────────────────────────────────────────
if ($AutoApprove) {
    if ($TranscriptPath) {
        $dir = Split-Path -Parent $TranscriptPath
        if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
        $header = "=== $(Get-Date -Format s) — $Model driving $Runbook, AutoApprove ==="
        $created = $false
        for ($i = 0; $i -lt 5 -and -not $created; $i++) {
            try { Set-Content -Path $TranscriptPath -Value $header -ErrorAction Stop; $created = $true }
            catch { Start-Sleep -Milliseconds 200 }
        }
        if (-not $created) { throw "Could not create transcript file after 5 retries: $TranscriptPath (locked by another process?)" }
    }
    Write-Host "`n=== agent loop (AutoApprove) — every proposed command runs unattended ===" -ForegroundColor Cyan
    Write-Host "installer hard-block still active; max $MaxTurns turns; stops after 2 consecutive no-command turns`n"

    $noCommandStreak = 0
    $cmdHistory = New-Object System.Collections.Generic.List[string]
    for ($turn = 1; $turn -le $MaxTurns; $turn++) {
        $r = Invoke-Agent -Messages $messages
        $reply = $r.message.content
        $messages += @{ role = "assistant"; content = $reply }

        $turnHeader = "`n--- turn $turn/$MaxTurns [context: $($r.prompt_eval_count) tokens] ---"
        Write-Host $turnHeader -ForegroundColor Cyan
        Write-Host $reply
        Write-Transcript "$turnHeader`n$reply"

        if ($r.prompt_eval_count -gt 28000) {
            Write-Warning "Approaching the 32k context limit. Consider restarting with a state summary."
        }

        $cmd = Get-Command-Block $reply
        if (-not $cmd) {
            $noCommandStreak++
            Write-Host "(no command proposed — streak $noCommandStreak/2)" -ForegroundColor DarkYellow
            Write-Transcript "(no command proposed — streak $noCommandStreak/2)"
            if ($noCommandStreak -ge 2) {
                Write-Host "`nTwo turns with no proposed command — stopping (done, or stuck)." -ForegroundColor Yellow
                break
            }
            $messages += @{ role = "user"; content = "State the current step id and issue the next command in a fenced powershell block. If the runbook is complete, say so explicitly." }
            continue
        }
        $noCommandStreak = 0

        if ($cmd -match $script:ForbiddenCommands) {
            Write-Host "`n--- REFUSED (not executed) ---" -ForegroundColor Red
            Write-Host $cmd -ForegroundColor Red
            Write-Transcript "--- REFUSED (not executed) ---`n$cmd"
            $messages += @{ role = "user"; content = @"
REFUSED - that command was not executed and never will be.

The solver stack is ALREADY INSTALLED AND VERIFIED: WSL Ubuntu, OpenFOAM v2412 with
the chtMultiRegion solvers, CalculiX 2.21, Gmsh 4.14.0-git, and every required Python
package. check_environment.py prints "READY: full CFD/FEA toolchain available."

Do not propose an installer again. State which runbook step you are on and issue the
next command in the Part C sequence.
"@ }
            continue
        }

        # Loop guard: a small model re-reading a non-fatal warning (e.g. a known,
        # expected checkMesh warning) can cycle through 2-3 distinct commands
        # (re-inspect the log, re-run the step, re-inspect again) without ever
        # repeating one back-to-back -- a same-as-last-turn check misses that. Instead
        # count how many times this exact command already appears in recent history.
        $occurrences = ($cmdHistory | Where-Object { $_ -eq $cmd }).Count
        $cmdHistory.Add($cmd)
        if ($cmdHistory.Count -gt 8) { $cmdHistory.RemoveAt(0) }

        if ($occurrences -ge 3) {
            Write-Host "`n--- STOPPING: this command has now recurred $($occurrences + 1) times in recent history (stuck in a cycle) ---" -ForegroundColor Red
            Write-Transcript "--- STOPPING: command recurred $($occurrences + 1) times in recent history ---`n$cmd"
            break
        }
        if ($occurrences -ge 1) {
            Write-Host "`n--- SKIPPED (this command already ran recently; not re-run) ---" -ForegroundColor DarkYellow
            Write-Host $cmd -ForegroundColor DarkYellow
            Write-Transcript "--- SKIPPED (already ran recently) ---`n$cmd"
            $messages += @{ role = "user"; content = @"
SKIPPED - this exact command already ran within the last few turns and its output was
already shown to you. Running it again will not produce new information, and you appear
to be cycling between a small set of commands instead of progressing.

Do not try to fix, refine, patch, or regenerate the mesh, geometry, or any file that a
prior command's WARNING referred to, unless the runbook explicitly instructs a fix. A
checkMesh WARNING (as opposed to a FOAM FATAL ERROR) on this CAD is a known, documented,
expected result -- inspecting it once is enough. Re-inspecting it, or inventing a
mesh-refinement step that is not written in the runbook, is not part of Part C.

State the current step id and issue the NEXT command that is actually written in the
runbook's Part C -- copy it from the runbook text you were given, don't improvise one.
"@ }
            continue
        }

        Write-Host "`n--- executing ---" -ForegroundColor Yellow
        Write-Host $cmd -ForegroundColor Yellow
        Write-Transcript "--- executing ---`n$cmd"

        $out = try {
            (Invoke-Expression $cmd 2>&1 | Out-String)
        } catch {
            "COMMAND FAILED: $($_.Exception.Message)"
        }
        Write-Host "`n--- output ---" -ForegroundColor DarkGray
        Write-Host $out
        Write-Transcript "--- output ---`n$out"

        $trimmed = $out
        if ($trimmed.Length -gt 6000) {
            $trimmed = $trimmed.Substring(0, 3000) + "`n...[middle truncated]...`n" +
                       $trimmed.Substring($trimmed.Length - 3000)
        }
        foreach ($kw in $script:KnownBenignWarnings) {
            if ($out -match $kw.Pattern) {
                $trimmed += "`n`n$($kw.Note)"
                Write-Transcript "(known-benign-warning note injected: $($kw.Pattern))"
                break
            }
        }
        $messages += @{ role = "user"; content = $trimmed }
    }

    Write-Host "`nAutoApprove session ended. $($messages.Count) messages, $turn turns." -ForegroundColor Cyan
    Write-Transcript "`n=== $(Get-Date -Format s) — session ended, $($messages.Count) messages ==="
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
    foreach ($kw in $script:KnownBenignWarnings) {
        if ($out -match $kw.Pattern) {
            $trimmed += "`n`n$($kw.Note)"
            break
        }
    }
    $messages += @{ role = "user"; content = $trimmed }
}

Write-Host "`nSession ended. $($messages.Count) messages." -ForegroundColor Cyan
