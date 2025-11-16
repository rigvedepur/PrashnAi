@echo off
echo Starting PrashnAI Quiz App with conda environment...
set QUIZ_DIR=%~dp0QUIZ_DIR
echo QUIZ_DIR set to: %QUIZ_DIR%
C:\Users\Rigved\miniconda3\envs\prashnai-env\python.exe app.py
pause
