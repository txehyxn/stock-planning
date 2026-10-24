@echo off
rem ==============================================================================
rem 파일명: backup.bat
rem 설명: PostgreSQL(stock_db) Docker 컨테이너 데이터베이스 자동 덤프 백업 스크립트
rem 저장: backups\stock_db_backup_YYYYMMDD_HHMMSS.sql
rem ==============================================================================

echo ================================================================
echo [DBA] PostgreSQL Docker 컨테이너 무중단 스냅샷 백업 시작
echo ================================================================

rem 1. backups 폴더 유무 확인 및 자동 생성
if not exist "backups" (
    echo [안내] backups 폴더가 없어 새로 생성합니다...
    mkdir "backups"
)

rem 2. 현재 날짜와 시간 YYYYMMDD_HHMMSS 타임스탬프 추출
for /f %%a in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TIMESTAMP=%%a
set "BACKUP_FILE=backups\stock_db_backup_%TIMESTAMP%.sql"

rem 3. stock_db 컨테이너 실행 여부 점검
docker inspect -f "{{.State.Running}}" stock_db 2>nul | findstr "true" >nul
if errorlevel 1 (
    echo [오류] stock_db 컨테이너가 실행 중이지 않습니다.
    echo 먼저 'docker compose up -d'를 실행하여 DB 컨테이너를 구동해 주세요.
    exit /b 1
)

rem 4. Docker exec를 통한 pg_dump 덤프 추출
echo [진행] stock_db 덤프 생성 중...
docker exec -i stock_db pg_dump -U postgres -d stock_db --clean --if-exists > "%BACKUP_FILE%"

if errorlevel 1 (
    echo [오류] pg_dump 백업 추출에 실패했습니다.
    if exist "%BACKUP_FILE%" del "%BACKUP_FILE%"
    exit /b 1
)

rem 5. 완료 결과 및 파일 크기 출력
echo.
echo ================================================================
echo [완료] PostgreSQL 데이터베이스 백업이 성공적으로 완료되었습니다!
for %%I in ("%BACKUP_FILE%") do (
    echo - 백업 파일 경로 : %%~fI
    echo - 백업 파일 크기 : %%~zI 바이트
)
echo ================================================================

exit /b 0

