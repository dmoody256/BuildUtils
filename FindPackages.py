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
import itertools
import copy
from multiprocessing import TimeoutError
from multiprocessing.pool import ThreadPool

if sys.platform == 'win32':
    ERROR_NO_MORE_ITEMS = 259
    try:
        from winreg import *
    except ImportError:  # Python 2
        from _winreg import *

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


def getKey(rootTree, keystr, value):

    if sys.platform == 'win32':

        KEY_READ_64 = KEY_READ | KEY_WOW64_64KEY

        def iterkeys(key):
            for i in itertools.count():
                try:
                    yield EnumKey(key, i)
                except OSError as e:
                    if e.winerror == ERROR_NO_MORE_ITEMS:
                        break
                    raise

        def itervalues(key):
            for i in itertools.count():
                try:
                    yield EnumValue(key, i)
                except OSError as e:
                    if e.winerror == ERROR_NO_MORE_ITEMS:
                        break
                    raise

        def val2addr(val):
            return ':'.join('%02x' % b for b in bytearray(val))
        try:
            key = OpenKey(rootTree, keystr, 0, KEY_READ_64)
            for keyvalue in itervalues(key):
                if keyvalue[0] == value:
                    return keyvalue
            CloseKey(key)
        except:
            pass

class PackageFinder(object):
    def __init__(self, env, paths, required, timeout, conf_dir):

        self.env = env
        self.user_paths = paths
        self.sys_paths = []
        self.required = required
        self.timeout = timeout
        self.p = ColorPrinter()
        self.version = ""
        self.timedout = {'timedout': False}
        self.addPlatformPaths()
        if not conf_dir:
            self.conf_dir = 'confdir'
        else:
            self.conf_dir = conf_dir
        self.packagename = ""

    def startSearch(self):
        if self.timeout:
            pool = ThreadPool(processes=1)
            async_result = pool.apply_async(
                self.searchThread)
            try:
                return async_result.get(timeout)
            except TimeoutError:
                self.timedout['timedout'] = True
                async_result.get()
                if self.required:
                    self.p.ErrorPrint("Timedout after " + str(timeout) +
                                        " seconds searching for " + self.packagename)
                else:
                    self.p.InfoPrint(" Timedout after " + str(timeout) +
                                        " seconds searching for " + self.packagename)
                return None
        else:
            return self.searchThread()

    def getTestEnv(self):
        if self.env is None:
            test_env = Environment()
        else:
            test_env = self.env.Clone()
        return test_env

    def tryPackageConfig(self):
        
        if any(os.access(os.path.join(path, 'pkg-config'), os.X_OK) for path in os.environ["PATH"].split(os.pathsep)):
            test_env = self.getTestEnv()
            pkgconfig_str = 'pkg-config ' + self.packagename + " --cflags --libs"
            
            test_env.ParseConfig(pkgconfig_str)
            if self.compileTest(test_env):
                self.version = subprocess.check_output(
                    ['pkg-config', '--modversion', self.packagename]).decode('utf8').strip()
                self.p.InfoPrint(" Found " + self.packagename + " version " + self.version)
                self.env.ParseConfig(pkgconfig_str)
                return test_env

    def addPlatformPaths(self):
        test_env = self.getTestEnv()

        # check parent directory of the current project
        self.sys_paths.append(os.path.abspath(
            test_env.Dir('.').abspath + '/..'))

        if sys.platform == 'win32':
            if not IsCrossCompile(test_env):
                if GetTargetArch(test_env) == 'amd64':
                    self.sys_paths.append("C:/Program Files")
                else:
                    self.sys_paths.append("C:/Program Files (x86)")
                if self.required:
                    # check user directory, and program files
                    self.sys_paths.append(os.environ.get('USERPROFILE'))
                    
        elif 'linux' in sys.platform:
            if not IsCrossCompile(test_env):
                if GetTargetArch(test_env) == 'amd64':
                    self.sys_paths.append(["/usr/include", "/usr/lib64"])
                    self.sys_paths.append(["/usr/include", "/usr/lib/x86_64-linux-gnu"])
                else:
                    self.sys_paths.append(["/usr/include", "/usr/lib/i386-linux-gnu"])
                self.sys_paths.append(["/usr/local/include", "/usr/local/lib"])
                self.sys_paths.append(["/usr/include", "/usr/lib"])
                
                
    def searchThread(self):

        self.p.InfoPrint(" Searching for " + self.packagename + "...")
        # first search user paths
        result = self.search(self.user_paths, required=self.required)
        if result:
            return result
        if self.timedout['timedout']:
            return

        # next try package config
        result = self.tryPackageConfig()
        if result:
            return result
        if self.timedout['timedout']:
            return

        # finally try system paths
        result = self.search(self.sys_paths, required=self.required)
        if result:
            return result
        if self.required:
            self.p.ErrorPrint("Failed to find working " + self.packagename + " package.")
        else:
            self.p.InfoPrint(" Couldn't find " + self.packagename + ".")

   
