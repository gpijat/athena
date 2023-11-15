from __future__ import annotations

import abc
import re
import os
import numbers
import time
import inspect
import enum
import pkgutil
import tempfile
import sys
import typing
from collections.abc import Collection
from dataclasses import dataclass, field

import cProfile
import pstats

from pprint import pprint

from athena import AtConstants
from athena import AtExceptions
from athena import AtUtils
from athena import AtStatus

class Event(object):

    def __init__(self, name):
        self._name = name
        self._callbacks = []

    def __call__(self, *args, **kwargs):
        for callback in self._callbacks:
            callback(*args, **kwargs)

    def addCallback(self, callback):
        if not callable(callback):
            AtUtils.LOGGER.warning(
                'Event "{0}" failed to register callback: Object "{1}" is not callable.'.format(self.name, callback)
            )
            return False

        self._callbacks.append(callback)

        return True


class EventSystem(abc.ABC):

    RegisterCreated = Event('RegisterCreated')
    BlueprintsReloaded = Event('BlueprintsReloaded')
    ProcessReseted = Event('ProcessReseted')
    
    DevModeEnabled = Event('DevModeEnabled')
    DevModeDisabled = Event('DevModeDisabled')


class AtSession(object):

    __instance = None

    class __AtSession(object):

        def __init__(self):
            self._dev = False

        # @AtUtils.lazyProperty
        # def environVar(self):
        #     return '{program}_{software}'.format(
        #         program=AtConstants.PROGRAM_NAME.upper(), 
        #         software=self.software.upper()
        #     ) 

        # @AtUtils.lazyProperty
        # def environ(self):
        #     if self.environVar in os.environ:
        #         return os.environ[self.environVar]

        #     os.environ[self.environVar] = ''
        #     if self.platform in ('Linux', 'Darwin'):
        #         os.system('export {}={}'.format(self.environVar, ''))
        #     elif self.platform == 'Windows':
        #         os.system('setx {} {}'.format(self.environVar, ''))

        #     return os.environ[self.environVar]

        @AtUtils.lazyProperty
        def register(self):
            return Register()

        @property
        def dev(self):
            return self._dev

        @dev.setter
        def dev(self, value):
            self._dev = bool(value)
            if value:
                EventSystem.DevModeEnabled()
            else:
                EventSystem.DevModeDisabled()

    def __new__(cls, *args, **kwargs):
        if cls.__instance is None:
            cls.__instance = cls.__AtSession()

        return cls.__instance


#TODO: When Python 3.10 will be more widely used according to vfxplatform, add slots.
@dataclass(frozen=True)
class ProtoFeedback(abc.ABC):
    feedback: object
    selectable: bool = field(compare=False)
    children: list[ProtoFeedback] = field(default_factory=list, init=False, hash=False)

    def __iter__(self):
        for child in self.children:
            yield child

    def __str__(self):
        return str(self.feedback)

    @abc.abstractmethod
    def select(self, replace:bool = True):
        NotImplemented

    @abc.abstractmethod
    def deselect(self):
        NotImplemented

    def parent(self, *feedbacks: list[ProtoFeedback]):
        self.children.extend(feedbacks)


@dataclass(frozen=True)
class FeedbackContainer(ProtoFeedback):
    feedback: Thread
    status: AtStatus.Status

    def __str__(self):
        return self.feedback._title

    def select(self, replace:bool = True) -> bool:
        if not self.selectable:
            return replace

        for child in self.children:
            child.select(replace=replace)
            replace = False

        return replace

    def deselect(self):
        if not self.selectable:
            return

        for child in self.children:
            child.deselect()

    def setStatus(self, status:AtStatus.Status):
        object.__setattr__(self, 'status', status)


@dataclass(frozen=True)
class Feedback(ProtoFeedback):
    feedback: object

    def select(self, replace:bool = True) -> bool:
        if not self.selectable:
            for child in self.children:
                child.select(replace=replace)
                replace = False

        return replace

    def deselect(self):
        if not self.selectable:
            for child in self.children:
                child.deselect()


class Thread(object):
    """To define in a Process as class attribute constant."""

    __slots__ = (
        '_title', 
        '_defaultFailStatus', 
        '_failStatus', 
        '_defaultSuccessStatus', 
        '_successStatus',
        '_documentation',
        'select',
        'display',
    )

    def __init__(self, title: str, failStatus: AtStatus.FailStatus = AtStatus.ERROR, successStatus: AtStatus.SuccessStatus = AtStatus.SUCCESS, documentation: str = None):

        if not isinstance(failStatus, AtStatus.FailStatus):
            raise AtExceptions.StatusException('`{}` is not a valid fail status.'.format(failStatus._name))
        if not isinstance(successStatus, AtStatus.SuccessStatus):
            raise AtExceptions.StatusException('`{}` is not a valid success status.'.format(successStatus._name))

        self._title = title

        self._defaultFailStatus = failStatus
        self._failStatus = failStatus

        self._defaultSuccessStatus = successStatus
        self._successStatus = successStatus

        self._documentation = documentation

    @property
    def title(self) -> str:
        return self._title

    @property
    def failStatus(self) -> AtStatus.FailStatus:
        return self._failStatus

    @property
    def successStatus(self) -> AtStatus.SuccessStatus:
        return self._successStatus

    def overrideFailStatus(self, status: AtStatus.FailStatus):
        self._failStatus = status

    def overrideSuccessStatus(self, status: AtStatus.SuccessStatus):
        self._successStatus = status

    def status(self, state: bool) -> AtStatus.Status:
        if state:
            return self._successStatus
        else:
            return self._failStatus


