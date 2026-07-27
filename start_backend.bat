@echo off
set PYTHONPATH=c:\Projekty\FrigoCore\backend
c:\Python313\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause