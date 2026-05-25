$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $repo "docs\ppt"
$outPath = Join-Path $outDir "OccuEVRoute_classroom_presentation.pptx"
$figPath = Join-Path $repo "docs\figures\occupancy_horizon_shap_bar.png"
$horizonCsv = Join-Path $repo "docs\figures\occupancy_horizon_by_horizon_metrics.csv"
$plannerAsset = Join-Path $repo "docs\ppt\assets\planner-demo-clean.png"
$rankingAsset = Join-Path $repo "docs\ppt\assets\ranking-diagnostics.png"
$searchAsset = Join-Path $repo "docs\ppt\assets\route-search-comparison.png"
$pipelineAsset = Join-Path $repo "docs\ppt\assets\data-artifact-pipeline.png"
$featureAsset = Join-Path $repo "docs\ppt\assets\model-feature-stack.png"
$complexityAsset = Join-Path $repo "docs\ppt\assets\complexity-tradeoff.png"

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
& "C:\Users\36144\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (Join-Path $PSScriptRoot "create_ppt_assets.py") | Out-Null
if (Test-Path $outPath) {
    Remove-Item -LiteralPath $outPath -Force
}

$ppLayoutBlank = 12
$msoFalse = 0
$msoTrue = -1
$ppSaveAsOpenXMLPresentation = 24

$ppt = New-Object -ComObject PowerPoint.Application
$ppt.Visible = $msoTrue
$presentation = $ppt.Presentations.Add($msoTrue)
$presentation.PageSetup.SlideWidth = 960
$presentation.PageSetup.SlideHeight = 540

function Rgb {
    param([int]$R, [int]$G, [int]$B)
    return $R + ($G * 256) + ($B * 65536)
}

$theme = @{
    Navy = Rgb 20 45 78
    Blue = Rgb 42 111 151
    Teal = Rgb 46 139 137
    Green = Rgb 68 145 106
    Red = Rgb 188 83 73
    Grey = Rgb 84 96 112
    LightGrey = Rgb 242 245 248
    MidGrey = Rgb 216 224 232
    White = Rgb 255 255 255
    Black = Rgb 18 24 32
}

function Add-Slide {
    param([string]$Title, [string]$Subtitle = "")
    $slide = $presentation.Slides.Add($presentation.Slides.Count + 1, $ppLayoutBlank)
    $slide.Background.Fill.ForeColor.RGB = $theme.White

    $bar = $slide.Shapes.AddShape(1, 0, 0, 960, 10)
    $bar.Fill.ForeColor.RGB = $theme.Teal
    $bar.Line.Visible = $msoFalse

    $titleBox = $slide.Shapes.AddTextbox(1, 44, 28, 780, 48)
    $titleBox.TextFrame.TextRange.Text = $Title
    $titleBox.TextFrame.TextRange.Font.Name = "Aptos Display"
    $titleBox.TextFrame.TextRange.Font.Size = 30
    $titleBox.TextFrame.TextRange.Font.Bold = $msoTrue
    $titleBox.TextFrame.TextRange.Font.Color.RGB = $theme.Navy
    $titleBox.TextFrame.MarginLeft = 0
    $titleBox.TextFrame.MarginRight = 0
    $titleBox.TextFrame.MarginTop = 0
    $titleBox.TextFrame.MarginBottom = 0

    if ($Subtitle.Length -gt 0) {
        $subBox = $slide.Shapes.AddTextbox(1, 46, 76, 780, 28)
        $subBox.TextFrame.TextRange.Text = $Subtitle
        $subBox.TextFrame.TextRange.Font.Name = "Aptos"
        $subBox.TextFrame.TextRange.Font.Size = 13
        $subBox.TextFrame.TextRange.Font.Color.RGB = $theme.Grey
        $subBox.TextFrame.MarginLeft = 0
        $subBox.TextFrame.MarginTop = 0
    }

    $footer = $slide.Shapes.AddTextbox(1, 44, 505, 820, 20)
    $footer.TextFrame.TextRange.Text = "OccuEVRoute | DI22001 Algorithms and AI"
    $footer.TextFrame.TextRange.Font.Name = "Aptos"
    $footer.TextFrame.TextRange.Font.Size = 8.5
    $footer.TextFrame.TextRange.Font.Color.RGB = $theme.Grey
    $footer.TextFrame.MarginLeft = 0
    $footer.TextFrame.MarginTop = 0

    $num = $slide.Shapes.AddTextbox(1, 890, 505, 40, 20)
    $num.TextFrame.TextRange.Text = [string]$slide.SlideIndex
    $num.TextFrame.TextRange.Font.Name = "Aptos"
    $num.TextFrame.TextRange.Font.Size = 8.5
    $num.TextFrame.TextRange.Font.Color.RGB = $theme.Grey
    $num.TextFrame.TextRange.ParagraphFormat.Alignment = 3
    return $slide
}

