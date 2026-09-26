@call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
cl /nologo /O2 /LD fldrop.c ole32.lib shell32.lib user32.lib /Fe:fldrop.dll
