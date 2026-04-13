Write-Host "Starting FastAPI Backend..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd backend; .\`.venv\Scripts\uvicorn.exe main:app --reload`""

Write-Host "Starting React + Electron Frontend..." -ForegroundColor Green
cd frontend
npm run dev
