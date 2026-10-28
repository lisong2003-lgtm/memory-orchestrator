@echo off
setlocal
set "PY=%PYTHON%"
if "%PY%"=="" (py -3 >nul 2>&1 && set "PY=py -3") 
if "%PY%"=="" set "PY=python"
%PY% "%~dp0monitor_dialogs.py" %*
exit /b %ERRORLEVEL%
