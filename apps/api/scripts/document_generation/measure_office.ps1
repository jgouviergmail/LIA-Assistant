<#
.SYNOPSIS
    Ask Word, PowerPoint and Excel what they think of the rendered corpus.

.DESCRIPTION
    A MEASUREMENT, never a gate (the shape of `mobile:probe`): CI has no Office,
    and a paid-for-by-hand check cannot be a merge requirement. Run it at review
    time and read the numbers.

    PowerPoint is the only thing that can say whether text overflows a slide;
    Word is the only thing that computes a field or a table of contents; Excel
    is the only thing that decides whether a workbook opens without repair.

    Exit code is 1 when a slide overflows or a file refuses to open.
#>
param(
    [string]$Dir = "data/document_corpus_out"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path $Dir
$overflows = 0
$failures = 0

Write-Output "=== PowerPoint ==="
$decks = Get-ChildItem -Path $root -Filter *.pptx
if ($decks) {
    $powerpoint = New-Object -ComObject PowerPoint.Application
    foreach ($file in $decks) {
        try {
            $deck = $powerpoint.Presentations.Open($file.FullName, $true, $false, $false)
        } catch {
            $failures++; Write-Output "  REFUSED $($file.Name): $($_.Exception.Message)"; continue
        }
        $slideOverflows = 0
        foreach ($slide in $deck.Slides) {
            foreach ($shape in $slide.Shapes) {
                if ($shape.HasTextFrame -and $shape.TextFrame.HasText) {
                    $range = $shape.TextFrame.TextRange
                    $over = [math]::Round($range.BoundHeight - $shape.Height, 1)
                    if ($over -gt 0) {
                        $slideOverflows++
                        Write-Output "  OVERFLOW $($file.Name) s$($slide.SlideIndex) '$($shape.Name)' by $over pt"
                    }
                }
            }
        }
        $overflows += $slideOverflows
        $size = "$($deck.PageSetup.SlideWidth)x$($deck.PageSetup.SlideHeight)"
        Write-Output "  $($file.Name): $($deck.Slides.Count) slides, $size, overflows=$slideOverflows"
        # NEVER overwrite the artefact under measurement: LIA renders its own PDF.
        $deck.SaveAs("$($file.FullName).powerpoint.pdf", 32)
        $deck.Close()
    }
    $powerpoint.Quit()
}

Write-Output "=== Word ==="
$documents = Get-ChildItem -Path $root -Filter *.docx
if ($documents) {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    foreach ($file in $documents) {
        try {
            $document = $word.Documents.Open($file.FullName, $false, $true)
        } catch {
            $failures++; Write-Output "  REFUSED $($file.Name): $($_.Exception.Message)"; continue
        }
        $pages = $document.ComputeStatistics(2)
        $toc = $document.TablesOfContents.Count
        $footer = ($document.Sections.Item(1).Footers.Item(1).Range.Text -replace "`r", "").Trim()
        $numbers = @()
        foreach ($paragraph in $document.Paragraphs) {
            if ($paragraph.Style.NameLocal -match '^(Heading|Titre) 1' -and $numbers.Count -lt 3) {
                $numbers += "[$($paragraph.Range.ListFormat.ListString)]"
            }
        }
        Write-Output "  $($file.Name): $pages pages, TOC=$toc, footer='$footer', H1 numbers=$($numbers -join ' ')"
        $document.ExportAsFixedFormat("$($file.FullName).word.pdf", 17)
        $document.Close(0)
    }
    $word.Quit()
}

Write-Output "=== Excel ==="
$books = Get-ChildItem -Path $root -Filter *.xlsx
if ($books) {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    foreach ($file in $books) {
        try {
            $book = $excel.Workbooks.Open($file.FullName)
        } catch {
            $failures++; Write-Output "  REFUSED $($file.Name): $($_.Exception.Message)"; continue
        }
        $sheet = $book.Sheets.Item(1)
        Write-Output "  $($file.Name): $($book.Sheets.Count) sheets, tables=$($sheet.ListObjects.Count), freeze=$($excel.ActiveWindow.FreezePanes)"
        $book.Close($false)
    }
    $excel.Quit()
}

Write-Output "OVERFLOWS=$overflows REFUSED=$failures"
if ($overflows -gt 0 -or $failures -gt 0) { exit 1 }
