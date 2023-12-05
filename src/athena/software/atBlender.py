from typing import Iterable

import bpy


def select(toSelect: Iterable[bpy.types.Object], replace: bool = True) -> None:
    """Allow software selection in Blender.

    Parameters:
        toSelect: All nodes to select.
        replace: Whether or not to replace the current selection with the new objects to select.
    """

    if replace:
        bpy.ops.object.select_all(action='DESELECT')

    for each in toSelect:
        each.select_set(True)


def getDisplay(object_: bpy.types.Object) -> str:
    """Get a proper displayable string for the given object.

    Will simply return the object's name.

    Parameters:
        object_: The object to get the name from.

    Return:
        The name of the given object.
    """

    return object_.name
