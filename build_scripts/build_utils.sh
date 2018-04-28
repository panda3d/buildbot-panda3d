#!/bin/bash
# Helper utilities for build

PYTHON_DOWNLOAD_URL=https://www.python.org/ftp/python
# XXX: the official https server at www.openssl.org cannot be reached
# with the old versions of openssl and curl in Centos 5.11 hence the fallback
# to the ftp mirror:
OPENSSL_DOWNLOAD_URL=ftp://ftp.openssl.org/source
# Ditto the curl sources
# FIXME: This is about the only mirror that supports bootstrapping over a
# broken version of curl. Unfortunately, we are hardcoding the directory used
# to download the new version of curl.
CURL_DOWNLOAD_URL=https://github.com/curl/curl/releases/download/curl-7_57_0

GET_PIP_URL=https://bootstrap.pypa.io/get-pip.py

AUTOCONF_DOWNLOAD_URL=http://ftp.gnu.org/gnu/autoconf
AUTOMAKE_DOWNLOAD_URL=http://ftp.gnu.org/gnu/automake
LIBTOOL_DOWNLOAD_URL=http://ftp.gnu.org/gnu/libtool


function check_var {
    if [ -z "$1" ]; then
        echo "required variable not defined"
        exit 1
    fi
}


function lex_pyver {
    # Echoes Python version string padded with zeros
    # Thus:
    # 3.2.1 -> 003002001
    # 3     -> 003000000
    echo $1 | awk -F "." '{printf "%03d%03d%03d", $1, $2, $3}'
}


function do_cpython_build {
    local py_ver=$1
    check_var $py_ver
    local ucs_setting=$2
    check_var $ucs_setting
    tar -xzf Python-$py_ver.tgz
    pushd Python-$py_ver
    if [ "$ucs_setting" = "none" ]; then
        unicode_flags=""
        dir_suffix=""
    else
        local unicode_flags="--enable-unicode=$ucs_setting"
        local dir_suffix="-$ucs_setting"
    fi
    local prefix="/opt/_internal/cpython-${py_ver}${dir_suffix}"
    mkdir -p ${prefix}/lib
    ./configure --prefix=${prefix} --disable-shared $unicode_flags > /dev/null
    make -j2 > /dev/null
    make install > /dev/null
    popd
    rm -rf Python-$py_ver
    # Some python's install as bin/python3. Make them available as
    # bin/python.
    if [ -e ${prefix}/bin/python3 ]; then
        ln -s python3 ${prefix}/bin/python
    fi
    ${prefix}/bin/python /build_scripts/get-pip.py
    if [ -e ${prefix}/bin/pip3 ] && [ ! -e ${prefix}/bin/pip ]; then
        ln -s pip3 ${prefix}/bin/pip
    fi
    # Since we fall back on a canned copy of get-pip.py, we might not have
    # the latest pip and friends. Upgrade them to make sure.
    ${prefix}/bin/pip install -U --require-hashes -r ${MY_DIR}/requirements.txt
    local abi_tag=$(${prefix}/bin/python ${MY_DIR}/python-tag-abi-tag.py)
    ln -s ${prefix} /opt/python/${abi_tag}
}


function build_cpython {
    local py_ver=$1
    check_var $py_ver
    check_var $PYTHON_DOWNLOAD_URL
    curl -fsSLO $PYTHON_DOWNLOAD_URL/$py_ver/Python-$py_ver.tgz
    curl -fsSLO $PYTHON_DOWNLOAD_URL/$py_ver/Python-$py_ver.tgz.asc
    gpg --verify Python-$py_ver.tgz.asc
    if [ $(lex_pyver $py_ver) -lt $(lex_pyver 3.3) ]; then
        #do_cpython_build $py_ver ucs2
        do_cpython_build $py_ver ucs4
    else
        do_cpython_build $py_ver none
    fi
    rm -f Python-$py_ver.tgz
    rm -f Python-$py_ver.tgz.asc
}


