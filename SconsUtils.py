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
Utility functios used for building.
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
import collections.abc

# scons
from SCons.Script.SConscript import call_stack
from SCons.Script.Main import Progress
from SCons import Action
from SCons.Defaults import Copy, mkdir_func, get_paths_str
from SCons.Script import Main
from SCons.Node import NodeList
from SCons.Environment import Environment
from SCons.Script.Main import GetOption
from SCons.Errors import BuildError
from SCons.Platform import TempFileMunge
from SCons.Action import ActionFactory


from BuildUtils.ColorPrinter import ColorPrinter
from BuildUtils import get_num_cpus

Mkdir = ActionFactory(mkdir_func,
                      lambda dir: ColorPrinter().InfoPrint(' Mkdir(%s)' % get_paths_str(dir)))


def SetBuildJobs(env):
    ###################################################
    # Determine number of Jobs
    # start by assuming num_jobs was not set
    NUM_JOBS_SET = False
    if GetOption("num_jobs") == 1:
        # if num_jobs is the default we need to check sys.argv
        # to see if the user happened to set the default
        for arg in sys.argv:
            if arg.startswith("-j") or arg.startswith("--jobs"):
                if arg == "-j" or arg == "--jobs":
                    if int(sys.argv[sys.argv.index(arg)+1]) == 1:
                        NUM_JOBS_SET = True
                else:
                    if arg.startswith("-j"):
                        if int(arg[2:]) == 1:
                            NUM_JOBS_SET = True
    else:
        # user must have set something if it wasn't default
        NUM_JOBS_SET = True

    # num_jobs wasn't specificed so let use the
    # max number since the user doesn't seem to care
    if not NUM_JOBS_SET:
        NUM_CPUS = get_num_cpus()
        ColorPrinter().InfoPrint(" Building with " + str(NUM_CPUS) + " parallel jobs")
        env.SetOption("num_jobs", NUM_CPUS)
    else:
        # user wants a certain number of jobs so do that
        ColorPrinter().InfoPrint(
            " Building with " + str(GetOption('num_jobs')) + " parallel jobs")


def ImportVar(import_name):
    """
    Function to workaround pylints dislike for globals.
    """
    frame = call_stack[-1]
    return frame.exports[import_name]


def bf_to_str(bf):
    """
    Convert an element of GetBuildFailures() to a string
    in a useful way.
    """
    import SCons.Errors
    # unknown targets product None in list
    if bf is None:
        return '(unknown tgt)'
    elif isinstance(bf, SCons.Errors.StopError):
        return str(bf)
    elif bf.node:
        return str(bf.node) + ': ' + bf.errstr
    elif bf.filename:
        return bf.filename + ': ' + bf.errstr
    return 'unknown failure: ' + bf.errstr


def build_status():
    """Convert the build status to a 2-tuple, (status, msg)."""
    from SCons.Script import GetBuildFailures
    bf = GetBuildFailures()
    if bf:
        # bf is normally a list of build failures; if an element is None,
        # it's because of a target that scons doesn't know anything about.
        status = 'failed'
        failures_message = "\n".join(["%s" % bf_to_str(x)
                                      for x in bf if x is not None])
    else:
        # if bf is None, the build completed successfully.
        status = 'ok'
        failures_message = ''
    return (status, failures_message)


