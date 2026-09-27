#!/usr/bin/env bash
# Put an unpacked OfficeR bundle where the desktop looks for applications.
#
#   sudo ./install.sh                  # /opt/officer, launchers in /usr/local/bin
#   sudo PREFIX=/usr LIBDIR=/opt/officer ./install.sh
#
# It installs the bundle as it stands, so the copy under /opt stays removable
# with `rm -rf /opt/officer` and the three files in PREFIX/bin.

set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PREFIX="${PREFIX:-/usr/local}"
LIBDIR="${LIBDIR:-/opt/officer}"

if [ "$(id -u)" -ne 0 ]; then
    echo "This writes to ${PREFIX} and ${LIBDIR}; run it as root:  sudo ./install.sh"
    exit 1
fi
if [ ! -x "${HERE}/officer" ]; then
    echo "${HERE} is not an unpacked OfficeR bundle (no ./officer in it)."
    exit 1
fi

echo "==> Copying the bundle to ${LIBDIR}"
mkdir -p "${LIBDIR}"
rm -rf "${LIBDIR}/officer" "${LIBDIR}/_internal"
cp -r "${HERE}/officer" "${HERE}/_internal" "${LIBDIR}/"

echo "==> Launchers in ${PREFIX}/bin"
for app in hub writer rsheet presentr; do
    suffix=""; [ "${app}" != "hub" ] && suffix="-${app}"
    printf '#!/usr/bin/env bash\nexec "%s/officer" --app %s "$@"\n' \
        "${LIBDIR}" "${app}" > "${PREFIX}/bin/officer${suffix}"
    chmod +x "${PREFIX}/bin/officer${suffix}"
done

echo "==> Menu entries and icons"
mkdir -p "${PREFIX}/share/applications" \
         "${PREFIX}/share/icons/hicolor/512x512/apps"
for file in "${HERE}"/share/applications/*.desktop; do
    sed "s|^Exec=.*officer|Exec=officer|" "${file}" \
        > "${PREFIX}/share/applications/$(basename "${file}")"
done
for icon in "${HERE}"/share/icons/hicolor/512x512/apps/*.png; do
    cp "${icon}" "${PREFIX}/share/icons/hicolor/512x512/apps/"
done

command -v update-desktop-database >/dev/null && \
    update-desktop-database "${PREFIX}/share/applications" || true
command -v gtk-update-icon-cache >/dev/null && \
    gtk-update-icon-cache -q "${PREFIX}/share/icons/hicolor" || true

echo "==> Done. WriteR, RSheet and PresentR are in the applications menu, and"
echo "    ${PREFIX}/bin/officer opens the hub."
