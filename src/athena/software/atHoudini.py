import hou


class DefaultContext(object):

    __IS_RUNNING = False

    def __enter__(self):
        pass

    def __exit__(self, type, value, traceback):
        pass


def select(toSelect, replace=True):
    if replace:
        hou.clearAllSelected()

    for each in toSelect:
        each.setSelected(True)


def getDisplay(object_):
    return object_.name()


def toViewportHUD(widget):
    pass