def display_build_status(project_dir, start_time):
    """Display the build status.  Called by atexit.
    Here you could do all kinds of complicated things."""
    status, _unused_failures_message = build_status()

    ColorPrinter.cleanUpPrinter()
    printer = ColorPrinter()

    compile_logs = []
    link_logs = []

    for root, dirs, files in os.walk(project_dir + '/build'):
        for name in files:
            if name.endswith('_compile.txt'):
                compile_logs.append(os.path.join(root, name))
            if name.endswith('_link.txt'):
                link_logs.append(os.path.join(root, name))

    for filename in compile_logs:
        compileOutput = []
        sourcefile = os.path.basename(filename).replace("_compile.txt", "")
        f = open(filename, "r")

        tempList = f.read().splitlines()
        if tempList:
            if("windows" in platform.system().lower() and len(tempList) == 1):
                continue
            compileOutput += [
                printer.OKBLUE
                + sourcefile
                + ":"
                + printer.ENDC
            ]
            compileOutput += tempList

        pending_output = os.linesep
        found_info = False

        for line in compileOutput:
            if(('error' in line or 'warning' in line or "note" in line) and not line.startswith(sourcefile)):
                line = printer.highlight_word(line, "error", printer.FAIL)
                line = printer.highlight_word(line, "warning", printer.WARNING)
                line = printer.highlight_word(line, "note", printer.OKBLUE)
                found_info = True
            pending_output += line + os.linesep
        if found_info:
            print(pending_output)

    for filename in link_logs:
        linkOutput = []
        sourcefile = os.path.basename(filename).replace("_link.txt", "")
        f = open(filename, "r")
        tempList = f.read().splitlines()
        if tempList:
            linkOutput += [
                printer.OKBLUE
                + sourcefile
                + ":"
                + printer.ENDC
            ]
            linkOutput += tempList

        pending_output = os.linesep
        found_info = False
        for line in linkOutput:
            if(('error' in line or 'warning' in line or "note" in line) and not line.startswith(sourcefile)):
                line = printer.highlight_word(line, "error", printer.FAIL)
                line = printer.highlight_word(line, "warning", printer.WARNING)
                line = printer.highlight_word(line, "note", printer.OKBLUE)
                found_info = True
            pending_output += line + os.linesep
        if found_info:
            print(pending_output)

    if status == 'failed':
        print(printer.FAIL + "Build failed" + printer.ENDC +
              " in %.3f seconds" % (time.time() - start_time))
    elif status == 'ok':
        print(printer.OKGREEN + "Build succeeded" + printer.ENDC +
              " in %.3f seconds" % (time.time() - start_time))


class TempFileMungeOutput(TempFileMunge):

    def __call__(self, target, source, env, for_signature):
        cmdlist = super(TempFileMungeOutput, self).__call__(
            target, source, env, for_signature)
        if isinstance(cmdlist, collections.abc.Sequence) and not isinstance(cmdlist, str):
            newcmdlist = [cmdlist[0]]
            linkpath = cmdlist[1].split('\n')
            newcmdlist.append(linkpath[0])
            newcmdlist.append('2>&1')
            newcmdlist.append('>')
            newcmdlist.append(env['PROJECT_DIR'] + '/' + env['TEMPFILEBUILDDIR'] +
                              '/build_logs/' + env['TEMPFILEPROGNAME'] + '_link.txt')
            return newcmdlist
        else:
            return (cmdlist + ' 2>&1 > ' + env['PROJECT_DIR'] + '/' + env['TEMPFILEBUILDDIR'] +
                    '/build_logs/' + env['TEMPFILEPROGNAME'] + '_link.txt')


