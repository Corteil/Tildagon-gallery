#!/bin/sh
# Fetch the three bitbank2 libraries imgtool is built on into ./libs
# (Apache 2.0). Pinned to the commits this module was tested with.
set -e
cd "$(dirname "$0")"
mkdir -p libs
get() {  # name commit
    if [ ! -d "libs/$1/.git" ]; then
        git clone -q "https://github.com/bitbank2/$1" "libs/$1"
    fi
    git -C "libs/$1" fetch -q origin
    git -C "libs/$1" checkout -q "$2"
    echo "$1 at $2"
}
get jpegdec 484cb4e1466eea5382b6ff6387365dec81734d2b
get jpegenc f51421bdaba8e098dc82130a17adaae6d61c3377
get pngdec 2855e785bc1a80763c89a2afd808faf6156d35c6