function Add-Text {
    param($Slide, [string]$Text, [double]$X, [double]$Y, [double]$W, [double]$H, [double]$Size = 16, [int]$Color = $theme.Black, [switch]$Bold)
    $box = $Slide.Shapes.AddTextbox(1, $X, $Y, $W, $H)
    $box.TextFrame.TextRange.Text = $Text
    $box.TextFrame.TextRange.Font.Name = "Aptos"
    $box.TextFrame.TextRange.Font.Size = $Size
    $box.TextFrame.TextRange.Font.Color.RGB = $Color
    if ($Bold) { $box.TextFrame.TextRange.Font.Bold = $msoTrue }
    $box.TextFrame.MarginLeft = 0
    $box.TextFrame.MarginRight = 0
    $box.TextFrame.MarginTop = 0
    $box.TextFrame.MarginBottom = 0
    return $box
}

function Add-Bullets {
    param($Slide, [string[]]$Items, [double]$X, [double]$Y, [double]$W, [double]$H, [double]$Size = 16)
    $text = ($Items | ForEach-Object { "- $_" }) -join "`r"
    $box = Add-Text $Slide $text $X $Y $W $H $Size $theme.Black
    $box.TextFrame.TextRange.ParagraphFormat.SpaceAfter = 8
    return $box
}

function Add-Card {
    param($Slide, [string]$Heading, [string]$Body, [double]$X, [double]$Y, [double]$W, [double]$H, [int]$Accent = $theme.Blue)
    $shape = $Slide.Shapes.AddShape(5, $X, $Y, $W, $H)
    $shape.Fill.ForeColor.RGB = $theme.LightGrey
    $shape.Line.ForeColor.RGB = $theme.MidGrey
    $shape.Line.Weight = 1

    $accentBar = $Slide.Shapes.AddShape(1, $X, $Y, 6, $H)
    $accentBar.Fill.ForeColor.RGB = $Accent
    $accentBar.Line.Visible = $msoFalse

    Add-Text $Slide $Heading ($X + 18) ($Y + 14) ($W - 28) 24 15 $theme.Navy -Bold | Out-Null
    Add-Text $Slide $Body ($X + 18) ($Y + 44) ($W - 28) ($H - 54) 12.5 $theme.Grey | Out-Null
}

function Add-Arrow {
    param($Slide, [double]$X1, [double]$Y1, [double]$X2, [double]$Y2)
    $line = $Slide.Shapes.AddLine($X1, $Y1, $X2, $Y2)
    $line.Line.ForeColor.RGB = $theme.Grey
    $line.Line.Weight = 1.4
    $line.Line.EndArrowheadStyle = 3
}

function Add-FlowStep {
    param($Slide, [string]$Label, [string]$Body, [double]$X, [double]$Y, [double]$W, [double]$H, [int]$Color)
    $shape = $Slide.Shapes.AddShape(5, $X, $Y, $W, $H)
    $shape.Fill.ForeColor.RGB = $theme.White
    $shape.Line.ForeColor.RGB = $Color
    $shape.Line.Weight = 1.6
    Add-Text $Slide $Label ($X + 12) ($Y + 10) ($W - 24) 22 13 $Color -Bold | Out-Null
    Add-Text $Slide $Body ($X + 12) ($Y + 36) ($W - 24) ($H - 42) 10.5 $theme.Grey | Out-Null
}