#TODO: On a major update, replace individual process computation with process that subscribe to iteration.
# e.g. AtPolygonIterator -> Iterate over polygons of a mesh and notify subscribers.
class Process(abc.ABC):
    """Abstract class from which any athena Processes must inherit.

    The Process object define default instance attributes for user to use and that are managed through the `automatic`
    decorator.
    When implementing a new Process you must defined at least one `Thread` object as a class attribute. When the Process
    will be instanciated the class Threads will be replaced with `_RuntimeThread` instances by the `Process` class constructor.
    You must use these Threads to manage the differents error the Process will have to check and maybe fix.
    It comes with methods to manage the internal feedback and the potentially connected QProgressbar.
    There is 3 non implemented methods that can or must be overrided to make a working Process.
        - `check`: This method is the only method that require to be overrided, it must allow to retrieve errors and
            set the success status of the process threads.
        - `fix`: Override this method to implement a way to automaticaly fix thread's errors found by the `check`.
        - `tool`: Allow to define a tool to allow a "semi-manual" fix by user.
    Also you can use the `setProgressValue` method to give feedback to the user on the current state of the check or fix
    progress, you can also give a str value to display on the progressbar. A progressBar must be linked for this feature to work.

    Some sunder attributes are also defined at the class level and allow to define some data to replace the class default one.
    For instance, defining `_name_` will give a name to the Process, different of the class name from `__name__`. This allow to define
    a nice name for users. There is the currently available sunder attributes:
        - `_name_`
        - `_doc_`

    You may want to create a custom base class for all your Process, if so, this base class must also inherit from `Process` to be
    recognized by the athena's API. You should not override the `__new__` method without using super or the Process will not be
    setuped as it should.
    """

    FEEDBACK_CONTAINER_CLASS = FeedbackContainer

    _name_ = ''
    _doc_ = ''

    _listenForUserInteruption = Event('ListenForUserInteruption')

    def __new__(cls, *args, **kwargs):
        """Generate a new class instance and setup its default attributes.
        
        The base class `Process` can't be instanciated because it is an abstract class made to be inherited
        and overrided by User Processes.
        `__new__` will simply create you instance and retrieve all the `Thread` to replace them with `_RuntimeThread`,
        all theses `_RuntimeThread` instances will then be stored in a private instance attribute. They will be accesible
        with a property `threads`.
        The sunder method will be set to the class data `instance._name_ = cls._name_ or cls.__name__`, this allow to use
        the class raw data if no nice values was set.
        """

        # Create the instance
        instance = super(Process, cls).__new__(cls, *args, **kwargs)

        # Instance internal data (Must not be altered by user)
        instance._feedbackContainer = cls.__makeFeedbackContainer()
        instance.__progressbar = None

        instance.__doInterupt = False

        # Sunder instance attribute (Can be overrided user to custom the process)
        instance._name_ = cls._name_ or cls.__name__
        instance._doc_ = cls._doc_ or cls.__doc__

        return instance

    def __str__(self):
        """Give a nice representation of the Process with it's nice name."""
        return '<Process `{0}` at {1}>'.format(self._name_, hex(id(self)))

    @classmethod
    def __makeFeedbackContainer(cls):
        return {thread: cls.FEEDBACK_CONTAINER_CLASS(thread, True, AtStatus._DEFAULT) for thread in cls.threads()}

    @classmethod
    def threads(cls):
        """Property to access the process instance threads."""
        for _, member in inspect.getmembers(cls):
            if isinstance(member, Thread):
                yield member

    def check(self, *args, **kwargs):
        """This method must be implemented on all Process and must retrieve error to set Threads status and feedback."""
        ...
        
    def fix(self, *args, **kwargs):
        """This method can be implemented to allow an automatic fix of the errors retrieved by the Process check."""
        ...

    def tool(self, *args, **kwargs):
        """This method can be implemented to open a window that can allow the user to manually find or fix the errors."""
        ...

    def setProgressbar(self, progressBar):
        """This method should be used to setup the Process progress bar

        Parameters
        ----------
        progressBar: QtWidgets.QProgressBar
            The new progress bar to link to The Process instance.
        """

        self.__progressbar = progressBar

    def setProgess(self, value=None, text=None):
        if value is not None:
            self.setProgressValue(value)

        if text is not None:
            self.setProgressText(text)

    def setProgressValue(self, value):
        """Set the progress value of the Process progress bar if exist.
        
        Parameters
        -----------
        value: numbres.Number
            The value to set the progress to.
        text: str or None
            Text to display in the progressBar, if None, the Default is used.
        """

        if self.__progressbar is None:
            return

        #WATCHME: `numbers.Number` is an abstract base class that define operations progressively, the first call to
        # this method will define it for the first time, this is why the profiler can detect some more calls for the
        # first call of the first process to be run. --> We talk about insignifiant time but the displayed data will
        # be a bit different.  see: https://docs.python.org/2/library/numbers.html
        assert isinstance(value, numbers.Number), 'Argument `value` is not numeric'
        
        if value and value != self.__progressbar.value():
            self.__progressbar.setValue(float(value))

    def setProgressText(self, text):
        if self.__progressbar is None:
            return

        assert isinstance(text, str), 'Argument `text` is not text'

        if text and text != self.__progressbar.text():
            self.__progressbar.setFormat(AtConstants.PROGRESSBAR_FORMAT.format(text))

    def clearFeedback(self):
        self._feedbackContainer = self.__makeFeedbackContainer()

    def hasFeedback(self, thread):
        return bool(self._feedbackContainer[thread].children)

    def addFeedback(self, thread, feedback):
        self._feedbackContainer[thread].parent(feedback)

    def iterFeedback(self, thread):
        return iter(self._feedbackContainer[thread].children)

    def feedbackCount(self, thread):
        return len(self._feedbackContainer[thread].children)

    def getFeedbacks(self):
        return self._feedbackContainer.values()

    def setSuccess(self, thread):
        self._feedbackContainer[thread].setStatus(thread.status(True))

    def setFail(self, thread):
        self._feedbackContainer[thread].setStatus(thread.status(False))

    def setSkipped(self, thread):
        self._feedbackContainer[thread].setStatus(AtStatus._SKIPPED)

    def listenForUserInteruption(self):
        if self.__doInterupt:
            return

        self._listenForUserInteruption()

        if self.__doInterupt:
            self.__doInterupt = False
            raise AtExceptions.AtProcessExecutionInterrupted()

    def _registerInteruption(self):
        self.__doInterupt = True