class ProgressCounter(object):

    """
    Utility class used for printing progress during the build.
    """
    class ProgressBuild():

        def __init__(self, sources, target, static):

            self.count = 0.0
            self.progress_sources = dict()
            self.target = None
            self.target_reported = False
            self.target_install = ''
            for source in sources:
                # print("Making key: " + os.path.splitext(source)[0])
                self.progress_sources[os.path.splitext(source)[0]] = False
            self.target = target
            if static:
                self.static_lib = "-static"
            else:
                self.static_lib = ""

    def __init__(self):
        self.printer = ColorPrinter()
        self.progress_builders = []

    def AddBuild(self, env, sources, target, static=False):
        env['PROJECT_DIR'] = env.get(
            'PROJECT_DIR', env.Dir('.').abspath)
        # self.printer.SetSize(self.target_name_size)
        # pathed_sources = [env.File(source).abspath.replace('\\', '/').replace(env['PROJECT_DIR'] + '/', '')
        #                  for source in sources]
        self.progress_builders.append(
            self.ProgressBuild(sources, target, static))

    def __call__(self, node, *args, **kw):
        # print(str(node))

        slashed_node = str(node).replace("\\", "/")
        for build in self.progress_builders:

            # print(build.target + ": "+str(node.get_state())+" - " + slashed_node)
            if(slashed_node.endswith(build.target)):

                target_name = os.path.splitext(build.target)[
                    0] + build.static_lib

                if(build.count == 0):
                    self.printer.InfoPrint(
                        self.printer.OKBLUE + "[ " + target_name + " ]" + self.printer.ENDC + " Building " + build.target)
                filename = os.path.basename(slashed_node)
                if(node.get_state() == 2) and not build.target_reported:
                    self.printer.LinkPrint(target_name, "Linking " + filename)
                    build.target_reported = True
                elif not build.target_reported:
                    self.printer.LinkPrint(
                        target_name, "Skipping, already built " + filename)
                    build.target_reported = True
        # TODO: make hanlding this file extensions better
        if(slashed_node.endswith(".obj")
           or slashed_node.endswith(".o")
           or slashed_node.endswith(".os")):

            slashed_node_file = os.path.splitext(slashed_node)[0]
            # print(" - " + slashed_node_file)
            for build in self.progress_builders:
                try:
                    if(not build.progress_sources[slashed_node_file]):
                        build.progress_sources[slashed_node_file] = True
                        target_name = os.path.splitext(build.target)[
                            0] + build.static_lib

                        if(build.count == 0):
                            self.printer.InfoPrint(
                                self.printer.OKBLUE + "[ " + target_name + " ]" + self.printer.ENDC + " Building " + build.target)

                        build.count += 1
                        percent = build.count / \
                            len(build.progress_sources.keys()) * 100.00
                        filename = os.path.basename(slashed_node)

                        if(node.get_state() == 2):
                            self.printer.CompilePrint(
                                percent, target_name, "Compiling " + filename)
                        else:
                            self.printer.CompilePrint(
                                percent, target_name, "Skipping, already built " + filename)

                        break
                except KeyError:
                    pass


