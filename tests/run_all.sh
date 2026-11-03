#!/bin/sh
# All the PC tests. Needs Pillow; the C tests also need a C compiler and the
# libraries from natmod/fetch_libs.sh. Run from anywhere.
set -e
cd "$(dirname "$0")/.."
python3 tests/test_prepare.py | tail -1
for mode in 2024 2026; do
    for kb in 0 1; do
        MODE=$mode KB=$kb python3 tests/test_gallery.py | tail -1
    done
done
if [ -d natmod/libs/jpegdec ] || natmod/fetch_libs.sh; then
    make -s -C natmod/test
    python3 natmod/test/compare.py | tail -2
    python3 natmod/test/app_test.py | tail -1
fi
