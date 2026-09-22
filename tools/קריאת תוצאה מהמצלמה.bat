@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
echo.
echo   קורא את לוח התוצאות מהמצלמה ושולח לאפליקציה
echo   לעצירה: Ctrl+C
echo.
python tools\score_cam.py %*
pause
