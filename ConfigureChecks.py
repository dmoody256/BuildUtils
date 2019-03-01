from BuildUtils.ColorPrinter import ColorPrinter

p = ColorPrinter()


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
        'Checking for a pointer-size integer type... '))
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


def CheckUnistdH(context):
    context.Message(p.ConfigString('Checking for unistd.h... '))
    result = context.TryCompile("""
        # include <unistd.h>
        int main() { return 0; }
    """,
                                '.c')
    if result:
        context.env["ZCONFH"] = re.sub(
            r"def\sHAVE_UNISTD_H(.*)\smay\sbe", r" 1\1 was", context.env["ZCONFH"], re.MULTILINE)
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
    if result:
        context.env["ZCONFH"] = re.sub(
            r"def\sHAVE_STDARG_H(.*)\smay\sbe", r" 1\1 was", context.env["ZCONFH"], re.MULTILINE)
    context.Result(result)
    return result


def AddZPrefix(context):
    context.Message(p.ConfigString('Using z_ prefix on all symbols... '))
    result = context.env['ZPREFIX']
    if result:
        context.env["ZCONFH"] = re.sub(
            r"def\sZ_PREFIX(.*)\smay\sbe", r" 1\1 was", context.env["ZCONFH"], re.MULTILINE)
    context.Result(result)
    return result


def AddSolo(context):
    context.Message(p.ConfigString('Using Z_SOLO to build... '))
    result = context.env['SOLO']
    if result:
        context.env["ZCONFH"] = re.sub(
            r"\#define\sZCONF_H", r"#define ZCONF_H\n#define Z_SOLO", context.env["ZCONFH"], re.MULTILINE)
    context.Result(result)
    return result


def AddCover(context):
    context.Message(p.ConfigString('Using code coverage flags... '))
    result = context.env['COVER']
    if result:
        context.env.Append(CCFLAGS=[
            '-fprofile-arcs',
            '-ftest-coverage',
        ])
        context.env.Append(LINKFLAGS=[
            '-fprofile-arcs',
            '-ftest-coverage',
        ])
        context.env.Append(LIBS=[
            'gcov',
        ])
    if not context.env['GCC_CLASSIC'] == "":
        context.env.Replace(CC=context.env['GCC_CLASSIC'])
    context.Result(result)
    return result


def CheckVsnprintf(context):
    context.Message(p.ConfigString(
        "Checking whether to use vs[n]printf() or s[n]printf()... "))
    result = context.TryCompile("""
        # include <stdio.h>
        # include <stdarg.h>
        # include "zconf.h"
        int main()
        {
        # ifndef STDC
            choke me
        # endif
            return 0;
        }
    """,
                                '.c')
    if result:
        context.Result("using vs[n]printf().")
    else:
        context.Result("using s[n]printf().")
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
            "  WARNING: vsnprintf() not found, falling back to vsprintf(). zlib"))
        print(p.ConfigString(
            "  can build but will be open to possible buffer-overflow security"))
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
            "  WARNING: apparently vsnprintf() does not return a value. zlib"))
        print(p.ConfigString(
            "  can build but will be open to possible string-format security"))
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
            "  WARNING: apparently vsprintf() does not return a value. zlib"))
        print(p.ConfigString(
            "  can build but will be open to possible string-format security"))
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
            "  WARNING: snprintf() not found, falling back to sprintf(). zlib"))
        print(p.ConfigString(
            "  can build but will be open to possible buffer-overflow security"))
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
            "  WARNING: apparently snprintf() does not return a value. zlib"))
        print(p.ConfigString(
            "  can build but will be open to possible string-format security"))
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
            "  WARNING: apparently sprintf() does not return a value. zlib"))
        print(p.ConfigString(
            "  can build but will be open to possible string-format security"))
        print(p.ConfigString("  vulnerabilities."))
    return result


def CheckHidden(context):
    context.Message(p.ConfigString(
        "Checking for attribute(visibility) support... "))
    result = context.TryCompile("""
        # define ZLIB_INTERNAL __attribute__((visibility ("hidden")))
        int ZLIB_INTERNAL foo;
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