class Register(object):
    """The register is a container that allow the user to load and manage blueprints.

    After initialisation the register will not contain any data and you will need to manually load the data using the
    pyton import path of module path to load blueprints.
    It can be reloaded to simplify devellopment and magic methods like `__eq__` or `__bool__` are implemented.
    """

    def __init__(self):
        """Get the software and setup Register's blueprints list."""
        
        self.__blueprints = list()
        self._currentBlueprint = None

        EventSystem.RegisterCreated()

    def __bool__(self):
        """Allow to check if the register is empty or not based on the loaded blueprints."""
        return bool(self.__blueprint)

    __nonzero__ = __bool__

    def __eq__(self, other):
        """Allow to use '==' for logical comparison.

        This will first check if the compared object is also a Register, then it will compare all the internal data
        except the blueprints instances.

        Parameters
        ----------
        other: object
            Object to compare to this instance, should be another Register

        Notes
        -----
        A register is equal to another if the following attributes contains the same data:
            - software
            - blueprints
        """

        if not isinstance(other, self.__class__):
            return False

        return all((
            self._blueprints == other._blueprints,
        ))

    #FIXME: The import system is not easy to use, find a better way to use them.
    #TODO: Find a way to implement this feature and clean the import process.
    # def loadBlueprintFromPythonStr(self, pythonCode, moduleName):
    #     module = AtUtils.moduleFromStr(pythonCode, name=moduleName)
    #     self.loadBlueprintFromModule(Blueprint(module))

    def loadBlueprintsFromPackageStr(self, package):
        self.loadBlueprintsFromPackage(AtUtils.importFromStr(package))

    def loadBlueprintsFromPackage(self, package):
        for modulePath in AtUtils.iterBlueprintsPath(package):
            self.loadBlueprintFromModulePath(modulePath)

    def loadBlueprintFromModuleStr(self, moduleStr):
        self.loadBlueprintFromModule(AtUtils.importFromStr(moduleStr))

    def loadBlueprintFromModulePath(self, modulePath):
        module = AtUtils.importFromStr(AtUtils.pythonImportPathFromPath(modulePath))
        self.loadBlueprintFromModule(module)

    def loadBlueprintFromModule(self, module):
        newBlueprint = Blueprint(module)
        for i, blueprint in enumerate(self.__blueprints):
            if blueprint == newBlueprint:
                self.__blueprints[i] = newBlueprint
                break
        else:
            self.__blueprints.append(newBlueprint)

    def clear(self):
        """Remove all loaded blueprints from this register."""
        del self.__blueprints[:]

    @property
    def blueprints(self):
        """Get all Register blueprints"""
        return tuple(self.__blueprints)

    @property
    def currentBlueprint(self):
        return self._currentBlueprint

    @currentBlueprint.setter
    def currentBlueprint(self, blueprint):
        if blueprint in self.__blueprints:
            self._currentBlueprint = blueprint

    def blueprintByName(self, name):
        """Get a blueprints based on it's name, if no blueprint match the name, `None` is returned.

        Parameters
        ----------
        name: str
            The name of the blueprint to find.

        Return:
        -------
        str:
            The blueprint that match the name, or None if no blueprint match the given name.
        """

        for blueprint in self.__blueprints:
            if blueprint._name == name:
                return blueprint

    def reload(self):
        """Clear the blueprints and reload them to ensure all blueprints are up to date."""

        blueprints = self.__blueprints[:]
        self.clear()

        for blueprint in blueprints:
            for processor in blueprint.processors:
                AtUtils.reloadModule(processor.module)
            self.loadBlueprintFromModule(AtUtils.reloadModule(blueprint._module))

        EventSystem.BlueprintsReloaded()


#TODO: Maybe make this a subclass of types.ModuleType and wrap class creation.
class Blueprint(object):
    """A blueprints refer to a python module that contain the required data to make athena works.

    The module require at least two variables:
        - header: It contain a list of names ordered, this is the order of the checks.
        - descriptions: The description is a dict where each value in the header contain a dict of data to init a processor.
    Another variable called `settings` can also be added as a dict, these values will then allow to modify behaviour of the
    tool based on the current blueprint.

    The Blueprint is a lazy object that will load all it's data on demand to reduce initialisation calls, for example, no processors
    are created for a blueprints untils it's `processor` attribute is called.

    Notes:
        - The name of a processor is based on the name of it's module.
        - Data can be stored on a Blueprint using the `setData` method, this allow to store widgets if they are already
        created for example or any other kind of data.
    """

    def __init__(self, module):
        """Init the blueprint object by defining it's attributes"""

        self._module = module

        self._name = os.path.splitext(os.path.basename(module.__file__))[0] or module.__name__

    def __bool__(self):
        """Allow to deteremine if the blueprint contains processors or not.

        Return:
        -------
        bool:
            True if the blueprint contain at least one processor else False.
        """
        return bool(self.processors)

    __nonzero__ = __bool__

    def __hash__(self):
        return hash(self._module.__file__)

    def __eq__(self, other):
        return self._module.__file__ == other._module.__file__

    @property
    def name(self):
        """Property to get the Blueprint's name."""

        return self._name

    @property
    def module(self):
        """Property to get the Blueprint's module"""

        return self._module

    @AtUtils.lazyProperty
    def file(self):
        """Lazy property to get the Blueprint's module file path."""

        return os.path.dirname(self._module.__file__)

    @AtUtils.lazyProperty    
    def icon(self):
        """Lazy property to get the Blueprint's icon path.

        Notes:
            - The icon must be a `.png` file in the same folder as the Blueprint's module.
        """

        return os.path.join(self.file, '{0}.png'.format(self._name))

    @AtUtils.lazyProperty
    def header(self):
        """Lazy property to get the Blueprint's header."""

        return getattr(self._module, 'header', ())

    @AtUtils.lazyProperty
    def descriptions(self):
        """Lazy property to get the Blueprint's descriptions."""

        return getattr(self._module, 'descriptions', {})

    @AtUtils.lazyProperty
    def settings(self):
        """Lazy property to get the Blueprint's descriptions."""

        return getattr(self._module, 'settings', {})

    @AtUtils.lazyProperty
    def processors(self):
        """Lazy property to get the Blueprint's descriptors.
        
        It will create all the processors from the Blueprint's decsriptions ordered based on the header.
        This will also automatically resolve the links for each description in case this is meant to be used in batch.
        """
        
        batchLinkResolve = {}
        processorObjects = []

        for id_ in self.header:
            if id_ not in self.descriptions:
                continue

            processor = Processor(**self.descriptions[id_], settings=self.settings)

            processorObjects.append(processor)
            batchLinkResolve[id_] = processor if processor.inBatch else None
        
        # Default resolve for descriptions if available in batch, call the `resolveLinks` method from descriptions to change the targets functions.
        for processor in processorObjects:
            processor.resolveLinks(batchLinkResolve, check=AtConstants.CHECK, fix=AtConstants.FIX, tool=AtConstants.TOOL)

        return processorObjects

    def processorByName(self, name):
        """Find a processor from blueprint's processors based on it's name.
        
        Parameters:
        ----------
        name: str
            The name of the processor to find.

        Return:
        -------
        str
            The processor that match the name, or None if no processor match the given name.
        """

        for processor in self.processors:
            if processor.moduleName == name:
                return processor