def FindGraphite2(env=None, paths=[], required=False, timeout=None, conf_dir=None):

    class Graphite2Finder(PackageFinder):
        def __init__(self, env, paths, required, timeout, conf_dir):
            super(Graphite2Finder, self).__init__(env, paths, required, timeout, conf_dir)
            self.packagename = 'graphite2'

            if os.environ.get('GRAPHITE2_DIR'):
                self.user_paths.append(os.environ.get('GRAPHITE2_DIR'))

            if env and env.get('GRAPHITE2_DIR'):
                self.user_paths.append(env.get('GRAPHITE2_DIR'))

        def compileTest(self, env):
            env.Append(LIB=['graphite2'])
            conf = Configure(
                env,
                conf_dir=self.conf_dir + "/findgraphite2",
                log_file=self.conf_dir + "/findgraphite2/conf.log")

            result = conf.TryLink("""
            #include <graphite2/Fonts.h>
            int main()
            {
                int nMajor, int nMinor, int nBugFix;
                gr_engine_version(&nMajor, &nMinor, &nBugFix);
                return 0;
            }
            """, '.c')

            conf.Finish()
            return result
                

        def search(self, paths, required=False):

            found_headers = None
            found_libs = None
            found_graphite_version = None
            test_env = self.getTestEnv()

            for test_path in paths:
                self.p.InfoPrint(" Looking in " + str(test_path))

                # include and lib paths passed seperatly
                if type(test_path) is list:
                    for root, dirs, files in os.walk(test_path[0], topdown=False):
                        for name in files:
                            if self.timedout['timedout']:
                                return
                            if name == 'Fonts.h' and os.path.basename(root) == 'graphite2':
                                found_headers = os.path.dirname(root)
                                test_env.Append(CPPPATH=[found_headers])
                                break
                        if found_headers:
                            break

                    for root, dirs, files in os.walk(test_path[1], topdown=False):
                        for name in files:
                            if self.timedout['timedout']:
                                return
                            if ('graphite2' in name
                                and (env["SHLIBSUFFIX"] in name or env["LIBSUFFIX"] in name)):
                                found_libs = root
                                test_env.Append(LIBPATH=[root])
                                break
                        if found_libs:
                            break
                # look in same dir for lib and include
                else:
                    for root, dirs, files in os.walk(test_path, topdown=False):
                        for name in files:
                            if self.timedout['timedout']:
                                return
                            if name == 'Fonts.h' and os.path.basename(root) == 'graphite2':
                                found_freetype_version = os.path.join(
                                    root, name)
                                found_headers = os.path.dirname(root)
                                test_env.Append(CPPPATH=[found_headers])
                            if ('graphite2' in name
                                and (env["SHLIBSUFFIX"] in name or env["LIBSUFFIX"] in name)):
                                found_libs = root
                                test_env.Append(LIBPATH=[root])

                            if found_headers and found_libs:
                                break
                        if found_headers and found_libs:
                            break
                        
                if found_headers and found_libs and found_freetype_version:
                   
                    if self.compileTest(test_env):
                        with open(found_freetype_version) as f:
                            contents = f.read()
                            major = re.search(
                                r'^#define\s+GR2_VERSION_MAJOR\s+(\d+)', contents, re.MULTILINE)
                            if major:
                                self.version += str(major.group(1))
                            minor = re.search(
                                r'^#define\s+GR2_VERSION_MINOR\s+(\d+)', contents, re.MULTILINE)
                            if minor:
                                self.version += "." + str(minor.group(1))
                            patch = re.search(
                                r'^#define\s+GR2_VERSION_BUGFIX\s+(\d+)', contents, re.MULTILINE)
                            if patch:
                                self.version += "." + str(patch.group(1))

                        self.p.InfoPrint(" Found " + self.packagename + " version " + self.version +
                                         " in " + str(found_headers))
                        if self.env:
                            self.env.Append(
                                LIBPATH=[found_libs],
                                CPPPATH=[found_headers],
                                LIB=['graphite2'])
                            return self.env
                        else:
                            return test_env
                    else:
                        self.p.InfoPrint(" Candidate failed in " + test_path)
                        test_env = self.getTestEnv()
                        found_libs = None
                        found_headers = None
                        found_freetype_version = None
                else:
                    test_env = self.getTestEnv()

    finder = Graphite2Finder(env, paths, required, timeout, conf_dir)
    return finder.startSearch()


def FindGlib(env=None, paths=[], required=False, timeout=None):
    p = ColorPrinter()
    p.InfoPrint(" FindGlib not implemented, skipping.")
    return None


def FindIcu(env=None, paths=[], required=False, timeout=None):
    p = ColorPrinter()
    p.InfoPrint(" FindIcu not implemented, skipping.")
    return None


