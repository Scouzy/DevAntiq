# Original procedural motion background, 8-second seamless loop, no audio.
$ErrorActionPreference = 'Stop'
$mediaPath = Join-Path $PSScriptRoot '../media'
New-Item -ItemType Directory -Force -Path $mediaPath | Out-Null
$filter = "nullsrc=s=640x360:r=24:d=8,geq=r='12+36*exp(-pow((Y/H-0.48-0.16*sin(X/W*5+T*PI/4))/0.16,2))':g='10+16*exp(-pow((Y/H-0.48-0.16*sin(X/W*5+T*PI/4))/0.13,2))':b='24+85*exp(-pow((Y/H-0.48-0.16*sin(X/W*5+T*PI/4))/0.2,2))',format=yuv420p"
& ffmpeg -hide_banner -loglevel error -f lavfi -i $filter -c:v libx264 -crf 24 -preset fast -movflags +faststart -an -y (Join-Path $mediaPath 'studio-aurora.mp4')
if ($LASTEXITCODE -ne 0) { throw 'Video generation failed.' }
& ffmpeg -hide_banner -loglevel error -i (Join-Path $mediaPath 'studio-aurora.mp4') -frames:v 1 -update 1 -y (Join-Path $mediaPath 'studio-aurora.jpg')
if ($LASTEXITCODE -ne 0) { throw 'Poster generation failed.' }