function Add-SystemDiagram {
    param($Slide, [double]$X, [double]$Y, [double]$W, [double]$H)
    $leftW = $W * 0.25
    $midW = $W * 0.30
    $rightW = $W * 0.27
    $gap = $W * 0.06
    Add-FlowStep $Slide "Frontend" "Map click, vehicle inputs, ranking metric, result panels" $X $Y $leftW $H $theme.Teal
    Add-FlowStep $Slide "Backend API" "Request validation, response shaping, diagnostics" ($X + $leftW + $gap) $Y $midW $H $theme.Blue
    Add-FlowStep $Slide "Domain modules" "Route search, CSP checks, occupancy prediction, sorting" ($X + $leftW + $gap + $midW + $gap) $Y $rightW $H $theme.Green
    Add-Arrow $Slide ($X + $leftW + 6) ($Y + $H / 2) ($X + $leftW + $gap - 8) ($Y + $H / 2)
    Add-Arrow $Slide ($X + $leftW + $gap + $midW + 6) ($Y + $H / 2) ($X + $leftW + $gap + $midW + $gap - 8) ($Y + $H / 2)
}

function Add-TableLike {
    param($Slide, [object[]]$Rows, [double]$X, [double]$Y, [double]$W, [double]$RowH)
    $col1 = $W * 0.28
    $col2 = $W * 0.52
    $col3 = $W * 0.20
    for ($i = 0; $i -lt $Rows.Count; $i++) {
        $yy = $Y + $i * $RowH
        $bg = $Slide.Shapes.AddShape(1, $X, $yy, $W, $RowH - 4)
        $bg.Fill.ForeColor.RGB = if ($i % 2 -eq 0) { $theme.LightGrey } else { $theme.White }
        $bg.Line.ForeColor.RGB = $theme.MidGrey
        Add-Text $Slide $Rows[$i][0] ($X + 12) ($yy + 10) ($col1 - 18) 28 12.5 $theme.Navy -Bold | Out-Null
        Add-Text $Slide $Rows[$i][1] ($X + $col1 + 8) ($yy + 10) ($col2 - 18) 42 11.5 $theme.Black | Out-Null
        Add-Text $Slide $Rows[$i][2] ($X + $col1 + $col2 + 6) ($yy + 10) ($col3 - 12) 42 10.5 $theme.Grey | Out-Null
    }
}

function Add-LineChart {
    param($Slide, [string]$CsvPath, [double]$X, [double]$Y, [double]$W, [double]$H)
    if (-not (Test-Path $CsvPath)) { return }
    $rows = Import-Csv $CsvPath
    if ($rows.Count -lt 2) { return }

    $plotX = $X + 44
    $plotY = $Y + 18
    $plotW = $W - 64
    $plotH = $H - 58
    $axis = $Slide.Shapes.AddShape(1, $plotX, $plotY, $plotW, $plotH)
    $axis.Fill.Visible = $msoFalse
    $axis.Line.ForeColor.RGB = $theme.MidGrey
    $axis.Line.Weight = 1

    $minH = 5.0
    $maxH = 120.0
    $minR2 = 0.88
    $maxR2 = 0.99
    $points = @()
    foreach ($r in $rows) {
        $horizon = [double]$r.prediction_horizon_min
        $r2 = [double]$r.r2
        $px = $plotX + (($horizon - $minH) / ($maxH - $minH)) * $plotW
        $py = $plotY + (1 - (($r2 - $minR2) / ($maxR2 - $minR2))) * $plotH
        $points += ,@($px, $py, $horizon, $r2)
    }
    for ($i = 0; $i -lt $points.Count - 1; $i++) {
        Add-Arrow $Slide $points[$i][0] $points[$i][1] $points[$i+1][0] $points[$i+1][1]
    }
    foreach ($p in $points) {
        $dot = $Slide.Shapes.AddShape(9, $p[0] - 3.5, $p[1] - 3.5, 7, 7)
        $dot.Fill.ForeColor.RGB = $theme.Teal
        $dot.Line.Visible = $msoFalse
    }
    Add-Text $Slide "R2 by prediction horizon" $X ($Y - 22) $W 20 13 $theme.Navy -Bold | Out-Null
    Add-Text $Slide "5 min" ($plotX - 6) ($plotY + $plotH + 8) 45 16 9 $theme.Grey | Out-Null
    Add-Text $Slide "120 min" ($plotX + $plotW - 42) ($plotY + $plotH + 8) 55 16 9 $theme.Grey | Out-Null
    Add-Text $Slide "0.99" ($plotX - 38) ($plotY - 3) 30 16 9 $theme.Grey | Out-Null
    Add-Text $Slide "0.88" ($plotX - 38) ($plotY + $plotH - 10) 30 16 9 $theme.Grey | Out-Null
}

