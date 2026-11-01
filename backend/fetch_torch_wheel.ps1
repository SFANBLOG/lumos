# ============================================================
# 预下载 torch CPU wheel 到 backend/ 目录, 供 Dockerfile 构建使用
# 来源: 阿里云 pytorch CPU wheel 镜像 (国内 CDN, 支持断点续传)
# 首次构建前运行一次:
#   powershell -ExecutionPolicy Bypass -File .\fetch_torch_wheel.ps1
# ============================================================
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$wheel = 'torch-2.6.0+cpu-cp312-cp312-linux_x86_64.whl'
$out = Join-Path $dir $wheel
$url = 'https://mirrors.aliyun.com/pytorch-wheels/cpu/torch-2.6.0%2Bcpu-cp312-cp312-linux_x86_64.whl'

$hdr = curl.exe -sI --max-time 20 $url
$m = [regex]::Match($hdr, 'Content-Length:\s*(\d+)')
$exp = if ($m.Success) { [int64]$m.Groups[1].Value } else { 0 }
Write-Host "目标大小: $exp 字节"

for ($i = 0; $i -lt 40; $i++) {
    curl.exe -s -L -C - --max-time 300 -o $out $url
    $sz = (Get-Item $out -ErrorAction SilentlyContinue).Length
    Write-Host ("尝试 $i -> $sz 字节")
    if ($exp -gt 0 -and $sz -ge $exp) { Write-Host "下载完成: $out"; break }
    Start-Sleep -Seconds 2
}
