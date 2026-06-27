#!/bin/bash
# Inner build script — runs INSIDE the container
# Invoked by tools/build-deb-outer.sh via podman
set -ex

apt-get update -qq
apt-get install -y -qq \
    debhelper \
    dh-python \
    python3-all \
    python3-setuptools \
    gettext \
    fakeroot \
    dpkg-dev

cd /bups

# Clean stale artifacts
rm -rf debian/bups debian/*.log debian/files

# Build binary package only, no signing, using fakeroot
dpkg-buildpackage -b -us -uc -rfakeroot

# Output is placed in parent of source (/), copy to /out
cp /bups_*.deb /out/
echo "=== Build complete ==="
ls -lh /out/