function Add-DatasetFlow {
    param($Slide)
    $laneY = @(128, 258, 388)
    $laneTitle = @("Routing data", "Occupancy labels", "ML feature context")
    $steps = @(
        @("OSM road graph", "station access", "route graph"),
        @("UrbanEV time series", "lag features", "future occupancy labels"),
        @("POI / weather / station profile", "neighbor history", "ML feature table")
    )
    $colors = @($theme.Blue, $theme.Teal, $theme.Green)
    for ($lane = 0; $lane -lt 3; $lane++) {
        $y = $laneY[$lane]
        Add-Text $Slide $laneTitle[$lane] 58 ($y + 20) 150 24 13 $theme.Navy -Bold | Out-Null
        $x1 = 230; $boxW = 170; $boxH = 58; $gap = 60
        for ($i = 0; $i -lt 3; $i++) {
            $x = $x1 + $i * ($boxW + $gap)
            Add-FlowStep $Slide $steps[$lane][$i] "" $x $y $boxW $boxH $colors[$lane]
            if ($i -lt 2) {
                Add-Arrow $Slide ($x + $boxW + 8) ($y + 29) ($x + $boxW + $gap - 10) ($y + 29)
            }
        }
    }
}

function Add-Dot {
    param($Slide, [double]$X, [double]$Y, [int]$Color, [double]$Size = 10)
    $dot = $Slide.Shapes.AddShape(9, $X - $Size / 2, $Y - $Size / 2, $Size, $Size)
    $dot.Fill.ForeColor.RGB = $Color
    $dot.Line.Visible = $msoFalse
    return $dot
}

