@echo off
REM Right-click -> "Run as administrator". Teammates ko port 5000 tak aane deta hai.
netsh advfirewall firewall add rule name="KahaniFM Hub 5000" dir=in action=allow protocol=TCP localport=5000
pause
