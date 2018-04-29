#!/bin/bash

# Make sure that the resulting stuff is world-readable
umask 002

# Make sure the manylinux repository is up-to-date.
git clone https://github.com/panda3d/manylinux.git
pushd manylinux
git fetch origin master
git reset --hard origin/master

# Prefetch sources for OpenSSL and cURL.
bash ./docker/build_scripts/prefetch.sh openssl curl

popd