function Add-SearchPanel {
    param($Slide, [string]$Title, [string]$Caption, [double]$X, [double]$Y, [double]$W, [double]$H, [string]$Kind)
    $panel = $Slide.Shapes.AddShape(5, $X, $Y, $W, $H)
    $panel.Fill.ForeColor.RGB = $theme.LightGrey
    $panel.Line.ForeColor.RGB = $theme.MidGrey
    Add-Text $Slide $Title ($X + 12) ($Y + 10) ($W - 24) 20 12.5 $theme.Navy -Bold | Out-Null
    Add-Text $Slide $Caption ($X + 12) ($Y + $H - 34) ($W - 24) 24 9.5 $theme.Grey | Out-Null

    if ($Kind -eq "bfs") {
        $cx = $X + 42; $cy = $Y + 62
        for ($i = 0; $i -lt 5; $i++) {
            Add-Dot $Slide ($cx + $i * 34) $cy $theme.Blue 11 | Out-Null
            if ($i -lt 4) { Add-Arrow $Slide ($cx + $i * 34 + 8) $cy ($cx + ($i + 1) * 34 - 8) $cy }
        }
        Add-Text $Slide "S" ($cx - 5) ($cy - 25) 20 14 9 $theme.Blue -Bold | Out-Null
        Add-Text $Slide "G" ($cx + 4 * 34 - 5) ($cy - 25) 20 14 9 $theme.Red -Bold | Out-Null
    }
    elseif ($Kind -eq "bibfs") {
        $cx = $X + 42; $cy = $Y + 62
        for ($i = 0; $i -lt 5; $i++) {
            $color = if ($i -lt 2) { $theme.Blue } elseif ($i -gt 2) { $theme.Green } else { $theme.Red }
            Add-Dot $Slide ($cx + $i * 34) $cy $color 11 | Out-Null
            if ($i -lt 4) { Add-Arrow $Slide ($cx + $i * 34 + 8) $cy ($cx + ($i + 1) * 34 - 8) $cy }
        }
        Add-Text $Slide "meet" ($cx + 2 * 34 - 18) ($cy - 28) 44 14 9 $theme.Red -Bold | Out-Null
    }
    elseif ($Kind -eq "astar") {
        $sx = $X + 42; $sy = $Y + 76; $gx = $X + $W - 42; $gy = $Y + 48
        Add-Dot $Slide $sx $sy $theme.Blue 12 | Out-Null
        Add-Dot $Slide $gx $gy $theme.Red 12 | Out-Null
        Add-Arrow $Slide ($sx + 10) ($sy - 4) ($gx - 12) ($gy + 4)
        $cone = $Slide.Shapes.AddShape(4, $sx + 28, $gy + 2, $W - 100, 42)
        $cone.Fill.ForeColor.RGB = Rgb 232 243 244
        $cone.Line.ForeColor.RGB = $theme.Teal
        $cone.Line.DashStyle = 4
        Add-Text $Slide "h(n)" ($X + $W/2 - 18) ($Y + 54) 50 16 10 $theme.Teal -Bold | Out-Null
    }
    elseif ($Kind -eq "ch") {
        Add-FlowStep $Slide "offline" "ranks + shortcuts" ($X + 14) ($Y + 48) 78 50 $theme.Green
        Add-Arrow $Slide ($X + 96) ($Y + 73) ($X + 124) ($Y + 73)
        Add-FlowStep $Slide "online" "upward query" ($X + 130) ($Y + 48) 78 50 $theme.Blue
        Add-Text $Slide "then unpack shortcuts" ($X + 32) ($Y + 104) 150 16 9 $theme.Grey | Out-Null
    }
}

function Add-SearchVisuals {
    param($Slide)
    Add-SearchPanel $Slide "BFS" "single frontier; unweighted baseline" 58 124 200 138 "bfs"
    Add-SearchPanel $Slide "Bidirectional BFS" "two frontiers meet in the middle" 278 124 200 138 "bibfs"
    Add-SearchPanel $Slide "A* / ALT A*" "heuristic guides expansion to goal" 498 124 200 138 "astar"
    Add-SearchPanel $Slide "CH Query" "preprocess once, query faster" 718 124 190 138 "ch"
}

# Slide 1
$s = Add-Slide "OccuEVRoute" "EV charging route planning and congestion-aware recommendation for Shenzhen"
Add-Text $s "Route search + battery feasibility + ML occupancy prediction" 55 142 720 48 24 $theme.Navy -Bold | Out-Null
Add-Bullets $s @(
    "Input: user location, vehicle state, search constraints",
    "Output: ranked charging stations, routes, SOC, predicted occupancy, diagnostics",
    "Goal: explainable course-demo system, not a production navigation product"
) 58 218 690 150 17 | Out-Null
if (Test-Path $plannerAsset) {
    $pic = $s.Shapes.AddPicture($plannerAsset, $msoFalse, $msoTrue, 600, 305, 300, 180)
    $pic.Line.ForeColor.RGB = $theme.MidGrey
} else {
    Add-Card $s "Presentation focus" "Problem, dataset, route-search approach, ML model, results, complexity, limitations." 610 350 280 86 $theme.Teal
}

