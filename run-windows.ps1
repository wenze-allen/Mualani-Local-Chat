[CmdletBinding()]
param(
    [ValidateSet("auto", "vulkan", "cpu")]
    [string]$Backend = "auto",
    [ValidateSet("", "4b", "9b")]
    [string]$Model = "",
    [ValidateSet("", "short", "long")]
    [string]$ResponseMode = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cli = if ($env:MUALANI_LLAMA_CLI) { $env:MUALANI_LLAMA_CLI } else { Join-Path $Root "bin\llama-cli.exe" }
$DataDir = if ($env:MUALANI_DATA_DIR) { $env:MUALANI_DATA_DIR } else { Join-Path $Root "data" }
$Preferences = if ($env:MUALANI_PREFERENCES_FILE) { $env:MUALANI_PREFERENCES_FILE } else { Join-Path $DataDir "preferences.conf" }

function Find-Model([string]$Key, [string]$Override) {
    if ($Override -and (Test-Path -LiteralPath $Override -PathType Leaf)) {
        return (Resolve-Path -LiteralPath $Override).Path
    }
    $Directory = Join-Path $Root "models\$Key"
    $Found = Get-ChildItem -LiteralPath $Directory -Filter *.gguf -File -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -First 1
    if ($Found) { return $Found.FullName }
    return ""
}

if (-not (Test-Path -LiteralPath $Cli -PathType Leaf)) {
    throw "Runtime binary not found: $Cli"
}
$Model4B = Find-Model "4b" $env:MUALANI_MODEL_4B
$Model9B = Find-Model "9b" $env:MUALANI_MODEL_9B
if (-not $Model4B -and -not $Model9B) {
    throw "No GGUF model was found. Put a model in models\4b or models\9b."
}

New-Item -ItemType Directory -Force -Path (Join-Path $DataDir "sessions") | Out-Null
$LastModel = "9b"
$LastResponseMode = "short"
if (Test-Path -LiteralPath $Preferences -PathType Leaf) {
    foreach ($Line in Get-Content -LiteralPath $Preferences) {
        if ($Line -eq "model=4b" -or $Line -eq "model=9b") { $LastModel = $Line.Substring(6) }
        if ($Line -eq "response_mode=short" -or $Line -eq "response_mode=long") { $LastResponseMode = $Line.Substring(14) }
    }
}
if (-not $Model) { $Model = if ($env:MUALANI_START_MODEL) { $env:MUALANI_START_MODEL } else { $LastModel } }
if (-not $ResponseMode) { $ResponseMode = if ($env:MUALANI_RESPONSE_MODE) { $env:MUALANI_RESPONSE_MODE } else { $LastResponseMode } }
if ($Model -eq "4b" -and -not $Model4B) { $Model = "9b" }
if ($Model -eq "9b" -and -not $Model9B) { $Model = "4b" }

if ($Backend -eq "auto") {
    $DeviceText = (& $Cli --list-devices 2>&1 | Out-String)
    $Backend = if ($DeviceText -match "(?i)vulkan") { "vulkan" } else { "cpu" }
}
$GpuLayers = if ($Backend -eq "vulkan") { 99 } else { 0 }

$RamGiB = [Math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$MemoryGiB = $RamGiB
if ($Backend -eq "vulkan") {
    if ($env:MUALANI_VRAM_GIB) {
        $MemoryGiB = [int]$env:MUALANI_VRAM_GIB
    } else {
        $Reported = Get-CimInstance Win32_VideoController | ForEach-Object { [Math]::Floor($_.AdapterRAM / 1GB) } | Measure-Object -Maximum
        $MemoryGiB = [Math]::Max(0, [int]$Reported.Maximum)
    }
}

if ($Backend -eq "vulkan") {
    if ($MemoryGiB -lt 6) { $Ctx4B = 16384; $Ctx9B = 4096 }
    elseif ($MemoryGiB -lt 8) { $Ctx4B = 32768; $Ctx9B = 4096 }
    elseif ($MemoryGiB -lt 12) { $Ctx4B = 65536; $Ctx9B = 16384 }
    elseif ($MemoryGiB -lt 16) { $Ctx4B = 131072; $Ctx9B = 65536 }
    elseif ($MemoryGiB -lt 24) { $Ctx4B = 196608; $Ctx9B = 131072 }
    else { $Ctx4B = 262144; $Ctx9B = 262144 }
} else {
    if ($MemoryGiB -lt 8) { $Ctx4B = 8192; $Ctx9B = 4096 }
    elseif ($MemoryGiB -lt 12) { $Ctx4B = 16384; $Ctx9B = 4096 }
    elseif ($MemoryGiB -lt 16) { $Ctx4B = 32768; $Ctx9B = 16384 }
    elseif ($MemoryGiB -lt 24) { $Ctx4B = 65536; $Ctx9B = 32768 }
    elseif ($MemoryGiB -lt 32) { $Ctx4B = 131072; $Ctx9B = 65536 }
    else { $Ctx4B = 262144; $Ctx9B = 131072 }
}
if ($env:MUALANI_CTX_4B) { $Ctx4B = [int]$env:MUALANI_CTX_4B }
if ($env:MUALANI_CTX_9B) { $Ctx9B = [int]$env:MUALANI_CTX_9B }
$SelectedModel = if ($Model -eq "4b") { $Model4B } else { $Model9B }
$Context = if ($Model -eq "4b") { $Ctx4B } else { $Ctx9B }

$env:LLAMA_CLI_SESSION_DIR = Join-Path $DataDir "sessions"
$env:LLAMA_CLI_PREFERENCES_FILE = $Preferences
$env:LLAMA_CLI_CURRENT_MODEL = $Model
$env:LLAMA_CLI_RESPONSE_MODE = $ResponseMode
$env:LLAMA_CLI_CTX_4B = "$Ctx4B"
$env:LLAMA_CLI_CTX_9B = "$Ctx9B"
$env:LLAMA_CLI_CHARACTER_CARDS_DIR = Join-Path $Root "app\cards\characters"
$env:LLAMA_CLI_CHARACTER_CARD_DEFAULTS = "traveler"
$env:LLAMA_CLI_RELATIONSHIP_CARDS_DIR = Join-Path $Root "app\cards\relationships"
$env:LLAMA_CLI_RELATIONSHIP_INDEX_FILE = Join-Path $Root "app\cards\relationships\runtime_index.json"
$env:LLAMA_CLI_WORLD_LORE_CARDS_DIR = Join-Path $Root "app\cards\world"
if ($Model4B) { $env:LLAMA_CLI_MODEL_4B = $Model4B }
if ($Model9B) { $env:LLAMA_CLI_MODEL_9B = $Model9B }

$Threads = if ($env:MUALANI_THREADS) { [int]$env:MUALANI_THREADS } else { [Math]::Min(8, [Environment]::ProcessorCount) }
Write-Host "Starting $Model model in $ResponseMode mode ($Backend backend, $Context-token context)."

$Arguments = @(
    "--model", $SelectedModel,
    "--system-prompt-file", (Join-Path $Root "app\prompts\mualani_system_prompt_zh.txt"),
    "--conversation", "--color", "on",
    "--reasoning", "off", "--reasoning-format", "deepseek",
    "--chat-template-kwargs", '{"enable_thinking":false}',
    "--ctx-size", "$Context", "--predict", "2048",
    "--n-gpu-layers", "$GpuLayers", "--flash-attn", "auto",
    "--threads", "$Threads", "--threads-batch", "$Threads",
    "--temp", "0.55", "--top-p", "0.85", "--min-p", "0.05",
    "--repeat-last-n", "128", "--repeat-penalty", "1.08",
    "--logit-bias", "248046-1.5"
)
if ($ExtraArgs) { $Arguments += $ExtraArgs }
& $Cli @Arguments
exit $LASTEXITCODE
