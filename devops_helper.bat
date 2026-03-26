@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_NAME=%~n0"
set "ACTION=%~1"
set "COMMIT_MSG=%~2"

set "SPACE_URL=https://huggingface.co/spaces/kmkarakaya/openLLMbenchmark"
set "SPACE_BRANCH=main"
set "TMP_DIR="

if "%ACTION%"=="" goto :usage
if /I "%ACTION%"=="help" goto :usage
if /I "%ACTION%"=="github" goto :run_github
if /I "%ACTION%"=="hf" goto :run_hf
if /I "%ACTION%"=="all" goto :run_all

echo [ERROR] Unknown action: %ACTION%
goto :usage_error

:usage
echo Usage:
echo   .\devops_helper.bat github "commit message"
echo   .\devops_helper.bat hf
echo   .\devops_helper.bat all "commit message"
echo.
echo Actions:
echo   github  Stages all changes, commits, and pushes to origin/current-branch.
echo   hf      Deploys current HEAD to Hugging Face Space (binary-safe snapshot).
echo   all     Runs github first, then hf.
echo.
echo Notes:
echo   - Run this script from anywhere inside the git repo.
echo   - For hf deploy, your working tree must be clean.
exit /b 0

:usage_error
exit /b 1

:ensure_repo
set "REPO_ROOT="
for /f "delims=" %%I in ('git rev-parse --show-toplevel 2^>nul') do set "REPO_ROOT=%%I"
if not defined REPO_ROOT (
  echo [ERROR] Not inside a git repository.
  exit /b 1
)
cd /d "%REPO_ROOT%"
exit /b 0

:get_current_branch
set "CURRENT_BRANCH="
for /f "delims=" %%I in ('git branch --show-current') do set "CURRENT_BRANCH=%%I"
if not defined CURRENT_BRANCH (
  echo [ERROR] Could not detect current branch.
  exit /b 1
)
exit /b 0

:is_clean_tree
git diff --quiet
if errorlevel 1 exit /b 1
git diff --cached --quiet
if errorlevel 1 exit /b 1
exit /b 0

:require_clean_tree
call :is_clean_tree
if errorlevel 1 (
  echo [ERROR] Working tree must be clean. Commit or stash your changes first.
  exit /b 1
)
exit /b 0

:run_github
call :ensure_repo || exit /b 1
call :get_current_branch || exit /b 1

call :is_clean_tree
if errorlevel 1 (
  if "%COMMIT_MSG%"=="" (
    echo [ERROR] Commit message is required when there are local changes.
    echo Example: %SCRIPT_NAME% github "Fix scoring edge cases"
    exit /b 1
  )
  echo [INFO] Staging all changes...
  git add -A || exit /b 1
  echo [INFO] Creating commit...
  git commit -m "%COMMIT_MSG%" || exit /b 1
) else (
  echo [INFO] Working tree is clean. Nothing to commit.
)

echo [INFO] Pushing to origin/%CURRENT_BRANCH%...
git push origin %CURRENT_BRANCH% || exit /b 1
echo [OK] GitHub push completed.
exit /b 0

:run_hf
call :ensure_repo || exit /b 1
call :get_current_branch || exit /b 1
call :require_clean_tree || exit /b 1

for /f "delims=" %%I in ('git rev-parse HEAD') do set "SOURCE_SHA=%%I"

if not exist "README.md" (
  echo [ERROR] README.md not found at repo root.
  exit /b 1
)

echo [INFO] Creating clean deployment snapshot for Hugging Face Space...
set "TMP_DIR=%TEMP%\hf_space_deploy_%RANDOM%%RANDOM%%RANDOM%"
mkdir "%TMP_DIR%" || (
  echo [ERROR] Could not create temp directory: %TMP_DIR%
  exit /b 1
)

robocopy "%REPO_ROOT%" "%TMP_DIR%" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP ^
  /XD ".git" ".pytest_cache" "__pycache__" ".venv" "venv" "env" "image\README" ^
  /XF "*.pyc" "*.pyo" "*.pyd" "*.log" "_debug_sidebar*.png" "*.docx" >nul
set "ROBO_EXIT=%ERRORLEVEL%"
if %ROBO_EXIT% GEQ 8 (
  echo [ERROR] Failed to prepare temp snapshot (robocopy exit=%ROBO_EXIT%).
  set "EXIT_CODE=1"
  goto :cleanup
)

pushd "%TMP_DIR%" || (
  echo [ERROR] Could not enter temp directory.
  set "EXIT_CODE=1"
  goto :cleanup
)

git init >nul || (
  echo [ERROR] git init failed in temp snapshot.
  popd
  set "EXIT_CODE=1"
  goto :cleanup
)
git config user.name "hf-space-deployer" >nul
git config user.email "hf-space-deployer@local" >nul
git add . || (
  echo [ERROR] git add failed in temp snapshot.
  popd
  set "EXIT_CODE=1"
  goto :cleanup
)
git commit -m "HF Space deploy from %CURRENT_BRANCH% (%SOURCE_SHA%)" >nul || (
  echo [ERROR] git commit failed in temp snapshot.
  popd
  set "EXIT_CODE=1"
  goto :cleanup
)
git remote add hf "%SPACE_URL%" >nul

setlocal EnableDelayedExpansion
set "REMOTE_SHA="
for /f "tokens=1" %%H in ('git ls-remote hf refs/heads/%SPACE_BRANCH%') do if not defined REMOTE_SHA set "REMOTE_SHA=%%H"
if defined REMOTE_SHA (
  git push hf HEAD:%SPACE_BRANCH% --force-with-lease=refs/heads/%SPACE_BRANCH%:!REMOTE_SHA!
  if errorlevel 1 (
    echo [WARN] Lease check failed. Refreshing remote ref and retrying once...
    set "REMOTE_SHA="
    for /f "tokens=1" %%H in ('git ls-remote hf refs/heads/%SPACE_BRANCH%') do if not defined REMOTE_SHA set "REMOTE_SHA=%%H"
    if defined REMOTE_SHA (
      git push hf HEAD:%SPACE_BRANCH% --force-with-lease=refs/heads/%SPACE_BRANCH%:!REMOTE_SHA!
    ) else (
      git push hf HEAD:%SPACE_BRANCH% --force
    )
  )
) else (
  git push hf HEAD:%SPACE_BRANCH% --force
)
set "PUSH_EXIT=!ERRORLEVEL!"
endlocal & set "PUSH_EXIT=%PUSH_EXIT%"

popd

if not "%PUSH_EXIT%"=="0" (
  echo [ERROR] Hugging Face push failed.
  set "EXIT_CODE=1"
  goto :cleanup
)

echo [OK] Hugging Face Space deploy completed.
set "EXIT_CODE=0"
goto :cleanup

:run_all
if "%COMMIT_MSG%"=="" (
  echo [ERROR] Commit message is required for 'all'.
  echo Example: %SCRIPT_NAME% all "Update benchmark UI"
  exit /b 1
)

call :run_github
if errorlevel 1 exit /b 1

call :run_hf
exit /b %ERRORLEVEL%

:cleanup
if defined TMP_DIR (
  if exist "%TMP_DIR%" rmdir /s /q "%TMP_DIR%"
)
if not defined EXIT_CODE set "EXIT_CODE=1"
exit /b %EXIT_CODE%
