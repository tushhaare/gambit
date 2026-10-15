# KahaniFM DEV Agent — one command setup + run (Windows PowerShell)
# Ye script: Python check/install -> agent download -> Chrome (ChatGPT) kholna -> agent chalana.
# Har din naya team link ho to dashboard se naya command copy karke yahi chalao.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Hub   = "{{ hub }}"
$Key   = "{{ key }}"
$Name  = "{{ name }}"
$Ver   = "{{ v }}"
$Home2 = Join-Path $env:LOCALAPPDATA "KahaniFM-Agent-DEV"   # DEV: purane agent se alag
$Out   = Join-Path ([Environment]::GetFolderPath("Desktop")) "KahaniFM Outputs DEV"

function Say($t, $c = "White") { Write-Host $t -ForegroundColor $c }
$Total = [Diagnostics.Stopwatch]::StartNew()

# ---------- live timer: lamba kaam background mein chalao, yahan progress + time dikhao ----------
function Fmt($sec) { $sec = [int][math]::Max(0, $sec); "{0}:{1:00}" -f [int][math]::Floor($sec / 60), ($sec % 60) }
function Run-Timed($label, $key, [int]$est, $exe, [string[]]$argv) {
  # pichli baar jitna time laga tha, wahi estimate (warna default)
  $tfile = Join-Path $Home2 "time_$key.txt"
  try { $prev = [int](Get-Content $tfile -ErrorAction Stop); if ($prev -gt 5) { $est = [int]($prev * 1.1) } } catch {}
  $log = Join-Path $env:TEMP ("kfm_" + [guid]::NewGuid().ToString("N") + ".log")
  $argStr = ($argv | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join " "
  Say ("  " + $label + "  (andaazan " + (Fmt $est) + " min)") Cyan
  try {
    $p = Start-Process -FilePath $exe -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError "$log.err" -NoNewWindow -PassThru
  } catch { Say ("  Shuru nahi hua: " + $_) Red; return 1 }
  $null = $p.Handle   # exit code sahi milne ke liye
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $spin = "|/-\"; $i = 0
  $w = 79; try { $w = [Console]::WindowWidth - 1 } catch {}
  if ($w -lt 40) { $w = 79 }
  if ($w -gt 140) { $w = 140 }
  while (-not $p.HasExited) {
    $el  = $sw.Elapsed.TotalSeconds
    $pct = [math]::Min(97, [int](100 * $el / [math]::Max(1, $est)))
    $bar = ("#" * [int]($pct / 5)).PadRight(20, ".")
    $left = if ($el -lt $est) { "~" + (Fmt ($est - $el)) + " baaki" } else { "thoda aur... chal raha hai" }
    $now = ""
    try {
      $ln = Get-Content $log -Tail 3 -ErrorAction SilentlyContinue | Where-Object { $_.Trim() } | Select-Object -Last 1
      if ($ln) {
        $ln = $ln.Trim()
        if ($ln -match "Downloading\s+(\S+?)-\d.*?\(([^)]+)\)") { $now = "download: " + $Matches[1] + " (" + $Matches[2] + ")" }
        elseif ($ln -match "^Collecting\s+(\S+)") { $now = "dhoondh raha: " + $Matches[1] }
        elseif ($ln -match "^Installing collected") { $now = "install ho raha hai..." }
        else { $now = $ln }
      }
    } catch {}
    $line = "  {0} [{1}] {2,3}%  {3} beeta | {4}" -f $spin[$i % 4], $bar, $pct, (Fmt $el), $left
    if ($now) { $line += " | " + $now }
    if ($line.Length -gt $w) { $line = $line.Substring(0, $w) }
    Write-Host ("`r" + $line.PadRight($w)) -NoNewline -ForegroundColor DarkCyan
    $i++; Start-Sleep -Milliseconds 500
  }
  $p.WaitForExit()
  $took = $sw.Elapsed.TotalSeconds
  Write-Host ("`r" + "".PadRight($w)) -NoNewline
  $code = $p.ExitCode
  if ($code -eq 0) {
    Write-Host ("`r  [####################] 100%  " + (Fmt $took) + " mein ho gaya") -ForegroundColor Green
    try { Set-Content $tfile ([int]$took) } catch {}
  } else {
    Write-Host ("`r  Fail (code " + $code + ") " + (Fmt $took) + " baad. Aakhri lines:") -ForegroundColor Red
    Get-Content "$log.err", $log -Tail 6 -ErrorAction SilentlyContinue | ForEach-Object { Say ("    " + $_) DarkGray }
  }
  Remove-Item $log, "$log.err" -ErrorAction SilentlyContinue
  return $code
}

Say ""
Say "  KahaniFM DEV Agent (test version) — $Name" Yellow
Say "  Hub: $Hub"
Say ""
New-Item -ItemType Directory -Force -Path $Home2, $Out | Out-Null

# ---------- 1. Python ----------
function Find-Py {
  $cands = @()
  $cands += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
  $cands += Get-ChildItem "C:\Program Files\Python3*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
  $cands += "py", "python"
  foreach ($c in $cands) {
    try {
      $v = & $c -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
      if ($LASTEXITCODE -eq 0 -and $v -and ([version]$v -ge [version]"3.9")) { return $c }
    } catch {}
  }
  return $null
}
$py = Find-Py
if (-not $py) {
  Say "[1/4] Python nahi mila — install kar raha hoon (sirf pehli baar)..." Cyan
  $null = Run-Timed "Python 3.12 install" "python" 180 "winget" @("install", "-e", "--id", "Python.Python.3.12", "--scope", "user", "--silent", "--accept-package-agreements", "--accept-source-agreements")
  $py = Find-Py
  if (-not $py) {
    Say "Python install nahi ho paya. https://www.python.org/downloads/ se install karo ('Add to PATH' tick), phir ye command dobara chalao." Red
    Read-Host "Enter dabao"; return
  }
}
Say "[1/4] Python ready" Green

# ---------- 2. Agent files + packages ----------
$venv = Join-Path $Home2 "venv"
$vpy  = Join-Path $venv "Scripts\python.exe"
$newVenv = -not (Test-Path $vpy)
if ($newVenv) {
  Say "[2/4] Agent ka alag Python folder (venv) ban raha hai..." Cyan
  $null = Run-Timed "venv" "venv" 25 $py @("-m", "venv", $venv)
}
foreach ($f in @("agent.py", "engine_browser.py", "imgconv.py")) {
  Invoke-WebRequest -UseBasicParsing "$Hub/agent/files/$f" -OutFile (Join-Path $Home2 $f) -Headers @{ "ngrok-skip-browser-warning" = "1" }
}
# packages sirf tab jab list badle (har tool update pe dobara nahi)
$Deps   = "requests playwright pillow | v1"
$marker = Join-Path $Home2 "deps.ok"
if (-not (Test-Path $marker) -or ((Get-Content $marker -ErrorAction SilentlyContinue) -ne $Deps)) {
  Say "[2/4] Packages install ho rahe hain (sirf pehli baar)..." Cyan
  if ($newVenv) { $null = Run-Timed "pip update" "pip" 20 $vpy @("-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off", "--upgrade", "pip") }
  $rc = Run-Timed "requests + playwright + pillow" "deps" 120 $vpy @("-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off", "requests", "playwright", "pillow")
  if ($rc -ne 0) { Say "Packages install fail. Internet check karo aur dobara chalao." Red; Read-Host "Enter dabao"; return }
  Set-Content $marker $Deps
}
Say "[2/4] Agent ready" Green

$cfgJson = @{ hub_url = $Hub; agent_key = $Key; name = $Name; cdp_url = "http://localhost:9223"; output_dir = $Out } | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $Home2 "agent.json"), $cfgJson, (New-Object System.Text.UTF8Encoding $false))

