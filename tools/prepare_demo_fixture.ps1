param(
    [string]$Target = (Join-Path $PSScriptRoot '..\fixtures\generated\demo'),
    [switch]$IncludeJunction
)

$ErrorActionPreference = 'Stop'
$targetPath = [System.IO.Path]::GetFullPath($Target)
if (Test-Path -LiteralPath $targetPath) {
    throw "Target already exists; refusing to overwrite: $targetPath"
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.Directory]::CreateDirectory($targetPath) | Out-Null

$empty = Join-Path $targetPath 'empty'
$deep = Join-Path $targetPath 'depth'
$many = Join-Path $targetPath 'many'
$thai = Join-Path $targetPath 'ชื่อ ไทย'
foreach ($directory in @($empty, $deep, $many, $thai)) {
    [System.IO.Directory]::CreateDirectory($directory) | Out-Null
}

$cursor = $deep
for ($level = 1; $level -le 8; $level++) {
    $cursor = Join-Path $cursor ('level-{0:D2}' -f $level)
    [System.IO.Directory]::CreateDirectory($cursor) | Out-Null
}
[System.IO.File]::WriteAllText((Join-Path $cursor 'leaf.txt'), 'deep', $utf8)

for ($number = 1; $number -le 60; $number++) {
    $file = Join-Path $many ('child-{0:D3}.txt' -f $number)
    [System.IO.File]::WriteAllText($file, 'x', $utf8)
}

[System.IO.File]::WriteAllText((Join-Path $thai 'รายงาน 1.txt'), 'hello', $utf8)
[System.IO.File]::WriteAllBytes((Join-Path $targetPath 'zero.bin'), [byte[]]@())
[System.IO.File]::WriteAllBytes((Join-Path $targetPath 'large.bin'), (New-Object byte[] (1024 * 1024)))

$files = @(Get-ChildItem -LiteralPath $targetPath -Recurse -File -Force)
$directories = @(Get-ChildItem -LiteralPath $targetPath -Recurse -Directory -Force)
$fileCount = $files.Count
$directoryCount = $directories.Count + 1
$logicalBytes = ($files | Measure-Object -Property Length -Sum).Sum

if ($IncludeJunction) {
    $junction = Join-Path $targetPath 'back-to-root'
    New-Item -ItemType Junction -Path $junction -Target $targetPath | Out-Null
}

[pscustomobject]@{
    Path = $targetPath
    RegularFiles = $fileCount
    DirectoriesIncludingRoot = $directoryCount
    ManyChildren = @(Get-ChildItem -LiteralPath $many -File).Count
    LogicalBytes = $logicalBytes
    JunctionIncluded = [bool]$IncludeJunction
}
