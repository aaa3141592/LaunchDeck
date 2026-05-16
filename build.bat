@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo =========================
echo LaunchDeck Build
echo =========================
echo.

REM =========================
REM clean
REM =========================
rmdir /s /q build_files 2>nul
del /q *.spec 2>nul
del /q launch_deck.exe 2>nul

mkdir build_files
mkdir build_files\build
mkdir build_files\dist

REM =========================
REM PyInstaller
REM =========================
python -m PyInstaller ^
  --clean ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --icon="settings_file\icon.ico" ^
  --name launch_deck ^
  --hidden-import=mido ^
  --hidden-import=mido.backends.rtmidi ^
  --hidden-import=rtmidi ^
  --hidden-import=python-rtmidi ^
  --collect-all=customtkinter ^
  --collect-all=pynput ^
  --collect-all=pystray ^
  --collect-all=PIL ^
  --add-data "core;core" ^
  --add-data "ui;ui" ^
  --add-data "settings_file;settings_file" ^
  --distpath "build_files\dist" ^
  --workpath "build_files\build" ^
  --specpath "." ^
  LaunchDeck.py

REM =========================
REM move exe
REM =========================
if exist "build_files\dist\launch_deck.exe" (
    move /y "build_files\dist\launch_deck.exe" "launch_deck.exe"
)

rmdir /s /q build_files 2>nul
del /q *.spec 2>nul

echo.
echo Output:
echo %cd%\launch_deck.exe
echo =========================
echo Build Complete
echo =========================
echo.

pause