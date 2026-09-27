#!/usr/bin/env bash
# Build OfficeR's three Linux packages from one frozen tree.
#
#   packaging/build_dist.sh             # writes into ~/Apps
#   OUT=/tmp/x packaging/build_dist.sh  # or wherever they should land
#
# The tree comes from packaging/officer.spec (PyInstaller), so what a user
# installs carries its own Python and Qt: nothing is asked of their system
# beyond the libraries a desktop Linux already has.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV="${OFFICER_VENV:-${HOME}/.officer-build/venv}"
PY="${VENV}/bin/python"
OUT="${OUT:-${HOME}/Apps}"
TOOLS="${HOME}/.officer-build"
BUILD="${ROOT}/dist/build"
PAYLOAD="${BUILD}/officer"

VERSION="$("${PY}" -c 'import tomllib,pathlib;print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])')"
MACHINE="$(uname -m)"
case "${MACHINE}" in
    x86_64) DEB_ARCH="amd64" ;;
    aarch64) DEB_ARCH="arm64" ;;
    *) DEB_ARCH="$(dpkg --print-architecture)" ;;
esac
NAME="OfficeR-${VERSION}-linux-${MACHINE}"

#: One launcher per application: the frozen binary reads --app and runs it.
write_wrappers() {
    local dest="$1" binroot="$2" app suffix
    mkdir -p "${dest}"
    for app in hub writer rsheet presentr; do
        suffix=""; [ "${app}" != "hub" ] && suffix="-${app}"
        printf '#!/usr/bin/env bash\nexec "%s/officer" --app %s "$@"\n' \
            "${binroot}" "${app}" > "${dest}/officer${suffix}"
        chmod +x "${dest}/officer${suffix}"
    done
}

