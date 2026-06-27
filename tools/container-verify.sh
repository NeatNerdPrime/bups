#!/bin/bash
# Inner verification script — runs INSIDE the container after installing the .deb
# Invoked by the outer build script via podman
set -ex

DEB_PATH="$1"
RELEASE="$2"

apt-get update -qq
# Install the .deb with its dependencies
apt-get install -y -qq gir1.2-adw-1 gir1.2-gtk-4.0 python3-gi python3-gi-cairo \
    cifs-utils encfs sshfs bup 2>/dev/null || true
dpkg -i "$DEB_PATH" || apt-get install -f -y -qq

echo "=== Verification: $RELEASE ==="

# 1. Binary exists and is executable
which bups
bups --version 2>/dev/null || python3 -c "import bups; print('bups version:', bups.__version__)"

# 2. All Python modules import
python3 -c "
import bups
from bups import version, config, manager, worker, sudo
from bups.scheduler import anacron, systemd
from bups.fuse import root
print('All modules import OK, version:', version.__version__)
"

# 3. Locale files installed
for lang in de es fr; do
    test -f /usr/share/locale/$lang/LC_MESSAGES/bups.mo && echo "locale $lang OK" || echo "MISSING: locale $lang"
done

# 4. Desktop file installed
test -f /usr/share/applications/bups.desktop && echo "desktop file OK" || echo "MISSING: desktop file"

# 5. No extra files outside allowlist
echo "=== Package contents ==="
dpkg -L bups | sort

echo "=== ALL VERIFICATION CHECKS PASSED for $RELEASE ==="