def SetupBuildEnv(env, progress, prog_type, prog_name, source_files, build_dir, install_dir):

    build_env = env.Clone()
    # build_env.Execute(Mkdir(install_dir))
    build_env['PROJECT_DIR'] = build_env.get(
        'PROJECT_DIR', build_env.Dir('.').abspath)
    build_env['TEMPFILE'] = TempFileMungeOutput
    build_env['TEMPFILEBUILDDIR'] = build_dir
    build_env['TEMPFILEPROGNAME'] = prog_name
    header_files = []
    if prog_type == "unit":
        temp = []
        for source in source_files:
            temp.append(source.replace(".h", ".c"))
        header_files = source_files
        source_files = temp

    win_redirect = ""
    linux_redirect = "2>&1"
    if sys.platform == 'win32':
        win_redirect = "2>&1"
        linux_redirect = ""

    # clear out all previous build compile logs
    build_env['PROJECT_DIR'] + "/" + build_dir + "/build_logs"
    import os
    for root, dirs, files in os.walk(build_env['PROJECT_DIR'] + "/" + build_dir + "/build_logs"):
        for name in files:
            if name.endswith('.txt'):
                #os.unlink(os.path.join(root, name))
                pass

    source_objs = []
    source_build_files = []
    for file in source_files:
        build_env.VariantDir(
            build_dir + "/" + os.path.dirname(file), os.path.dirname(file), duplicate=0)

        file = build_dir + "/" + file
        source_build_files.append(file)

        if(prog_type == 'shared'):
            build_obj = build_env.SharedObject(file,
                                               SHCCCOM=build_env['SHCCCOM'] + " " + win_redirect + " > \"" + build_env['PROJECT_DIR'] + "/" + build_dir + "/build_logs/" + os.path.splitext(
                                                   os.path.basename(file))[0] + "_compile.txt\" " + linux_redirect,
                                               SHCXXCOM=build_env['SHCXXCOM'] + " " + win_redirect + " > \"" + build_env['PROJECT_DIR'] + "/" + build_dir + "/build_logs/" + os.path.splitext(os.path.basename(file))[0] + "_compile.txt\" " + linux_redirect)
            source_objs.append(build_obj)
        elif(prog_type == 'static' or prog_type == 'exec'):

            filename = os.path.splitext(os.path.basename(file))[0]
            build_obj = build_env.Object(file,
                                         CCCOM=build_env['CCCOM'] + " " + win_redirect + " > \"" + build_env['PROJECT_DIR'] +
                                         "/" + build_dir + "/build_logs/" + filename + "_compile.txt\" " + linux_redirect,
                                         CXXCOM=build_env['CXXCOM'] + " " + win_redirect + " > \"" + build_env['PROJECT_DIR'] + "/" + build_dir + "/build_logs/" + filename + "_compile.txt\" " + linux_redirect)
            source_objs.append(build_obj)

    if prog_type == 'shared':
        progress.AddBuild(env, source_build_files, env.subst(
            '$SHLIBPREFIX') + prog_name + env.subst('$SHLIBSUFFIX'))
    elif prog_type == 'static':
        progress.AddBuild(env, source_build_files, env.subst(
            '$LIBPREFIX') + prog_name + env.subst('$LIBSUFFIX'), True)
    elif prog_type == 'exec' or prog_type == 'unit':
        progress.AddBuild(env, source_build_files, env.subst(
            '$PROGPREFIX') + prog_name + env.subst('$PROGSUFFIX'))

    if(prog_type == 'shared'):
        if sys.platform != 'win32':
            linkcom_string_match = re.sub(
                r"\s\>\".*", "\",", build_env['SHLINKCOM'])
            build_env['SHLINKCOM'] = linkcom_string_match + str(
                " > " + build_env['PROJECT_DIR'] + "/" + build_dir + "/build_logs/" + prog_name + "_link.txt 2>&1")
    elif(prog_type == 'static' or prog_type == 'exec' or prog_type == 'unit'):
        if sys.platform != 'win32':
            linkcom_string_match = re.sub(
                r"\s\>\".*", "\",", build_env['LINKCOM'])
            build_env['LINKCOM'] = linkcom_string_match + str(
                " > " + build_env['PROJECT_DIR'] + "/" + build_dir + "/build_logs/" + prog_name + "_link.txt 2>&1")

    if(prog_type == "shared"):
        prog = build_env.SharedLibrary(
            build_env['PROJECT_DIR'] + "/" + build_dir + "/" + prog_name, source_objs)
        if type(prog) is NodeList:
            prog_build_name = os.path.basename(prog[0].abspath)
        else:
            prog_build_name = os.path.basename(prog.abspath)
        build_env.AlwaysBuild(build_env.Command(
            install_dir + '/' + prog_build_name, prog, Copy('$TARGET', '$SOURCE')))

    elif(prog_type == "static"):
        prog = build_env.StaticLibrary(
            build_env['PROJECT_DIR'] + "/" + build_dir + "/" + prog_name, source_objs)
        if type(prog) is NodeList:
            prog_build_name = os.path.basename(prog[0].abspath)
        else:
            prog_build_name = os.path.basename(prog.abspath)
        build_env.AlwaysBuild(build_env.Command(
            install_dir + '/' + prog_build_name, prog, Copy('$TARGET', '$SOURCE')))

    elif(prog_type == 'exec'):
        prog = build_env.Program(
            build_env['PROJECT_DIR'] + "/" + build_dir + "/" + prog_name, source_objs)

        if type(prog) is NodeList:
            prog_build_name = os.path.basename(prog[0].abspath)
        else:
            prog_build_name = os.path.basename(prog.abspath)
        build_env.AlwaysBuild(build_env.Command(
            install_dir + '/' + prog_build_name, prog, Copy('$TARGET', '$SOURCE')))

    elif(prog_type == 'unit'):
        prog = build_env.CxxTest(
            build_env['PROJECT_DIR'] + "/" + build_dir + "/" + prog_name, header_files, CXXTEST_RUNNER="ErrorPrinter", CXXTEST_OPTS="--world="+prog_name)
        for exe in prog:
            if os.path.basename(os.path.splitext(str(exe))[0]) == prog_name:
                for node in exe.children():
                    if os.path.basename(os.path.splitext(str(node))[0]) == prog_name:
                        if sys.platform != 'win32':
                            node.get_executor().set_action_list(Action.Action('$CXX -o $TARGET -c $CXXFLAGS $CCFLAGS $_CCCOMCOM $SOURCES ' + win_redirect +
                                                                              " > \"" + build_env['PROJECT_DIR'] + "/" + build_dir + "/build_logs/" + prog_name + "_compile.txt\" " + linux_redirect, '$CXXCOMSTR'))

    if not os.path.exists(build_env['PROJECT_DIR'] + "/" + build_dir + "/build_logs"):
        os.makedirs(build_env['PROJECT_DIR'] + "/" + build_dir + "/build_logs")

    # if ARGUMENTS.get('fail', 0):
    #    Command('target', 'source', ['/bin/false'])

    build_env['BUILD_LOG_TIME'] = datetime.datetime.fromtimestamp(
        time.time()).strftime('%Y_%m_%d__%H_%M_%S')

    def print_cmd_line(s, targets, sources, env):
        with open(env['PROJECT_DIR'] + "/" + build_dir + "/build_logs/build_" + env['BUILD_LOG_TIME'] + ".log", "a") as f:
            f.write(s + "\n")

    try:
        print_cmd = GetOption('option_verbose')
    except AttributeError:
        print_cmd = False

    if not print_cmd:
        build_env['PRINT_CMD_LINE_FUNC'] = print_cmd_line

    built_bins = []
    if("Windows" in platform.system()):
        if(prog_type == 'shared'):
            built_bins.append(build_dir + "/" + build_env.subst(
                '$SHLIBPREFIX') + prog_name + build_env.subst('$SHLIBSUFFIX'))
        elif(prog_type == 'static'):
            built_bins.append(build_dir + "/" + build_env.subst(
                '$LIBPREFIX') + prog_name + build_env.subst('$LIBSUFFIX'))
        elif(prog_type == 'exec'):
            built_bins.append(build_dir + "/" + build_env.subst(
                '$PROGPREFIX') + prog_name + build_env.subst('$PROGSUFFIX'))
    else:
        if(prog_type == 'shared'):
            built_bins.append(build_dir + "/" + build_env.subst(
                '$SHLIBPREFIX') + prog_name + build_env.subst('$SHLIBSUFFIX'))
        elif(prog_type == 'static'):
            built_bins.append(build_dir + "/" + build_env.subst(
                '$LIBPREFIX') + prog_name + build_env.subst('$LIBSUFFIX'))
        elif(prog_type == 'exec'):
            built_bins.append(build_dir + "/" + build_env.subst(
                '$PROGPREFIX') + prog_name + build_env.subst('$PROGSUFFIX'))

    return [build_env, prog]


