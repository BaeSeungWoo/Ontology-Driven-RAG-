# Native Caddy launcher for the Windows host where IIS already owns 80 and 443.
# Caddy does not read .env, so the values live in the process environment.
# Fill in the placeholders, keep this file out of source control if you do.

$env:VOICE_DOMAIN      = 'voice.example.com'
$env:VOICE_HTTPS_PORT  = '8443'
$env:VOICE_CERT        = 'C:\certs\voice\voice.example.com-chain.pem'
$env:VOICE_KEY         = 'C:\certs\voice\voice.example.com-key.pem'
$env:VOICE_FRONTEND    = '127.0.0.1:3000'
$env:VOICE_BACKEND     = '127.0.0.1:8000'
$env:VOICE_BASIC_USER  = 'voice'
# Output of: caddy hash-password
$env:VOICE_BASIC_HASH  = ''
# Same value as the backend VOICE_GATEWAY_KEY. Never a NEXT_PUBLIC_ variable.
$env:VOICE_GATEWAY_KEY = ''

foreach ($name in 'VOICE_BASIC_HASH', 'VOICE_GATEWAY_KEY') {
    if (-not (Get-Item "env:$name").Value) { throw "$name is empty. Fill it in before starting Caddy." }
}
if ($env:VOICE_GATEWAY_KEY.Length -lt 32) { throw 'VOICE_GATEWAY_KEY must be at least 32 characters; the backend refuses a public origin without it.' }
foreach ($path in $env:VOICE_CERT, $env:VOICE_KEY) {
    if (-not (Test-Path $path)) { throw "Certificate file not found: $path" }
}

$caddyfile = Join-Path $PSScriptRoot 'Caddyfile.windows'
caddy validate --config $caddyfile --adapter caddyfile
if ($LASTEXITCODE -ne 0) { throw 'Caddyfile validation failed.' }
caddy run --config $caddyfile --adapter caddyfile
