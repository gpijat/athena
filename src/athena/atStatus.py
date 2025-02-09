from __future__ import annotations

import abc
import numbers
from dataclasses import dataclass, field
from typing import Type, Optional, Any, Tuple, Sequence

from athena import atExceptions


_ALL_STATUS = {}
"""Store all Status that have been created to keep track of them and allow finding lowest/highest"""


class Status(abc.ABC):
    """Base `Status` class from which status inherit From.

    A Status represent the result state of an Athena's :class:`~Process`, it allows to categorise and prioritise it's 
    state using the :attr:`~Status.level`.
    A status also have a :attr:`~Status.color` assigned that may be used in a user interface to display the result to the
    users.

    Important:
        Every subclass of status must be `frozen` and `ordered` dataclass so that comparison operator will be implemented
        to sort the different statuses.
    """

    # name: str = field(compare=False)
    """The name of the Status, mostly used to differentiate multiple statuses of the same type. Not used in comparison."""

    # color: Tuple[numbers.Number, numbers.Number, numbers.Number] = field(compare=False)
    """The color that represent the status, to differentiate multiple statuses in a UI for instance. Not used in comparison"""

    # level: float = float('nan')
    """
    The level for the status, it must be a float greater than or equal to zero, `inf` or `nan` but those should be reserved
    for special use case.
    """
    
    def __init__(self, name, color, level):
        self._name = name
        self._color = color
        self._level = level

        global _ALL_STATUS

        _ALL_STATUS.setdefault(self.__class__, set()).add(self)

    def __repr__(self) -> str:
        """Human readable representation of the Status object.

        Return:
            A string representation of the Status including it's class, name and level. The color is represented as an
            rgb and therefore not expressive enough to be included.
        """

        return '<{}: {} ({})>'.format(self.__class__.__name__, self._name, self._level)
    
    def __eq__(self, other):
        if not isinstance(other, Status):
            raise TypeError('\'{}\' objects can only be compared to other \'{}\' objects.'.format(self.__class__.__name__))
        
        return self._level == other._level
    
    def __gt__(self, other):
        if not isinstance(other, Status):
            raise TypeError('\'{}\' objects can only be compared to other \'{}\' objects.'.format(self.__class__.__name__))
        
        return self._level > other._level
    
    def __lt__(self, other):
        if not isinstance(other, Status):
            raise TypeError('\'{}\' objects can only be compared to other \'{}\' objects.'.format(self.__class__.__name__))
        
        return self._level < other._level
    
    def __hash__(self):
        return hash((self._name, self._color, self._level))
    
    @property
    def name(self):
        return self._name
    
    @property
    def color(self):
        return self._color
    
    @property
    def level(self):
        return self._level


class FailStatus(Status):
    """Represent a Fail Status, can be instantiated to define a new Failure level
    
    Notes:
        :class:`~FailStatus` should use level values greater than 0, the higher the value is, the more critical the Status
        is.
    """

    ...


class SuccessStatus(Status):
    """Represent a Success Status, can be instantiated to define a new Success level

    Notes:
        :class:`~SuccessStatus` should use level values lower than 0, the lower the value is, the less critical the Status
        is.
    """

    ...


class _BuiltInStatus(Status):
    """Represent a Built-In Status, can be instantiated to define a new Built-In level

    Creating new built-in Status must be reserved for framework level behavior, developers must work with other Status 
    types. Built-in Status usually represent special case and have special behavior recognized by the framework itself
    or third-party UI/Extensions.

    Notes:
        :class:`~_BuiltInStatus` instances should use special level, `0.0` is common and totally fine for a "default" 
        kind of built-in Status, on the other hand, built-in statuses that represent an exception may benefit from 
        something like `nan`.
        At the end, for :class:`~_BuiltInStatus` the level is less important as it's mostly used to sort Status and 
        built-in are handle differently as they are "specials" by nature.
    """

    ...


_DEFAULT: _BuiltInStatus =  _BuiltInStatus('Default', (60, 60, 60), 0.0)
"""Default Status, it is set as base status for all :class:`.Process`"""

_SKIPPED: _BuiltInStatus = _BuiltInStatus('Skipped', (85, 85, 85), float('nan'))
"""Represent the state of a :class:`~Process` for which execution has been skipped."""

SUCCESS: SuccessStatus = SuccessStatus('Success', (0, 128, 0), -float('inf'))
"""Base success status, represent the classic state of a successful :class:`~Process` execution."""

CORRECT: SuccessStatus = SuccessStatus('Correct', (22, 194, 15), -1.0)
"""Represent a "good enough" :class:`~Process` execution. Still successful but not optimal."""

WARNING: FailStatus = FailStatus('Warning', (196, 98, 16), 1.0)
"""Represent a lightly fail status, that are usually not too problematic as is but that may require attention."""

ERROR: FailStatus = FailStatus('Error', (150, 0, 0), float('inf'))
"""Base fail status, represent the classic state of a failed :class:`~Process` execution.""" 

_ABORTED: _BuiltInStatus = _BuiltInStatus('Aborted', (100, 100, 100), float('nan'))
"""Status to represent the state of a :class:`~Process` that has been aborted by user."""

_EXCEPTION: _BuiltInStatus = _BuiltInStatus('Exception', (125, 125, 125), float('nan'))
"""Status for a Process which encountered an Exception and was interupted."""


def get_all_statuses() -> Tuple[Status, ...]:
    """Return all existing Status in a list.

    Return:
        All instance of Status subclass defined. Contains the built-in one (defined in this module) as well as user defined
        Success subclass.
    """

    return tuple(status for status_type_list in _ALL_STATUS.values() for status in status_type_list)


def get_status_by_name(name: str) -> Optional[Status]:
    """Find Status instance based on it's name.

    Parameters:
        name: The name of the status to find.

    Return:
        The status that match the name if any, else None.
    """

    for status in get_all_statuses():
        if status.name == name:
            return status
    else:
        return None


def get_all_fail_status() -> Tuple[FailStatus, ...]:
    """Get all Fail Status instances.

    Return:
        All Fail Statuses instances.
    """

    return tuple(_ALL_STATUS[FailStatus])


def get_all_success_status() -> Tuple[SuccessStatus, ...]:
    """Get all Success Status instances.

    Return:
        All Success Statuses instances.
    """

    return tuple(_ALL_STATUS[SuccessStatus])


def lowest_fail_status() -> FailStatus:
    """Get the lowest Fail Status instance based on Status.level.

    Return:
        The Fail Status with the lowest level.
    """

    return sorted(get_all_fail_status(), key=lambda x: x.level)[0]


def highest_fail_status() -> FailStatus:
    """Get the highest Fail Status instance based on Status.level.

    Return:
        The Fail Status with the highest level.
    """

    return sorted(get_all_fail_status(), key=lambda x: x.level)[-1]


def lowest_success_status() -> SuccessStatus:
    """Get the lowest Success Status instance based on Status.level.

    Return:
        The Success Status with the lowest level.
    """

    return sorted(get_all_success_status(), key=lambda x: x.level)[0]


def highest_success_status() -> SuccessStatus:
    """Get the highest Success Status instance based on Status.level.

    Return:
        The Success Status with the highest level.
    """

    return sorted(get_all_success_status(), key=lambda x: x.level)[-1]
