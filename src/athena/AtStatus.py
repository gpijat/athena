import abc


_ALL_STATUS = {}

class Status(abc.ABC):
    """This is the base `Status` class that all type of status inherit From."""

    __slots__ = ('_name', '_level', '_color')

    def __new__(cls, *args, **kwargs):
        """Allow to store all new levels in the __ALL_LEVELS class variable to return singleton."""

        instance = super(Status, cls).__new__(cls)
        _ALL_STATUS.setdefault(instance.__class__, set()).add(instance)

        return instance
    
    def __init__(self, name, color, level):
        """Create the __Status object and setup it's attributes"""

        self._name = name
        self._color = color
        self._level = level

    def __lt__(self, other):
        return self._level < other._level

    def __le__(self, other):
        return self._level <= other._level

    def __gt__(self, other):
        return self._level > other._level

    def __ge__(self, other):
        return self._level >= other._level

    def __eq__(self, other):
        return self._level == other._level

    def __ne__(self, other):
        return self._level != other._level

    def __hash__(self):
        return hash(id(self))

    @property
    def name(self):
        """Property to access the name of the __Status"""
        return self._name

    @property
    def level(self):
        """Property to access the level of the __Status"""
        return self._level

    @property
    def color(self):
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

_DEFAULT =  _BuiltInStatus('Default', (60, 60, 60), 0.0)
_SKIPPED = _BuiltInStatus('Skipped', (85, 85, 85), 0.0)

CORRECT = SuccessStatus('Correct', (22, 194, 15), 0.1)
SUCCESS = SuccessStatus('Success', (0, 128, 0), 0.2)

WARNING = FailStatus('Warning', (196, 98, 16), 1.1)
ERROR = FailStatus('Error', (150, 0, 0), 1.2)
CRITICAL = FailStatus('Critical', (102, 0, 0), 1.3)

_ABORTED = _BuiltInStatus('Aborted', (100, 100, 100), float('nan'))
_EXCEPTION = _BuiltInStatus('Exception', (125, 125, 125), float('nan'))


def getAllStatus():
    """Return all existing Status in a list.

    Return:
    -------
    list
        List containing all Status defined, Based on `Status.__Status._ALL_STATUS` keys.
    """

    return tuple(status for statusTypeList in __ALL_STATUS.values() for status in statusTypeList)


def getStatusByName(name):
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


def getAllFailStatus():
    """Get all Fail Statuses.

    Return:
    -------
    list
        List of all Fail Statuses defined.
    """

    return __ALL_STATUS[FailStatus]


def getAllSuccessStatus(cls):
    """Get all Success Statuses.

    Return:
    -------
    list
        List of all Success Statuses defined.
    """

    return __ALL_STATUS[SuccessStatus]


def lowestFailStatus(cls):
    """Get the lowest Fail Status based on Status._level.

    Return:
    -------
    FailStatus:
        The Fail Status with the lowest priority.
    """

    return sorted(getAllFailStatus(), key=lambda x: x._level)[0]


def highestFailStatus(cls):
    """Get the highest Fail Status based on Status._level.

    Return:
    -------
    FailStatus:
        The Fail Status with the highest priority.
    """

    return sorted(getAllFailStatus(), key=lambda x: x._level)[-1]


def lowestSuccessStatus(cls):
    """Get the lowest Success Status based on Status._level.

    Return:
    -------
    FailStatus:
        The Success Status with the lowest priority.
    """

    return sorted(getAllSuccessStatus(), key=lambda x: x._level)[0]


def highestSuccessStatus(cls):
    """Get the highest Success Status based on Status._level.

    Return:
    -------
    FailStatus:
        The Success Status with the highest priority.
    """

    return sorted(getAllSuccessStatus(), key=lambda x: x._level)[-1]
