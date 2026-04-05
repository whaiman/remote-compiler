# Run ruff checks and format
Write-Host "Running Ruff Format..." -ForegroundColor Cyan
ruff format rgcc tests

Write-Host "Running Ruff Check..." -ForegroundColor Cyan
ruff check rgcc tests --fix --show-fixes

Write-Host "Running MyPy..." -ForegroundColor Cyan
mypy rgcc --ignore-missing-imports --strict

Write-Host "Done!" -ForegroundColor Green
