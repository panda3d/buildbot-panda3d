#!/bin/bash

# Make sure that the resulting stuff is world-readable
umask 002

branch="main"
if [ "${1%-*}" = "manylinux1" ] || [ "${1%-*}" = "manylinux2010" ]; then
    branch="${1%-*}"
fi

# Make sure the manylinux repository is up-to-date.
git clone -b $branch https://github.com/panda3d/manylinux.git
pushd manylinux
git fetch origin $branch
git reset --hard origin/$branch

# Prefetch sources for OpenSSL and cURL.
if [ -f ./docker/build_scripts/prefetch.sh ]; then
    bash ./docker/build_scripts/prefetch.sh perl openssl curl cacert
fi

popd