def FindFreetype(env=None, paths=[], required=False, timeout=None, conf_dir=None):
    class FreetypeFinder(PackageFinder):
        def __init__(self, env, paths, required, timeout, conf_dir):
            super(FreetypeFinder, self).__init__(env, paths, required, timeout, conf_dir)

            self.packagename = 'freetype2'

            if os.environ.get('FREETYPE_DIR'):
                self.user_paths.append(os.environ.get('FREETYPE_DIR'))

            if env and env.get('FREETYPE_DIR'):
                self.user_paths.append(env.get('FREETYPE_DIR'))

        def compileTest(self, env):
            env.Append(LIBS=['freetype'])
            conf = Configure(
                env,
                conf_dir=self.conf_dir + "/findfreetype",
                log_file=self.conf_dir + "/findfreetype/conf.log")

            result = conf.TryLink("""
            #include <ft2build.h>
            #include FT_FREETYPE_H
            int main()
            {
                FT_Library  library;
                FT_Init_FreeType( &library );
                return 0;
            }
            """, '.c')
            conf.Finish()
            return result


        def addPlatformPaths(self):
            test_env = self.getTestEnv()
            if sys.platform == 'win32':
                if not IsCrossCompile(test_env):
                    # check gtk paths, lifted from cmake
                    gtkpath = getKey(HKEY_CURRENT_USER, 'SOFTWARE\\gtkmm\\2.4',
                                     'Path')
                    if gtkpath:
                        self.sys_paths.append(gtkpath)

                    gtkpath = getKey(HKEY_LOCAL_MACHINE, 'SOFTWARE\\gtkmm\\2.4',
                                     'Path')
                    if gtkpath:
                        self.sys_paths.append(gtkpath)

            super(FreetypeFinder, self).addPlatformPaths()

        def search(self, paths, required=False):

            found_headers = None
            found_libs = None
            found_freetype_version = None
            test_env = self.getTestEnv()

            for test_path in paths:
                self.p.InfoPrint(" Looking in " + str(test_path))

                # include and lib paths passed seperatly
                if type(test_path) is list:
                    for root, dirs, files in os.walk(test_path[0], topdown=False):
                        for name in files:
                            if self.timedout['timedout']:
                                return
                            if name == 'ft2build.h':
                                found_headers = root
                                test_env.Append(CPPPATH=[root])
                                break
                        
                        if found_headers:
                            break

                    for root, dirs, files in os.walk(test_path[1], topdown=False):
                        for name in files:
                            if self.timedout['timedout']:
                                return
                            if ('freetype' in name
                                and (env["SHLIBSUFFIX"] in name or env["LIBSUFFIX"] in name)):
                                found_libs = root
                                test_env.Append(LIBPATH=[root])
                                break
                        if found_libs:
                            break
                # look in same dir for lib and include
                else:
                    for root, dirs, files in os.walk(test_path, topdown=False):
                        for name in files:
                            if self.timedout['timedout']:
                                return
                            if name == 'ft2build.h':
                                found_headers = root
                                test_env.Append(CPPPATH=[root])
                            if ('freetype' in name
                                    and (env["SHLIBSUFFIX"] in name or env["LIBSUFFIX"] in name)):
                                test_env.Append(LIBPATH=[root])
                                found_libs = root

                            if found_headers and found_libs:
                                break
                        if found_headers and found_libs:
                            break
                        
                if found_headers and found_libs:
                    for root, dirs, files in os.walk(found_headers, topdown=False):
                        for name in files:
                            if self.timedout['timedout']:
                                return
                            if name == 'freetype.h':
                                found_freetype_version = os.path.join(
                                    root, name)
                                break
                        if found_freetype_version:
                            break

                    if self.compileTest(test_env):
                        with open(found_freetype_version) as f:
                            contents = f.read()
                            major = re.search(
                                r'^#define\s+FREETYPE_MAJOR\s+(\d+)', contents, re.MULTILINE)
                            if major:
                                self.version += str(major.group(1))
                            minor = re.search(
                                r'^#define\s+FREETYPE_MINOR\s+(\d+)', contents, re.MULTILINE)
                            if minor:
                                self.version += "." + str(minor.group(1))
                            patch = re.search(
                                r'^#define\s+FREETYPE_PATCH\s+(\d+)', contents, re.MULTILINE)
                            if patch:
                                self.version += "." + str(patch.group(1))

                        self.p.InfoPrint(" Found " + self.packagename + " version " + self.version +
                                         " in " + str(found_headers))
                        if self.env:
                            self.env.Append(
                                LIBPATH=[found_libs],
                                CPPPATH=[found_headers],
                                LIB=['freetype'])
                            return self.env
                        else:
                            return test_env
                    else:
                        self.p.InfoPrint(" Candidate failed in " + found_headers + " and " + found_libs)
                        test_env = self.getTestEnv()
                        found_libs = None
                        found_headers = None
                        found_freetype_version = None
                else:
                    test_env = self.getTestEnv()
                    found_libs = None
                    found_headers = None
                    found_freetype_version = None

    finder = FreetypeFinder(env, paths, required, timeout, conf_dir)
    return finder.startSearch()
