#!/bin/sh
set -e
scriptdir="$(dirname "$0")"
basedir="${scriptdir}"/..
version="$(python3 ${scriptdir}/gen-version.py)"
DESTDIR="$(mktemp -d)"
zipfile="${1:-nextp8_${version}.zip}"
if [ -f "${zipfile}" ]; then rm "${zipfile}"; fi
mkdir -p "${DESTDIR}/machines/nextp8/carts"
mkdir -p "${DESTDIR}/machines/nextp8/cartdata"
mkdir -p "${DESTDIR}/docs/guides"
mkdir -p "${DESTDIR}/docs/extracores"
mkdir -p "${DESTDIR}/docs/licenses/nextp8"
cp "${basedir}"/nextp8-loader/build/loader.bin "${DESTDIR}"/machines/nextp8/
cp "${basedir}"/femto8-nextp8/build-nextp8/femto8.bin "${DESTDIR}"/machines/nextp8/nextp8.bin
cp "${basedir}"/femto8-nextp8/carts/welcome.p8 "${DESTDIR}"/machines/nextp8/carts/welcome.p8
cp "${basedir}"/femto8-nextp8/carts/snake.p8 "${DESTDIR}"/machines/nextp8/carts/snake.p8
cp "${basedir}"/nextp8/machines/nextp8/core.cfg "${DESTDIR}"/machines/nextp8/
cp "${basedir}"/nextp8/docs/QUICKSTART.txt "${DESTDIR}"/docs/extracores/nextp8.txt
grep -A 10000 '^\(Licenses\|Licences\)' "${basedir}"/nextp8/docs/download.md >"${DESTDIR}"/docs/licenses/nextp8-license.md
cp "${basedir}"/nextp8/docs/licences/*NOTICES* "${DESTDIR}"/docs/licenses/nextp8
cp "${basedir}"/nextp8/docs/licences/gpl-3.0.txt "${DESTDIR}"/docs/licenses/nextp8
cp "${basedir}"/nextp8/docs/licences/apache-2.0.txt "${DESTDIR}"/docs/licenses/nextp8
if [ "$2" != "--no-bitstream" ]; then
    cp "${basedir}"/nextp8-core/nextp8-issue5.runs/impl_1/nextp8_top_issue5.bit "${DESTDIR}"/machines/nextp8/core3.bit
fi
"${scriptdir}/md_to_nextguide.py" "${basedir}"/nextp8/docs/ug "${DESTDIR}"/docs/guides/nextp8.gde
abszipfile="$(readlink -f "${zipfile}")"
oldpwd="${PWD}"
cd "${DESTDIR}"
zip -r "${abszipfile}" *
cd "${oldpwd}"
rm -r "${DESTDIR}"
