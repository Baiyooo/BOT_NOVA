@echo off
setlocal enabledelayedexpansion
rem ===================================================================
rem  NovaBot: el unico archivo para usar el bot.
rem
rem    BOT.bat              abre el bot (sin consola). La primera vez
rem                         instala lo que falte (Python, librerias, ADB).
rem    BOT.bat texto        menu en modo texto (si la ventana falla)
rem    BOT.bat diagnostico  informe del equipo en pantalla
rem
rem  Al abrirse, el propio bot (en segundo plano y sin ventanas) instala
rem  la version nueva que haya en Descargas, el lector de texto si falta
rem  y hace el diagnostico. Para EXPORTAR una version: EMPAQUETAR.bat.
rem ===================================================================
set "APP=%~dp0programa"
cd /d "%APP%" 2>nul
if errorlevel 1 (
  echo.
  echo  Falta la carpeta "programa" junto a este archivo.
  echo.
  pause
  exit /b 1
)
title NovaBot
set "DATOS=%LOCALAPPDATA%\NovaBot"
if not exist "%DATOS%" mkdir "%DATOS%" 2>nul
set "LOG=%DATOS%\instalacion.log"
set "MODO=%~1"

rem ---- 1) Python (si no esta, se instala una vez con winget) ----
call :BUSCAR_PY
if not defined PY (
  echo.
  echo  NovaBot: primera vez en este equipo. Instalo Python 3.12...
  echo  ^(si Windows pide permiso, acepta^)
  echo [winget] instalando Python >> "%LOG%"
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements >> "%LOG%" 2>&1
  set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
  call :BUSCAR_PY
)
if not defined PY (
  echo.
  echo  No he podido instalar Python solo.
  echo  Descargalo de https://www.python.org/downloads/ y marca
  echo  "Add python.exe to PATH" y "tcl/tk and IDLE". Luego abre BOT.bat otra vez.
  echo.
  pause
  exit /b 1
)

%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  Tu Python no trae tkinter, que es lo que dibuja la ventana.
  echo  Reinstala Python desde https://www.python.org/downloads/ marcando
  echo  "tcl/tk and IDLE". Mientras tanto: BOT.bat texto
  echo.
  pause
  exit /b 1
)

rem ---- 2) librerias (solo si faltan) ----
%PY% -c "import cv2, numpy" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  Instalo las librerias del bot ^(1-2 minutos, solo la primera vez^)...
  %PY% -m pip install --upgrade pip >> "%LOG%" 2>&1
  %PY% -m pip install opencv-python numpy rapidocr-onnxruntime -c requirements.txt >> "%LOG%" 2>&1
  %PY% -c "import cv2, numpy" >nul 2>&1
  if errorlevel 1 (
    echo  ERROR instalando librerias. Mira %LOG%
    pause
    exit /b 1
  )
)

rem ---- 3) ADB de BlueStacks: se activa una sola vez ----
if not exist "%DATOS%\adb_activado.txt" (
  %PY% main.py --activar-adb >> "%LOG%" 2>&1
  if errorlevel 2 (
    echo  ADB: BlueStacks esta abierto; se activara otra vez que lo abras cerrado. >> "%LOG%"
  ) else (
    > "%DATOS%\adb_activado.txt" echo %date% %time%
  )
)

if /i "%MODO%"=="texto" (
  %PY% main.py --menu
  pause
  exit /b 0
)
if /i "%MODO%"=="diagnostico" (
  %PY% -m nucleo.diagnostico_sistema
  pause
  exit /b 0
)

rem ---- 4) acceso directo NovaBot en el Escritorio (abre el bot sin consola) ----
set "PYW="
for /f "delims=" %%i in ('%PY% -c "import sys,os;p=os.path.join(os.path.dirname(sys.executable),'pythonw.exe');print(p if os.path.exists(p) else '')" 2^>nul') do set "PYW=%%i"
set "ICO=%APP%\recursos\NovaBot.ico"
set "DESTINO=%~dp0BOT.bat"
if defined PYW set "DESTINO=!PYW!"
set "RUTA_OK="
if exist "%DATOS%\acceso.txt" set /p RUTA_OK=<"%DATOS%\acceso.txt"
if not exist "%~dp0NovaBot.lnk" set "RUTA_OK="
if /i not "!RUTA_OK!"=="%~dp0;!DESTINO!" if exist "%ICO%" (
  > "%DATOS%\acceso.txt" echo %~dp0;!DESTINO!
  powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $dst='!DESTINO!'; $arg=''; if($dst -like '*pythonw.exe'){ $arg=[char]34+'%APP%\main.py'+[char]34 }; foreach($d in @('%~dp0', [Environment]::GetFolderPath('Desktop')+'\')){ $l=$w.CreateShortcut($d+'NovaBot.lnk'); $l.TargetPath=$dst; $l.Arguments=$arg; $l.WorkingDirectory='%APP%'; $l.IconLocation='%ICO%,0'; $l.WindowStyle=7; $l.Description='NovaBot'; $l.Save() }" >nul 2>&1
)

rem ---- 5) abrir la ventana ----
if defined PYW (
  start "" "%PYW%" "%APP%\main.py"
  exit /b 0
)
echo  Abriendo la ventana... ^(no cierres esto^)
%PY% "%APP%\main.py"
if errorlevel 1 (
  echo.
  echo  La ventana ha fallado. Mira %DATOS%\error_gui.log
  echo.
  pause
)
exit /b 0

:BUSCAR_PY
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
  if exist "!P1!\python.exe" set "PY="!P1!\python.exe""
  if exist "!P2!\python.exe" set "PY="!P2!\python.exe""
)
exit /b 0