function build_cpythons {
    check_var $GET_PIP_URL
    # CentOS 5 curl uses such an old OpenSSL that it doesn't support the TLS
    # versions used by the get-pip server. Keep trying though, because we'll
    # want to go back using $GET_PIP_URL when we upgrade to a newer CentOS...
    curl -sSLO $GET_PIP_URL || cp ${MY_DIR}/get-pip.py .
    # Import public keys used to verify downloaded Python source tarballs.
    # https://www.python.org/static/files/pubkeys.txt
    gpg --import ${MY_DIR}/cpython-pubkeys.txt
    for py_ver in $@; do
        build_cpython $py_ver
    done
    # Remove GPG hidden directory.
    rm -rf /root/.gnupg/
    rm -f get-pip.py
}


function do_openssl_build {
    ./config no-ssl2 no-shared -fPIC --prefix=/usr/local/ssl > /dev/null
    make > /dev/null
    make install > /dev/null
}


function check_sha256sum {
    local fname=$1
    check_var ${fname}
    local sha256=$2
    check_var ${sha256}

    echo "${sha256}  ${fname}" > ${fname}.sha256
    sha256sum -c ${fname}.sha256
    rm -f ${fname}.sha256
}


function build_openssl {
    local openssl_fname=$1
    check_var ${openssl_fname}
    local openssl_sha256=$2
    check_var ${openssl_sha256}
    check_var ${OPENSSL_DOWNLOAD_URL}
    curl -sSLO ${OPENSSL_DOWNLOAD_URL}/${openssl_fname}.tar.gz
    check_sha256sum ${openssl_fname}.tar.gz ${openssl_sha256}
    tar -xzf ${openssl_fname}.tar.gz
    (cd ${openssl_fname} && do_openssl_build)
    rm -rf ${openssl_fname} ${openssl_fname}.tar.gz
}


function do_curl_build {
    LIBS=-ldl ./configure --with-ssl --disable-shared > /dev/null
    make > /dev/null
    make install > /dev/null
}


function build_curl {
    local curl_fname=$1
    check_var ${curl_fname}
    local curl_sha256=$2
    check_var ${curl_sha256}
    check_var ${CURL_DOWNLOAD_URL}
    curl -sSLO ${CURL_DOWNLOAD_URL}/${curl_fname}.tar.bz2
    check_sha256sum ${curl_fname}.tar.bz2 ${curl_sha256}
    tar -jxf ${curl_fname}.tar.bz2
    (cd ${curl_fname} && do_curl_build)
    rm -rf ${curl_fname} ${curl_fname}.tar.bz2
}


function do_standard_install {
    ./configure > /dev/null
    make > /dev/null
    make install > /dev/null
}


function build_autoconf {
    local autoconf_fname=$1
    check_var ${autoconf_fname}
    local autoconf_sha256=$2
    check_var ${autoconf_sha256}
    check_var ${AUTOCONF_DOWNLOAD_URL}
    curl -sSLO ${AUTOCONF_DOWNLOAD_URL}/${autoconf_fname}.tar.gz
    check_sha256sum ${autoconf_fname}.tar.gz ${autoconf_sha256}
    tar -zxf ${autoconf_fname}.tar.gz
    (cd ${autoconf_fname} && do_standard_install)
    rm -rf ${autoconf_fname} ${autoconf_fname}.tar.gz
}


function build_automake {
    local automake_fname=$1
    check_var ${automake_fname}
    local automake_sha256=$2
    check_var ${automake_sha256}
    check_var ${AUTOMAKE_DOWNLOAD_URL}
    curl -sSLO ${AUTOMAKE_DOWNLOAD_URL}/${automake_fname}.tar.gz
    check_sha256sum ${automake_fname}.tar.gz ${automake_sha256}
    tar -zxf ${automake_fname}.tar.gz
    (cd ${automake_fname} && do_standard_install)
    rm -rf ${automake_fname} ${automake_fname}.tar.gz
}


function build_libtool {
    local libtool_fname=$1
    check_var ${libtool_fname}
    local libtool_sha256=$2
    check_var ${libtool_sha256}
    check_var ${LIBTOOL_DOWNLOAD_URL}
    curl -sSLO ${LIBTOOL_DOWNLOAD_URL}/${libtool_fname}.tar.gz
    check_sha256sum ${libtool_fname}.tar.gz ${libtool_sha256}
    tar -zxf ${libtool_fname}.tar.gz
    (cd ${libtool_fname} && do_standard_install)
    rm -rf ${libtool_fname} ${libtool_fname}.tar.gz
}
