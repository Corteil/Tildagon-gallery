#!/bin/sh
# One-shot setup and test on a Raspberry Pi (or any Debian/Ubuntu PC).
#   natmod/test/pi_setup.sh   install tools, build the C core, run the PC tests
# Then plug a badge in and:  python3 tools/badge.py test
set -e
cd "$(dirname "$0")/../.."
if command -v apt-get >/dev/null; then
    sudo apt-get install -y build-essential git python3-pip python3-pil
fi
# mpremote talks to the badge over USB
python3 -m pip install --user --break-system-packages mpremote 2>/dev/null || python3 -m pip install --user mpremote
# serial access without sudo
if ! id -nG | grep -qw dialout; then
    sudo usermod -aG dialout "$USER" && echo "Added you to 'dialout': log out and in again before using the badge."
fi
natmod/fetch_libs.sh
make -C natmod/test
python3 natmod/test/compare.py | tail -3
python3 natmod/test/app_test.py | tail -1
echo "PC tests done. Next: plug in a badge, then   python3 tools/badge.py test"
