# This file is licensed under the MIT License.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

"""
Utility functios used for find packages.
"""

# python
import os
import glob
import time
import datetime
import atexit
import platform
import subprocess
import re
import sys

from SCons.Environment import Environment
from SCons.Script.SConscript import Configure

from BuildUtils.ColorPrinter import ColorPrinter


def GetTargetArch(env=None):
    return GetArchs(env)[0]


def GetHostArch(env=None):
    return GetArchs(env)[1]


def IsCrossCompile(env=None):
    return GetTargetArch(env) != GetHostArch(env)


def GetArchs(env=None):

    archs = [
        'x86',
        'amd64',
        'arm',
        'arm64',
        'ia64'
    ]

    arch_map = {
        'x86_64': 'amd64',
        'amd64': 'amd64',
        'ia64': 'ia64',
        'x86': 'x86',
        'i386': 'x86',
        'i686': 'x86',
        'arm': 'arm',
        'aarch64_be': 'arm64',
        'aarch64': 'arm64',
        'armv8l': 'arm64',
        'arm64': 'arm64'
    }

    target_arch = None
    host_arch = None

    if env:
        if env['TARGET_ARCH'] in archs:
            target_arch = env['TARGET_ARCH']
        elif env['HOST_ARCH'] in archs:
            target_arch = env['HOST_ARCH']

        if env['HOST_ARCH'] in archs:
            host_arch = env['HOST_ARCH']

    if not target_arch:
        target_arch = arch_map.get(platform.machine(), 'amd64')

    if not host_arch:
        host_arch = arch_map.get(platform.machine(), 'amd64')

    return [target_arch, host_arch]


def FindFreetype(env, paths=[]):

    search_paths = []
    version = ""
    p = ColorPrinter()
    found_headers = None
    found_libs = None
    found_bins = None
    found_freetype_version = None

    test_env = Environment()
    test_env.Append(LIBS=['freetype'])
    original_libs = env.get('LIBPATH')
    original_includes = env.get('CPPPATH')

    search_paths += paths

    if sys.platform == 'win32':
        if not IsCrossCompile(env):
            search_paths.append(os.environ.get('USERPROFILE'))

    p.InfoPrint(" Searching for Freetype...")
    for test_path in search_paths:
        p.InfoPrint(" Looking in " + test_path)
        for root, dirs, files in os.walk(test_path, topdown=False):
            for name in files:
                if name == 'ft2build.h':
                    found_headers = root
                    test_env.Append(CPPPATH=[root])
                if ('freetype' in name
                        and (env["SHLIBSUFFIX"] in name or env["LIBSUFFIX"] in name)):
                    test_env.Append(LIBPATH=[root])
                    found_libs = root

        if found_headers and found_libs:

            for root, dirs, files in os.walk(found_headers, topdown=False):
                for name in files:
                    if name == 'freetype.h':
                        found_freetype_version = os.path.join(root, name)

            conf = Configure(
                test_env,
                conf_dir="findfreetype/conf_tests",
                log_file="conf.log")

            result = conf.TryLink("""
            # include <ft2build.h>
            # include FT_FREETYPE_H
            int main()
            {
                FT_Library  library;
                return FT_Init_FreeType( &library );
            }
            """, '.c')

            if result:
                with open(found_freetype_version) as f:
                    contents = f.read()
                    major = re.search(
                        r'^#define\s+FREETYPE_MAJOR\s+(\d+)', contents, re.MULTILINE)
                    if major:
                        version += str(major.group(1))
                    minor = re.search(
                        r'^#define\s+FREETYPE_MINOR\s+(\d+)', contents, re.MULTILINE)
                    if minor:
                        version += "." + str(minor.group(1))
                    patch = re.search(
                        r'^#define\s+FREETYPE_PATCH\s+(\d+)', contents, re.MULTILINE)
                    if patch:
                        version += "." + str(patch.group(1))

                p.InfoPrint(" Found freetype " + version +
                            " in " + str(found_headers))

                env.Append(
                    LIBPATH=[found_libs],
                    CPPPATH=[found_headers])
                return
            else:
                p.InfoPrint(" Candidate failed in " + test_path)
                test_env['LIBPATH'] = original_libs
                found_libs = None
                test_env['CPPPATH'] = original_includes
                found_headers = None