class Processor(object):
    """The Processor is a proxy for a process object, build from the description of a blueprint.

    The Processor will init all informations it need to wrap a process like the methods that have been overrided, 
    if it can run a check, a fix, if it is part of te ui/batch, its name, docstring and a lot more.
    It will also resolve some of it's data lazilly to speed up execution process.
    """

    def __init__(self, process, category=None, arguments=None, tags=0, links=(), statusOverrides=None, settings=None, **kwargs):
        """Init the Processor instances attributes and define all the default values. The tags will also be resolved.

        Parameters
        -----------
        process: str
            The python path to import the process from, it must be a full import path to the Process class.
        category: str
            The name of the category of the Processor, if no value are provided the category will be `AtConstants.DEFAULT_CATEGORY` (default: `None`)
        arguments: dict(str: tuple(tuple, dict))
            This dict must contain by method name ('__init__', 'check', ...) a tuple containing a tuple for the args and 
            a dict for the keyword arguments. (default: `None`)
        tags: int
            The tag is an integer where bytes refers to `athena.AtCore.Tags`, it must be made of one or more tags. (default: `None`)
        links: tuple(tuple(str, Links, Links))
            The links must contain an ordered sequence of tuple with a str (ID) to another Process of the same blueprint, and two
            Links that are the source and the target methods to connect. (default: `None`)
        statusOverride: dict(str: dict(type: AtStatus.Status))
            Status overrides must be a dict with name of process Thread as key (str) and a dict with `AtStatus.FailStatus` or
            `AtStatus.SuccessStatus` as key (possibly both) and the status for the override as value. (default: `None`)
        settings: dict
            Setting is a dict that contain data as value for each setting name as key. (default: `None`)
        **kwargs:
            All remaining data passed at initialisation will automatically be used to init the Processor data.
        """

        self._processStrPath = process
        self._category = category or AtConstants.DEFAULT_CATEGORY
        self._arguments = arguments
        self._tags = tags
        self._links = links
        self._statusOverrides = statusOverrides
        self._settings = settings or {}

        self.__linksData = {Link.CHECK: [], Link.FIX: [], Link.TOOL: []}

        self.__isEnabled = True

        self.__isNonBlocking = False

        self.__inUi = True
        self.__inBatch = True

        # -- We setup the tags because this process is really fast and does not require to be lazy.
        # This also give access to more data without the need to build the process instance.
        self.setupTags()

        # -- Declare a blueprint internal data, these data are directly retrieved from blueprint's non built-in keys.
        self._data = dict(**kwargs)
        self._processProfile = _ProcessProfile()

    def __repr__(self):
        """Return the representation of the Processor."""
        return '<{0} `{1}` at {2}>'.format(self.__class__.__name__, self._processStrPath.rpartition('.')[2], hex(id(self)))

    @AtUtils.lazyProperty
    def moduleName(self):
        return self._processStrPath.rpartition('.')[2]

    @AtUtils.lazyProperty
    def module(self):
        """Lazy property that import and hold the module object for the Processor's Process."""

        return AtUtils.importProcessModuleFromPath(self._processStrPath)

    @AtUtils.lazyProperty
    def process(self):
        """Lazy property to get the process class object of the Processor"""

        initArgs, initKwargs = self.getArguments('__init__')
        process = getattr(self.module, self._processStrPath.rpartition('.')[2])(*initArgs, **initKwargs)

        # We do the overrides only once, they require the process instance.
        self._overrideLevels(process, self._statusOverrides)
        
        return process

    @AtUtils.lazyProperty
    def overridedMethods(self):
        """Lazy property to get the overrided methods of the Processor's Process class."""

        return AtUtils.getOverridedMethods(self.process.__class__, Process)

    @AtUtils.lazyProperty
    def niceName(self):
        """Lazy property to get a nice name based on the Processor's Process name."""

        return AtUtils.camelCaseSplit(self.process._name_)

    @AtUtils.lazyProperty
    def docstring(self):
        """Lazy property to get the docstring of the Processor's process."""
        return self._createDocstring()

    @AtUtils.lazyProperty
    def hasCheckMethod(self):
        """Get if the Processor's Process have a `check` method."""
        return bool(self.overridedMethods.get(AtConstants.CHECK, False))

    @AtUtils.lazyProperty
    def hasFixMethod(self):
        """Get if the Processor's Process have a `fix` method."""
        return bool(self.overridedMethods.get(AtConstants.FIX, False))

    @AtUtils.lazyProperty
    def hasToolMethod(self):
        """Get if the Processor's Process have a `tool` method."""
        return bool(self.overridedMethods.get(AtConstants.TOOL, False))

    @property
    def rawName(self):
        """Get the raw name of the Processor's Process."""
        return self.process._name_

    @property
    def isEnabled(self):
        """Get the Blueprint's enabled state."""
        return self.__isEnabled

    @property
    def isCheckable(self):
        """Get the Blueprint's checkable state"""
        return self.__isCheckable

    @property
    def isFixable(self):
        """Get the Blueprint's fixable state"""
        return self.__isFixable

    @property
    def inUi(self):
        """Get if the Blueprint should be run in ui"""
        return self.__inUi
    
    @property
    def inBatch(self):
        """Get if the Blueprint should be run in batch"""
        return self.__inBatch

    @property
    def isNonBlocking(self):
        """Get the Blueprint's non blocking state"""
        return self.__isNonBlocking

    @property
    def category(self):
        """Get the Blueprint's category"""
        return self._category

    def getSetting(setting, default=None):
        """Get the value for a specific setting if it exists, else None.

        Parameters:
        -----------
        setting: typing.hashable
            The setting to get from the Processor's settings.
        default: object
            The default value to return if the Processor does not have any value for this setting. (default: `None`)

        Return:
        -------
        object
            The value for the given setting or the default value if the given setting does not exists.
        """

        return self._settings.get(setting, default)

    def getLowestFailStatus(self):
        """Get the lowest Fail status from all Threads of the Processor's Process.

        Return:
        -------
        Status.FailStatus:
            The Lowest Fail Status of the Processor's Process
        """

        return next(iter(sorted((thread._failStatus for thread in self._threads.values()), key=lambda x: x._priority)), None)

    def getLowestSuccessStatus(self):
        """Get the lowest Success status from all Threads of the Processor's Process.

        Return:
        -------
        Status.SuccessStatus
            The Lowest Success Status of the Processor's Process
        """
        return next(iter(sorted((thread._successStatus for thread in self._threads.values()), key=lambda x: x._priority)), None)

    def _check(self, links=True, doProfiling=False):
        """This is a wrapper for the Processor's process's check that will automatically execute it with the right parameters.

        Parameters
        ----------
        links: bool
            Should the wrapper launch the connected links or not.
        doProfiling: bool
            Whether the check method will be runt with the Processor's Profiler and data retrieved or not. (default: `False`)

        Returns
        -------
        type
            The Processor's Process feedback.
        bool
            True if the Processor's Process have any feedback, False otherwise.
        """
        
        args, kwargs = self.getArguments(AtConstants.CHECK)

        try:
            if doProfiling:
                self._processProfile.profileMethod(self.process.check, *args, **kwargs)
            else:
                self.process.check(*args, **kwargs)
        except Exception as exception:
            raise
        finally:
            if links:
                self.runLinks(Link.CHECK)

        return self.process.getFeedbacks()

    def _fix(self, links=True, doProfiling=False):
        """This is a wrapper for the Processor's process's fix that will automatically execute it with the right parameters.
        
        Parameters
        ----------
        links: bool
            Should the wrapper launch the connected links or not.
        doProfiling: bool
            Whether the fix method will be runt with the Processor's Profiler and data retrieved or not. (default: `False`)

        Returns
        -------
        type
            The Processor's Process feedback.
        bool
            True if the Processor's Process have any feedback, False otherwise.
        """

        args, kwargs = self.getArguments(AtConstants.FIX)

        try:
            if doProfiling:
                self._processProfile.profileMethod(self.process.fix, *args, **kwargs)
            else:
                self.process.fix(*args, **kwargs)
        except Exception:
            raise
        finally:
            if links:
                self.runLinks(Link.FIX)

        return self.process.getFeedbacks()

    def _tool(self, links=True, doProfiling=False):
        """This is a wrapper for the Processor's process's tool that will automatically execute it with the right parameters.

        Parameters
        ----------
        links: bool
            Should the wrapper launch the connected links or not.
        doProfiling: bool
            Whether the tool method will be runt with the Processor's Profiler and data retrieved or not. (default: `False`)


        Returns
        -------
        type
            The value returned by the tool method.
        """

        args, kwargs = self.getArguments(AtConstants.TOOL)

        try:
            if doProfiling:
                returnValue = self._processProfile.profileMethod(self.process.tool, *args, **kwargs)
            else:
                returnValue = self.process.tool(*args, **kwargs)
        except Exception:
            raise
        finally:
            if links:
                self.runLinks(Link.TOOL)

        return returnValue

    def check(self, links=True, doProfiling=False):
        """Same as `_check` method but will check if the Processor is checkable and has a check method."""
        if not self.hasCheckMethod or not self.isCheckable:
            return (), AtStatus._DEFAULT

        return self._check(links=links, doProfiling=doProfiling)

    def fix(self, links=True, doProfiling=False):
        """Same as `_fix` method but will check if the Processor is checkable and has a check method."""
        if not self.hasFixMethod or not self.isFixable:
            return (), AtStatus._DEFAULT

        return self._fix(links=links, doProfiling=doProfiling)

    def tool(self, links=True, doProfiling=False):
        """Same as `_tool` method but will check if the Processor is checkable and has a check method."""
        if not self.hasToolMethod:
            return None

        return self._tool(links=links, doProfiling=doProfiling)

    def runLinks(self, which):
        """Run the Processor's links for the given method.
        
        Parameters:
        -----------
        which: athena.AtCore.Link
            Which link we want to run.
        """

        for link in self.__linksData[which]:
            link()

    def getArguments(self, method):
        """Retrieve arguments for the given method of the Processor's Process.
        
        Parameters
        ----------
        method: types.FunctionType
            The method for which retrieve the arguments and keyword arguments.

        Notes
        -----
        This method will not raise any error, if no argument is found, return a tuple containing empty
        list and empty dict.

        Returns
        -------
        tuple
            Tuple containing a list of args and a dict of kwargs
            => tuple(list, dict)
        """

        arguments = self._arguments
        if arguments is None:
            return ([], {})

        arguments = arguments.get(method, None)
        if arguments is None:
            return ([], {})

        return arguments

    @AtUtils.lazyProperty
    def parameters(self):
        parameters = []

        for attribute in vars(type(self.process)).values():
            if isinstance(attribute, Parameter):
                parameters.append(attribute)
        
        return tuple(parameters)

    def getParameter(self, parameter):
        return parameter.__get__(self.process, type(self.process))

    def setParameter(self, parameter, value):
        parameter.__set__(self.process, value)
        return self.getParameter(parameter)

    def setupTags(self):
        """Setup the tags used by this Processor to modify the Processor's behaviour."""

        self.__isEnabled = True
        self.__isCheckable = self.hasCheckMethod
        self.__isFixable = self.hasFixMethod
        self.__hasTool = self.hasToolMethod
        self.__isNonBlocking = False
        self.__inBatch = True
        self.__inUi = True

        tags = self._tags

        if tags is None:
            return

        if tags & Tag.DISABLED:
            self.__isEnabled = False

        if tags & Tag.NO_CHECK:
            self.__isCheckable = False

        if tags & Tag.NO_FIX:
            self.__isFixable = False

        if tags & Tag.NO_TOOL:
            self.__hasTool = False

        if tags & Tag.NON_BLOCKING:
            self.__isNonBlocking = True

        if tags & Tag.NO_BATCH:
            self.__inBatch = False

        if tags & Tag.NO_UI:
            self.__inUi = False

    def resolveLinks(self, linkedObjects, check=AtConstants.CHECK, fix=AtConstants.FIX, tool=AtConstants.TOOL):
        """Resolve the links between the given objects and the current Blueprint's Process.

        This need to be called with an ordered list of Objects (Blueprint or custom object) with None for blueprints to skip.
        (e.g. to skip those that should not be linked because they dont have to be run in batch or ui.)

        Parameters
        ----------
        linkedObjects: list(object, ...)
            List of all objects used to resolve the current Blueprint links. Objects to skip have to be replaced with `None`.
        check: str
            Name of the method to use as check link on the given objects.
        fix: str
            Name of the method to use as fix link on the given objects.
        tool: str
            Name of the method to use as tool link on the given objects.
        """

        self.__linksData = linksData = {Link.CHECK: [], Link.FIX: [], Link.TOOL: []}

        if not linkedObjects:
            return

        links = self._links
        if links is None:
            return

        for link in links:
            id_, _driver, _driven = link
            if linkedObjects[id_] is None:
                continue

            driven = _driven
            driven = check if _driven == Link.CHECK else driven
            driven = fix if _driven == Link.FIX else driven
            driven = tool if _driven == Link.TOOL else driven

            linksData[_driver].append(getattr(linkedObjects[id_], driven))

    def _overrideLevels(self, process, overrides):
        """Override the Processor's Process's Threads Statuses based on a dict of overrides.

        Will iter through all Processor's Process's Threads and do the overrides from the dict by replacing the Fail
        or Success Statuses.

        Parameters:
        -----------
        process: AtCore.Process
            The Processor's Process instance.
        overrides: dict(str: dict(AtStatus.FailStatus|AtStatus.SuccessStatus: AtStatus.Status))
            The data to do the Status Overrides from.
        """

        #FIXME: It's highly likely that this override the statuses owned by the class.
        # This is an issue if we need to  add the process twice.

        if not overrides:
            return

        for threadName, overridesDict in overrides.items():
            if not hasattr(process, threadName):
                raise RuntimeError('Process {0} have not thread named {1}.'.format(process._name_, threadName))
            thread = getattr(process, threadName)
            
            # Get the fail overrides for the current name
            status = overridesDict.get(AtStatus.FailStatus, None)
            if status is not None:
                if not isinstance(status, AtStatus.FailStatus):
                    raise RuntimeError('Fail feedback status override for {0} "{1}" must be an instance or subclass of {2}'.format(
                        process._name_,
                        threadName,
                        AtStatus.FailStatus
                    ))
                thread.overrideFailStatus(status)
            
            # Get the success overrides for the current name
            status = overridesDict.get(AtStatus.SuccessStatus, None)
            if status is not None:
                if not isinstance(status, AtStatus.SuccessStatus):
                    raise RuntimeError('Success feedback status override for {0} "{1}" must be an instance or subclass of {2}'.format(
                        process._name_,
                        threadName,
                        AtStatus.SuccessStatus
                    ))
                thread.overrideSuccessStatus(status)

    def setProgressbar(self, progressbar):
        """ Called in the ui this method allow to give access to the progress bar for the user

        Parameters
        ----------
        progressbar: QtWidgets.QProgressBar
            QProgressBar object to connect to the process to display check and fix progression.
        """

        self.process.setProgressbar(progressbar)

    def _createDocstring(self):
        """Generate the Blueprint doc from Process docstring and data in the `_docFormat_` variable.

        Returns
        -------
        str
            Return the formatted docstring to be more readable and also display the path of the process.
        """

        docstring = self.process._doc_ or AtConstants.NO_DOCUMENTATION_AVAILABLE
        docstring += '\n {0} '.format(self._processStrPath)

        docFormat = {}
        for match in re.finditer(r'\{(\w+)\}', docstring):
            matchStr = match.group(1)
            docFormat[matchStr] = self.process._docFormat_.get(matchStr, '')

        return docstring.format(**docFormat)

    def getData(self, key, default=None):
        """Get the Processor's Data for the given key or default value if key does not exists.

        Parameters:
        -----------
        key: typing.hashable
            The key to get the data from.
        default: object
            The default value to return if the key does not exists.
        """

        return self._data.get(key, default)

    def setData(self, key, value):
        """Set the Processor's Data for the given key

        Parameters:
        -----------
        key: typing.hashable
            The key to set the data.
        value: object
            The value to store as data for the give key.
        """

        self._data[key] = value


