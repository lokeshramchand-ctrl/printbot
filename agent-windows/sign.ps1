# Authenticode-signs dist\PrintBotAgent.exe and timestamps it.
#   Release: set PRINTBOT_SIGN_PFX (path) and PRINTBOT_SIGN_PASSWORD -> signs with your real code-signing cert.
#   Dev:     otherwise creates/reuses a self-signed cert "PrintBot Dev" (CurrentUser store). The exe is then
#            validly signed but only trusted on machines that import dev-cert.cer; SmartScreen still warns elsewhere.
$ErrorActionPreference = "Stop"
$exe = Join-Path $PSScriptRoot "dist\PrintBotAgent.exe"
$ts = "http://timestamp.digicert.com"

if ($env:PRINTBOT_SIGN_PFX) {
    $pw = ConvertTo-SecureString $env:PRINTBOT_SIGN_PASSWORD -AsPlainText -Force
    $cert = Get-PfxCertificate -FilePath $env:PRINTBOT_SIGN_PFX -Password $pw
    $mode = "release"
} else {
    $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -eq "CN=PrintBot Dev" -and $_.NotAfter -gt (Get-Date) } | Select-Object -First 1
    if (-not $cert) {
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=PrintBot Dev" -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(3)
    }
    Export-Certificate -Cert $cert -FilePath (Join-Path $PSScriptRoot "dev-cert.cer") | Out-Null
    $mode = "self-signed dev"
}

$r = Set-AuthenticodeSignature -FilePath $exe -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $ts
if ($r.SignerCertificate -eq $null) { throw "Signing failed: $($r.StatusMessage)" }
Write-Host "Signed ($mode): $exe  [$($r.Status)] $($cert.Subject)"
