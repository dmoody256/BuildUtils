import re

from BuildUtils.ColorPrinter import ColorPrinter

from SCons.Conftest import _lang2suffix, _YesNoResult

p = ColorPrinter()

def CheckHeader(context, header_name, header = None, language = None,
                                                        include_quotes = None):
    """
    Configure check for a C or C++ header file "header_name".
    Optional "header" can be defined to do something before including the
    header file (unusual, supported for consistency).
    "language" should be "C" or "C++" and is used to select the compiler.
    Default is "C".
    Sets HAVE_header_name in context.havedict according to the result.
    Note that this uses the current value of compiler and linker flags, make
    sure $CFLAGS and $CPPFLAGS are set correctly.
    Returns an empty string for success, an error message for failure.
    """
    # Why compile the program instead of just running the preprocessor?
    # It is possible that the header file exists, but actually using it may
    # fail (e.g., because it depends on other header files).  Thus this test is
    # more strict.  It may require using the "header" argument.
    #
    # Use <> by default, because the check is normally used for system header
    # files.  SCons passes '""' to overrule this.

    # Include "confdefs.h" first, so that the header can use HAVE_HEADER_H.
    if context.headerfilename:
        includetext = '#include "%s"\n' % context.headerfilename
    else:
        includetext = ''
    if not header:
        header = ""

    lang, suffix, msg = _lang2suffix(language)
    if msg:
        context.Display("Cannot check for header file %s: %s\n"
                                                          % (header_name, msg))
        return msg

    if not include_quotes:
        include_quotes = "<>"

    text = "%s%s\n#include %s%s%s\n\n" % (includetext, header,
                             include_quotes[0], header_name, include_quotes[1])

    context.Message(p.ConfigString("Checking for %s header file %s... " % (lang, header_name)))
    ret = context.CompileProg(text, suffix)
    context.Result(ret)
    return ret

def CheckFunc(context, function_name, header = None, language = None):
    """
    Configure check for a function "function_name".
    "language" should be "C" or "C++" and is used to select the compiler.
    Default is "C".
    Optional "header" can be defined to define a function prototype, include a
    header file or anything else that comes before main().
    Sets HAVE_function_name in context.havedict according to the result.
    Note that this uses the current value of compiler and linker flags, make
    sure $CFLAGS, $CPPFLAGS and $LIBS are set correctly.
    Returns an empty string for success, an error message for failure.
    """

    # Remarks from autoconf:
    # - Don't include <ctype.h> because on OSF/1 3.0 it includes <sys/types.h>
    #   which includes <sys/select.h> which contains a prototype for select.
    #   Similarly for bzero.
    # - assert.h is included to define __stub macros and hopefully few
    #   prototypes, which can conflict with char $1(); below.
    # - Override any gcc2 internal prototype to avoid an error.
    # - We use char for the function declaration because int might match the
    #   return type of a gcc2 builtin and then its argument prototype would
    #   still apply.
    # - The GNU C library defines this for functions which it implements to
    #   always fail with ENOSYS.  Some functions are actually named something
    #   starting with __ and the normal name is an alias.

    if context.headerfilename:
        includetext = '#include "%s"' % context.headerfilename
    else:
        includetext = ''
    if not header:
        header = """
        #ifdef __cplusplus
        extern "C"
        #endif
        char %s();""" % function_name

    lang, suffix, msg = _lang2suffix(language)
    if msg:
        context.Display(p.ConfigString("Cannot check for %s(): %s\n" % (function_name, msg)))
        return msg

    text = """
    %(include)s
    #include <assert.h>
    %(hdr)s

    int main(void) {
    #if defined (__stub_%(name)s) || defined (__stub___%(name)s)
    fail fail fail
    #else
    %(name)s();
    #endif

    return 0;
    }
    """ % { 'name': function_name,
            'include': includetext,
            'hdr': header }
    context.Message(p.ConfigString("Checking for %s function %s()... " % (lang, function_name)))
    ret = context.BuildProg(text, suffix)
    context.Result(ret)
    return ret