class Tag(object):
    """Tags are modifiers used by athena to affect the way a process could be run, through or outside a ui.
    It Allow processes to be optional, non blocking, hide their checks and more.

    Attributes
    ----------
    DISABLED: str
        Define if a process should be disabled (by default it is enable)
    NO_CHECK: str
        This tag will remove the check of a process, it will force the isCheckable to False in blueprint.
    NO_FIX: str
        This tag will remove the fix of a process, it will force the isFixable to False in blueprint.
    NO_TOOL: str
        This tag will remove the tool of a process, it will force the hasTool to False in blueprint.
    NON_BLOCKING: str
        A non blocking process will raise a non blocking error, its error is ignored.
    NO_BATCH: str
        This process will only be executed in ui.
    NO_UI: str
        This process will only be executed in batch.
    OPTIONAL: str
       This tag will set a check optional, an optional process is not checked by default and will.
    DEPENDANT: str
        A dependent process need links to be run through another process.
    """

    NO_TAG          = 0

    DISABLED        = 1

    NO_CHECK        = 2
    NO_FIX          = 4
    NO_TOOL         = 8

    NON_BLOCKING    = 16
    
    NO_BATCH        = 32
    NO_UI           = 64
    
    OPTIONAL        = NON_BLOCKING | DISABLED
    DEPENDANT       = NO_CHECK | NO_FIX | NO_TOOL


