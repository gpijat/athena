import sys
import os


class DefaultContext(object):

    __IS_RUNNING = False

    def __enter__(self):
        pass

    def __exit__(self, type, value, traceback):
        pass


def select(toSelect, replace=True):
    pass


def getDisplay(object_):
    return str(object_)


def toViewportHUD(widget):
    pass