def CheckSolarisAtomics(context):
    context.Message(p.ConfigString('Checking for Solaris Atomics... '))
    result = context.TryCompile("""
        #include <atomic.h>
        /* This requires Solaris Studio 12.2 or newer: */
        #include <mbarrier.h>
        void memory_barrier (void) { __machine_rw_barrier (); }
        int atomic_add (volatile unsigned *i) { return atomic_add_int_nv (i, 1); }
        void *atomic_ptr_cmpxchg (volatile void **target, void *cmp, void *newval) { return atomic_cas_ptr (target, cmp, newval); }
        int main () { return 0; }
    """,
                                '.c')
    if result:
        context.env.Append(CPPDEFINES=['HAVE_SOLARIS_ATOMIC_OPS'])
    context.Result(result)
    return result


def CheckIntelAtomicPrimitives(context):
    context.Message(p.ConfigString('Checking for Intel Atomics... '))
    result = context.TryCompile("""
        void memory_barrier (void) { __sync_synchronize (); }
        int atomic_add (int *i) { return __sync_fetch_and_add (i, 1); }
        int mutex_trylock (int *m) { return __sync_lock_test_and_set (m, 1); }
        void mutex_unlock (int *m) { __sync_lock_release (m); }
        int main () { return 0; }
    """,
                                '.c')
    if result:
        context.env.Append(CPPDEFINES=['HAVE_INTEL_ATOMIC_PRIMITIVES'])
    context.Result(result)
    return result


def CheckLargeFile64(context):
    context.Message(p.ConfigString('Checking for off64_t... '))

    prev_defines = ""
    if('CPPDEFINES' in context.env):
        prev_defines = context.env['CPPDEFINES']

    context.env.Append(CPPDEFINES=['_LARGEFILE64_SOURCE=1'])
    result = context.TryCompile("""
        # include <sys/types.h>
        off64_t dummy = 0;
    """,
                                '.c')
    if not result:
        context.env.Replace(CPPDEFINES=prev_defines)
    context.Result(result)
    return result


def CheckFseeko(context):
    context.Message(p.ConfigString('Checking for fseeko... '))
    result = context.TryCompile("""
        # include <stdio.h>
        int main(void) {
            fseeko(NULL, 0, 0);
            return 0;
        }
    """,
                                '.c')
    if not result:
        context.env.Append(CPPDEFINES=['NO_FSEEKO'])
    context.Result(result)
    return result


def CheckSizeT(context):
    context.Message(p.ConfigString('Checking for size_t... '))
    result = context.TryCompile("""
        # include <stdio.h>
        # include <stdlib.h>
        size_t dummy = 0;
    """,
                                '.c')
    context.Result(result)
    return result


def CheckSizeTLongLong(context):
    context.Message(p.ConfigString('Checking for long long... '))
    result = context.TryCompile("""
        long long dummy = 0;
    """,
                                '.c')
    context.Result(result)
    return result


def CheckSizeTPointerSize(context, longlong_result):
    result = []
    context.Message(p.ConfigString(
        'Checking for pointer-size type... '))
    if longlong_result:
        result = context.TryRun("""
            # include <stdio.h>
            int main(void) {
                if (sizeof(void *) <= sizeof(int)) puts("int");
                else if (sizeof(void *) <= sizeof(long)) puts("long");
                else puts("z_longlong");
                return 0;
            }
        """,
                                '.c')
    else:
        result = context.TryRun("""
            # include <stdio.h>
            int main(void) {
                if (sizeof(void *) <= sizeof(int)) puts("int");
                else puts("long");
                return 0;
            }
        """,
                                '.c')

    if result[1] == "":
        context.Result("Failed.")
        return False
    else:
        context.env.Append(CPPDEFINES=['NO_SIZE_T='+result[1]])
        context.Result(result[1] + ".")
        return True


def CheckSharedLibrary(context):
    context.Message(p.ConfigString('Checking for shared library support... '))
    
    result = context.TryBuild(context.env.SharedLibrary, """
        extern int getchar();
        int hello() {return getchar();}
    """,
                              '.c')

    context.Result(result)
    return result