#: The desktop entries, with Exec aimed at where this package puts its launchers.
write_desktop() {
    local dest="$1" binroot="$2" file
    mkdir -p "${dest}"
    for file in "${ROOT}"/desktop/*.desktop; do
        if [ -n "${binroot}" ]; then
            sed "s|^Exec=officer|Exec=${binroot}/officer|" "${file}" \
                > "${dest}/$(basename "${file}")"
        else
            cp "${file}" "${dest}/"
        fi
    done
}

write_icons() {
    local dest="$1" app
    mkdir -p "${dest}"
    for app in officer officer-writer officer-rsheet officer-presentr; do
        cp "${ROOT}/officer/assets/logo.png" "${dest}/${app}.png"
    done
}

echo "==> OfficeR ${VERSION} (${MACHINE}), frozen tree from ${VENV}"

# -- 1. the one binary every package wraps ------------------------------------ #

"${VENV}/bin/pyinstaller" --noconfirm --clean \
    --distpath "${BUILD}" --workpath "${BUILD}/work" \
    "${SCRIPT_DIR}/officer.spec"
test -x "${PAYLOAD}/officer"
mkdir -p "${OUT}"

# -- 2. the tarball: unpack it and run it, on any Linux ----------------------- #

TAR_ROOT="${BUILD}/${NAME}"
rm -rf "${TAR_ROOT}"; mkdir -p "${TAR_ROOT}"
cp -r "${PAYLOAD}/." "${TAR_ROOT}/"
write_wrappers "${TAR_ROOT}/bin" "${TAR_ROOT}"
write_desktop "${TAR_ROOT}/share/applications" "${TAR_ROOT}/bin"
write_icons "${TAR_ROOT}/share/icons/hicolor/512x512/apps"
cp "${SCRIPT_DIR}/install.sh" "${TAR_ROOT}/install.sh"
chmod +x "${TAR_ROOT}/install.sh"
cat > "${TAR_ROOT}/README-install.txt" <<EOF
OfficeR ${VERSION}

Run an application straight from this folder:

    ./bin/officer-writer notes.docx
    ./bin/officer-rsheet
    ./bin/officer-presentr
    ./bin/officer            (the hub, which opens all three)

To have the desktop menu and file manager find them, install as root:

    sudo ./install.sh

Nothing else is needed: this build carries its own Python and Qt.
EOF
echo "==> ${OUT}/${NAME}.tar.gz"
tar -czf "${OUT}/${NAME}.tar.gz" -C "${BUILD}" "${NAME}"

# -- 3. the .deb -------------------------------------------------------------- #

DEB="${BUILD}/deb"
rm -rf "${DEB}"
mkdir -p "${DEB}/opt/officer" "${DEB}/usr/bin" "${DEB}/DEBIAN"
cp -r "${PAYLOAD}/." "${DEB}/opt/officer/"
write_wrappers "${DEB}/usr/bin" "/opt/officer"
write_desktop "${DEB}/usr/share/applications" ""
write_icons "${DEB}/usr/share/icons/hicolor/512x512/apps"
cat > "${DEB}/DEBIAN/control" <<EOF
Package: officer
Version: ${VERSION}
Section: editors
Priority: optional
Architecture: ${DEB_ARCH}
Maintainer: Amlan <sheulyrani1986@gmail.com>
Depends: libgl1, libegl1, libxkbcommon0, libxkbcommon-x11-0, libdbus-1-3, libfontconfig1, libglib2.0-0t64, libx11-6, libx11-xcb1, libxcb1, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-shm0, libxcb-sync1, libxcb-xfixes0, libxcb-xinerama0, libxcb-xkb1, libxi6, libxrender1, libsm6, libice6, zlib1g, liblzma5, libzstd1
Description: OfficeR, a Linux-native office suite
 WriteR (word processor), RSheet (spreadsheet) and PresentR (presentations),
 each dressed like its Microsoft 365 counterpart and reading and writing the
 .docx, .odt, .xlsx, .ods, .pptx and .odp files those suites use. The package
 carries its own Python and Qt, so nothing further has to be installed.
Installed-Size: $(du -sk "${DEB}/opt" | cut -f1)
EOF
echo "==> ${OUT}/officer_${VERSION}_${DEB_ARCH}.deb"
dpkg-deb --build --root-owner-group "${DEB}" \
    "${OUT}/officer_${VERSION}_${DEB_ARCH}.deb"

# -- 4. the AppImage ---------------------------------------------------------- #

APPDIR="${BUILD}/AppDir"
rm -rf "${APPDIR}"; mkdir -p "${APPDIR}/usr/bin"
cp -r "${PAYLOAD}/." "${APPDIR}/usr/bin/"
cat > "${APPDIR}/AppRun" <<'EOF'
#!/usr/bin/env bash
# OFFICER_APP picks which application the single AppImage opens.
SELF="$(dirname "$(readlink -f "$0")")"
exec "${SELF}/usr/bin/officer" --app "${OFFICER_APP:-hub}" "$@"
EOF
chmod +x "${APPDIR}/AppRun"
cp "${ROOT}/desktop/officer.desktop" "${APPDIR}/officer.desktop"
cp "${ROOT}/officer/assets/logo.png" "${APPDIR}/officer.png"

TOOL="${TOOLS}/appimagetool"
if [ ! -x "${TOOL}/AppRun" ]; then
    echo "==> Fetching appimagetool"
    mkdir -p "${TOOLS}"
    [ -x "${TOOLS}/appimagetool.AppImage" ] || wget -q -O "${TOOLS}/appimagetool.AppImage" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${MACHINE}.AppImage"
    chmod +x "${TOOLS}/appimagetool.AppImage"
    # --appimage-extract writes squashfs-root wherever it is run from.
    rm -rf "${TOOLS}/squashfs-root"
    ( cd "${TOOLS}" && ./appimagetool.AppImage --appimage-extract >/dev/null )
    mv "${TOOLS}/squashfs-root" "${TOOL}"
fi
echo "==> ${OUT}/OfficeR-${VERSION}-${MACHINE}.AppImage"
ARCH="${MACHINE}" "${TOOL}/AppRun" "${APPDIR}" \
    "${OUT}/OfficeR-${VERSION}-${MACHINE}.AppImage"

echo "==> Built"
ls -lh "${OUT}"
