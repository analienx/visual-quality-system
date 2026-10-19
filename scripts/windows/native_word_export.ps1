# Native Microsoft Word-only, one-shot DOCX -> PDF pagination probe.
# Operates on an already-existing local read-only DOCX. Output must be a
# new file inside an isolated private temporary directory. Never opens
# another Word session or updates the user's source file.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$DocumentPath,
    [Parameter(Mandatory=$true)][string]$PdfPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$vqsDoc = [System.IO.Path]::GetFullPath($DocumentPath)
$vqsPdf = [System.IO.Path]::GetFullPath($PdfPath)
if (-not $vqsDoc.EndsWith('.docx', [System.StringComparison]::OrdinalIgnoreCase) -or
    -not $vqsPdf.EndsWith('.pdf', [System.StringComparison]::OrdinalIgnoreCase) -or
    $vqsDoc.StartsWith('\\') -or $vqsPdf.StartsWith('\\') -or
    -not [System.IO.File]::Exists($vqsDoc) -or [System.IO.File]::Exists($vqsPdf)) {
    throw 'strict local DOCX input and fresh private PDF output required'
}
$vqsAlready=@(Get-Process WINWORD -ErrorAction SilentlyContinue)
if ($vqsAlready.Count -ne 0) {
    throw 'existing Word session detected; exclusive run-owned Word lease unavailable'
}
$vqsWord=$null
$vqsOpened=$null
try {
    $vqsWord=New-Object -ComObject Word.Application
    $vqsWord.Visible=$false
    $vqsWord.DisplayAlerts=0
    $vqsWord.AutomationSecurity=3
    $vqsProcess=@(Get-Process WINWORD -ErrorAction Stop)
    if ($vqsProcess.Count -ne 1) {
        throw 'cannot uniquely identify isolated run-owned Word process'
    }
    $vqsWordPid=[int]$vqsProcess[0].Id
    $vqsOpened=$vqsWord.Documents.Open($vqsDoc,$false,$true)
    if (-not $vqsOpened.ReadOnly -or
        -not [string]::Equals($vqsOpened.FullName,$vqsDoc,
            [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Word did not open the exact source in read-only mode'
    }
    $vqsOpened.Repaginate()
    $vqsPages=[int]$vqsOpened.ComputeStatistics(2)
    if ($vqsPages -lt 1 -or $vqsPages -gt 2000) {
        throw 'Word reports invalid/unsupported page count'
    }
    $vqsParagraphs=[int]$vqsOpened.Paragraphs.Count
    $vqsTables=[int]$vqsOpened.Tables.Count
    if ($vqsParagraphs -lt 1 -or $vqsParagraphs -gt 15000 -or $vqsTables -gt 1000) {
        throw 'Word document exceeds bounded structural inventory'
    }
    $vqsHeadings=@()
    $vqsParaNumber=0
    foreach ($vqsPara in $vqsOpened.Paragraphs) {
        $vqsParaNumber++
        $vqsStyle=''
        try { $vqsStyle=[string]$vqsPara.Range.Style.NameLocal } catch {}
        if ($vqsStyle -match '^(Heading|Überschrift|Nadpis)\s*[1-9]') {
            $vqsRange=$vqsPara.Range
            $vqsPage=[int]$vqsRange.Information(3)
            $vqsVertical=[double]$vqsRange.Information(6)
            $vqsHeadings+=@{
                paragraph=$vqsParaNumber
                page=$vqsPage
                y_points=$vqsVertical
                style=$vqsStyle
            }
        }
    }
    $vqsTablePages=@()
    for ($vqsT=1; $vqsT -le $vqsTables; $vqsT++) {
        $vqsTable=$vqsOpened.Tables.Item($vqsT)
        $vqsStart=$vqsTable.Range.Duplicate
        $vqsStart.Collapse(1)
        $vqsEnd=$vqsTable.Range.Duplicate
        $vqsEnd.Collapse(0)
        $vqsTablePages+=@{
            index=$vqsT
            start_page=[int]$vqsStart.Information(3)
            end_page=[int]$vqsEnd.Information(3)
        }
    }
    $vqsSectionMargins=@()
    for ($vqsS=1; $vqsS -le $vqsOpened.Sections.Count; $vqsS++) {
        $vqsSection=$vqsOpened.Sections.Item($vqsS)
        $vqsSetup=$vqsSection.PageSetup
        $vqsSectionMargins+=@{
            index=$vqsS
            width_points=[double]$vqsSetup.PageWidth
            height_points=[double]$vqsSetup.PageHeight
            top_points=[double]$vqsSetup.TopMargin
            bottom_points=[double]$vqsSetup.BottomMargin
            left_points=[double]$vqsSetup.LeftMargin
            right_points=[double]$vqsSetup.RightMargin
        }
    }
    $vqsOpened.ExportAsFixedFormat($vqsPdf,17)
    if (-not [System.IO.File]::Exists($vqsPdf)) {
        throw 'Word reported export but native PDF is absent'
    }
    [pscustomobject]@{
        schema='vqs.native-word-pagination/1'
        renderer='Microsoft Word'
        native_word_pid=$vqsWordPid
        word_version=[string]$vqsWord.Version
        read_only=[bool]$vqsOpened.ReadOnly
        source_full_name=[string]$vqsOpened.FullName
        page_count=$vqsPages
        paragraphs=$vqsParagraphs
        tables=$vqsTables
        headings=@($vqsHeadings)
        table_pages=@($vqsTablePages)
        sections=@($vqsSectionMargins)
        utc=(Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json -Depth 12 -Compress
} finally {
    if ($vqsOpened) {
        try { $vqsOpened.Close($false) } catch {}
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($vqsOpened)
    }
    if ($vqsWord) {
        try { $vqsWord.Quit() } catch {}
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($vqsWord)
    }
}
