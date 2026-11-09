@echo off
rem Double-click to start Noodle (or run it from a terminal). Sets everything up the first time.
rem   run.bat            start (installs and builds on first run)
rem   run.bat --update   pull the latest code (needs Git), rebuild, then start
rem Needs Python 3.11-3.13 and Bun; if they are missing it offers to install them with winget.
rem Data is kept in .\data. Stop with Ctrl+C or by closing the window.
setlocal
cd /d "%~dp0"
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links;%USERPROFILE%\.bun\bin"

call :findpython
if not defined PY (
  echo Python 3.11, 3.12 or 3.13 was not found.
  call :ask "Install Python 3.12 now with winget" || goto :fail
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  call :findpython
  if not defined PY (
    echo Python was installed, but this window cannot see it yet. Close this window and double-click run.bat again.
    goto :fail
  )
)

if /i "%~1"=="--update" (
  git pull --ff-only || goto :fail
  if exist frontend\build rmdir /s /q frontend\build
  if exist .venv\.deps-ok del .venv\.deps-ok
)

if not exist frontend\build\index.html (
  where bun >nul 2>&1 || (
    echo Bun ^(needed once, to build the interface^) was not found.
    call :ask "Install Bun now with winget" || goto :fail
    winget install -e --id Oven-sh.Bun --accept-package-agreements --accept-source-agreements
    where bun >nul 2>&1 || (
      echo Bun was installed, but this window cannot see it yet. Close this window and double-click run.bat again.
      goto :fail
    )
  )
  echo Building the interface ^(first run, takes a minute^)...
  pushd frontend
  call bun install --frozen-lockfile || (popd & goto :fail)
  call bun run build || (popd & goto :fail)
  popd
)

if not exist .venv\.deps-ok (
  echo Installing Python packages...
  %PY% -m venv .venv || goto :fail
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\python -m pip install --quiet -r backend\requirements.txt || goto :fail
  type nul > .venv\.deps-ok
)

if not defined NOODLE_DATA set "NOODLE_DATA=%CD%\data"
set "NOODLE_STATIC=%CD%\frontend\build"
if not defined NOODLE_EXTRA_PORT set "NOODLE_EXTRA_PORT=0"
if not defined NOODLE_PORT set "NOODLE_PORT=8090"
if not exist "%NOODLE_DATA%" mkdir "%NOODLE_DATA%"

echo.
echo Noodle is starting. Open http://localhost:%NOODLE_PORT% in your browser.
echo Leave this window open while you use Noodle. Close it to stop.
echo.
cd backend
..\.venv\Scripts\python -m noodle
goto :fail

:findpython
set "PY="
for %%C in ("py -3.13" "py -3.12" "py -3.11" python) do (
  if not defined PY (
    %%~C -c "import sys; sys.exit(not ((3, 11) <= sys.version_info[:2] <= (3, 13)))" >nul 2>&1 && set "PY=%%~C"
  )
)
exit /b 0

:ask
choice /m %1
if errorlevel 2 exit /b 1
exit /b 0

:fail
echo.
echo Noodle stopped. Read the messages above, then press any key to close this window.
pause >nul
exit /b 1
