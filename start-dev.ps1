Set-Location "C:\Users\dokun\PycharmProjects\R.A.M.B.O"

Write-Host ""
Write-Host "[ RAMBO ] Starting DEV mode (hot-reload, port 3001)..." -ForegroundColor Cyan
Write-Host ""

docker compose stop rambo-frontend 2>$null | Out-Null
docker compose up --build rambo-backend rambo-frontend-dev

Write-Host ""
Write-Host "[ RAMBO ] Dev frontend: http://localhost:3001" -ForegroundColor Green
