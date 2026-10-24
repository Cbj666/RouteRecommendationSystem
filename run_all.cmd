@echo off
rem 一键复现包装：绕过 PowerShell 执行策略，双击也能跑
rem 用法： run_all.cmd            (全流程)
rem        run_all.cmd -SkipTests
setlocal
cd /d "%~dp0"
where pwsh >nul 2>nul
if %errorlevel%==0 (
  pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_all.ps1" %*
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_all.ps1" %*
)
exit /b %errorlevel%
