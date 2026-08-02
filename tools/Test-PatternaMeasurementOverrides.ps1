[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$mainPagePath = Join-Path $PSScriptRoot '..\Patterna\MainPage.xaml.cs'
$source = Get-Content -Raw -LiteralPath $mainPagePath
$classMatch = [regex]::Match(
    $source,
    'public sealed class MeasurementParameter[\s\S]+?(?=\r?\npublic sealed class CustomMeasurement)')

if (-not $classMatch.Success) {
    throw 'Could not locate MeasurementParameter in MainPage.xaml.cs.'
}

$typeDefinition = @"
#nullable enable
using System;
using System.ComponentModel;

$($classMatch.Value)
"@

Add-Type -TypeDefinition $typeDefinition -Language CSharp

$measurement = [MeasurementParameter]::new(
    'waistDepth',
    'Natural waist depth',
    18.5,
    10.0,
    38.0,
    0.1,
    'cm')

$measurement.SetEstimatedValue(20.0)
if ($measurement.Value -ne 20.0 -or $measurement.IsUserOverride) {
    throw 'An untouched estimate was not applied correctly.'
}

$measurement.Value = 22.4
$measurement.MarkUserEntered()
$measurement.SetEstimatedValue(27.0)
if ($measurement.Value -ne 22.4 -or -not $measurement.IsUserOverride) {
    throw 'A manual measurement was overwritten by a later estimate.'
}

$measurement.Restore(24.2, $false)
$measurement.SetEstimatedValue(25.1)
if ($measurement.Value -ne 25.1 -or $measurement.IsUserOverride) {
    throw 'A restored estimated value did not remain eligible for estimation.'
}

$measurement.Restore(26.3, $true)
$measurement.SetEstimatedValue(30.0)
if ($measurement.Value -ne 26.3 -or -not $measurement.IsUserOverride) {
    throw 'A restored manual override was overwritten by estimation.'
}

$measurement.Reset()
if ($measurement.Value -ne 18.5 -or $measurement.IsUserOverride) {
    throw 'Reset did not restore the baseline estimate state.'
}

[pscustomobject]@{
    EstimatedValueUpdates = $true
    ManualOverrideSurvives = $true
    RestoredOriginsSurvive = $true
    ResetClearsOverride = $true
    Result = 'Passed'
}
