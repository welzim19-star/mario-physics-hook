@echo off
set GCC=C:\Users\W3lz0\AppData\Local\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin\gcc.exe
set GPP=C:\Users\W3lz0\AppData\Local\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin\g++.exe
cd /d "D:\Modding\MarioPhysics"
echo [COMPILADOR] Compilando mario64_physics_new.dll...
"%GPP%" -shared -O2 -fno-strict-aliasing -std=c++20 -DSM64_LIB_EXPORT -static -static-libgcc -static-libstdc++ -I include -I minhook\include -I D:\Modding\er-mario\libsm64\src -o mario64_physics_new.dll src\dll_main.cpp obj_sm64\mh_buffer.o obj_sm64\mh_hook.o obj_sm64\mh_trampoline.o obj_sm64\mh_hde64.o libsm64.a -lwinmm -lxinput -lpsapi
if %errorlevel% equ 0 (
    echo [SUCESSO] mario64_physics_new.dll compilada com exito!
) else (
    echo [ERRO] Falha na compilacao! Codigo: %errorlevel%
)

