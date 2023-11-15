import bpy


class DefaultContext(object):

    __IS_RUNNING = False

    def __enter__(self):
        pass

    def __exit__(self, type, value, traceback):
        pass


def select(toSelect, replace=True):
    if replace:
        bpy.ops.object.select_all(action='DESELECT')

    for each in toSelect:
        each.select_set(True)


def getDisplay(object_):
    return object_.name


def toViewportHUD(widget):
    pass
