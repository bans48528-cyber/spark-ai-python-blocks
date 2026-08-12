param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Test-LocalPort {
    param(
        [string]$Address,
        [int]$PortNumber,
        [int]$TimeoutMilliseconds = 250
    )

    $client = $null
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $connection = $client.BeginConnect($Address, $PortNumber, $null, $null)
        if (-not $connection.AsyncWaitHandle.WaitOne($TimeoutMilliseconds)) {
            return $false
        }
        $client.EndConnect($connection)
        return $true
    } catch {
        return $false
    } finally {
        if ($client -ne $null) {
            $client.Close()
        }
    }
}

function Get-PythonCommand {
    $candidates = @(
        @{ File = "python"; Args = @() },
        @{ File = "py"; Args = @("-3") }
    )

    foreach ($candidate in $candidates) {
        try {
            & $candidate.File @($candidate.Args + @(
                "-c",
                "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
            )) *> $null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
        }
    }

    throw "Python 3.10 or newer was not found. Install Python and make sure python or py is available."
}

function Start-BrowserWhenReady {
    param(
        [string]$Address,
        [int]$PortNumber,
        [string]$TargetUrl
    )

    Start-Job -ArgumentList $Address, $PortNumber, $TargetUrl -ScriptBlock {
        param($Address, $PortNumber, $TargetUrl)

        $deadline = (Get-Date).AddSeconds(15)
        while ((Get-Date) -lt $deadline) {
            $client = $null
            try {
                $client = [System.Net.Sockets.TcpClient]::new()
                $connection = $client.BeginConnect($Address, $PortNumber, $null, $null)
                if ($connection.AsyncWaitHandle.WaitOne(250)) {
                    $client.EndConnect($connection)
                    Start-Process $TargetUrl
                    return
                }
            } catch {
            } finally {
                if ($client -ne $null) {
                    $client.Close()
                }
            }
            Start-Sleep -Milliseconds 300
        }

        Start-Process $TargetUrl
    } | Out-Null
}

$projectRoot = Resolve-ProjectRoot
$serverScript = Join-Path $projectRoot "tools\sparkai_web.py"
$url = ("http://{0}:{1}/generate" -f $HostAddress, $Port)

if (-not (Test-Path $serverScript)) {
    throw ("Cannot find {0}. Make sure the project files are complete." -f $serverScript)
}

Set-Location $projectRoot

if (Test-LocalPort -Address $HostAddress -PortNumber $Port) {
    Write-Host ("Spark AI generator is already running: {0}" -f $url) -ForegroundColor Green
    if (-not $NoBrowser) {
        Start-Process $url
    }
    return
}

$python = Get-PythonCommand

Write-Host "Starting Spark AI generator..." -ForegroundColor Cyan
Write-Host ("Project root: {0}" -f $projectRoot)
Write-Host ("Service URL:  {0}" -f $url)
Write-Host "Close this window to stop the service."
Write-Host ""

if (-not $NoBrowser) {
    Start-BrowserWhenReady -Address $HostAddress -PortNumber $Port -TargetUrl $url
}

& $python.File @($python.Args + @(
    "-u",
    $serverScript,
    "--host",
    $HostAddress,
    "--port",
    [string]$Port
))