def CheckBSymbolic(context):
    context.Message(p.ConfigString('Checking for -Bsymbolic-functions... '))
    if context.env['CC'] == 'gcc' or context.env['CC'] == 'clang':
        prev_flags = None
        if('LINKFLAGS' in context.env):
            prev_flags = context.env['LINKFLAGS']

        context.env.Append(LINKFLAGS=['-Bsymbolic-functions'])
        result = context.TryBuild(context.env.SharedLibrary, """
            extern int getchar();
            int hello() {return getchar();}
        """,
                                '.c')
    
        context.env.Replace(LINKFLAGS=prev_flags)
    else:
        result = False
    context.Result(result)
    return result

def CheckStdCpp11(context):
    context.Message(p.ConfigString('Checking for c++11 support... '))
    prev_flags = None
    if 'CCFLAGS' in context.env:
        prev_flags = context.env['CCFLAGS']

    if context.env['CC'] == 'cl':
        context.env.Append(CCFLAGS=['/std:c++11'])
    else:
        context.env.Append(CCFLAGS=['-std=c++11'])

    result = context.TryCompile("""
        int main() { return 0; }
    """,
                                '.c')
    context.env['CCFLAGS']=prev_flags                 
    context.Result(result)
    return result

def CheckStdCpp14(context):
    context.Message(p.ConfigString('Checking for c++14 support... '))
    prev_flags = None
    if 'CCFLAGS' in context.env:
        prev_flags = context.env['CCFLAGS']

    if context.env['CC'] == 'cl':
        context.env.Append(CCFLAGS=['/std:c++14'])
    else:
        context.env.Append(CCFLAGS=['-std=c++14'])

    result = context.TryCompile("""
        int main() { return 0; }
    """,
                                '.c')
    context.env['CCFLAGS']=prev_flags                 
    context.Result(result)
    return result

def CheckStdCpp17(context):
    context.Message(p.ConfigString('Checking for c++17 support... '))
    prev_flags = None
    if 'CCFLAGS' in context.env:
        prev_flags = context.env['CCFLAGS']

    if context.env['CC'] == 'cl':
        context.env.Append(CCFLAGS=['/std:c++17'])
    else:
        context.env.Append(CCFLAGS=['-std=c++17'])

    result = context.TryCompile("""
        int main() { return 0; }
    """,
                                '.c')
    context.env['CCFLAGS']=prev_flags                 
    context.Result(result)
    return result

def CheckUnistdH(context):
    context.Message(p.ConfigString('Checking for unistd.h... '))
    result = context.TryCompile("""
        # include <unistd.h>
        int main() { return 0; }
    """,
                                '.c')
    context.Result(result)
    return result


def CheckStrerror(context):
    context.Message(p.ConfigString('Checking for strerror... '))
    result = context.TryCompile("""
        # include <string.h>
        # include <errno.h>
        int main() { return strlen(strerror(errno)); }
    """,
                                '.c')
    if not result:
        context.env.Append(CPPDEFINES=['NO_STRERROR'])
    context.Result(result)
    return result


def CheckStdargH(context):
    context.Message(p.ConfigString('Checking for stdarg.h... '))
    result = context.TryCompile("""
        # include <stdarg.h>
        int main() { return 0; }
    """,
                                '.c')
    context.Result(result)
    return result

def CheckVsnStdio(context):
    context.Message(p.ConfigString("Checking for vsnprintf() in stdio.h... "))
    result = context.TryCompile("""
        # include <stdio.h>
        # include <stdarg.h>
        int mytest(const char *fmt, ...)
        {
            char buf[20];
            va_list ap;
            va_start(ap, fmt);
            vsnprintf(buf, sizeof(buf), fmt, ap);
            va_end(ap);
            return 0;
        }
        int main()
        {
            return (mytest("Hello%d\\n", 1));
        }
    """,
                                '.c')
    context.Result(result)
    if not result:
        context.env.Append(CPPDEFINES=["NO_vsnprintf"])
        print(p.ConfigString(
            "  WARNING: vsnprintf() not found, falling back to vsprintf()."))
        print(p.ConfigString(
            "  Can build but will be open to possible buffer-overflow security"))
        print(p.ConfigString("  vulnerabilities."))
    return result