def run_unit_tests(base_dir):
    """
    Callback function to run the test script.
    """

    test_env = os.environ
    test_env['TEST_BIN_DIR'] = base_dir+'/build/bin'

    proc = subprocess.Popen(
        args=['python', 'run_unit_tests.py'],
        cwd=base_dir+'/Testing',
        env=test_env
    )
    output = proc.communicate()[0]
    # print(output)


def run_visual_tests(base_dir):
    """
    Callback function to run the test script.
    """
    if('SIKULI_DIR' not in os.environ
       and not os.path.isdir(base_dir+'/Testing/VisualTests/SikuliX')):

        printer = ColorPrinter()
        printer.InfoPrint(
            ' Need to download and install sikuli... please be extra patient...')
        proc = subprocess.Popen([sys.executable, 'install_sikuliX.py'],
                                cwd=base_dir+'/Testing/VisualTests',
                                stderr=subprocess.STDOUT,
                                stdout=subprocess.PIPE,
                                shell=False)
        output, result = proc.communicate()
        output = output.decode("utf-8")
        if 'RunSetup: ... SikuliX Setup seems to have ended successfully ;-)' in output:
            printer.InfoPrint(' Silkuli Installed!')
        else:
            printer.InfoPrint(' Silkuli Failed to install!:')
            # print(output.decode("utf-8"))

    test_env = os.environ
    if 'SIKULI_DIR' not in os.environ:
        test_env['SIKULI_DIR'] = base_dir+'/Testing/VisualTests/SikuliX'

    test_env['TEST_BIN_DIR'] = base_dir+'/build/bin'

    if 'DISPLAY' not in test_env:
        test_env['DISPLAY'] = ':0'

    proc = subprocess.Popen(
        args=['python', 'run_visual_tests.py'],
        cwd=base_dir+'/Testing',
        env=test_env
    )
    output = proc.communicate()[0]
    # print(output)


