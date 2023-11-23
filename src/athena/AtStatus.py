from __future__ import annotations
import abc

from typing import Type, Optional, Any, Tuple, Sequence



_ALL_STATUS = {}

class Status(abc.ABC):
    """This is the base `Status` class that all type of status inherit From."""

    __slots__: Tuple[str] = ('_name', '_level', '_color')

    def __new__(cls, *args: Any, **kwargs: Any) -> Status:
        """Allow to store all new levels in the __ALL_LEVELS class variable to return singleton."""

        instance = super(Status, cls).__new__(cls)
        _ALL_STATUS.setdefault(instance.__class__, set()).add(instance)

        return instance
    
    def __init__(self, name: str, color: Sequence[float, float, float], level: float) -> None:
        """Create the __Status object and setup it's attributes"""

        self._name = name
        self._color = tuple(color)
        self._level = level

    def __lt__(self, other: Status) -> bool:
        return self._level < other._level

    def __le__(self, other: Status) -> bool:
        return self._level <= other._level

    def __gt__(self, other: Status) -> bool:
        return self._level > other._level

    def __ge__(self, other: Status) -> bool:
        return self._level >= other._level

    def __eq__(self, other: Status) -> bool:
        return self._level == other._level

    def __ne__(self, other: Status) -> bool:
        return self._level != other._level

    def __hash__(self) -> int:
        return hash(id(self))

    @property
    def name(self) -> str:
        """Property to access the name of the __Status"""
        return self._name

    @property
    def level(self) -> int:
        """Property to access the level of the __Status"""
        return self._level

    @property
    def color(self) -> Tuple[float, float, float]:
        """Property to access the color of the __Status"""
        return self._color

class FailStatus(Status):
    """Represent a Fail Status, can be instantiated to define a new Fail level"""
    ...

class SuccessStatus(Status):
    """Represent a Success Status, can be instantiated to define a new Success level"""
    ...

class _BuiltInStatus(Status):
    """Represent a Built-In Status, can be instantiated to define a new Built-In level"""
    ...

_DEFAULT: _BuiltInStatus =  _BuiltInStatus('Default', (60, 60, 60), 0.0)
"""Default Status, it is set as base status for all :py:class:`.Process`"""

_SKIPPED: _BuiltInStatus = _BuiltInStatus('Skipped', (85, 85, 85), 0.0)

CORRECT: SuccessStatus = SuccessStatus('Correct', (22, 194, 15), 0.1)
"""lolo"""

SUCCESS: SuccessStatus = SuccessStatus('Success', (0, 128, 0), 0.2)

WARNING: FailStatus = FailStatus('Warning', (196, 98, 16), 1.1)
ERROR: FailStatus = FailStatus('Error', (150, 0, 0), 1.2)
CRITICAL: FailStatus = FailStatus('Critical', (102, 0, 0), 1.3)

_ABORTED: _BuiltInStatus = _BuiltInStatus('Aborted', (100, 100, 100), float('nan'))
_EXCEPTION: _BuiltInStatus = _BuiltInStatus('Exception', (125, 125, 125), float('nan'))


def getAllStatus() -> Tuple[Status, ...]:
    """Return all existing Status in a list.

    Return:
    -------
    list
        List containing all Status defined, Based on `Status.__Status._ALL_STATUS` keys.
    """

    return tuple(status for statusTypeList in _ALL_STATUS.values() for status in statusTypeList)


def getStatusByName(name: str) -> Optional[Status]:
    """Get a Status based on it's name.

    Parameters:
    -----------
    name: str
        Name of the status to find.

    Return:
    -------
    Status.__Status | None
        The status that match the name if any, else None.
    """

    for status in getAllStatus():
        if status._name == name:
            return status
    else:
        return None


def getAllFailStatus() -> Tuple[FailStatus, ...]:
    """Get all Fail Statuses.

    Return:
    -------
    list
        List of all Fail Statuses defined.
    """

    return tuple(_ALL_STATUS[FailStatus])


def getAllSuccessStatus() -> Tuple[SuccessStatus, ...]:
    """Get all Success Statuses.

    Return:
    -------
    list
        List of all Success Statuses defined.
    """

    return tuple(_ALL_STATUS[SuccessStatus])


def lowestFailStatus() -> FailStatus:
    """Get the lowest Fail Status based on Status._level.

    Return:
    -------
    FailStatus:
        The Fail Status with the lowest priority.
    """

    return sorted(getAllFailStatus(), key=lambda x: x._level)[0]


def highestFailStatus() -> FailStatus:
    """Get the highest Fail Status based on Status._level.

    Return:
    -------
    FailStatus:
        The Fail Status with the highest priority.
    """

    return sorted(getAllFailStatus(), key=lambda x: x._level)[-1]


def lowestSuccessStatus() -> SuccessStatus:
    """Get the lowest Success Status based on Status._level.

    Return:
    -------
    FailStatus:
        The Success Status with the lowest priority.
    """

    return sorted(getAllSuccessStatus(), key=lambda x: x._level)[0]


def highestSuccessStatus() -> SuccessStatus:
    """Get the highest Success Status based on Status._level.

    Return:
    -------
    FailStatus:
        The Success Status with the highest priority.
    """

    return sorted(getAllSuccessStatus(), key=lambda x: x._level)[-1]