def CheckVsnprintfReturn(context):
    context.Message(p.ConfigString(
        "Checking for return value of vsnprintf()... "))
    result = context.TryCompile("""
        # include <stdio.h>
        # include <stdarg.h>
        int mytest(const char *fmt, ...)
        {
            int n;
            char buf[20];
            va_list ap;
            va_start(ap, fmt);
            n = vsnprintf(buf, sizeof(buf), fmt, ap);
            va_end(ap);
            return n;
        }
        int main()
        {
            return (mytest("Hello%d\\n", 1));
        }
    """,
                                '.c')
    context.Result(result)
    if not result:
        context.env.Append(CPPDEFINES=["HAS_vsnprintf_void"])
        print(p.ConfigString(
            "  WARNING: apparently vsnprintf() does not return a value."))
        print(p.ConfigString(
            "  Can build but will be open to possible string-format security"))
        print(p.ConfigString("  vulnerabilities."))
    return result


def CheckVsprintfReturn(context):
    context.Message(p.ConfigString(
        "Checking for return value of vsnprintf()... "))
    result = context.TryCompile("""
        # include <stdio.h>
        # include <stdarg.h>
        int mytest(const char *fmt, ...)
        {
            int n;
            char buf[20];
            va_list ap;
            va_start(ap, fmt);
            n = vsprintf(buf, fmt, ap);
            va_end(ap);
            return n;
        }
        int main()
        {
            return (mytest("Hello%d\\n", 1));
        }
    """,
                                '.c')
    context.Result(result)
    if not result:
        context.env.Append(CPPDEFINES=["HAS_vsprintf_void"])
        print(p.ConfigString(
            "  WARNING: apparently vsprintf() does not return a value."))
        print(p.ConfigString(
            "  Can build but will be open to possible string-format security"))
        print(p.ConfigString("  vulnerabilities."))
    return result


def CheckSnStdio(context):
    context.Message(p.ConfigString("Checking for snprintf() in stdio.h... "))
    result = context.TryCompile("""
        # include <stdio.h>
        int mytest()
        {
            char buf[20];
            snprintf(buf, sizeof(buf), "%s", "foo");
            return 0;
        }
        int main()
        {
            return (mytest());
        }
    """,
                                '.c')
    context.Result(result)
    if not result:
        context.env.Append(CPPDEFINES=["NO_snprintf"])
        print(p.ConfigString(
            "  WARNING: snprintf() not found, falling back to sprintf()."))
        print(p.ConfigString(
            "  Can build but will be open to possible buffer-overflow security"))
        print(p.ConfigString("  vulnerabilities."))
    return result


def CheckSnprintfReturn(context):
    context.Message(p.ConfigString(
        "Checking for return value of snprintf()... "))
    result = context.TryCompile("""
        # include <stdio.h>
        int mytest()
        {
            char buf[20];
            return snprintf(buf, sizeof(buf), "%s", "foo");
        }
        int main()
        {
            return (mytest());
        }
    """,
                                '.c')
    context.Result(result)
    if not result:
        context.env.Append(CPPDEFINES=["HAS_snprintf_void"])
        print(p.ConfigString(
            "  WARNING: apparently snprintf() does not return a value."))
        print(p.ConfigString(
            "  Can build but will be open to possible string-format security"))
        print(p.ConfigString("  vulnerabilities."))
    return result


def CheckSprintfReturn(context):
    context.Message(p.ConfigString(
        "Checking for return value of sprintf()... "))
    result = context.TryCompile("""
        # include <stdio.h>
        int mytest()
        {
            char buf[20];
            return sprintf(buf, "%s", "foo");
        }
        int main()
        {
            return (mytest());
        }
    """,
                                '.c')
    context.Result(result)
    if not result:
        context.env.Append(CPPDEFINES=["HAS_sprintf_void"])
        print(p.ConfigString(
            "  WARNING: apparently sprintf() does not return a value."))
        print(p.ConfigString(
            "  Can build but will be open to possible string-format security"))
        print(p.ConfigString("  vulnerabilities."))
    return result


def CheckHidden(context):
    context.Message(p.ConfigString(
        "Checking for attribute(visibility) support... "))
    result = context.TryCompile("""
        # define HIDDEN_INTERNAL __attribute__((visibility ("hidden")))
        int HIDDEN_INTERNAL foo;
        int main()
        {
            return 0;
        }
    """,
                                '.c')
    context.Result(result)
    if result:
        context.env.Append(CPPDEFINES=["HAVE_HIDDEN"])
    return result
