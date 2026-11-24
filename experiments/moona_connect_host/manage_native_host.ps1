[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)]
    [ValidateSet('Install', 'Uninstall')]
    [string]$Action,

    [ValidatePattern('(?-i)^[a-p]{32}$')]
    [string]$ExtensionId
)

$ErrorActionPreference = 'Stop'
if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA no está disponible.' }

$hostName = 'com.moona.connect'
$directory = Join-Path $env:LOCALAPPDATA 'MOONA\Connect'
$manifestPath = Join-Path $directory "$hostName.json"
$databasePath = Join-Path $directory 'indicators.db'
$registryPath = "Software\Google\Chrome\NativeMessagingHosts\$hostName"
$registry = [Microsoft.Win32.Registry]::CurrentUser
$currentKey = $registry.OpenSubKey($registryPath)
if ($currentKey) {
    try {
        if ($currentKey.GetValue('') -ne $manifestPath) {
            throw 'El nombre del host está registrado con otro manifiesto.'
        }
    } finally {
        $currentKey.Dispose()
    }
}

if ($Action -eq 'Install') {
    if (-not $ExtensionId) { throw 'Indica el ID de MOONA Connect que aparece en chrome://extensions.' }
    $repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
    $expectedExe = Join-Path $repo '.moona-connect-build\dist\moona-connect-host\moona-connect-host.exe'
    $exe = (Resolve-Path -LiteralPath $expectedExe).Path
    $manifest = @{
        name = $hostName
        description = 'Host local de MOONA Connect'
        path = $exe
        type = 'stdio'
        allowed_origins = @("chrome-extension://$ExtensionId/")
    } | ConvertTo-Json

    if ($PSCmdlet.ShouldProcess("HKCU\$registryPath", "Registrar el host para $ExtensionId")) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        [IO.File]::WriteAllText($manifestPath, $manifest, [Text.UTF8Encoding]::new($false))
        $key = $registry.CreateSubKey($registryPath)
        try {
            $key.SetValue('', $manifestPath, [Microsoft.Win32.RegistryValueKind]::String)
        } finally {
            $key.Dispose()
        }
    }
} elseif ($PSCmdlet.ShouldProcess("HKCU\$registryPath", 'Quitar registro, manifiesto y datos locales de MOONA Connect')) {
    $registry.DeleteSubKey($registryPath, $false)
    foreach ($file in @($manifestPath, $databasePath, "$databasePath-journal")) {
        if (Test-Path -LiteralPath $file -PathType Leaf) {
            Remove-Item -LiteralPath $file
        }
    }
}
