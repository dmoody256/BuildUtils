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
                
                header_dirs = subprocess.check_output(
                    ['pkg-config', self.packagename, "--cflags"]).decode('utf8').strip().split(' ')
                header_dirs += ['-I/usr/include']
                found_version = False
                for path in header_dirs:
                    if path.startswith('-I'):
                        path = path[2:]
                        for root, dirs, files in os.walk(path, topdown=False):
                            for name in files:
                                if self.timedout['timedout']:
                                    return
                                version_file = self.checkVersion(test_env, name, root)
                                if version_file:
                                    found_version = version_file
                                    break
                            if found_version:
                                break
                    
                    if found_version:
                        break
                if found_version:
                    self.p.InfoPrint(" Found " + self.packagename + " version " + self.version)
                else:
                    self.p.InfoPrint(" Found " + self.packagename + " with unknown version.")
                if self.env:
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
                    self.sys_paths.append("C:/cygwin64")
                    self.sys_paths.append("C:/msys64")
                else:
                    self.sys_paths.append("C:/Program Files (x86)")
                    self.sys_paths.append("C:/cygwin")
                    self.sys_paths.append("C:/msys")
                self.sys_paths.append("C:/MinGW")
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
                
    def search(self, paths, required=False):

        found_headers = None
        found_libs = None
        found_version = None
        test_env = self.getTestEnv()

        for test_path in paths:
            self.p.InfoPrint(" Looking in " + str(test_path))

            # include and lib paths passed seperatly
            if type(test_path) is list:
                for root, dirs, files in os.walk(test_path[0], topdown=False):
                    for name in files:
                        if self.timedout['timedout']:
                            return
                        header_dir = self.checkHeader(test_env, name, root)
                        if header_dir:
                            found_headers = header_dir
                            break
                    if found_headers:
                        break

                for root, dirs, files in os.walk(test_path[1], topdown=False):
                    for name in files:
                        if self.timedout['timedout']:
                            return
                        lib_dir = self.checkLib(test_env, name, root)
                        if lib_dir:
                            found_libs = lib_dir
                            break
                    if found_libs:
                        break
            # look in same dir for lib and include
            else:
                for root, dirs, files in os.walk(test_path, topdown=False):
                    for name in files:
                        if self.timedout['timedout']:
                            return
                        header_dir = self.checkHeader(test_env, name, root)
                        if header_dir:
                            found_headers = header_dir
                            break
                        lib_dir = self.checkLib(test_env, name, root)
                        if lib_dir:
                            found_libs = lib_dir
                            break
                    if found_headers and found_libs:
                        break
                    
            if found_headers and found_libs:
                for root, dirs, files in os.walk(found_headers, topdown=False):
                    for name in files:
                        if self.timedout['timedout']:
                            return
                        version_file = self.checkVersion(test_env, name, root)
                        if version_file:
                            found_version = version_file
                            break
                    if found_version:
                        break

                if self.compileTest(test_env):
                    self.p.InfoPrint(" Found " + self.packagename + " version " + self.version +
                                        " in " + str(found_headers))
                    return self.foundPackage(test_env, found_libs, found_headers, found_version)
                else:
                    self.p.InfoPrint(" Candidate failed in " + found_headers + " and " + found_libs)
                    test_env = self.getTestEnv()
                    found_libs = None
                    found_headers = None
                    found_version = None
            else:
                test_env = self.getTestEnv()
                found_libs = None
                found_headers = None
                found_freetype_version = None

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
            #include <graphite2/Font.h>
            int main()
            {
                int nMajor, nMinor, nBugFix;
                gr_engine_version(&nMajor, &nMinor, &nBugFix);
                return 0;
            }
            """, '.c')

            conf.Finish()
            return result

        def checkHeader(self, env, file, root):
            if file == 'Font.h' and os.path.basename(root) == 'graphite2':
                env.Append(CPPPATH=[os.path.dirname(root)])
                return os.path.dirname(root)

        def checkLib(self, env, file, root):
            if ('graphite2' in file
                and (file.startswith(env["SHLIBPREFIX"]) or file.startswith(env["LIBPREFIX"]))
                and (file.endswith(env["SHLIBSUFFIX"]) or file.endswith(env["SHLIBSUFFIX"]))):
                env.Append(LIBPATH=[root])
                return root
        
        def checkVersion(self, env, file, root):
            if file == 'Font.h' and os.path.basename(root) == 'graphite2':
                version_file = os.path.join(root, file)
                with open(version_file) as f:
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
                return version_file

        def foundPackage(self, env, found_libs, found_headers, found_version):
            if self.env:
                self.env.Append(
                    LIBPATH=[found_libs],
                    CPPPATH=[found_headers],
                    LIB=['graphite2'])
                return self.env
            else:
                return env
                
    finder = Graphite2Finder(env, paths, required, timeout, conf_dir)
    return finder.startSearch()


def FindGlib(env=None, paths=[], required=False, timeout=None, conf_dir=None):
    class GlibFinder(PackageFinder):
        def __init__(self, env, paths, required, timeout, conf_dir):
            super(GlibFinder, self).__init__(env, paths, required, timeout, conf_dir)

            self.packagename = 'glib-2.0'

            if os.environ.get('GLIB_DIR'):
                self.user_paths.append(os.environ.get('GLIB_DIR'))

            if env and env.get('GLIB_DIR'):
                self.user_paths.append(env.get('GLIB_DIR'))

        def compileTest(self, env):
            env.Append(LIBS=['glib-2.0'])
            conf = Configure(
                env,
                conf_dir=self.conf_dir + "/findglib2",
                log_file=self.conf_dir + "/findglib2/conf.log")

            result = conf.TryLink("""
            #include <glib.h>
            int main()
            {
                const gchar* check = glib_check_version (
                    GLIB_MAJOR_VERSION,
                    GLIB_MINOR_VERSION,
                    GLIB_MICRO_VERSION);
             
                return (int)check;
            }
            """, '.c')
            conf.Finish()
            return result

        def checkHeader(self, env, file, root):
            if file == 'glib.h':
                env.Append(CPPPATH=[root])
                return root
            if file == 'glibconfig.h':
                env.Append(CPPPATH=[root])
                return root

        def checkLib(self, env, file, root):
            if ('glib-2.0' in file
                and (file.startswith(env["SHLIBPREFIX"]) or file.startswith(env["LIBPREFIX"]))
                and (file.endswith(env["SHLIBSUFFIX"]) or file.endswith(env["SHLIBSUFFIX"]))):
                env.Append(LIBPATH=[root])
                found_headers = False
                for configroot, dirs, files in os.walk(root, topdown=False):
                    for name in files:
                        if self.timedout['timedout']:
                            return
                        header_dir = self.checkHeader(env, name, configroot)
                        if header_dir:
                            found_headers = header_dir
                            break
                    if found_headers:
                        break
                return root

        def checkVersion(self, env, file, root):
            if file == 'glibconfig.h':
                version_file = os.path.join(root, file)
                with open(version_file) as f:
                    contents = f.read()
                    major = re.search(
                        r'^#define\s+GLIB_MAJOR_VERSION\s+(\d+)', contents, re.MULTILINE)
                    if major:
                        self.version += str(major.group(1))
                    minor = re.search(
                        r'^#define\s+GLIB_MINOR_VERSION\s+(\d+)', contents, re.MULTILINE)
                    if minor:
                        self.version += "." + str(minor.group(1))
                    patch = re.search(
                        r'^#define\s+GLIB_MICRO_VERSION\s+(\d+)', contents, re.MULTILINE)
                    if patch:
                        self.version += "." + str(patch.group(1))
                return version_file

        def foundPackage(self, env, found_libs, found_headers, found_version):
            if self.env:
                self.env.AppendUnique(
                    LIBPATH=found_libs,
                    CPPPATH=env['CPPPATH'],
                    LIB=['glib-2.0'])
                return self.env
            else:
                return env
    
    finder = GlibFinder(env, paths, required, timeout, conf_dir)
    return finder.startSearch()


def FindIcu(env=None, paths=[], required=False, timeout=None, conf_dir=None):
    class IcuFinder(PackageFinder):
        def __init__(self, env, paths, required, timeout, conf_dir):
            super(IcuFinder, self).__init__(env, paths, required, timeout, conf_dir)
            self.packagename = 'icu-uc'

            if os.environ.get('ICU_DIR'):
                self.user_paths.append(os.environ.get('ICU_DIR'))

            if env and env.get('ICU_DIR'):
                self.user_paths.append(env.get('ICU_DIR'))

        def compileTest(self, env):
            env.Append(LIB=['icuuc', 'icudata'])
            conf = Configure(
                env,
                conf_dir=self.conf_dir + "/findicu",
                log_file=self.conf_dir + "/findicu/conf.log")

            result = conf.TryLink("""
            #include <unicode/ucnv.h>
            int main()
            {
                UErrorCode status = U_ZERO_ERROR;
                UConverter *defConv;
                defConv = u_getDefaultConverter(&status);
                if (U_FAILURE(status)) {
                    return 1;
                }
                return 0;
            }
            """, '.c')

            conf.Finish()
            return result

        def checkHeader(self, env, file, root):
            if file == 'ucnv.h' and os.path.basename(root) == 'unicode':
                env.Append(CPPPATH=[os.path.dirname(root)])
                return os.path.dirname(root)

        def checkLib(self, env, file, root):
            if ('icuuc' in file
                and (file.startswith(env["SHLIBPREFIX"]) or file.startswith(env["LIBPREFIX"]))
                and (file.endswith(env["SHLIBSUFFIX"]) or file.endswith(env["SHLIBSUFFIX"]))):
                env.Append(LIBPATH=[root])
                return root
            if ('icudata' in file
                and (file.startswith(env["SHLIBPREFIX"]) or file.startswith(env["LIBPREFIX"]))
                and (file.endswith(env["SHLIBSUFFIX"]) or file.endswith(env["SHLIBSUFFIX"]))):
                env.Append(LIBPATH=[root])
                return root
        
        def checkVersion(self, env, file, root):
            if file == 'uvernum.h' and os.path.basename(root) == 'unicode':
                version_file = os.path.join(root, file)
                with open(version_file) as f:
                    contents = f.read()
                    major = re.search(
                        r'^#define\s+U_ICU_VERSION_MAJOR_NUM\s+(\d+)', contents, re.MULTILINE)
                    if major:
                        self.version += str(major.group(1))
                    minor = re.search(
                        r'^#define\s+U_ICU_VERSION_MINOR_NUM\s+(\d+)', contents, re.MULTILINE)
                    if minor:
                        self.version += "." + str(minor.group(1))
                    patch = re.search(
                        r'^#define\s+U_ICU_VERSION_PATCHLEVEL_NUM\s+(\d+)', contents, re.MULTILINE)
                    if patch:
                        self.version += "." + str(patch.group(1))
                return version_file

        def foundPackage(self, env, found_libs, found_headers, found_version):
            if self.env:
                self.env.Append(
                    LIBPATH=[found_libs],
                    CPPPATH=[found_headers],
                    LIB=['icuuc', 'icudata'])
                return self.env
            else:
                return env
    
    finder = IcuFinder(env, paths, required, timeout, conf_dir)
    return finder.startSearch()


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

        def checkHeader(self, env, file, root):
            if file == 'ft2build.h':
                env.Append(CPPPATH=[root])
                return root

        def checkLib(self, env, file, root):
            if ('freetype' in file
                and (file.startswith(env["SHLIBPREFIX"]) or file.startswith(env["LIBPREFIX"]))
                and (file.endswith(env["SHLIBSUFFIX"]) or file.endswith(env["SHLIBSUFFIX"]))):
                env.Append(LIBPATH=[root])
                return root
        
        def checkVersion(self, env, file, root):
            if file == 'freetype.h':
                version_file = os.path.join(root, file)
                with open(version_file) as f:
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
                return version_file

        def foundPackage(self, env, found_libs, found_headers, found_version):
            if self.env:
                self.env.Append(
                    LIBPATH=[found_libs],
                    CPPPATH=[found_headers],
                    LIB=['freetype'])
                return self.env
            else:
                return env

    finder = FreetypeFinder(env, paths, required, timeout, conf_dir)
    return finder.startSearch()

def FindCairo(env=None, paths=[], required=False, timeout=None, conf_dir=None):
    class CairoFinder(PackageFinder):
        def __init__(self, env, paths, required, timeout, conf_dir):
            super(CairoFinder, self).__init__(env, paths, required, timeout, conf_dir)

            self.packagename = 'cairo'

            if os.environ.get('CAIRO_DIR'):
                self.user_paths.append(os.environ.get('CAIRO_DIR'))

            if env and env.get('CAIRO_DIR'):
                self.user_paths.append(env.get('CAIRO_DIR'))

        def compileTest(self, env):
            env.Append(LIBS=['cairo'])
            conf = Configure(
                env,
                conf_dir=self.conf_dir + "/findcairo",
                log_file=self.conf_dir + "/findcairo/conf.log")

            result = conf.TryLink("""
            #include <cairo.h>
            int main()
            {
                const char* version = cairo_version_string();
                return 0;
            }
            """, '.c')
            conf.Finish()
            return result

        def checkHeader(self, env, file, root):
            if file == 'cairo.h':
                env.Append(CPPPATH=[root])
                return root

        def checkLib(self, env, file, root):
            if ('cairo' in file
                and (file.startswith(env["SHLIBPREFIX"]) or file.startswith(env["LIBPREFIX"]))
                and (file.endswith(env["SHLIBSUFFIX"]) or file.endswith(env["SHLIBSUFFIX"]))):
                env.Append(LIBPATH=[root])
                return root
        
        def checkVersion(self, env, file, root):
            if file == 'cairo-version.h':
                version_file = os.path.join(root, file)
                with open(version_file) as f:
                    contents = f.read()
                    major = re.search(
                        r'^#define\s+CAIRO_VERSION_MAJOR\s+(\d+)', contents, re.MULTILINE)
                    if major:
                        self.version += str(major.group(1))
                    minor = re.search(
                        r'^#define\s+CAIRO_VERSION_MINOR\s+(\d+)', contents, re.MULTILINE)
                    if minor:
                        self.version += "." + str(minor.group(1))
                    patch = re.search(
                        r'^#define\s+CAIRO_VERSION_MICRO\s+(\d+)', contents, re.MULTILINE)
                    if patch:
                        self.version += "." + str(patch.group(1))
                return version_file

        def foundPackage(self, env, found_libs, found_headers, found_version):
            if self.env:
                self.env.Append(
                    LIBPATH=[found_libs],
                    CPPPATH=[found_headers],
                    LIB=['cairo'])
                return self.env
            else:
                return env

    finder = CairoFinder(env, paths, required, timeout, conf_dir)
    return finder.startSearch()
