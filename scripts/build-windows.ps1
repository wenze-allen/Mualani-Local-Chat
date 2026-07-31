[CmdletBinding()]
param([string]$Configuration = "Release")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Source = if ($env:MUALANI_SOURCE_DIR) { $env:MUALANI_SOURCE_DIR } else { Join-Path $Root ".build\llama.cpp" }
$Build = if ($env:MUALANI_BUILD_DIR) { $env:MUALANI_BUILD_DIR } else { Join-Path $Root ".build\windows-x64" }
$Stage = Join-Path $Root "dist\Mualani-Local-Chat-windows-x64"
$Commit = "e9fa0781f1c25fc4fe8c86be1edc6970661ad6f0"

if (-not (Test-Path -LiteralPath (Join-Path $Source ".git"))) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Source) | Out-Null
    git init $Source
    git -C $Source remote add origin https://github.com/ggml-org/llama.cpp.git
    git -C $Source fetch --depth=1 origin $Commit
    git -C $Source checkout --detach FETCH_HEAD
}
$Current = (git -C $Source rev-parse HEAD).Trim()
if ($Current -ne $Commit) { throw "Unexpected upstream checkout: $Current" }
Copy-Item -Path (Join-Path $Root "overlay\*") -Destination $Source -Recurse -Force

cmake -S $Source -B $Build -A x64 `
    -DBUILD_SHARED_LIBS=OFF `
    -DGGML_NATIVE=OFF `
    -DGGML_VULKAN=ON `
    -DMUALANI_TEXT_ONLY=ON
cmake --build $Build --config $Configuration --target llama-cli --parallel

if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "bin"), (Join-Path $Stage "models\4b"), (Join-Path $Stage "models\9b") | Out-Null
Copy-Item -LiteralPath (Join-Path $Build "bin\$Configuration\llama-cli.exe") -Destination (Join-Path $Stage "bin")
Copy-Item -LiteralPath (Join-Path $Root "app") -Destination $Stage -Recurse
Copy-Item -LiteralPath (Join-Path $Root "licenses") -Destination $Stage -Recurse
Copy-Item -LiteralPath (Join-Path $Root "run-windows.ps1") -Destination $Stage
Copy-Item -LiteralPath (Join-Path $Root "README.md"), (Join-Path $Root "README.zh-CN.md"), (Join-Path $Root "LICENSE"), (Join-Path $Root "THIRD_PARTY_NOTICES.md"), (Join-Path $Root "SOURCES.md") -Destination $Stage
Write-Host "Windows package staged at $Stage"
