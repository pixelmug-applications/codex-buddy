#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG_ID="com.pixelmug.codex"
OUT_DIR="$ROOT_DIR/release"
PKGROOT="${PKGROOT:-/private/tmp/pixelmug-codex-pkgroot-${UID:-$(id -u)}}"
COMPONENT_PKG="$ROOT_DIR/build/pixelmug-codex-component.pkg"
COMPONENT_PLIST="$ROOT_DIR/build/pixelmug-codex-components.plist"

cd "$ROOT_DIR"
mkdir -p "$OUT_DIR" "$ROOT_DIR/build"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r requirements-build.txt
python -m pip install -e .
VERSION="$(python -c 'from importlib.metadata import version; print(version("pixelmug-codex"))')"
FINAL_PKG="$OUT_DIR/PixelMugCodex-${VERSION}.pkg"

rm -rf dist build/pyinstaller "$PKGROOT" "$COMPONENT_PKG"
python packaging/make_macos_icon.py
pyinstaller --clean --noconfirm --workpath build/pyinstaller packaging/pixelmug-codex-cli.spec
pyinstaller --clean --noconfirm --workpath build/pyinstaller packaging/pixelmug-codex-app.spec

mkdir -p "dist/PixelMug Codex.app/Contents/Resources/assets" "dist/PixelMug Codex.app/Contents/Frameworks/assets"
cp assets/status-icon.png assets/status-icon@2x.png "dist/PixelMug Codex.app/Contents/Resources/assets/"
cp assets/status-icon.png assets/status-icon@2x.png "dist/PixelMug Codex.app/Contents/Frameworks/assets/"

mkdir -p "$PKGROOT/usr/local/bin" "$PKGROOT/Applications"
install -m 0755 "dist/pixelmug-codex" "$PKGROOT/usr/local/bin/pixelmug-codex"
ditto "dist/PixelMug Codex.app" "$PKGROOT/Applications/PixelMug Codex.app"

cat > "$COMPONENT_PLIST" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<array>
  <dict>
    <key>BundleHasStrictIdentifier</key>
    <true/>
    <key>BundleIsRelocatable</key>
    <false/>
    <key>BundleIsVersionChecked</key>
    <false/>
    <key>BundleOverwriteAction</key>
    <string>upgrade</string>
    <key>RootRelativeBundlePath</key>
    <string>Applications/PixelMug Codex.app</string>
  </dict>
</array>
</plist>
PLIST

# Optional code signing. For public distribution you should sign and notarize.
if [[ -n "${DEVELOPER_ID_APPLICATION:-}" ]]; then
  codesign --force --deep --options runtime --sign "$DEVELOPER_ID_APPLICATION" "$PKGROOT/Applications/PixelMug Codex.app"
  codesign --force --options runtime --sign "$DEVELOPER_ID_APPLICATION" "$PKGROOT/usr/local/bin/pixelmug-codex"
fi

pkgbuild \
  --root "$PKGROOT" \
  --identifier "$PKG_ID" \
  --version "$VERSION" \
  --component-plist "$COMPONENT_PLIST" \
  --scripts "$ROOT_DIR/packaging/scripts" \
  --install-location / \
  "$COMPONENT_PKG"

if [[ -n "${DEVELOPER_ID_INSTALLER:-}" ]]; then
  productbuild --sign "$DEVELOPER_ID_INSTALLER" --package "$COMPONENT_PKG" "$FINAL_PKG"
else
  productbuild --package "$COMPONENT_PKG" "$FINAL_PKG"
fi

echo "Built: $FINAL_PKG"

echo "Optional notarization example:"
echo "  xcrun notarytool submit '$FINAL_PKG' --keychain-profile '<profile>' --wait"
echo "  xcrun stapler staple '$FINAL_PKG'"
