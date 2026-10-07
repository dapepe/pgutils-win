@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"
set "CLI_PATH=%ROOT_DIR%\cli.py"
set "VENV_DIR=%ROOT_DIR%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQS=%ROOT_DIR%\requirements.txt"

if not exist "%REQS%" (
  echo requirements.txt not found at "%REQS%" 1>&2
  exit /b 1
)

if not exist "%VENV_PY%" (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv "%VENV_DIR%"
  ) else (
    where python >nul 2>nul
    if not errorlevel 1 (
      python -m venv "%VENV_DIR%"
    ) else (
      echo Python not found in PATH. Install Python 3 or use the Python launcher ^(py^). 1>&2
      exit /b 1
    )
  )

  if not exist "%VENV_PY%" (
    echo Failed to create virtual environment at "%VENV_DIR%" 1>&2
    exit /b 1
  )
)

"%VENV_PY%" -c "import typer, rich" >nul 2>nul
if %ERRORLEVEL%==0 goto run_cli

"%VENV_PY%" -m pip install -r "%REQS%"
if %ERRORLEVEL% NEQ 0 (
  echo Failed to install dependencies from "%REQS%" 1>&2
  exit /b 1
)

:run_cli
"%VENV_PY%" "%CLI_PATH%" %*
exit /b %ERRORLEVEL%
