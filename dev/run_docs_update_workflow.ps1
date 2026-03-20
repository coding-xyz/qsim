param(
    [switch]$SkipTests,
    [switch]$SkipBuild,
    [switch]$PromptOnly,
    [string]$SiteDir = "site",
    [string]$WorkflowConfig = "scripts/docs_update.config.json",
    [string[]]$RequiredDocs,
    [string[]]$RequiredSite,
    [switch]$Relaxed
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Step($msg) {
    Write-Host "`n==> $msg" -ForegroundColor Cyan
}

function Check-File([string]$path) {
    if (-not (Test-Path $path)) {
        throw "Missing required file: $path"
    }
}

function Check-FileMaybe([string]$path, [bool]$relaxed) {
    if (Test-Path $path) {
        Write-Host "OK: $path"
        return $true
    }
    if ($relaxed) {
        Write-Warning "Missing (relaxed): $path"
        return $false
    }
    throw "Missing required file: $path"
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

$promptFile = "scripts/codex_prompt_docs_update.md"
$requiredDocsDefault = @(
    "mkdocs.yml",
    "docs/WIKI.md",
    "docs/wiki/overview.md",
    "docs/wiki/qec_analysis.md",
    "docs/api/index.md",
    "docs/api/analysis.md",
    "docs/api/qec.md"
)

function Get-RequiredSiteFiles([string]$dir) {
    return @(
        "$dir/WIKI.html",
        "$dir/wiki/overview.html",
        "$dir/wiki/qec_analysis.html",
        "$dir/api/index.html",
        "$dir/api/analysis.html",
        "$dir/api/qec.html"
    )
}

# Optional config file for team/user customization.
if (Test-Path $WorkflowConfig) {
    Step "Load workflow config: $WorkflowConfig"
    $cfg = Get-Content -Raw $WorkflowConfig | ConvertFrom-Json
    if ($null -ne $cfg.prompt_file -and [string]::IsNullOrWhiteSpace([string]$cfg.prompt_file) -eq $false) {
        $promptFile = [string]$cfg.prompt_file
    }
    if ($null -ne $cfg.site_dir -and [string]::IsNullOrWhiteSpace([string]$cfg.site_dir) -eq $false -and $PSBoundParameters.ContainsKey("SiteDir") -eq $false) {
        $SiteDir = [string]$cfg.site_dir
    }
    if ($null -ne $cfg.required_docs -and $PSBoundParameters.ContainsKey("RequiredDocs") -eq $false) {
        $RequiredDocs = @($cfg.required_docs | ForEach-Object { [string]$_ })
    }
    if ($null -ne $cfg.required_site -and $PSBoundParameters.ContainsKey("RequiredSite") -eq $false) {
        $RequiredSite = @($cfg.required_site | ForEach-Object { [string]$_ })
    }
}

if ($null -eq $RequiredDocs -or $RequiredDocs.Count -eq 0) {
    $RequiredDocs = $requiredDocsDefault
}

Step "Codex prompt template"
Check-File $promptFile
Get-Content -Raw $promptFile | Write-Host

if ($PromptOnly) {
    Step "Prompt-only mode complete"
    exit 0
}

Step "Check required docs files"
foreach ($f in $RequiredDocs) {
    [void](Check-FileMaybe $f $Relaxed.IsPresent)
}

if (-not $SkipTests) {
    Step "Run tests"
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONPATH = "src"
    pytest -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) {
        throw "pytest failed with exit code $LASTEXITCODE"
    }
}

if (-not $SkipBuild) {
    Step "Build docs"
    $env:PYTHONDONTWRITEBYTECODE = "1"
    mkdocs build --clean --site-dir $SiteDir
    if ($LASTEXITCODE -ne 0) {
        # Windows often locks files under site/. Fall back to a unique dir.
        $fallback = "site_rerun_{0}" -f [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        Write-Warning "mkdocs build to '$SiteDir' failed; retrying with '$fallback'."
        mkdocs build --clean --site-dir $fallback
        if ($LASTEXITCODE -ne 0) {
            throw "mkdocs build failed with exit code $LASTEXITCODE"
        }
        $SiteDir = $fallback
    }
}

Step "Check generated site pages"
if ($null -eq $RequiredSite -or $RequiredSite.Count -eq 0) {
    $RequiredSite = Get-RequiredSiteFiles $SiteDir
}
foreach ($f in $RequiredSite) {
    $normalized = if ([System.IO.Path]::IsPathRooted($f)) { $f } else { $f -replace "^site/", "$SiteDir/" }
    [void](Check-FileMaybe $normalized $Relaxed.IsPresent)
}

Step "Done"
Write-Host "Docstring + Wiki + API reference workflow passed." -ForegroundColor Green
Write-Host "Built site dir: $SiteDir"