def cppcheck_command(base_dir, jobs):
    """
    Callback function to run the test script.
    """
    printer = ColorPrinter()
    if "windows" in platform.system().lower():
        cppcheck_exec = base_dir+'/build/bin/cppcheck.exe'
    else:
        cppcheck_exec = './cppcheck'

    def execute():

        proc = subprocess.Popen(
            [cppcheck_exec,
                '--enable=all',
                '--suppress=*:../include/glm*',
                '-I../include',
                '-j',
                str(jobs),
                '-DGLM_FORCE_RADIANS',
                '-DODGL_LIBRARAY_BUILD',
                '../../Core',
                '../../AppFrameworks'
             ],
            cwd=base_dir+'/build/bin',
            stderr=subprocess.STDOUT,
            stdout=subprocess.PIPE,
            universal_newlines=True
        )
        for stdout_line in iter(proc.stdout.readline, ""):
            yield stdout_line
        proc.stdout.close()
        return_code = proc.wait()
        if return_code:
            raise subprocess.CalledProcessError(return_code, cppcheck_exec)

    style = ' (style) '
    performance = ' (performance) '
    portability = ' (portability) '
    warning = ' (warning) '
    error = ' (error) '
    information = ' (information) '

    errors = 0
    warnings = 0
    noncritical = 0

    for output in execute():
        output = output.strip()
        if(output.startswith('[') or output.endswith(r'% done')):

            if(style in output):
                noncritical += 1
                output = printer.highlight_word(
                    output, ' (style) ', printer.OKBLUE)
            elif(performance in output):
                noncritical += 1
                output = printer.highlight_word(
                    output, ' (performance) ', printer.OKBLUE)
            elif(portability in output):
                noncritical += 1
                output = printer.highlight_word(
                    output, ' (portability) ', printer.OKBLUE)
            elif(warning in output):
                warnings += 1
                output = printer.highlight_word(
                    output, ' (warning) ', printer.WARNING)
            elif(error in output):
                errors += 1
                output = printer.highlight_word(
                    output, ' (error) ', printer.FAIL)
            elif(information in output):
                noncritical += 1

            printer.CppCheckPrint(' ' + output)

    printer.InfoPrint(' Cppcheck finished, findings:')
    printer.InfoPrint('     Non-Critical: ' + str(noncritical))
    printer.InfoPrint('     Warnings:     ' + str(warnings))
    printer.InfoPrint('     Errors:       ' + str(errors))

    # TODO: enable once all cppcheck errors are cleaned up
    # if(noncritical + warnings + errors > 0):
    #    return BuildError(errstr='Cppcheck Failed!')
