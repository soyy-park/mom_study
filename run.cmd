@echo off
rem This project lives inside a Google Drive synced folder. The virtual env must
rem live OUTSIDE Drive (on the local disk) or pip/uv become slow and lock up.
rem This wrapper tells uv where the env is, then forwards the command as-is.
rem
rem Examples:
rem   run.cmd sync                        - install / update dependencies
rem   run.cmd run python capture_app.py   - run the capture GUI
rem   run.cmd run python ocr_pipeline.py --selftest
setlocal
if "%UV_PROJECT_ENVIRONMENT%"=="" set "UV_PROJECT_ENVIRONMENT=%LOCALAPPDATA%\uv-envs\quiz-capture"
uv %*
