Set-Location "C:\Users\dokun\PycharmProjects\R.A.M.B.O"

Write-Host ""
Write-Host "[ RAMBO ] Building + starting PROD mode (port 3000)..." -ForegroundColor Green
Write-Host ""

docker compose stop rambo-frontend-dev 2>$null | Out-Null
docker compose down
docker compose up --build rambo-backend rambo-frontend

Write-Host ""
Write-Host "[ RAMBO ] Production frontend: http://localhost:3000" -ForegroundColor Green
