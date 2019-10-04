import platform
import os
import sys
import time

from queue import Queue, Empty
from threading import Thread


class ColorPrinter():
    """
    Utility class used for printing colored messages.
    """

    warned = False
    threadStarted = False
    terminateThread = False
    printThread = None
    printQueue = Queue()

    def __init__(self, size=1):
        self.size = size

        if not ColorPrinter.threadStarted:
            ColorPrinter.terminateThread = False
            ColorPrinter.printThread = Thread(
                target=ColorPrinter.printQueueThread)
            ColorPrinter.printThread.daemon = True
            ColorPrinter.threadStarted = True
            ColorPrinter.printThread.start()

        try:
            from colorama import init
            init()
            self.HEADER = '\033[95m'
            self.OKBLUE = '\033[94m'
            self.OKGREEN = '\033[92m'
            self.WARNING = '\033[93m'
            self.FAIL = '\033[91m'
            self.ENDC = '\033[0m'
        except ImportError:
            if "windows" in platform.system().lower():
                if not ColorPrinter.warned:
                    ColorPrinter.printQueue.put(
                        "[!WARN!!] Failed to import colorama, build output will be uncolored.")
                    ColorPrinter.warned = True
                self.HEADER = ''
                self.OKBLUE = ''
                self.OKGREEN = ''
                self.WARNING = ''
                self.FAIL = ''
                self.ENDC = ''
            else:
                self.HEADER = '\033[95m'
                self.OKBLUE = '\033[94m'
                self.OKGREEN = '\033[92m'
                self.WARNING = '\033[93m'
                self.FAIL = '\033[91m'
                self.ENDC = '\033[0m'

    def cleanUpPrinter():
        ColorPrinter.terminateThread = True
        ColorPrinter.printThread.join()

    def printQueueThread():
        while True:
            time.sleep(0.001)
            while not ColorPrinter.printQueue.empty():
                try:
                    printItem = ColorPrinter.printQueue.get(
                        block=False)
                    sys.stdout.write(printItem + os.linesep)
                except Empty:
                    pass
            if ColorPrinter.terminateThread:
                break

    def SetSize(self, size):
        self.size = size

    def PrintItem(self, item):
        """
        Put something in the print queue to be printed.
        """
        ColorPrinter.printQueue.put(item)

    def highlight_word(self, line, word, color):
        """
        Highlights the word in the passed line if its present.
        """
        return line.replace(word, color + word + self.ENDC)

    def InfoPrint(self, message):
        """
        Prints a purple info message.
        """
        ColorPrinter.printQueue.put(self.InfoString(message))

    def CppCheckPrint(self, message):
        """
        Prints a purple info message.
        """
        ColorPrinter.printQueue.put(
            self.HEADER + "[CPPCHK!]" + self.ENDC + message)

    def InfoString(self, message):
        """
        Prints a purple info message.
        """
        return self.HEADER + "[ -INFO-]" + self.ENDC + message

    def ErrorPrint(self, message):
        """
        Prints a red error message.
        """
        ColorPrinter.printQueue.put(
            self.FAIL + "[  ERROR] " + self.ENDC + message)

    def CompilePrint(self, percent, build, message):
        """
        Prints a compiled message, including a green percent prefix.
        """
        percent_string = "{0:.2f}".format(percent)
        if percent < 100:
            percent_string = " " + percent_string
        if percent < 10:
            percent_string = " " + percent_string
        print_string = self.OKGREEN + \
            "[" + percent_string + "%]" + self.OKBLUE + \
            "[ " + build + " ] " + self.ENDC + message
        ColorPrinter.printQueue.put(print_string)

    def LinkPrint(self, build, message):
        """
        Prints a linked message, including a green link prefix.
        """
        ColorPrinter.printQueue.put(self.OKGREEN + "[ LINK!!]" + self.OKBLUE +
                                    "[ " + build + " ] " + self.ENDC + message)

    def TestPassPrint(self, message):
        """
        Prints a test result message.
        """
        ColorPrinter.printQueue.put(
            self.OKGREEN + "[ PASS!!]" + self.ENDC + message)

    def TestResultPrint(self, message):
        """
        Prints a test result message.
        """
        results_lines = message.split(os.linesep)
        for line in results_lines:
            ColorPrinter.printQueue.put(
                self.OKBLUE + "[RESULTS] " + self.ENDC + line)

    def TestFailPrint(self, message):
        """
        Prints a test result message.
        """
        ColorPrinter.printQueue.put(
            self.FAIL + "[ FAIL!!]" + self.ENDC + message)

    def ConfigString(self, message):
        """
        Prints a blue configure message.
        """
        return self.OKBLUE + "[ CONFIG] " + self.ENDC + message
