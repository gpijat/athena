from typing import Iterable, Union

try: from typing import Protocol
except: from typing_extensions import Protocol

import unreal


class SupportsStr(Protocol):
    """Type Hints Protocol implementation for all class that support string convertion."""

    def __str__(self) -> str:
        """Minimal implementation to supports the str Protocol."""
        ...


def select(toSelect: Iterable[unreal.Actor], replace: bool = True) -> None:
    """Allow in-scene selection for Unreal-Engine.

    Parameters:
        toSelect: All Unreal actors to select in the current scene.
        replace: Whether or not the current selection should be replaced with the new objects.
    """

    actorSubSystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    if replace:
        actorSubSystem.clear_actor_selection_set()

    for each in toSelect:
        actorSubSystem.set_actor_selection_state(each, True)


def getDisplay(object_: Union[unreal.Actor, SupportsStr]) -> str:
    """Get a displayable string for the given object.
    
    If the input is an `unreal.Actor` object, it's label is returned. If not, it's just converted to string.

    Parameters:
        object_: The object to get a displayable string from. `unreal.Actor` are preferred but not mandatory.

    Return:
        A displayable string for the given object. For `unreal.Actor`, the label is returned.

    Notes:
        This methods works whether the input is an unreal.Actor or anything else that implement the str protocol.
    """

    if isinstance(object_, unreal.Actor):
        return object_.get_actor_label()

    return str(object_)