# ---------- 3. Chrome (ChatGPT) ----------
$cdpOk = $false
try { Invoke-WebRequest -UseBasicParsing "http://localhost:9223/json/version" -TimeoutSec 2 | Out-Null; $cdpOk = $true } catch {}
if (-not $cdpOk) {
  $chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
              "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
              "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
              "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
              "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $chrome) { Say "Google Chrome nahi mila. Chrome install karke dobara chalao." Red; Read-Host "Enter dabao"; return }
  $chromeProf = Join-Path $Home2 "chrome-profile"
  Start-Process $chrome -ArgumentList "--remote-debugging-port=9223", "--user-data-dir=`"$chromeProf`"", "--no-first-run", "https://chatgpt.com/"
  Start-Sleep -Seconds 4
  $first = Join-Path $Home2 "login.ok"
  if (-not (Test-Path $first)) {
    Say ""
    Say "[3/4] Ek naya Chrome khula hai. Usme ChatGPT pe LOGIN karo (sirf pehli baar)." Yellow
    Read-Host "      Login ho jaaye to yahan Enter dabao"
    Set-Content $first "ok"
  }
}
Say "[3/4] Chrome + ChatGPT ready" Green

# ---------- 4. Run ----------
Say ("      Setup time: " + (Fmt $Total.Elapsed.TotalSeconds) + " min") DarkGray
Say "[4/4] Agent chalu — ye window KHULI rakho. Images yahan bhi save hongi:" Green
Say "      $Out" White
Say ""
Set-Location $Home2
& $vpy (Join-Path $Home2 "agent.py")