class Link(enum.Enum):
    """Give access to the AtConstants to simplify the use of the links."""

    CHECK = AtConstants.CHECK
    FIX = AtConstants.FIX
    TOOL = AtConstants.TOOL


# -- MetaID and ID are prototype to manage the values in blueprints header. 
#TODO: This must be removed or replaced for something more robust.
class MetaID(type):
        
    def __getattr__(cls, value):
        if value not in cls._DATA:
            setattr(cls, value, value)
            cls._DATA.add(value)

        return value

    def __getattribute__(cls, value):
        if value in type.__dict__:
            raise ValueError('Can not create ID: `{0}`, it will override python <type> inherited attribute of same name.'.format(value))

        return type.__getattribute__(cls, value)


class ID(object, metaclass=MetaID):
    
    _DATA = set()

    def __new__(cls):
        raise NotImplementedError('{0} is not meant to be instanciated.'.format(cls))

    @classmethod
    def flush(cls):
        cls._DATA.clear()  


class Parameter(abc.ABC):

    TYPE = typing.Any

    def __init__(self, default: typing.Any):
        self.__default = default
        self.__value = default
        
        self.__name = ''

    def __set_name__(self, owner: object, name: str):
        self.__name = '__' + name
        setattr(owner, self.__name, self.__value)

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return getattr(instance, self.__name)

    def __set__(self, instance, value: str):
        castValue = self.typeCast(value)

        if self.validate(castValue):
            setattr(instance, self.__name, castValue)

    def __delete__(self, instance):
        setattr(instance, self.__name, self.__default)

    @property
    def name(self) -> str:
        return self.__name[2:]

    @property
    def default(self) -> typing.Any:
        return self.__default

    @abc.abstractmethod
    def typeCast(self, value: str) -> typing.Any:
        NotImplemented

    @abc.abstractmethod
    def validate(self, value: typing.Any) -> bool:
        NotImplemented


