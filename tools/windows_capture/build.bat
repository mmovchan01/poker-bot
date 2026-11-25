@echo off
setlocal
where cl >nul 2>nul
if errorlevel 1 (
  echo Run this file from the x64 Native Tools Command Prompt for Visual Studio.
  pause
  exit /b 1
)
pushd "%~dp0"
cl /nologo /std:c++17 /EHsc /utf-8 /W4 /O2 /MT capture.cpp /Fe:GameCapture.exe /link gdiplus.lib shell32.lib
set "result=%errorlevel%"
if "%result%"=="0" (
  echo Done: %~dp0GameCapture.exe
) else (
  echo Build failed.
)
popd
pause
exit /b %result%
