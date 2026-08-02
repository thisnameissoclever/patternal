param(
    [Parameter(Mandatory = $true)]
    [string]$SourceTexture,

    [Parameter(Mandatory = $true)]
    [string]$AiReference,

    [Parameter(Mandatory = $true)]
    [string]$OutputTexture
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$drawingAssembly = [System.Drawing.Bitmap].Assembly.Location
$drawingPrimitivesAssembly = [System.Drawing.Rectangle].Assembly.Location
$gdiAssembly = Join-Path (Split-Path -Parent $drawingAssembly) 'System.Private.Windows.GdiPlus.dll'
$windowsCoreAssembly = Join-Path (Split-Path -Parent $drawingAssembly) 'System.Private.Windows.Core.dll'
if (-not (Test-Path -LiteralPath $gdiAssembly) -or -not (Test-Path -LiteralPath $windowsCoreAssembly)) {
    throw "The Windows drawing support assemblies were not found beside $drawingAssembly"
}

Add-Type -ReferencedAssemblies @($drawingAssembly, $drawingPrimitivesAssembly, $gdiAssembly, $windowsCoreAssembly) -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;

public static class PatternaBodyTextureCleaner
{
    public static int Run(string sourcePath, string aiReferencePath, string outputPath)
    {
        using var source = new Bitmap(sourcePath);
        using var aiReference = new Bitmap(aiReferencePath);
        using var aiScaled = new Bitmap(source.Width, source.Height, PixelFormat.Format32bppArgb);
        using (Graphics graphics = Graphics.FromImage(aiScaled))
        {
            graphics.CompositingMode = CompositingMode.SourceCopy;
            graphics.CompositingQuality = CompositingQuality.HighQuality;
            graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
            graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
            graphics.SmoothingMode = SmoothingMode.HighQuality;
            graphics.DrawImage(aiReference, 0, 0, source.Width, source.Height);
        }

        using var output = new Bitmap(source.Width, source.Height, PixelFormat.Format32bppArgb);
        using (Graphics graphics = Graphics.FromImage(output))
        {
            graphics.CompositingMode = CompositingMode.SourceCopy;
            graphics.DrawImageUnscaled(source, 0, 0);
        }

        Rectangle bounds = new Rectangle(0, 0, source.Width, source.Height);
        BitmapData outputData = output.LockBits(bounds, ImageLockMode.ReadWrite, PixelFormat.Format32bppArgb);
        BitmapData aiData = aiScaled.LockBits(bounds, ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        int byteCount = Math.Abs(outputData.Stride) * output.Height;
        byte[] outputBytes = new byte[byteCount];
        byte[] aiBytes = new byte[byteCount];
        Marshal.Copy(outputData.Scan0, outputBytes, 0, byteCount);
        Marshal.Copy(aiData.Scan0, aiBytes, 0, byteCount);

        int changedPixels = 0;
        for (int offset = 0; offset < byteCount; offset += 4)
        {
            int blue = outputBytes[offset];
            int green = outputBytes[offset + 1];
            int red = outputBytes[offset + 2];
            int maximum = Math.Max(red, Math.Max(green, blue));
            int minimum = Math.Min(red, Math.Min(green, blue));
            int chroma = maximum - minimum;
            if (chroma >= 32 || maximum < 55 || maximum > 205)
            {
                continue;
            }

            int aiBlue = aiBytes[offset];
            int aiGreen = aiBytes[offset + 1];
            int aiRed = aiBytes[offset + 2];
            int aiMaximum = Math.Max(aiRed, Math.Max(aiGreen, aiBlue));
            int aiMinimum = Math.Min(aiRed, Math.Min(aiGreen, aiBlue));
            if (aiMaximum - aiMinimum < 24)
            {
                continue;
            }

            double blend = chroma <= 12 ? 1.0 : (32.0 - chroma) / 20.0;
            outputBytes[offset] = Blend(blue, aiBlue, blend);
            outputBytes[offset + 1] = Blend(green, aiGreen, blend);
            outputBytes[offset + 2] = Blend(red, aiRed, blend);
            changedPixels++;
        }

        Marshal.Copy(outputBytes, 0, outputData.Scan0, byteCount);
        output.UnlockBits(outputData);
        aiScaled.UnlockBits(aiData);

        string parent = Path.GetDirectoryName(outputPath);
        if (!string.IsNullOrWhiteSpace(parent))
        {
            Directory.CreateDirectory(parent);
        }
        output.Save(outputPath, ImageFormat.Png);
        return changedPixels;
    }

    private static byte Blend(int original, int replacement, double blend)
    {
        double value = original * (1.0 - blend) + replacement * blend;
        return (byte)Math.Clamp((int)Math.Round(value), 0, 255);
    }
}
'@

$resolvedSource = (Resolve-Path -LiteralPath $SourceTexture).Path
$resolvedReference = (Resolve-Path -LiteralPath $AiReference).Path
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputTexture)
$changedPixels = [PatternaBodyTextureCleaner]::Run(
    $resolvedSource,
    $resolvedReference,
    $resolvedOutput)

[pscustomobject]@{
    OutputTexture = $resolvedOutput
    ChangedPixels = $changedPixels
} | ConvertTo-Json
