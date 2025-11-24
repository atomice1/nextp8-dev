#!/bin/sh
scriptdir="$(dirname "$0")"
basedir="$(dirname "${scriptdir}")"
version="$(python3 ${scriptdir}/gen-version.py)"
DESTDIR="$(mktemp -d)"
zipfile="${1:-nextp8_${version}.zip}"
if [ -f "${zipfile}" ]; then rm "${zipfile}"; fi
mkdir -p "${DESTDIR}/machines/nextp8/carts"
mkdir -p "${DESTDIR}/machines/nextp8/cartdata"
cp "${basedir}"/nextp8-loader/build/loader.bin "${DESTDIR}"/machines/nextp8/
cp "${basedir}"/femto8-nextp8/build-nextp8/femto8.bin "${DESTDIR}"/machines/nextp8/nextp8.bin
cp "${basedir}"/femto8-nextp8/carts/welcome.p8 "${DESTDIR}"/machines/nextp8/carts/welcome.p8
cp -r "${basedir}"/nextp8/machines/nextp8/core.cfg "${DESTDIR}"/machines/nextp8/
if [ "$2" != "--no-bitstream" ]; then
    cp "${basedir}"/nextp8-core/nextp8.runs/impl_1/nextp8.bit "${DESTDIR}"/machines/nextp8/core3.bit
fi
abszipfile="$(readlink -f "${zipfile}")"
oldpwd="${PWD}"
cd "${DESTDIR}"
zip -r "${abszipfile}" *
cd "${oldpwd}"
rm -r "${DESTDIR}"
