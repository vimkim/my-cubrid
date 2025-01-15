cmake_minimum_required(VERSION 3.20)
project(CUB3LIB_INSTALLER)

include(ExternalProject)

# Set installation directory
set(INSTALL_DIR "$ENV{HOME}/CUB3LIB")
set(DEFAULT_CONFIGURE_OPTS <SOURCE_DIR>/configure --prefix=${INSTALL_DIR} --enable-static --disable-shared --with-pic CFLAGS=-w CXXFLAGS=-w)

# URLs and hashes for libraries
set(FLEX_URL "https://github.com/CUBRID/3rdparty/raw/develop/flex/flex-2.6.4.tar.gz")
set(BISON_URL "https://github.com/CUBRID/3rdparty/raw/develop/bison/bison-3.4.1.tar.gz")
set(EXPAT_URL "https://github.com/CUBRID/3rdparty/raw/develop/expat/expat-2.2.5.tar.bz2")
set(EXPAT_HASH "SHA256=d9dc32efba7e74f788fcc4f212a43216fc37cf5f23f4c2339664d473353aedf6")
set(JANSSON_URL "https://github.com/CUBRID/3rdparty/raw/develop/jansson/jansson-2.10.tar.gz")
set(JANSSON_HASH "SHA256=78215ad1e277b42681404c1d66870097a50eb084be9d771b1d15576575cf6447")
set(LIBEDIT_URL "https://github.com/CUBRID/libedit/archive/refs/tags/csql_v1.1.tar.gz")
set(LIBEDIT_HASH "SHA256=972c7d46844b7b56adde028bb2269546938272dd8d7a58978b7a18a6f6e44141")
set(LIBUNIXODBC_URL "https://github.com/CUBRID/3rdparty/raw/develop/unixODBC/unixODBC-2.3.9.tar.gz")     # unixODBC library sources URL
set(LIBUNIXODBC_URL_HASH "SHA256=52833eac3d681c8b0c9a5a65f2ebd745b3a964f208fc748f977e44015a31b207")     # unixODBC library sources URL
set(OPENSSL_URL "https://github.com/CUBRID/3rdparty/raw/develop/openssl/openssl-1.1.1f.tar.gz")
set(OPENSSL_HASH "SHA256=186c6bfe6ecfba7a5b48c47f8a1673d0f3b0e5ba2e25602dd23b629975da3f35")
set(RE2_URL "https://github.com/CUBRID/3rdparty/raw/develop/re2/2022-06-01.tar.gz")
set(RE2_HASH "SHA256=f89c61410a072e5cbcf8c27e3a778da7d6fd2f2b5b1445cd4f4508bee946ab0f")
set(TBB_URL "https://github.com/CUBRID/3rdparty/raw/develop/tbb/v2021.11.0.tar.gz")
set(TBB_HASH "SHA256=782ce0cab62df9ea125cdea253a50534862b563f1d85d4cda7ad4e77550ac363")

# Create installation directory
file(MAKE_DIRECTORY ${INSTALL_DIR})

# Common ExternalProject options for logging
set(EP_LOG_OPTIONS
    LOG_DOWNLOAD TRUE
    LOG_UPDATE TRUE
    LOG_CONFIGURE TRUE
    LOG_BUILD TRUE
    LOG_INSTALL TRUE
    LOG_MERGED_STDOUTERR TRUE
    LOG_OUTPUT_ON_FAILURE TRUE
)

# Expat
ExternalProject_Add(expat
    URL ${EXPAT_URL}
    URL_HASH ${EXPAT_HASH}
    CONFIGURE_COMMAND ${DEFAULT_CONFIGURE_OPTS} --without-xmlwf --without-docbook
    BUILD_COMMAND make -j
    INSTALL_COMMAND make install
    TIMEOUT 600
    ${EP_LOG_OPTIONS}
)

ExternalProject_Add(libodbc
    URL ${LIBUNIXODBC_URL}
    URL_HASH ${LIBUNIXODBC_HASH}
    CONFIGURE_COMMAND    <SOURCE_DIR>/configure --prefix=${INSTALL_DIR} # ${DEFAULT_CONFIGURE_OPTS}
    BUILD_COMMAND        make -j AUTOCONF=: AUTOHEADER=: AUTOMAKE=: ACLOCAL=:
    INSTALL_COMMAND      make install AUTOCONF=: AUTOHEADER=: AUTOMAKE=: ACLOCAL=:
    TIMEOUT 600
    ${EP_LOG_OPTIONS}
)

# Jansson
ExternalProject_Add(jansson
    URL ${JANSSON_URL}
    URL_HASH ${JANSSON_HASH}
    CONFIGURE_COMMAND ${DEFAULT_CONFIGURE_OPTS}
    BUILD_COMMAND make -j
    INSTALL_COMMAND make install
    TIMEOUT 600
    ${EP_LOG_OPTIONS}
)

# LibEdit
ExternalProject_Add(libedit
    URL ${LIBEDIT_URL}
    URL_HASH ${LIBEDIT_HASH}
    CONFIGURE_COMMAND ${DEFAULT_CONFIGURE_OPTS} LIBS=-ldl
    BUILD_COMMAND make -j
    INSTALL_COMMAND make install
    TIMEOUT 600
    ${EP_LOG_OPTIONS}
)

# OpenSSL
ExternalProject_Add(openssl
    URL ${OPENSSL_URL}
    URL_HASH ${OPENSSL_HASH}
    CONFIGURE_COMMAND <SOURCE_DIR>/config --prefix=${INSTALL_DIR} no-shared
    BUILD_COMMAND make -j
    INSTALL_COMMAND make install_sw
    TIMEOUT 600
    ${EP_LOG_OPTIONS}
)

# RE2
ExternalProject_Add(re2
    URL ${RE2_URL}
    URL_HASH ${RE2_HASH}
    CONFIGURE_COMMAND ""
    BUILD_IN_SOURCE TRUE
    BUILD_COMMAND make -j CFLAGS=-fPIC CXXFLAGS=-fPIC prefix=${INSTALL_DIR}
    INSTALL_COMMAND make install prefix=${INSTALL_DIR}
    TIMEOUT 600
    ${EP_LOG_OPTIONS}
)

# TBB
ExternalProject_Add(tbb
    URL ${TBB_URL}
    URL_HASH ${TBB_HASH}
    CMAKE_ARGS 
        -DCMAKE_INSTALL_PREFIX=${INSTALL_DIR}
        -DTBB_STRICT=OFF
        -DCMAKE_INSTALL_LIBDIR=lib
        -DCMAKE_CXX_FLAGS=-DTBB_ALLOCATOR_TRAITS_BROKEN
        -D__TBB_DYNAMIC_LOAD_ENABLED=0
        -DTBBMALLOC_BUILD=OFF
        -DTBBMALLOC_PROXY_BUILD=OFF
        -DTBB_TEST=OFF
        -DTBB_ENABLE_IPO=OFF
        -DBUILD_SHARED_LIBS=OFF
        -DCMAKE_BUILD_TYPE=Release
    TIMEOUT 600
    ${EP_LOG_OPTIONS}
)

message(STATUS "Libraries will be installed to: ${INSTALL_DIR}")
message(STATUS "Build logs will be in your build directory under: <target-name>-prefix/src/<target-name>-stamp/")
