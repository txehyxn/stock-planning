@echo off
rem ==============================================================================
rem 파일명: restore.bat
rem 설명: PostgreSQL(stock_db) Docker 컨테이너 데이터베이스 복원 및 정합성 검증 스크립트
rem 사용:
rem   - 최근 백업 자동 복원: restore.bat
rem   - 특정 백업 수동 복원: restore.bat [백업파일경로]
rem ==============================================================================

echo ================================================================
echo [DBA] PostgreSQL Docker 컨테이너 데이터베이스 복원 시작
echo ================================================================

rem 1. stock_db 컨테이너 실행 여부 점검
docker inspect -f "{{.State.Running}}" stock_db 2>nul | findstr "true" >nul
if errorlevel 1 (
    echo [오류] stock_db 컨테이너가 실행 중이지 않습니다.
    echo 먼저 'docker compose up -d'를 실행하여 DB 컨테이너를 구동해 주세요.
    exit /b 1
)

rem 2. 복원 대상 백업 파일 결정
set "RESTORE_FILE="
if not "%~1"=="" goto use_arg

echo [안내] 지정된 파일이 없어 backups 폴더에서 가장 최근 백업 파일을 탐색합니다...
for /f "delims=" %%F in ('dir /b /o:-d backups\stock_db_backup_*.sql 2^>nul') do (
    if not defined RESTORE_FILE set "RESTORE_FILE=backups\%%F"
)
goto check_file

:use_arg
set "RESTORE_FILE=%~1"

:check_file
if "%RESTORE_FILE%"=="" (
    echo [오류] backups 폴더 내에 복원 가능한 백업 파일 [*.sql]이 존재하지 않습니다.
    echo 먼저 'backup.bat'을 실행하여 백업 파일을 생성해 주세요.
    exit /b 1
)

if not exist "%RESTORE_FILE%" (
    echo [오류] 지정된 백업 파일을 찾을 수 없습니다: %RESTORE_FILE%
    exit /b 1
)

rem 3. 복원 실행
echo.
echo - 복원 대상 파일: %RESTORE_FILE%
echo [진행] psql을 통해 stock_db로 복원 쿼리를 실행 중입니다...

docker exec -i stock_db psql -U postgres -d stock_db < "%RESTORE_FILE%"

if errorlevel 1 (
    echo.
    echo [오류] 데이터베이스 복원 작업 중 오류가 발생했습니다.
    exit /b 1
)

rem 4. 복구 정상 여부 검증 (테이블별 건수 SELECT)
echo.
echo ================================================================
echo [완료] 데이터베이스 복원 작업이 성공적으로 완료되었습니다!
echo [검증] 복원된 테이블별 레코드 건수 확인:
echo ----------------------------------------------------------------
docker exec -i stock_db psql -U postgres -d stock_db -c "SELECT 'daily_stock_prices' AS table_name, count(*) AS row_count FROM daily_stock_prices UNION ALL SELECT 'stock_predictions', count(*) AS row_count FROM stock_predictions;"
echo ================================================================

exit /b 0

