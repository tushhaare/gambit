@echo off
title KahaniFM - Team link (Tailscale Funnel)
REM Free public https link teammates ke liye. Pehle Tailscale install + login karo.
where tailscale >nul 2>nul || set "PATH=%PATH%;C:\Program Files\Tailscale"
echo.
echo  Team link chalu kar raha hoon (port 5000)...
echo  Pehli baar browser mein Tailscale "Funnel enable" ka page khul sakta hai - Allow/Enable dabao.
echo.
tailscale funnel --bg 5000
echo.
echo  ==== Aapka team link ====
tailscale funnel status
echo.
echo  Upar wala https://....ts.net link teammates ko bhejo.
echo  Ye link PC restart ke baad bhi wahi rehta hai (bas Tailscale + run.bat chalu ho).
echo  Band karna ho to:  tailscale funnel --https=443 off
pause
