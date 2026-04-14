@echo off
REM Register USB Transfer watcher as a Windows Task Scheduler task (runs at login)
REM Run this script as Administrator

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
set PYTHON=python

echo Creating scheduled task: Wave2MP3_USB_Transfer
schtasks /create /tn "Wave2MP3_USB_Transfer" /tr "%PYTHON% -m usb_transfer.transfer" /sc ONLOGON /rl HIGHEST /f /sd %DATE%
echo.
echo Task created. The USB transfer watcher will start automatically at login.
echo To run manually: python -m usb_transfer.transfer
echo To remove: schtasks /delete /tn "Wave2MP3_USB_Transfer" /f
pause