# Slide 2
$s = Add-Slide "Problem Definition" "Why this is more than finding the nearest charging station"
Add-Card $s "Travel cost" "Nearest or shortest-distance stations are not always optimal by road travel time." 58 132 260 130 $theme.Blue
Add-Card $s "EV feasibility" "Recommendations must satisfy max drive time, energy consumption, minimum arrival SOC, and charger count." 350 132 260 130 $theme.Green
Add-Card $s "Congestion risk" "Predicted occupancy is used as a station-crowding risk signal. It is not waiting time." 642 132 260 130 $theme.Teal
Add-Text $s "Computable objective" 58 315 260 26 18 $theme.Navy -Bold | Out-Null
Add-Bullets $s @(
    "Find feasible candidate stations",
    "Compute real road-network route metrics",
    "Rank feasible stations by user-selected metric"
) 58 352 520 110 15 | Out-Null
Add-Text $s "Default balanced ranking: drive_time_min / max_drive_time_min + predicted_occupancy_rate" 520 354 380 60 14.5 $theme.Navy -Bold | Out-Null
Add-Text $s "Lower score is better. Travel time is normalized; occupancy remains a congestion-risk term." 520 420 360 40 12.5 $theme.Grey | Out-Null

# Slide 3
$s = Add-Slide "Recommendation Workflow" "Pre-check narrows the search; post-check validates the actual route"
$x0 = 44; $y0 = 130; $w = 112; $h = 86; $gap = 22
$labels = @(
    @("User input", "location, SOC, constraints", $theme.Navy),
    @("Candidates", "nearby charging stations", $theme.Blue),
    @("Pre-check", "static feasibility filters", $theme.Green),
    @("Route search", "road-network algorithms", $theme.Teal),
    @("Post-check", "time, energy, SOC", $theme.Green),
    @("ML + rank", "occupancy risk sorting", $theme.Red)
)
for ($i = 0; $i -lt $labels.Count; $i++) {
    $x = $x0 + $i * ($w + $gap)
    Add-FlowStep $s $labels[$i][0] $labels[$i][1] $x $y0 $w $h $labels[$i][2]
    if ($i -lt $labels.Count - 1) { Add-Arrow $s ($x + $w + 4) ($y0 + 47) ($x + $w + $gap - 4) ($y0 + 47) }
}
Add-SystemDiagram $s 78 286 440 112
if (Test-Path $plannerAsset) {
    $pic = $s.Shapes.AddPicture($plannerAsset, $msoFalse, $msoTrue, 558, 286, 330, 198)
    $pic.Line.ForeColor.RGB = $theme.MidGrey
} else {
    Add-Card $s "Explainability point" "The final result shows why a station is recommended: drive time, distance, arrival SOC, predicted occupancy, and rejection diagnostics." 560 318 320 104 $theme.Teal
}

# Slide 4
$s = Add-Slide "Dataset" "Data is split into routing data and occupancy-prediction data"
if (Test-Path $pipelineAsset) {
    $pic = $s.Shapes.AddPicture($pipelineAsset, $msoFalse, $msoTrue, 52, 112, 856, 394)
    $pic.Line.ForeColor.RGB = $theme.MidGrey
} else {
    Add-DatasetFlow $s
    Add-Text $s "Scale: road graph 67,966 nodes / 148,995 edges; station access 1,365 stations / 17,479 chargers; ML samples 720k rows." 58 466 840 20 12.5 $theme.Navy -Bold | Out-Null
    Add-Text $s "Leakage control: time-based split; lag features only use current/past values; historical profiles are computed from training data." 58 488 840 18 11.5 $theme.Grey | Out-Null
}

# Slide 5
$s = Add-Slide "Search Strategy" "Six algorithms, two comparison axes"
if (Test-Path $searchAsset) {
    $pic = $s.Shapes.AddPicture($searchAsset, $msoFalse, $msoTrue, 44, 104, 872, 424)
    $pic.Line.ForeColor.RGB = $theme.MidGrey
} else {
    Add-SearchVisuals $s
    Add-Text $s "Two comparison axes" 58 302 240 26 18 $theme.Navy -Bold | Out-Null
    Add-TableLike $s @(
        @("Search-space reduction", "BFS -> Bidirectional BFS -> CH Bidirectional Dijkstra", "frontier / preprocess"),
        @("Weighted shortest path", "UCS -> A* -> ALT A*", "cost / heuristic"),
        @("Counting scope", "expanded_nodes counts popped or settled nodes; bidirectional methods count both frontiers.", "diagnostics")
    ) 58 342 830 44
    Add-Text $s "Road graph scale: 67,966 nodes / 148,995 edges. Default recommendation evaluates up to 20 candidate stations inside a 10 km search radius." 58 486 845 30 12.5 $theme.Navy -Bold | Out-Null
}

