# Resize the existing brand asset without changing its proportions or artwork.
Add-Type -AssemblyName System.Drawing
$iconDirectory = Join-Path $PSScriptRoot '../img/icons'
New-Item -ItemType Directory -Force -Path $iconDirectory | Out-Null
$source = [System.Drawing.Image]::FromFile((Join-Path $PSScriptRoot '../img/devantiq-logo.png'))
try {
    $variants = @(
        @{ Name = 'apple-touch-icon-v2.png'; Size = 180; Fill = 0.80 },
        @{ Name = 'icon-192-v2.png'; Size = 192; Fill = 0.80 },
        @{ Name = 'icon-512-v2.png'; Size = 512; Fill = 0.80 },
        @{ Name = 'icon-maskable-512-v2.png'; Size = 512; Fill = 0.64 }
    )
    foreach ($variant in $variants) {
        $size = $variant.Size
        $bitmap = [System.Drawing.Bitmap]::new($size, $size)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.Clear([System.Drawing.ColorTranslator]::FromHtml('#f1f3ff'))
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $scale = ($size * $variant.Fill) / [Math]::Max($source.Width, $source.Height)
            $width = [single]($source.Width * $scale)
            $height = [single]($source.Height * $scale)
            $rect = [System.Drawing.RectangleF]::new(($size - $width) / 2, ($size - $height) / 2, $width, $height)
            $graphics.DrawImage($source, $rect)
            $bitmap.Save((Join-Path $iconDirectory $variant.Name), [System.Drawing.Imaging.ImageFormat]::Png)
        } finally {
            $graphics.Dispose()
            $bitmap.Dispose()
        }
    }
} finally {
    $source.Dispose()
}