class BoolParameter(Parameter):

    TYPE = bool

    def __init__(self, default):
        if not isinstance(default, self.TYPE):
            raise ValueError('Value {} does not conform to {} validation.'.format(str(default), self.__class__.__name__))

        super(BoolParameter, self).__init__(default)

    def typeCast(self, value: str) -> bool:
        return value in (True, 'True', 'true', 'Yes', 'yes', 1, '1')

    def validate(self, value: bool) -> bool:
        return self.typeCast(value)


class _NumberParameter(Parameter):

    TYPE = numbers.Number

    def __init__(self, default, minimum=None, maximum=None, keepInRange=False):
        if not isinstance(default, self.TYPE):
            raise ValueError('Value {} does not conform to {} validation.'.format(str(default), self.__class__.__name__))

        super(_NumberParameter, self).__init__(default)

        self._minimum = minimum
        self._maximum = maximum
        self._keepInRange = keepInRange

    def typeCast(self, value: typing.Any) -> numbers.Number:
        value = self.TYPE(value)

        if self._keepInRange:
            if self._minimum is not None and value < self._minimum:
                return self._minimum
            elif self._maximum is not None and value > self._maximum:
                return self._maximum

        return value

    def validate(self, value: numbers.Number) -> bool:
        if self._minimum is not None and value < self._minimum:
            return False
        if self._maximum is not None and value > self._maximum:
            return False

        return True


class IntParameter(_NumberParameter):
    TYPE = int


class FloatParameter(_NumberParameter):
    TYPE = float


class StringParameter(Parameter):
    TYPE = str

    def __init__(self, default, validation=None, caseSensitive=True):
        if not isinstance(default, self.TYPE):
            raise ValueError('Value {} does not conform to {} validation.'.format(str(default), self.__class__.__name__))

        super(StringParameter, self).__init__(default)

        self._validation = validation
        self._caseSensitive = caseSensitive

    def typeCast(self, value: str) -> str:
        return self.TYPE(value.lower())

    def validate(self, value: str) -> bool:
        if self._validation is None:
            return True
        else:
            if self._caseSensitive:
                return value in self._validation
            else:
                return value.lower() in {validation.lower() for validation in self._validation}

        return False