# Slide 6
$s = Add-Slide "Constraints and Ranking" "Feasibility is checked before ranking; occupancy is only a risk signal"
Add-Card $s "Pre-check" "Before graph search: search radius, charger count, road access distance." 58 118 250 90 $theme.Green
Add-Card $s "Post-check" "After graph search: path found, drive time, energy use, arrival SOC." 356 118 250 90 $theme.Blue
Add-Card $s "Ranking" "Feasible stations are sorted by selected metric; balanced uses occupancy as risk." 654 118 250 90 $theme.Teal
if (Test-Path $rankingAsset) {
    $pic = $s.Shapes.AddPicture($rankingAsset, $msoFalse, $msoTrue, 82, 238, 800, 250)
    $pic.Line.ForeColor.RGB = $theme.MidGrey
} else {
    Add-Text $s "Balanced score" 72 332 240 28 20 $theme.Navy -Bold | Out-Null
    Add-Text $s "ml_rank_score = drive_time_min / max_drive_time_min + predicted_occupancy_rate" 72 370 720 34 17 $theme.Navy -Bold | Out-Null
    Add-Text $s "This does not convert occupancy into waiting time. The formula normalizes travel time and adds occupancy as congestion risk." 72 420 800 46 13.5 $theme.Grey | Out-Null
}

# Slide 7
$s = Add-Slide "Machine Learning Model" "XGBoost predicts future occupancy rate for the station arrival horizon"
if (Test-Path $featureAsset) {
    $pic = $s.Shapes.AddPicture($featureAsset, $msoFalse, $msoTrue, 52, 112, 856, 394)
    $pic.Line.ForeColor.RGB = $theme.MidGrey
} else {
    Add-Card $s "Prediction target" "target_occupancy_rate = occupancy_rate(t + prediction_horizon_min), where occupancy_rate = busy / total chargers." 58 128 270 140 $theme.Navy
    Add-Card $s "Model design" "A single multi-horizon XGBRegressor uses prediction_horizon_min as an input feature instead of training one model per horizon." 358 128 270 140 $theme.Teal
    Add-Card $s "Feature groups" "Time, weather, station profile, price, POI context, neighbor profile, and lag / rolling occupancy features." 658 128 270 140 $theme.Blue
    Add-Text $s "Why it matters for the route planner" 58 326 370 30 18 $theme.Navy -Bold | Out-Null
    Add-Bullets $s @(
        "Route search tells whether the station is reachable and how long it takes",
        "ML estimates how crowded the station may be near the arrival time",
        "The recommendation can show both travel metrics and congestion risk"
    ) 58 366 800 100 15 | Out-Null
}

# Slide 8
$s = Add-Slide "ML Results" "Time-split evaluation shows strong occupancy prediction performance"
Add-Card $s "Overall R2" "0.948742" 58 115 180 82 $theme.Teal
Add-Card $s "Overall MAE" "0.024937, around 2.5 percentage points." 268 115 220 82 $theme.Green
Add-Card $s "5 min R2" "0.9790, strongest at short horizon." 518 115 170 82 $theme.Blue
Add-Card $s "120 min R2" "0.8894, lower but still useful." 718 115 190 82 $theme.Red
if (Test-Path $figPath) {
    $pic = $s.Shapes.AddPicture($figPath, $msoFalse, $msoTrue, 62, 250, 420, 245)
    $pic.Line.ForeColor.RGB = $theme.MidGrey
}
Add-Text $s "Interpretation" 520 230 220 28 18 $theme.Navy -Bold | Out-Null
Add-Bullets $s @(
    "Shorter horizons are more accurate",
    "Lag and historical station profiles are important",
    "MAE should be explained in occupancy-rate units, not only as a model score"
) 520 268 370 92 13.5 | Out-Null
Add-LineChart $s $horizonCsv 520 410 350 96

