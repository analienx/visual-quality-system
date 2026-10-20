# Update precisely one native Word TOC in an isolated read-only source document.
# Save only to a brand-new local candidate DOCX, never back to the source.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$DocumentPath,
    [Parameter(Mandatory=$true)][string]$CandidatePath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$vqsSource = [System.IO.Path]::GetFullPath($DocumentPath)
$vqsTarget = [System.IO.Path]::GetFullPath($CandidatePath)
if (-not $vqsSource.EndsWith('.docx',[System.StringComparison]::OrdinalIgnoreCase) -or
    -not $vqsTarget.EndsWith('.docx',[System.StringComparison]::OrdinalIgnoreCase) -or
    $vqsSource.StartsWith('\\') -or $vqsTarget.StartsWith('\\') -or
    [string]::Equals($vqsSource,$vqsTarget,[System.StringComparison]::OrdinalIgnoreCase) -or
    -not [System.IO.File]::Exists($vqsSource) -or [System.IO.File]::Exists($vqsTarget)) {
    throw 'existing local DOCX source and distinct unused local candidate path required'
}
if (@(Get-Process WINWORD -ErrorAction SilentlyContinue).Count -ne 0) {
    throw 'another Word session exists; exclusive Word automation unavailable'
}
$vqsWord = $null
$vqsDocument = $null
try {
    $vqsWord = New-Object -ComObject Word.Application
    $vqsWord.Visible = $false
    $vqsWord.DisplayAlerts = 0
    $vqsWord.AutomationSecurity = 3
    $vqsProcess = @(Get-Process WINWORD -ErrorAction Stop)
    if ($vqsProcess.Count -ne 1) { throw 'run-owned Word process is not unique' }
    $vqsPid = [int]$vqsProcess[0].Id
    $vqsDocument = $vqsWord.Documents.Open($vqsSource,$false,$true)
    if (-not $vqsDocument.ReadOnly -or
        -not [string]::Equals($vqsDocument.FullName,$vqsSource,
            [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'source Word document was not opened exact-path read-only'
    }
    $vqsCountBefore = [int]$vqsDocument.TablesOfContents.Count
    if ($vqsCountBefore -ne 1) { throw 'requires precisely one recognized native TOC' }
    $vqsDocument.TablesOfContents.Item(1).Update()
    $vqsCountAfter = [int]$vqsDocument.TablesOfContents.Count
    if ($vqsCountAfter -ne 1 -or [System.IO.File]::Exists($vqsTarget)) {
        throw 'TOC was lost/multiplied or candidate path was occupied'
    }
    # 16 = wdFormatDocumentDefault. SaveAs2 changes the in-memory copy and
    # writes the new private path; no write operation targets the source.
    $vqsDocument.SaveAs2($vqsTarget,16)
    if (-not [System.IO.File]::Exists($vqsTarget) -or
        -not [string]::Equals($vqsDocument.FullName,$vqsTarget,
            [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Word did not save the exact isolated DOCX candidate'
    }
    [pscustomobject]@{
        schema = 'vqs.native-word-toc-candidate/1'
        renderer = 'Microsoft Word'
        native_word_pid = $vqsPid
        word_version = [string]$vqsWord.Version
        source_full_name = $vqsSource
        source_opened_read_only = $true
        candidate_full_name = $vqsTarget
        toc_count_before = $vqsCountBefore
        toc_count_after = $vqsCountAfter
        utc = (Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json -Compress
} finally {
    if ($vqsDocument) {
        try { $vqsDocument.Close($false) } catch {}
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($vqsDocument)
    }
    if ($vqsWord) {
        try { $vqsWord.Quit() } catch {}
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($vqsWord)
    }
}