class _ProcessProfile(object):
    """Profiler that allow to profile the execution of `athena.AtCore.Process`"""

    # Match integers, floats (comma or dot) and slash in case there is a separation for primitive calls.
    DIGIT_PATTERN = r'([0-9,.\/]+)'
    DIGIT_REGEX = re.compile(DIGIT_PATTERN)

    CATEGORIES = (
        ('ncalls', 'Number of calls. Multiple numbers (e.g. 3/1) means the function recursed. it reads: Calls / Primitive Calls.'),
        ('tottime', 'Total time spent in the function (excluding time spent in calls to sub-functions).'), 
        ('percall', 'Quotient of tottime divided by ncalls.'), 
        ('cumtime', 'Cumulative time spent in this and all subfunctions (from invocation till exit). This figure is accurate even for recursive functions.'), 
        ('percall', 'Quotient of cumtime divided by primitive calls.'), 
        ('filename:lineno(function)', 'Data for each function.')
    )

    def __init__(self):
        """Initialiste a Process Profiler and define the default instance attributes."""

        self._profiles = {} 

    def get(self, key, default=None):
        """Get a profile log from the given key, or default if key does not exists.
        
        Parameters:
        -----------
        key: typing.hashable
            The key to get data from in the profiler's profile data.
        default: object
            The default value to return in case the key does not exists.

        Return:
        -------
        object
            The data stored at the given key if exists else the default value is returned.
        """

        return self._profiles.get(key, default)

    def _getCallDataList(self, callData):
        """Format and split `cProfile.Profiler` call data list (each value in the list must be one line.)

        This will mostly remove heading or trailing spaces and return a list of tuple where each values in the
        string is now an entry in the tuple. The order is the same than `athena.AtCore._ProcessProfile.CATEGORIES`.
        
        Parameters:
        -----------
        callData: list(str, ...)
            List of call entry from a `cProfile.Profiler` run.
        """

        dataList = []
        for call in callData:
            callData = []

            filteredData = tuple(filter(lambda x: x, call.strip().split(' ')))
            if not filteredData:
                continue
            callData.extend(filteredData[0:5])

            value = ' '.join(filteredData[5:len(filteredData)])
            callData.append(float(value) if value.isdigit() else value)

            dataList.append(tuple(callData))

        return dataList

    def profileMethod(self, method, *args, **kwargs):
        """Profile the given method execution and return it's result. The profiling result will be stored in the 
        object.

        Try to execute the given method with the given args and kwargs and write the result in a temporary file.
        The result will then be read and each line splited to save a dict in the object `_profiles` attribute using
        the name of the given method as key.
        This dict will hold information like the time when the profiling was done (key = `time`, it can allow to not 
        update data in a ui for instance), the total number of calls and obviously a tuple with each call data (`calls`).
        The raw stats result is also saved under the `rawStats` key if the user want to use it directly.
        
        Parameters:
        -----------
        method: types.FunctionType
            A callable for which we want to profile the execution and save new data.
        *args: *list
            The arguments to call the method with.
        **kwargs: **kwargs
            The keywords arguments to call the method with.

        Return:
        -------
        object:
            The result of the given method with the provided args and kwargs.
        """

        assert callable(method), '`method` must be passed a callable argument.'

        profile = cProfile.Profile()

        # Run the method with `cProfile.Profile.runcall` to profile it's execution only. We define exception before
        # executing it, if an exception occur the except statement will be processed and `exception` will be updated
        # from `None` to the exception that should be raised.
        # At the end of this method exception must be raised in case it should be catch at upper leve in the code.
        # This allow to not skip the profiling even if an exception occurred. Of course the profiling will not be complete
        # But there should be all information from the beginning of the method to the exception. May be usefull for debugging.
        exception = None
        returnValue = None
        try:
            returnValue = profile.runcall(method, *args, **kwargs)
            self._profiles[method.__name__] = self.getStatsFromProfile(profile)
            return returnValue

        except Exception as exception_:
            self._profiles[method.__name__] = self.getStatsFromProfile(profile)
            raise

    def getStatsFromProfile(self, profile):
        """

        """

        # Create a temp file and use it as a stream for the `pstats.Stats` This will allow us to open the file
        # and retrieve the stats as a string. With regex it's now possible to retrieve all the data in a displayable format
        # for any user interface.
        fd, tmpFile = tempfile.mkstemp()
        try:
            with open(tmpFile, 'w') as statStream:
                stats = pstats.Stats(profile, stream=statStream)
                stats.sort_stats('cumulative')  # cumulative will use the `cumtime` to order stats, seems the most relevant.
                stats.print_stats()
            
            with open(tmpFile, 'r') as statStream:
                statsStr = statStream.read()
        finally:
            # No matter what happen, we want to delete the file.
            # It happen that the file is not closed here on Windows so we also call `os.close` to ensure it is really closed.
            # WindowsError: [Error 32] The process cannot access the file because it is being used by another process: ...
            os.close(fd)
            os.remove(tmpFile)

        split = statsStr.split('\n')
        methodProfile = {
            'time': time.time(),  # With this we will be able to not re-generate widget (for instance) if data have not been updated.
            'calls': self._getCallDataList(split[5:-1]),
            'rawStats': statsStr,
        }

        # Take care of possible primitive calls in the summary for `ncalls`.
        summary = self.DIGIT_REGEX.findall(split[0])
        methodProfile['tottime'] = summary[-1]
        if len(summary) == 3:
            methodProfile['ncalls'] = '{0}/{1}'.format(summary[0], summary[1])
        else:
            methodProfile['ncalls'] = summary[0]

        return methodProfile

        

# Setup
'''
import sys
sys.path.append('C:\Python27\Lib\site-packages')
sys.path.append('C:\Workspace\athena\src')

import athena.ressources.athena_example.ContextExample

import athena
athena._reload(__name__)

athena.launch(dev=True)
'''
