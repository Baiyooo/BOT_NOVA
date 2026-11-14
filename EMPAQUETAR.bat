@echo off
setlocal enabledelayedexpansion
title NovaBot - empaquetar
cd /d "%~dp0programa" 2>nul
if errorlevel 1 (
  echo  Falta la carpeta "programa" junto a este archivo.
  pause
  exit /b 1
)
set "PY="
py -3 -V >nul 2>&1
if !errorlevel! equ 0 set "PY=py -3"
if not defined PY (
  python -V >nul 2>&1
  if !errorlevel! equ 0 set "PY=python"
)
if not defined PY (
  set "P1=%LOCALAPPDATA%\Programs\Python\Python313"
  set "P2=%LOCALAPPDATA%\Programs\Python\Python312"
  if exist "!P1!\python.exe" set "PY=!P1!\python.exe"
  if exist "!P2!\python.exe" set "PY=!P2!\python.exe"
)
if not defined PY (
  echo.
  echo  No encuentro Python. Ejecuta INSTALAR.bat
  echo.
  pause
  exit /b 1
)
echo.
%PY% -m nucleo.empaquetar
echo.
echo  Para instalarlo en otro equipo: arrastra el .zip encima de ACTUALIZAR.bat alli.
echo.
pause
