from typing import Iterable

import hou


def select(toSelect: Iterable[hou.Node], replace: bool = True) -> None:
    """Implement software selection in Houdini.

    Parameters:
        toSelect: All `hou.Node` to select.
        replace: Whether or not the original selection must be replace with the given objects.
    """

    if replace:
        hou.clearAllSelected()

    for each in toSelect:
        each.setSelected(True)


def getDisplay(object_: hou.Node) -> str:
    """Get the given nice name for the given `hou.Node` for display purpose.

    Parameters:
        object_: The node to get a display from.
    
    Return:
        The name of the given `hou.Node` for display purpose.
    """

    return object_.name()
