@echo off
setlocal enabledelayedexpansion

:: Get script directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Configure paths with absolute paths
set "PYTHON_PATH=python.exe"
set "SAVE_SCRIPT=%SCRIPT_DIR%save_links.py"
set "UPLOAD_SCRIPT=%SCRIPT_DIR%AutoUploader.py"
set "LINKS_DIR=%SCRIPT_DIR%pending_links"
set "LOG_FILE=%SCRIPT_DIR%logs\upload_%date:~-4,4%%date:~-7,2%%date:~-10,2%_%time:~0,2%%time:~3,2%.log"

:: Retry configuration
set MAX_RETRIES=3
set INITIAL_DELAY=2
set BACKOFF_FACTOR=2

:: Create required directories if they don't exist
if not exist "%SCRIPT_DIR%config\" mkdir "%SCRIPT_DIR%config"
if not exist "%SCRIPT_DIR%logs\" mkdir "%SCRIPT_DIR%logs"
if not exist "%SCRIPT_DIR%track_log\" mkdir "%SCRIPT_DIR%track_log"
if not exist "%LINKS_DIR%\" mkdir "%LINKS_DIR%"

:: Set log file path
set "LOG_FILE=%SCRIPT_DIR%logs\upload_%date:~-4,4%%date:~-7,2%%date:~-10,2%_%time:~0,2%%time:~3,2%.log"

:: Clear previous log and initialize
echo [%date% %time%] Script started > "%LOG_FILE%"
echo [%date% %time%] Working Directory: %cd% >> "%LOG_FILE%"
echo [%date% %time%] Python Path: %PYTHON_PATH% >> "%LOG_FILE%"
echo [%date% %time%] Script Path: %UPLOAD_SCRIPT% >> "%LOG_FILE%"
echo [%date% %time%] Retry Settings: Max=%MAX_RETRIES% InitialDelay=%INITIAL_DELAY%s Backoff=%BACKOFF_FACTOR%x >> "%LOG_FILE%"

:: Main processing
if "%~2"=="" (
    if "%~1"=="" (
        echo Manual mode - enter details:
        set /p "link=Download link: "
        set /p "filename=Filename: "
        set "filepath="
        echo [%date% %time%] Manual mode input >> "%LOG_FILE%"
        
        :: Save the link first with retries
        call :SAVE_WITH_RETRY "!link!" "!filename!"
    ) else (
        :: Handle dropped file - save link first with retries
        set "link=%~f1"
        set "filename=%~1"
        set "filepath=%~f1"
        echo [%date% %time%] Processing dropped file: %~1 >> "%LOG_FILE%"
        call :SAVE_WITH_RETRY "!link!" "!filename!" "!filepath!"
    )
) else (
    :: Handle FileUploader submission - save link first with retries
    set "link=%~1"
    set "filename=%~2"
    set "filepath="
    echo [%date% %time%] Processing FileUploader submission >> "%LOG_FILE%"
    call :SAVE_WITH_RETRY "!link!" "!filename!"
)

:: Process all pending links with retries
call :PROCESS_QUEUE_WITH_RETRY

:: Final status
if errorlevel 1 (
    echo [%date% %time%] ERROR: Processing completed with errors >> "%LOG_FILE%"
    timeout /t 3 >nul
    exit /b 1
) else (
    echo [%date% %time%] Processing completed successfully >> "%LOG_FILE%"
    timeout /t 3 >nul
    exit /b 0
)

:: ----------------------------
:: Subroutines
:: ----------------------------

:SAVE_WITH_RETRY
setlocal
set RETRY_COUNT=0
set CURRENT_DELAY=%INITIAL_DELAY%

:SAVE_ATTEMPT
echo [%date% %time%] Saving link (Attempt !RETRY_COUNT! of %MAX_RETRIES%) >> "%LOG_FILE%"
"%PYTHON_PATH%" "%SAVE_SCRIPT%" %* >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    set /a RETRY_COUNT+=1
    if !RETRY_COUNT! lss %MAX_RETRIES% (
        echo [%date% %time%] Save failed, retrying in !CURRENT_DELAY! seconds >> "%LOG_FILE%"
        timeout /t !CURRENT_DELAY! >nul
        set /a CURRENT_DELAY*=BACKOFF_FACTOR
        goto SAVE_ATTEMPT
    )
    echo [%date% %time%] ERROR: Failed to save link after %MAX_RETRIES% attempts >> "%LOG_FILE%"
    endlocal
    exit /b 1
)
endlocal
exit /b 0

:PROCESS_QUEUE_WITH_RETRY
setlocal
set RETRY_COUNT=0
set CURRENT_DELAY=%INITIAL_DELAY%

:QUEUE_ATTEMPT
echo [%date% %time%] Processing queue (Attempt !RETRY_COUNT! of %MAX_RETRIES%) >> "%LOG_FILE%"
"%PYTHON_PATH%" "%UPLOAD_SCRIPT%" --process-queue >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    set /a RETRY_COUNT+=1
    if !RETRY_COUNT! lss %MAX_RETRIES% (
        echo [%date% %time%] Queue processing failed, retrying in !CURRENT_DELAY! seconds >> "%LOG_FILE%"
        timeout /t !CURRENT_DELAY! >nul
        set /a CURRENT_DELAY*=BACKOFF_FACTOR
        goto QUEUE_ATTEMPT
    )
    echo [%date% %time%] ERROR: Failed to process queue after %MAX_RETRIES% attempts >> "%LOG_FILE%"
    endlocal
    exit /b 1
)
endlocal
exit /b 0