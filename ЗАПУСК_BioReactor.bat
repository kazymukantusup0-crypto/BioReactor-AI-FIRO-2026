@echo off
rem ==================================================================
rem  BioReactor AI - start everything with one double click.
rem  1) Python environment (.venv)   2) Ollama + model warm-up
rem  3) Frontend build (if missing)  4) Dashboard + browser on AI Chat
rem ==================================================================
chcp 65001 >nul
rem UTF-8 for every Python started from here (console output and files opened without an encoding),
rem so Russian/Kazakh text and signs like "−" or "→" never crash on the Windows cp1251 console.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
setlocal EnableExtensions
cd /d "%~dp0"
title BioReactor AI

set "PORT=8765"
rem Demo mode: every 150 s without questions the server sends the model a one-token "ping",
rem so the GPU and the model do not fall asleep between the jury's questions (src/agent_v10/keepalive.py).
rem The ping is skipped while an answer is running. Set 0 to switch it off.
if not defined BIOREACTOR_KEEPALIVE_S set "BIOREACTOR_KEEPALIVE_S=150"
if not defined OLLAMA_URL set "OLLAMA_URL=http://127.0.0.1:11434"
set "DASHBOARD_URL=http://127.0.0.1:%PORT%/dashboard/#/chat"

echo.
echo  ==============================================
echo     BioReactor AI - запуск
echo  ==============================================
echo.

rem ---------- 1. Python environment ----------
echo [1/4] Проверяю Python-окружение .venv ...
if exist ".venv\Scripts\python.exe" goto :venv_ready
echo       .venv не найден - создаю окружение. Нужен интернет, 3-5 минут.
py -3.13 -m venv .venv
if errorlevel 1 goto :error_python
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :error_pip
:venv_ready
call ".venv\Scripts\activate.bat"
echo       OK

rem ---------- 2. Ollama ----------
echo [2/4] Проверяю Ollama на %OLLAMA_URL% ...
curl -s -m 3 %OLLAMA_URL%/api/version >nul 2>&1
if not errorlevel 1 goto :ollama_ready
where ollama >nul 2>&1
if errorlevel 1 goto :ollama_missing
echo       Ollama не отвечает - запускаю ollama serve ...
start "Ollama" /min ollama serve
set /a WAITED=0
:wait_ollama
rem 1-second pause. ping is used instead of "timeout": Git for Windows puts
rem another "timeout" into PATH, and timeout.exe fails without a console.
"%SystemRoot%\System32\PING.EXE" -n 2 127.0.0.1 >nul
set /a WAITED+=1
curl -s -m 2 %OLLAMA_URL%/api/version >nul 2>&1
if not errorlevel 1 goto :ollama_ready
if %WAITED% lss 20 goto :wait_ollama
goto :ollama_missing

:ollama_ready
echo       OK. Прогреваю модель в видеопамяти, в фоне ...
start "" /b python scripts\warmup_llm.py
goto :frontend

:ollama_missing
echo.
echo   ВНИМАНИЕ: Ollama недоступна.
echo   Агент будет работать в режиме без ИИ-модели: те же расчёты, без свободной речи.
echo   Чтобы включить ИИ: установите Ollama с ollama.com, затем выполните
echo       ollama pull qwen3:8b
echo   и перезапустите start.bat.
echo.

rem ---------- 3. Frontend build ----------
:frontend
echo [3/4] Проверяю сборку интерфейса frontend\dist ...
rem Rebuild when the build is missing OR older than frontend\src (after git pull).
python scripts\frontend_needs_build.py
if errorlevel 1 goto :frontend_ready
where npm >nul 2>&1
if errorlevel 1 goto :no_npm
echo       Сборки нет или она устарела - собираю интерфейс. 1-3 минуты.
pushd frontend
if exist "node_modules" goto :npm_build
call npm ci
if errorlevel 1 (popd & goto :error_build)
:npm_build
call npm run build
if errorlevel 1 (popd & goto :error_build)
popd
:frontend_ready
echo       OK

goto :dashboard

:no_npm
if not exist "frontend\dist\index.html" goto :error_node
echo       ВНИМАНИЕ: интерфейс изменился, но Node.js/npm не найден - запускаю старую сборку.
echo       Чтобы увидеть новый интерфейс, установите Node.js LTS с nodejs.org.

rem ---------- 4. Dashboard ----------
:dashboard
echo [4/4] Запускаю дашборд ...
curl -s -m 2 http://127.0.0.1:%PORT%/health >nul 2>&1
if errorlevel 1 goto :run_dashboard
echo       Дашборд уже запущен - просто открываю браузер.
start "" "%DASHBOARD_URL%"
goto :end

:run_dashboard
echo       Адрес: %DASHBOARD_URL%
echo       Браузер откроется сам. Чтобы остановить - закройте это окно или нажмите Ctrl+C.
echo       Модель не засыпает: короткий пинг раз в %BIOREACTOR_KEEPALIVE_S% с, если нет вопросов.
echo.
python main.py dashboard --port %PORT%
if errorlevel 1 goto :error_dashboard
goto :end

rem ---------- Errors ----------
:error_python
echo.
echo   ОШИБКА: не найден Python 3.13. Установите его с python.org,
echo   отметьте галочку "Add python.exe to PATH" и запустите start.bat снова.
goto :fail

:error_pip
echo.
echo   ОШИБКА: не удалось установить Python-пакеты.
echo   Проверьте интернет и выполните вручную:
echo       .venv\Scripts\python -m pip install -r requirements.txt
goto :fail

:error_node
echo.
echo   ОШИБКА: нет папки frontend\dist и не найден Node.js/npm.
echo   Установите Node.js LTS с nodejs.org и запустите start.bat снова.
goto :fail

:error_build
echo.
echo   ОШИБКА: не удалось собрать интерфейс. Посмотрите сообщения npm выше.
goto :fail

:error_dashboard
echo.
echo   ОШИБКА: дашборд завершился с ошибкой. Частая причина - порт %PORT% занят
echo   другой программой. Закройте её или перезагрузите ноутбук.
goto :fail

:fail
echo.
pause
exit /b 1

:end
endlocal
