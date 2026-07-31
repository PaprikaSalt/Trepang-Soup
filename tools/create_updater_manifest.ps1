param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,

    [string]$Notes = "New features and stability improvements.",
    [string]$Repository = "PaprikaSalt/Trepang-Soup",
    [string]$OutputPath = "latest.json"
)

$resolvedInstaller = Resolve-Path -LiteralPath $InstallerPath -ErrorAction Stop
$signaturePath = "$($resolvedInstaller.Path).sig"
if (-not (Test-Path -LiteralPath $signaturePath -PathType Leaf)) {
    throw "Updater signature not found: $signaturePath"
}

# GitHub normalizes spaces and other unsupported asset-name characters to dots.
$assetName = [IO.Path]::GetFileName($resolvedInstaller.Path) -replace '[^A-Za-z0-9._-]', '.'
$assetName = [Uri]::EscapeDataString($assetName)
$downloadUrl = "https://github.com/$Repository/releases/download/v$Version/$assetName"
$manifest = [ordered]@{
    version = $Version
    notes = $Notes
    pub_date = (Get-Date).ToUniversalTime().ToString("o")
    platforms = [ordered]@{
        "windows-x86_64" = [ordered]@{
            signature = (Get-Content -Raw -LiteralPath $signaturePath).Trim()
            url = $downloadUrl
        }
    }
}

$json = $manifest | ConvertTo-Json -Depth 5
# Windows PowerShell's utf8 mode adds a BOM, which some strict JSON clients reject.
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath), $json, [Text.UTF8Encoding]::new($false))
Write-Host "Created $OutputPath"
