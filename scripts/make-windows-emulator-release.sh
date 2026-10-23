#!/bin/bash
set -e
scriptdir="$(cd "$(dirname "$0")" && pwd)"
basedir="$(cd "${scriptdir}/.." && pwd)"
sqluxdir="${basedir}/sQLux-nextp8"
femto8dir="${basedir}/femto8-nextp8"

# Get femto8 version using the femto8 gen-version.py
FEMTO8_BASEDIR="${basedir}/femto8-nextp8"
if [ -f "${FEMTO8_BASEDIR}/gen-version.py" ]; then
    version="$(python3 ${FEMTO8_BASEDIR}/gen-version.py 2>/dev/null || echo "dev")"
elif [ -f "${FEMTO8_BASEDIR}/src/main.c" ]; then
    # Fallback: extract version from main.c
    version="$(grep -oP '#define\s+MAJOR_VERSION\s+\K\d+' ${FEMTO8_BASEDIR}/src/main.c 2>/dev/null || echo "dev")"
else
    version="dev"
fi

DESTDIR="$(mktemp -d)"
zipfile="${1:-/tmp/release.zip}"
if [ -f "${zipfile}" ]; then rm "${zipfile}"; fi

echo "Creating Windows release for femto8-nextp8 version ${version}"
echo "Destination directory: ${DESTDIR}"
echo "Output zip: ${zipfile}"

# Create directory structure
mkdir -p "${DESTDIR}/nextp8"
mkdir -p "${DESTDIR}/nextp8/carts"
mkdir -p "${DESTDIR}/nextp8/cartdata"
mkdir -p "${DESTDIR}/nextp8/roms"

# Check that binaries exist
if [ ! -f "${sqluxdir}/build-windows/sqlux.exe" ]; then
    echo "ERROR: sQLux Windows binary not found at ${sqluxdir}/build-windows/sqlux.exe"
    echo "Please build it first using: cd ${sqluxdir} && bash build_windows.sh"
    exit 1
fi

if [ ! -f "${sqluxdir}/build-windows/esp8266_test.exe" ]; then
    echo "ERROR: esp8266_test.exe not found at ${sqluxdir}/build-windows/"
    echo "Please build it first using: cd ${sqluxdir} && bash build_windows.sh"
    exit 1
fi

# Copy Windows executables
cp "${sqluxdir}/build-windows/sqlux.exe" "${DESTDIR}/nextp8/sqlux.exe"
cp "${sqluxdir}/build-windows/esp8266_test.exe" "${DESTDIR}/nextp8/esp8266_test.exe"

# Copy nextp8 loader ROM (required for femto8)
if [ ! -f "${basedir}/nextp8-loader/build/loader.bin" ]; then
    echo "ERROR: nextp8-loader ROM not found at ${basedir}/nextp8-loader/build/loader.bin"
    echo "Please build nextp8-loader first."
    exit 1
fi
cp "${basedir}/nextp8-loader/build/loader.bin" "${DESTDIR}/nextp8/roms/loader.bin"

# Copy SDL2.dll dependency
SDL2_DLL="${sqluxdir}/sdl2-mingw-build/build/bin/SDL2.dll"
if [ ! -f "${SDL2_DLL}" ]; then
    echo "ERROR: SDL2.dll not found at ${SDL2_DLL}"
    echo "Please build SDL2 first using build_windows.sh"
    exit 1
fi
cp "${SDL2_DLL}" "${DESTDIR}/nextp8/SDL2.dll"

# Copy MinGW runtime DLLs (required for statically linked executables)
#echo "Copying MinGW runtime DLLs..."
#MINGW_DLLS=(
#    "/usr/x86_64-w64-mingw32/lib/libwinpthread-1.dll"
#    "/usr/lib/gcc/x86_64-w64-mingw32/13-posix/libgcc_s_seh-1.dll"
#    "/usr/lib/gcc/x86_64-w64-mingw32/13-posix/libssp-0.dll"
#    "/usr/lib/gcc/x86_64-w64-mingw32/13-posix/libstdc++-6.dll"
#)
#for dll in "${MINGW_DLLS[@]}"; do
#    if [ -f "$dll" ]; then
#        cp "$dll" "${DESTDIR}/nextp8/"
#        echo "  Copied: $(basename $dll)"
#    else
#        echo "Warning: MinGW DLL not found: $dll"
#    fi
#done

# Copy default cart files from femto8-nextp8
femto8_carts_dir="${femto8dir}/carts"
if [ -f "${femto8_carts_dir}/welcome.p8" ]; then
    cp "${femto8_carts_dir}/welcome.p8" "${DESTDIR}/nextp8/carts/"
    cp "${femto8_carts_dir}/snake.p8" "${DESTDIR}/nextp8/carts/"
fi

# Build userguide HTML using pandoc
echo "Building userguide HTML..."
UG_DIR="${DESTDIR}/nextp8/user_guide"
mkdir -p "${UG_DIR}"
UG_SRC="${basedir}/nextp8/docs/ug"
if [ -d "${UG_SRC}" ]; then
    # Convert each markdown file to HTML
    for md_file in "${UG_SRC}"/*.md; do
        if [ -f "$md_file" ]; then
            base_name=$(basename "$md_file" .md)
            html_file="${UG_DIR}/${base_name}.html"
            # Use pandoc to convert to standalone HTML
            pandoc "$md_file" -f gfm -t html5 -s -o "$html_file" \
                --metadata title="nextp8 User Guide: ${base_name}" \
                --highlight-style pygments
            echo "  Built: ${base_name}.html"
        fi
    done
else
    echo "Warning: Userguide source not found at ${UG_SRC}"
fi

# Create Windows batch file to launch sQLux
cat > "${DESTDIR}/nextp8/start_nextp8_emulator.cmd" << 'BATCH_EOF'
@echo off
REM nextp8 Emulator launcher
REM This batch file starts sQLux with the correct options for nextp8

cd /d "%~dp0"

REM Check if help is requested
if "%1"=="--help" goto :help
if "%1"=="/h" goto :help
if "%1"=="/?" goto :help

REM Launch sQLux with nextp8-loader ROM, and SD card
sqlux.exe --rom1 roms/loader.bin --sdcard sdcard.img

goto :eof

:help
echo nextp8 Emulator
echo.
echo To launch sQLux, double-click this file or run:
echo   sqlux.exe --rom1 roms/loader.bin --sdcard sdcard.img
echo.
echo For more information, see:
echo   user_guide/README.html
echo.
pause
goto :eof
BATCH_EOF

# Create SD card image with default contents
echo "Creating SD card image..."
cd "${scriptdir}"
# Use project venv to ensure pyfatfs is available
. /home/chris/code/nextp8-dev/venv/bin/activate && \
python3 make-sdcard.py --no-bitstream -o "${DESTDIR}/nextp8/sdcard.img" -s 8 || \
{ echo "Error: pyfatfs module not found. Install with: pip install pyfatfs"; exit 1; }

# Create README for Windows
cat > "${DESTDIR}/nextp8/README_WINDOWS.txt" << 'README_EOF'
nextp8 Emulator
===============

Double-click "start_nextp8_emulator.cmd" to launch the sQLux emulator with
nextp8.

User guide HTML pages are available in the user_guide/ directory
README_EOF

# Create zip archive
abszipfile="$(readlink -f "${zipfile}")"
oldpwd="${PWD}"
cd "${DESTDIR}"
zip -r "${abszipfile}" *
cd "${oldpwd}"
rm -r "${DESTDIR}"

echo ""
echo "Windows release created: ${zipfile}"
ls -lh "${zipfile}"