# Slide 9
$s = Add-Slide "Performance and Complexity" "Results should be explained together with algorithmic trade-offs"
if (Test-Path $complexityAsset) {
    $pic = $s.Shapes.AddPicture($complexityAsset, $msoFalse, $msoTrue, 52, 118, 856, 360)
    $pic.Line.ForeColor.RGB = $theme.MidGrey
    Add-Text $s "Counting: expanded_nodes means popped / settled nodes; bidirectional methods count both frontiers; CH counts upward-graph settled nodes." 58 490 830 24 12.5 $theme.Navy -Bold | Out-Null
} else {
    Add-Card $s "Counting method" "expanded_nodes increments when a node is popped / settled. Bidirectional methods count both frontiers; CH counts settled upward-graph nodes." 58 120 270 130 $theme.Navy
    Add-Card $s "Runtime method" "runtime_seconds is measured per station route search. End-to-end recommendation cost depends on candidate count after pre-check." 358 120 270 130 $theme.Teal
    Add-Card $s "Path quality" "Weighted methods optimize travel time. BFS variants are useful baselines but not weighted shortest-path solvers." 658 120 250 130 $theme.Blue
    Add-Text $s "Complexity summary" 58 292 260 28 18 $theme.Navy -Bold | Out-Null
    Add-TableLike $s @(
        @("BFS", "O(V + E). Simple frontier expansion; ignores edge weights.", "baseline"),
        @("Bi-BFS", "O(V + E) worst-case; often reduces effective depth.", "two-frontier"),
        @("UCS", "Dijkstra-style O((V + E) log V) with travel-time cost.", "exact"),
        @("A* / ALT", "Same worst-case as UCS; fewer expansions with good heuristic.", "heuristic"),
        @("CH", "Offline ranks + shortcuts; online upward-graph query.", "preprocess")
    ) 58 330 500 32
    Add-Text $s "Concrete project scale" 610 292 260 28 18 $theme.Navy -Bold | Out-Null
    Add-Bullets $s @(
        "Road graph: 67,966 nodes / 148,995 edges",
        "Station access: 1,365 stations / 17,479 chargers",
        "CH index: 338,531 query edges / 192,196 shortcuts",
        "Default scope: top 20 candidates within 10 km"
    ) 610 332 300 105 12.5 | Out-Null
}

# Slide 10
$s = Add-Slide "Limitations and Conclusion" "A clear scope makes the project easier to defend"
Add-Card $s "Limitations" "No real waiting-time labels; occupancy is only congestion risk. No real-time traffic, live queue state, or charger-power dynamics." 58 126 390 154 $theme.Red
Add-Card $s "Future work" "Tune the congestion-risk weight, add live operational signals, and evaluate ranking behavior with user preference or real charging outcomes." 510 126 390 154 $theme.Teal
Add-Text $s "Conclusion" 58 330 250 30 20 $theme.Navy -Bold | Out-Null
Add-Text $s "OccuEVRoute integrates graph search, EV feasibility constraints, ML occupancy prediction, and explainable ranking into a coherent course-demo route planning system." 58 372 830 64 18 $theme.Navy | Out-Null
Add-Text $s "Q&A reminders: occupancy is not waiting time; ranking is heuristic and explainable; CH is an acceleration method, not a new objective function." 58 455 830 34 12.5 $theme.Grey | Out-Null

$presentation.SaveAs($outPath, $ppSaveAsOpenXMLPresentation)
$presentation.Close()
$ppt.Quit()

[System.Runtime.InteropServices.Marshal]::ReleaseComObject($presentation) | Out-Null
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null
Write-Output $outPath
