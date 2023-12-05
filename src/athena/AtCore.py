from __future__ import annotations

import abc
import cProfile
import enum
import inspect
import numbers
import os
import pstats
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from functools import cached_property
from types import ModuleType, FunctionType
from typing import TypeVar, Type, Iterator, Callable, Optional, Union, Any, Dict, List, Tuple, Mapping, Sequence

from athena import AtConstants, AtExceptions, AtStatus, AtUtils


class Event(object):
    """A simple event system for handling callbacks.

    This class allows you to create an event object that can be called like a function.
    Registered callbacks will be invoked when the event is called.
    """

    def __init__(self, name: str) -> None:
        """Initializes an Event with a given name.

        Parameters:
            name: The name of the event.
        """
        self._name = name
        self._callbacks = []

    def __call__(self, *args, **kwargs) -> None:
        """Invokes all registered callbacks with the provided arguments."""
        for callback in self._callbacks:
            callback(*args, **kwargs)

    def addCallback(self, callback: Callable) -> bool:
        """Adds a callback function to the event's list of callbacks.

        Parameters:
            callback: The callback function to be registered.

        Return:
            True if the callback was successfully registered, False otherwise.

        Warnings:
            If the provided callback is not callable, a warning message is logged,
            and the callback is not registered.
        """
        if not callable(callback):
            AtUtils.LOGGER.warning(
                'Event "{0}" failed to register callback: Object "{1}" is not callable.'.format(self.name, callback)
            )
            return False

        self._callbacks.append(callback)

        return True


class EventSystem(abc.ABC):
    """Athena's internal event system.

    This class defines events that can be used to notify subscribers
    when specific events occur within the base framework.
    """

    #: Event triggered when a new Register instance is created.
    RegisterCreated = Event('RegisterCreated')

    #: Event triggered when Blueprints are reloaded.
    BlueprintsReloaded = Event('BlueprintsReloaded')

    #: Event triggered when development mode is enabled.
    DevModeEnabled = Event('DevModeEnabled')

    #: Event triggered when development mode is disabled.
    DevModeDisabled = Event('DevModeDisabled')


class AtSession(object, metaclass=AtUtils.Singleton):
    """Singleton class representing the Athena's running session.

    This class provides a single instance that manages the session state,
    including a registration system and a development mode toggle.
    
    Example:
        >>> AtSession().dev = True  # Enable development mode.
    """

    def __init__(self) -> None:
        """Initialize a new instance of __AtSession."""

        self._dev: bool = False

    #TODO: Remove this code or update it for blueprint import 2.0
    # @cached_property
    # def environVar(self):
    #     return '{program}_{software}'.format(
    #         program=AtConstants.PROGRAM_NAME.upper(), 
    #         software=self.software.upper()
    #     ) 

    # @cached_property
    # def environ(self):
    #     if self.environVar in os.environ:
    #         return os.environ[self.environVar]

    #     os.environ[self.environVar] = ''
    #     if self.platform in ('Linux', 'Darwin'):
    #         os.system('export {}={}'.format(self.environVar, ''))
    #     elif self.platform == 'Windows':
    #         os.system('setx {} {}'.format(self.environVar, ''))

    #     return os.environ[self.environVar]

    @cached_property
    def register(self) -> Register:
        """Lazily creates and returns the Register."""

        return Register()

    @property
    def dev(self) -> bool:
        """Get the current state of development mode."""

        return self._dev

    @dev.setter
    def dev(self, value: bool) -> None:
        """Set the development mode state and trigger corresponding events."""

        self._dev = bool(value)
        if value:
            EventSystem.DevModeEnabled()
        else:
            EventSystem.DevModeDisabled()


#TODO: When Python 3.10 will be more widely used according to vfxplatform, add slots.
@dataclass(frozen=True)
class ProtoFeedback(abc.ABC):
    """Abstract base dataclass for Feedback objects used in Athena.

    This is the root of all feedback types and only meant to implement common behavior
    between all subclasses.
    It implement the default attributes and behavior for iteration.
    """

    feedback: Any
    """
    Represents the data held by the feedback instance, which can be of any type based on
    the specific needs of the associated process.
    """

    selectable: bool = field(compare=False)
    """
    Determines whether the feedback is selectable. This attribute is not used in comparison,
    meaning two instances with the same data (:obj:`~ProtoFeedback.feedback`) will be considered
    similar, regardless of the `selectable` value.
    """

    children: List[ProtoFeedback] = field(default_factory=list, init=False, hash=False, compare=False)
    """
    Holds references to all child feedback instances. Unlike the feedback itself, this attribute
    is mutable, and as such, it is not considered in comparison, hashing, or sorting.
    """

    def __iter__(self) -> Iterator[Any]:
        """Iterate over all children"""

        for child in self.children:
            yield child

    def __str__(self) -> str:
        """Return the string representation of the feedback data."""

        return str(self.feedback)

    @abc.abstractmethod
    def select(self):
        """Abstract method to select the feedback item.

        Raise:
            NotImplementedError: This method must be implemented by subclasses.
        """

        raise NotImplementedError()

    @abc.abstractmethod
    def deselect(self) -> None:
        """Abstract method to deselect the feedback item.

        Raise:
            NotImplementedError: This method must be implemented by subclasses.
        """

        raise NotImplementedError()

    def parent(self, *feedbacks: List[ProtoFeedback]) -> None:
        """Add child feedback items to create a hierarchical structure.

        Parameters:
            *feedbacks: Child feedback items to be added.
        """

        self.children.extend(feedbacks)


@dataclass(frozen=True)
class FeedbackContainer(ProtoFeedback):
    """Base class for Feedback Container containing feedbacks for a specific Thread.

    The FeedbackContainer is only meant to be used as a root for a Feedback hierarchy,
    compared to other feedback, it's "data" is a Thread, for which it contains feedbacks.
    It's also able to have a status, that must be set based on the Thread FailStatus or 
    SuccessStatus.
    
    Notes:
        The FeedbackContainer class implement a really basic selection and deselection process,
        you should consider reimplemting it if you intend to use a very specific selection mechanism
        or need to deal with advanced selection/deselection. (= A lot of elements to deal with)
    """

    feedback: Thread
    """The FeedbackContainer data must be the Thread for which it contain feedbacks."""

    status: AtStatus.Status
    """The FeedbackContainer status represent the result state of the Thread based on the contained feedbacks"""

    def __str__(self) -> str:
        """Simply return the title for the container's Thread"""

        return self.feedback._title

    def select(self, replace:bool = True) -> bool:
        """Allow selection for the FeedbackContainer.

        If it isn't selectable, this won't do anything. On the other hand, if it is,
        the behavior is to call the `select` method for each Feedback in the container's children one by one.
        Also, if `replace` is set to `True`, only the first child will replace the current selection
        while others will be added to it.
        
        Parameters:
            replace: Whether we replace or add to the current selection.

        Return:
            The current state of the `replace` parameter to know if following selection, in subclass
            implementation of this method must replace or add.
        """

        if not self.selectable:
            return replace
            
        for child in self.children:
            child.select(replace=replace)
            replace = False

        return replace

    def deselect(self) -> None:
        """Allow deselection for the FeedbackContainer.

        If it isn't selectable, this won't do anything. Otherwise, call the `deselect` method
        of each child Feedback, one by one.
        """

        if not self.selectable:
            return

        for child in self.children:
            child.deselect()

    def setStatus(self, status:AtStatus.Status) -> None:
        """Change the current FeedbackContainer status to the given status.

        Parameter:
            status: The new status to set this FeedbackContainer value to.
        """

        object.__setattr__(self, 'status', status)


@dataclass(frozen=True)
class Feedback(ProtoFeedback):
    """Base class representing a single found Feedback for Athena.

    The Feedback is an abstract way for Processes to register what they find.
    This class serves as the base Feedback class, suitable for most situations but includes no
    specific behavior for software/OS selection. The methods implement behavior, not actual selection
    actions. If you need real selection, consider implementing a subclass and overriding the select/deselect
    methods. Using this Base Feedback as the parent for other subclassed feedback will cascade the selection
    to them.

    Notes:
        For DCC-specific implementations, refer to athena.software. The list is not exhaustive and emphasizes
        common and global behavior. If you have specific needs for another software or pipeline-specific behavior,
        you can implement your own Feedback subclass.
    """

    def select(self, replace:bool = True) -> bool:
        """Allow selection for the Feedback.

        This implementation is a selection cascade mechanism meant to be overridden and/or called as a superclass.
        If the feedback is selectable, it won't do anything, as there are no defined selection behaviors for
        the default Feedback. If the Feedback is not selectable, it cascades to every child and calls their
        select method one by one.

        Parameters:
            replace: Whether to replace or add to the current selection.

        Notes:
            Having a non-selectable feedback can allow displaying data that has no selection capabilities
            or create a group for sub-feedbacks and select them all at once.
        """

        if not self.selectable:
            for child in self.children:
                child.select(replace=replace)
                replace = False

        return replace

    def deselect(self) -> None:
        """Allow deselection for the Feedback.

        This implementation is a deselection cascade mechanism meant to be overridden and/or called as a superclass.
        If the feedback is deselectable, it won't do anything, as there are no defined deselection behaviors for
        the default Feedback. If the Feedback is not deselectable, it cascades to every child and calls their
        deselect method one by one.

        Notes:
            Having a non-selectable feedback can allow displaying data that has no deselection capabilities
            or create a group for sub-feedbacks and deselect them all at once.
        """

        if not self.selectable:
            for child in self.children:
                child.deselect()


class Thread(object):
    """Represent a task within an Athena Process.

    A Thread in Athena signifies a single responsibility task assigned to a Process. Each Thread
    entails the responsibility for the Process to perform tests and register Feedbacks if any unexpected
    behavior is detected.
    
    The Thread encapsulates the task, defining its importance by specifying both failure and success statuses.
    The fail status denotes failure, and the success status indicates successful completion.
    
    These statuses can be overridden in the Blueprint for enhanced flexibility. It is essential to generate
    the Thread with its default and common statuses.
    
    Threads should be defined as class attributes in the Process and passed to methods that handle feedbacks.
    """

    __slots__ = (
        '_title', 
        '_defaultFailStatus', 
        '_failStatus', 
        '_defaultSuccessStatus', 
        '_successStatus',
        '_documentation',
    )

    def __init__(self, title: str, failStatus: AtStatus.FailStatus = AtStatus.ERROR, successStatus: AtStatus.SuccessStatus = AtStatus.SUCCESS, documentation: Optional[str] = None):
        """Initialize an instance of Thread.

        This method sets up a Thread instance with the provided parameters, including the thread title,
        default fail and success statuses, and an optional documentation. Their default values are different from their
        actual value.

        Parameters:
            title: The title of the Thread.
            failStatus: The default fail status for the command, will be set as failStatus and defaultFailStatus.
            successStatus:The default success status for the command, will be set as successStatus and defaultSuccessStatus
            documentation: Optional documentation or description for the Thread.

        Raises:
            AtExceptions.StatusException: If the provided failStatus or successStatus are not of the valid type.

        Notes:
            The failStatus and successStatus parameters should be members of the AtStatus.FailStatus and
            AtStatus.SuccessStatus enumerations, respectively. If not provided, the default statuses are
            set to AtStatus.ERROR and AtStatus.SUCCESS, respectively.
        """

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
        """Getter for the Thread's title.

        Return:
            The thread's title.
        """

        return self._title

    @property
    def failStatus(self) -> AtStatus.FailStatus:
        """Getter for the Thread's fail status.

        Return:
            The thread's fail status.
        """

        return self._failStatus

    @property
    def successStatus(self) -> AtStatus.SuccessStatus:
        """Getter for the Thread's success status.

        Return:
            The thread's success status..
        """

        return self._successStatus

    def overrideFailStatus(self, status: AtStatus.FailStatus) -> None:
        """Override the actual fail status.

        Parameters:
            status: The Status class to use as new fail status.
        """

        self._failStatus = status

    def overrideSuccessStatus(self, status: AtStatus.SuccessStatus) -> None:
        """Override the actual success status.

        Parameters:
            status: The Status class to use as new success status.
        """

        self._successStatus = status

    def status(self, state: bool) -> AtStatus.Status:
        """Get the Thread's current status based on given state boolean.

        Return:
            Success status if `state` is true, fail status otherwise.
        """

        if state:
            return self._successStatus
        else:
            return self._failStatus


#TODO: On a major update, replace individual process computation with process that subscribe to iteration.
# e.g. AtPolygonIterator -> Iterate over polygons of a mesh and notify subscribers.
class Process(abc.ABC):
    """Abstract class that serves as the foundation for all Athena Processes.

    The `Process` class acts as the base (abstract) class for all user-defined check processes within the Athena framework.
    To create a new process, it's essential to define at least one :class:`~Thread` object as a class attribute. These threads
    manage various feedbacks that the process will inspect and potentially address.

    During the execution of your process's :meth:`~Process.check`, if any issues are detected, you need to create 
    instances of the :obj:`~Feedback` class (or its subclasses) and register them for the appropriate threads using 
    the :meth:`~Process.addFeedback` method. In the :meth:`~Process.fix` method, iterate over these feedback 
    instances and implement any necessary actions to automatically resolve fixable issues.
    
    Additional methods for managing internal feedback are available, allowing you to retrieve feedbacks, iterate over them,
    or check if there are any feedbacks for a specific Thread.

    At the end of the check process, it's crucial to set the state for each Thread. By default, they are all set to the
    :obj:`.AtStatus._DEFAULT` built-in status. To change a Thread status, you can call the :meth:`~Process.setSuccess`
    or :meth:`~Process.setFail` methods.
    Alternatively, you can skip the execution of a specific Thread using the :meth:`~Process.setSkipped` method.

    Three non-implemented methods must or can be overridden to create a functional process:

        * :meth:`~Process.check`
        * :meth:`~Process.fix`
        * :meth:`~Process.tool`

    Communication of progress can be achieved using the `setProgress*` methods to provide feedback to the user on the
    current state of the check or fix progress. For this to work, a QProgressBar must be set using `setProgressBar`.

    Several sunder attributes are defined at the class level, providing the ability to replace default class data. For example,
    defining `_name_` gives a name to the process different from the class name obtained from `__name__`. This allows defining
    a user-friendly name. The currently available sunder attributes include:

        * `_name_`
        * `_doc_`

    If you wish to create a custom base class for all your processes, ensure that this base class also inherits from `Process`
    to be recognized by Athena's framework. Do not override the `__new__` method without using `super`, or the process will not
    be set up as intended.
    """

    FEEDBACK_CONTAINER_CLASS: Type[FeedbackContainer] = FeedbackContainer
    """
    Define which type of feedback container will be internally used to register Feedback per Thread.
    This is intended to be overrided in a subclass if you're willing to use a different FeedbackContainer implementation.
    """

    _name_: str = ''
    """The Process nice name. If not set, will be set to the value of __name__"""

    _doc_: str = ''
    """The Process user's documentation. If not set, will be set to the value of __doc__"""

    _listenForUserInteruption: Event = Event('ListenForUserInteruption')
    """Event that allow to notify subscribers when the user is trying to interupt the process execution."""

    def __new__(cls, *args: Any, **kwargs: Any) -> Type[Process]:
        """Create a new instance of the Process class.

        This method overrides the default `__new__` method and is responsible for initializing a new instance 
        of the class with some private attribute used internally.
        """

        # Create the instance
        instance = super(Process, cls).__new__(cls, *args, **kwargs)

        # Instance internal data (Must not be altered by user)
        instance._feedbackContainer: Dict[Thread, Type[FeedbackContainer]] = cls.__makeFeedbackContainer()
        instance.__progressbar: QtWidgets.QProgressBar = None

        instance.__doInterupt: bool = False

        # Sunder instance attribute (Can be overrided user to custom the process)
        # instance._name_ = cls._name_ or cls.__name__
        # instance._doc_ = cls._doc_ or cls.__doc__

        return instance

    def __repr__(self) -> str:
        """Give a nice representation of the Process with it's nice name."""
        
        return '<Process `{0}` at {1}>'.format(self._name_, hex(id(self)))

    @classmethod
    def __makeFeedbackContainer(cls) -> Dict[Thread, FeedbackContainer]:
        """Create and initialize a dictionary of :class:`~FeedbackContainers` for each :class:`~Thread`.

        This class method generates a dictionary of FeedbackContainers for each Thread associated with the Process class.
        The FeedbackContainers are initialized with the Thread, True (indicating the container is selectable),
        and :obj:`~.AtStatus._DEFAULT` (the default status for the containers).

        Return:
            A new dict with an empty FeedbackContainer per Thread with status set to :obj:`.AtStatus._DEFAULT`

        Note:
            This method is typically used internally within the Process class to initialize the FeedbackContainers for
            each associated Thread.

        See Also:

            * :class:`~Thread`: The class representing a task within the Athena framework.
            * :class:`~FeedbackContainer`: The container for managing feedback associated with a specific Thread.
            * :obj:`.AtStatus._DEFAULT`: The default status used when initializing FeedbackContainers.
        """

        return {thread: cls.FEEDBACK_CONTAINER_CLASS(thread, True, AtStatus._DEFAULT) for thread in cls.threads()}

    @classmethod
    def threads(cls) -> Iterator[Thread]:
        """Iterator to access all threads of the Process.
        
        Return:
            Each thread instances for the current Process.
        """

        for _, member in inspect.getmembers(cls):
            if isinstance(member, Thread):
                yield member

    def check(self, *args: Any, **kwargs: Any) -> None:
        """This method must be implemented on all Process to register feedbacks and set status for each threads"""
        ...
        
    def fix(self, *args: Any, **kwargs: Any) -> None:
        """This method can be implemented to allow an automatic fix for all feedbacks retrieved by the Process check."""
        ...

    def tool(self, *args: Any, **kwargs: Any) -> None:
        """This method can be implemented to open a window that can allow the user to manually find or fix the errors."""
        ...

    def setProgressbar(self, progressBar: QtWidgets.QProgressBar) -> None:
        """This method should be used to setup the Process progress bar widget.

        Parameters:
            progressBar: The new progress bar to link to The Process instance.
        """

        self.__progressbar = progressBar

    def setProgress(self, value: Optional[bool] = None, text: Optional[bool] = None) -> None:
        """Set the progress value and/or text for the associated QProgressBar.

        This method allows setting the progress value and/or text for the QProgressBar associated with the Process instance.
        It is typically used to provide feedback to the user on the current state of the check or fix progress.

        Parameters:
            value: The progress value to set. If None, the progress value remains unchanged.
            text: The progress text to set. If None, the progress text remains unchanged.
        """

        if value is not None:
            self.setProgressValue(value)

        if text is not None:
            self.setProgressText(text)

    def setProgressValue(self, value: numbers.Number) -> None:
        """Set the progress value of the Process progress bar if exist.
        
        Parameters:
            value: The value to set the progress to.

        Raise:
            TypeError: If `value` is not numeric.
        """

        if self.__progressbar is None:
            return

        #WATCHME: `numbers.Number` is an abstract base class that define operations progressively, the first call to
        # this method will define it for the first time, this is why the profiler can detect some more calls for the
        # first call of the first process to be run. --> We talk about insignifiant time but the displayed data will
        # be a bit different. see: https://docs.python.org/2/library/numbers.html
        if not isinstance(value, numbers.Number):
            raise TypeError('Argument `value` is not numeric')
        
        if value and value != self.__progressbar.value():
            self.__progressbar.setValue(float(value))

    def setProgressText(self, text: str) -> None:
        """Set the label text of the Process progress bar if exist.
        
        Parameters:
            text: Text to display in the progressBar.
        """

        if self.__progressbar is None:
            return

        if text and text != self.__progressbar.text():
            self.__progressbar.setFormat(AtConstants.PROGRESSBAR_FORMAT.format(text))

    def clearFeedback(self) -> None:
        """Clear all feedback associated with the threads in the process.

        This method resets the feedback containers for each thread by creating new instances of FeedbackContainers.
        It effectively clears any previously registered feedback.
        """

        self._feedbackContainer = self.__makeFeedbackContainer()

    def hasFeedback(self, thread) -> None:
        """Check if there is feedback registered for a specific thread.

        Parameters:
            thread: The thread to check for feedback.

        Return:
            True if there is feedback for the specified thread, False otherwise.
        """

        return bool(self._feedbackContainer[thread].children)

    def addFeedback(self, thread: Thread, feedback: Feedback) -> None:
        """Add feedback to the specified thread's feedback container.

        Parameters:
            thread: The thread to which the feedback will be added.
            feedback: The feedback instance to add.
        """

        self._feedbackContainer[thread].parent(feedback)

    def iterFeedback(self, thread: Thread) -> Iterator[Feedback, ...]:
        """Iterate over the feedback instances registered for a specific thread.

        Parameters:
            thread: The thread for which to iterate over feedback.

        Return:
            An iterator over the feedback instances for the specified thread.
        """

        return iter(self._feedbackContainer[thread].children)

    def feedbackCount(self, thread: Thread) -> int:
        """Get the count of feedback instances registered for a specific thread.

        Parameters:
            thread: The thread for which to get the feedback count.

        Return:
            The number of feedback instances for the specified thread.
        """

        return len(self._feedbackContainer[thread].children)

    def getFeedbackContainers(self) -> Tuple[FeedbackContainer]:
        """Get a tuple of all feedback containers associated with the threads.

        Return:
            A tuple containing all feedback containers associated with the threads.
        """

        return tuple(self._feedbackContainer.values())

    def setSuccess(self, thread: Thread) -> None:
        """Set the success status for a specific thread's feedback container.

        Parameters:
            thread: The thread for which to set the success status.
        """

        self._feedbackContainer[thread].setStatus(thread.status(True))

    def setFail(self, thread: Thread) -> None:
        """Set the fail status for a specific thread's feedback container.

        Parameters:
            thread: The thread for which to set the fail status.
        """

        self._feedbackContainer[thread].setStatus(thread.status(False))

    def setSkipped(self, thread: Thread) -> None:
        """Set the skipped status for a specific thread's feedback container.

        Parameters:
            thread: The thread for which to set the skipped status.
        """

        self._feedbackContainer[thread].setStatus(AtStatus._SKIPPED)

    def listenForUserInteruption(self) -> None:
        """Trigger an user interuption Event to prematurely end process execution.

        This method triggers the :obj:`~Process._listenForUserInteruption` Event, which requires a registered callback
        to invoke the :meth:`~Process._registerInteruption` method from the Qt Application.

        After triggering the event, if there is a callback to invoke the appropriate method, the boolean value
        for :obj:`~Process.__doIterupt` will be set to True, and an :class:`.AtExceptions.AtProcessExecutionInterrupted` 
        exception will be raised. This exception can be handle in the Qt Application to force the Process Status to 
        :obj:`.AtStatus._ABORTED`.

        Raises:
            AtExceptions.AtProcessExecutionInterrupted: If the interruption is caught and propagated.

        Important:
            When the Process is executing, the Qt Event System stacks QEvents, processing them at the end of the
            execution, typically after all process executions are finished. To catch user interactions during
            execution, the Qt Event System must process pending events. The :obj:`~Process._listenForUserInteruption`
            Event can trigger a call to `QApplication.processEvents`, accomplished by adding it as a callback for this 
            Event.

            When this method runs, the callbacks are triggered, allowing the processing of pending interactions, such as a key
            press. A side effect is that the key press becomes part of the Qt UI thread.

            To ensure the raise directly impacts the application and ends the process, it must be done from the main thread.
            Therefore, the :meth:`~Process._registerInteruption` method needs to be called from the Qt Application to
            toggle the behavior of this method so it can raise. Typically, this method is called in the check or fix 
            method, ensuring that the raise occurs from the main thread.
        """

        if self.__doInterupt:
            return

        self._listenForUserInteruption()

        if self.__doInterupt:
            self.__doInterupt = False
            raise AtExceptions.AtProcessExecutionInterrupted()

    def _registerInteruption(self) -> None:
        """Change the value for the private member :obj:`~Process.__doInterupt` to True.
        
        This simply allow to change the value of this private member from outside the class.
        """

        self.__doInterupt = True


class Register(object):
    """The register is a container that allow the user to load and manage blueprints.

    After initialisation the register will not contain any data and you will need to load the :class:`~Blueprint` you 
    want for your current Athena Session.
    The role of the register is to act as a loader and data keeper for all existing Blueprints you defined and want your
    user's to be able to use for their sanity checking.
    """

    def __init__(self) -> None:
        """Initialize the Register's internal data."""
        
        self.__blueprints: List[Blueprint, ...] = []
        self._currentBlueprint: Blueprint = None

        EventSystem.RegisterCreated()

    def __bool__(self) -> bool:
        """Allow to check if the register is empty or not based on the loaded blueprints."""
        return bool(self.__blueprint)

    __nonzero__ = __bool__

    #FIXME: The import system is not easy to use, find a better way to use them.
    #TODO: Find a way to implement this feature and clean the import process.
    # def loadBlueprintFromPythonStr(self, pythonCode, moduleName):
    #     module = AtUtils.moduleFromStr(pythonCode, name=moduleName)
    #     self.loadBlueprintFromModule(Blueprint(module))

    def loadBlueprintsFromPackageStr(self, package: str) -> None:
        """Load blueprints from a package name.

        This method calls the loadBlueprintsFromPackage method with the imported package object.

        Parameters:
            package: The python formatted path of the package to load blueprints from.

        Warning:
            This method is **deprectated** as it suppose a specific hierarchy, a feature inherited from
            the early ages of Athena. You're not supposed to have a specific hierarchy in you packages
            to load their blueprints.
        """

        self.loadBlueprintsFromPackage(AtUtils.importFromStr(package))

    def loadBlueprintsFromPackage(self, package: ModuleType) -> None:
        """Load blueprints from a package object.

        This method iterates over the blueprints paths in the package and calls the loadBlueprintFromModulePath 
        method for each one.

        Parameters:
            package: The package object to load blueprints from.

        Warning:
            This method is #deprectated** as it suppose a specific hierarchy, a feature inherited from
            the early ages of Athena. You're not supposed to have a specific hierarchy in you packages
            to load their blueprints.
        """

        for modulePath in AtUtils.iterBlueprintsPath(package):
            self.loadBlueprintFromModulePath(modulePath)

    def loadBlueprintFromModulePath(self, modulePath: str) -> None:
        """Load a blueprint from a module OS path.

        This method converts the module path to a python import path and load blueprints from it..

        Parameters:
            modulePath: The path of the module to load a blueprint from.
        """

        self.loadBlueprintFromPythonImportPath(AtUtils.pythonImportPathFromPath(modulePath))

    def loadBlueprintFromPythonImportPath(self, importStr: str) -> None:
        """Load a blueprint from a module python's import path.

        This method will import the module from the string and load blueprints from it.

        Parameters:
            importStr: The python import path to the Blueprint's module to load.
        """

        self.loadBlueprintFromModule(AtUtils.importFromStr(importStr))

    def loadBlueprintFromModule(self, module: ModuleType) -> None:
        """Load a blueprint from a module object.

        This method creates a Blueprint object from the module and adds it to the list of blueprints. 
        If a blueprint with the same name already exists, it replaces it with the new one.

        Parameters:
            module: The module object to load a blueprint from.
        """

        newBlueprint = Blueprint(module)
        for i, blueprint in enumerate(self.__blueprints):
            if blueprint == newBlueprint:
                self.__blueprints[i] = newBlueprint
                break
        else:
            self.__blueprints.append(newBlueprint)

    def clear(self) -> None:
        """Remove all loaded blueprints from this register."""

        del self.__blueprints[:]

    @property
    def blueprints(self) -> Tuple[Blueprint, ...]:
        """Getter for Register's blueprints
        
        Return:
            All blueprints in the current register.
        """

        return tuple(self.__blueprints)

    @property
    def currentBlueprint(self) -> Blueprint:
        """Getter for current blueprint.
        
        Return:
            The current blueprint.
        """

        return self._currentBlueprint

    @currentBlueprint.setter
    def currentBlueprint(self, blueprint: Blueprint) -> None:
        """Setter for current blueprint

        Set the current blueprint if it's an already registered blueprint recognized by the register.

        Parameters:
            blueprint: The new Blueprint to set as current blueprint.
        """

        if blueprint in self.__blueprints:
            self._currentBlueprint = blueprint

    def blueprintByName(self, name: str) -> Optional[Blueprint]:
        """Get a blueprints from the Register based on it's name.

        Will try to find the first Blueprint that match the given name. If none are found, nothing is returned.

        Parameters:
            name: The name of the blueprint to find.

        Return:
            The blueprint that match the name, or None if no blueprint match the given name.
        """

        for blueprint in self.__blueprints:
            if blueprint._name == name:
                return blueprint

    def reload(self) -> None:
        """Clear the currently loaded blueprints and reload them to ensure all blueprints are up to date.
        
        This is mostly intended for development usage, as users are not likely to update the Blueprints.
        It's the same are reloading the blueprints, but as they are hold in objects inside a list, they need
        to be rebuilt with the newly loaded instance of the module.
        """

        blueprints = self.__blueprints[:]
        self.clear()

        for blueprint in blueprints:
            for processor in blueprint.processors:
                AtUtils.reloadModule(processor.module)
            self.loadBlueprintFromModule(AtUtils.reloadModule(blueprint._module))

        EventSystem.BlueprintsReloaded()


#TODO: Maybe make this a subclass of types.ModuleType and wrap class creation.
class Blueprint(object):
    """Configuration for Athena processes, specifying order and settings.

    The Blueprint serves as a configuration for Athena processes, defining the order in which processes are executed and
    providing settings for each process. It requires two members to be defined in the module:

        * `header`: A list of names in the desired execution order, representing the sequence of processes.
        * `descriptions`: A dictionary where each value in the `header` contains data to initialize a :class:`~Processor`.

    An optional member called `settings` can be added, which must be a dictionary as well. The values in this dictionary 
    modify the global execution behavior for the current blueprint.

    The Blueprint lazily loads all its data on demand to minimize initialization calls. For example, processors are not
    created until the :meth:`~Blueprint.processors` attribute is called.

    Notes:
        The name of a processor is based on the name of its module.
        Data can be stored on a Blueprint using the `setData` method. This allows storing pre-existing widgets or any
        other type of data.
    """

    def __init__(self, module: ModuleType) -> None:
        """Initialize the blueprint object by defining it's attributes"""

        self._module = module

        self._name: str = os.path.splitext(os.path.basename(module.__file__))[0] or module.__name__

    def __bool__(self) -> bool:
        """Allow to deteremine if the blueprint contains processors or not.

        Return:
            True if the blueprint contain at least one processor else False.
        """
        return bool(self.processors)

    __nonzero__ = __bool__

    def __hash__(self) -> int:
        """Make the Blueprint hashable based on it's module file path.

        Return:
            The hash for the blueprint's module file path.
        """

        return hash(self._module.__file__)

    def __eq__(self, other: Blueprint) -> bool:
        """Support for logical comparison `equal`.
        
        Two Blueprints are considered similar if they are based on the same file.

        Return:
            Whether the current and other blueprints are based on the same module.
        """
        if not isinstance(other, Blueprint):
            return False

        return self._module.__file__ == other._module.__file__

    @property
    def name(self) -> str:
        """Getter for the Blueprint's name.
        
        Return:
            The Blueprint's name.
        """

        return self._name

    @property
    def module(self) -> ModuleType:
        """Getter for the Blueprint's module
        
        Return:
            The Blueprint's module.
        """

        return self._module

    @cached_property
    def file(self) -> str:
        """Lazy getter for the Blueprint's module file path.

        Return:
            The blueprint's module file path.
        """

        return os.path.dirname(self._module.__file__)

    @cached_property    
    def icon(self) -> str:
        """Lazy getter for the Blueprint's icon path.

        Return:
            The Blueprint's icon path.

        Notes:
            The icon must be a `.png` file in the same folder as the Blueprint's module.
        """

        return os.path.join(self.file, '{0}.png'.format(self._name))

    @cached_property
    def header(self) -> Tuple[str, ...]:
        """Lazy getter for the Blueprint's header.

        Return:
            The value for the `header` attribute in the Blueprint's module or an empty Tuple.
        """

        return getattr(self._module, 'header', ())

    @cached_property
    def descriptions(self) -> Dict[str, Dict[str, Any]]:
        """Lazy getter for the Blueprint's descriptions.

        Return:
            The value for the `descriptions` attribute in the Blueprint's module or an empty dict.
        """

        return getattr(self._module, 'descriptions', {})

    @cached_property
    def settings(self) -> Dict[str, Any]:
        """Lazy getter for the Blueprint's descriptions.

        Return:
            The value for the `settings` attribute in the Blueprint's module or an empty dict.
        """

        return getattr(self._module, 'settings', {})

    @cached_property
    def processors(self) -> Tuple[Processor, ...]:
        """Lazy getter for the Blueprint's processors.
        
        This will create all the processors from the Blueprint's decsriptions ordered based on the header and will 
        automatically resolve the links for each description in case this is meant to be used in batch.

        Return:
            A tuple containing all :class:`~Processor` for the current Blueprint's description.
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

        return tuple(processorObjects)

    def processorByName(self, name: str) -> Optional[Processor]:
        """Find a processor from blueprint's processors based on it's name.
        
        Parameters:
            name: The name of the processor to find.

        Return:
            The processor that match the name, or None if no processor match the given name.
        """

        for processor in self.processors:
            if processor.moduleName == name:
                return processor


class Tag(enum.IntFlag):
    """Tags are modifiers used by athena to affect the way a process behavior. 
    
    Tags are defined in the :class:`~Blueprint` and will be parsed by the :class:`~Processor` which will change 
    it's configuration based on them.
    The :class:`~Process` by itself is totaly unaware of it's Tags as they are only used by it's wrapper, the Processor.
    
    Tags allow Process to be optional, non blocking, hide their checks or even be completely disabled or dependant to
    another Process using Link.
    """

    NO_TAG: int = 0
    """This is used as default, representing the absence of any tag"""

    DISABLED: int = enum.auto()
    """Define if a process should be disabled (by default it is enabled)"""

    NO_CHECK: int = enum.auto()
    """This tag will remove the check of a process, it will force the isCheckable to False in blueprint."""

    NO_FIX: int = enum.auto()
    """This tag will remove the fix of a process, it will force the isFixable to False in blueprint."""

    NO_TOOL: int = enum.auto()
    """This tag will remove the tool of a process, it will force the hasTool to False in blueprint."""

    NON_BLOCKING: int = enum.auto()
    """A non blocking process will raise a non blocking error, its error is ignored."""
    
    NO_BATCH: int = enum.auto()
    """This process will only be executed in ui."""

    NO_UI: int = enum.auto()
    """This process will only be executed in batch."""
    
    OPTIONAL: int = NON_BLOCKING | DISABLED
    """This tag will set a check optional, an optional process is not checked by default and will."""

    DEPENDANT: int = NO_CHECK | NO_FIX | NO_TOOL
    """A dependent process need links to be run through another process."""


class Link(enum.Enum):
    """Give access to sentinel objects for each kind of link."""

    CHECK: object = object()
    """Represent the link to or from a Process' check method"""

    FIX: object = object()
    """Represent the link to or from a Process' fix method"""

    TOOL: object = object()
    """Represent the link to or from a Process' tool method"""


class Processor(object):
    """Proxy object representing a :class:`~Process` configured from a :class:`~Blueprint` description.

    The `Processor` is constructed based on a Python import string, responsible for instantiating and managing a specific 
    Process.
    It requires essential data typically specified in a Blueprint's description. The class internally determines the 
    implemented methods on the Process class, setting up attributes to describe available functionalities.

    In addition, the `Processor` resolves Tags and slightly overrides the initial Process behavior (e.g., removing `fix`,
    disabling the Process in batch mode). This adds flexibility to the framework by allowing customization of the Process's 
    behavior.

    The implementation of the `Processor` class is predominantly lazy, initializing only the necessary arguments during 
    instantiation and deferring expensive computation until they are actually needed, while caching their results. 
    The `Processor` takes on the responsibility of resolving all :class:`~Tag`, :class:`~Link`, and 
    :class:`~.AtStatus.Status` overrides for all Process' :class:`~Thread`. Additionally, it can be made aware of 
    :class:`~Blueprint` settings through the `setting` argument or receive extra data for later use.

    Overall, the `Processor` plays a pivotal role in configuring and executing Processes defined in a Blueprint, contributing 
    to the framework's flexibility and ease of use. Whether it's for using them in a UI or batch.
    """

    def __init__(self, 
        process: str, 
        category: Optional[str] = None, 
        arguments: Optional[Mapping[str, Tuple[Tuple[Any, ...], Mapping[str, Any]]]] = None, 
        tags: Tag = Tag.NO_TAG,
        links: Optional[Tuple[Tuple[str, Link, Link], ...]] = None,
        statusOverrides: Optional[Mapping[str, Mapping[Type[AtStatus.Status], AtStatus.Status]]] = None,
        settings: Optional[Mapping[str, Any]] = None, 
        **kwargs: Any) -> None:
        """Init the Processor instances attributes and define all the default values. The tags will also be resolved.

        Parameters:
            process: The python path to import the process from, it must be a full import path to the Process class.
            category: The name of the category of the Processor, if no value are provided the category will be `AtConstants.DEFAULT_CATEGORY` (default: `None`)
            arguments: This dict must contain by method name ('__init__', 'check', ...) a tuple containing a tuple for the args and 
                a dict for the keyword arguments.
            tags: The tag is an integer where bytes refers to `athena.AtCore.Tags`, it must be made of one or more tags. (default: `None`)
            links: The links must contain an ordered sequence of tuple with the name of another Process of the same blueprint, and two 
                Links that are the source and the target methods to connect.
            statusOverride: Status overrides must be a dict with name of process Thread as key (str) and a dict with `AtStatus.FailStatus` or
                `AtStatus.SuccessStatus` as key (possibly both) and the status for the override as value. (default: `None`)
            settings: Setting is a dict that contain data as value for each setting name as key. (default: `None`)
            **kwargs: All remaining data passed at initialisation will automatically be used to init the Processor data.
        """

        self._processStrPath = process
        self._category = category or AtConstants.DEFAULT_CATEGORY
        self._arguments = arguments
        self._tags = tags
        self._links = links
        self._statusOverrides = statusOverrides
        self._settings = settings or {}

        self.__linksData: Dict[Link, List] = {Link.CHECK: [], Link.FIX: [], Link.TOOL: []}

        self.__isEnabled: bool = True

        self.__isNonBlocking: bool = False

        self.__inUi: bool = True
        self.__inBatch: bool = True

        # -- We setup the tags because this process is really fast and does not require to be lazy.
        # This also give access to more data without the need to build the process instance.
        self.setupTags()

        # -- Declare a blueprint internal data, these data are directly retrieved from blueprint's non built-in keys.
        self._data = dict(**kwargs)
        self._processProfile: _ProcessProfile = _ProcessProfile()

    def __repr__(self) -> str:
        """Readable representation of the Processor object

        Returns:
            A readable representation of the Processor based on it's process import path and id.
        """

        return '<{0} `{1}` at {2}>'.format(self.__class__.__name__, self._processStrPath.rpartition('.')[2], hex(id(self)))

    @cached_property
    def moduleName(self) -> str:
        """Lazy getter for the Processor's Process module name.
        
        Return:
            The Processor's Process module name.
        """

        return self._processStrPath.split('.')[-2]

    @cached_property
    def module(self) -> ModuleType:
        """Lazy getter that import the Processor's Process module.

        Return:
            The Processor's Process module object that was imported.
        """

        return AtUtils.importProcessModuleFromPath(self._processStrPath)

    @cached_property
    def processClass(self):
        """Lazy getter for the Processor's Process class

        Return:
            The Processor's Process class
        """

        return getattr(self.module, self._processStrPath.rpartition('.')[2])

    @cached_property
    def process(self) -> Type[Process]:
        """Lazy getter for the Processor's Process class

        Return:
            An initialised instance of the Processor's Process class.
        """

        initArgs, initKwargs = self.getArguments('__init__')
        process = self.processClass(*initArgs, **initKwargs)

        self._overrideStatus(process, self._statusOverrides)
        
        return process

    @cached_property
    def parameters(self) -> Tuple[Parameter, ...]:
        """Lazy getter Processor's Process' Parameters.

        Return:
            All Parameters objects for the Processor's Process.
        """

        parameters = []

        for attribute in vars(self.processClass).values():
            if isinstance(attribute, Parameter):
                parameters.append(attribute)

        return tuple(parameters)

    @cached_property
    def overridedMethods(self) -> List[str]:
        """Lazy getter for the overrided methods of the Processor's Process class.

        Return:
            List of name for each overrided method on the Processor's Process class compared to :class:`~Process`
        """

        return AtUtils.getOverridedMethods(self.processClass, Process)

    @cached_property
    def niceName(self) -> str:
        """Lazy getter for the Processor's Process nice name.

        Return:
            A nice name for the Processor's Process, split if on camelCase.
        """

        return AtUtils.camelCaseSplit(self.rawName)

    @cached_property
    def docstring(self) -> str:
        """Lazy getter for the Processor's Process docstring

        Use the value in the Processor's :obj:`~Process._doc_` attribute, if it's empty, use class docstring
        :obj:`~Process.__doc__`. If it's also empty, fallback on :obj:`~.AtConstants.NO_DOCUMENTATION_AVAILABLE`

        Returns:
            The formatted docstring to be more readable and also display the path of the process.
        """

        docstring = self.processClass._doc_ or self.processClass.__doc__ or AtConstants.NO_DOCUMENTATION_AVAILABLE
        docstring += '\n {0} '.format(self._processStrPath)

        docFormat = {}
        for match in re.finditer(r'\{(\w+)\}', docstring):
            matchStr = match.group(1)
            docFormat[matchStr] = self.processClass._docFormat_.get(matchStr, '')

        return docstring.format(**docFormat)

    @cached_property
    def hasCheckMethod(self) -> bool:
        """Lazy getter to know if the Processor's Process has a `check` method.

        Return:
            True if the Processor's Process has a `check` method, False otherwise.
        """

        return bool(self.overridedMethods.get(AtConstants.CHECK, False))

    @cached_property
    def hasFixMethod(self) -> bool:
        """Lazy getter to know if the Processor's Process has a `fix` method.

        Return:
            True if the Processor's Process has a `fix` method, False otherwise.
        """

        return bool(self.overridedMethods.get(AtConstants.FIX, False))

    @cached_property
    def hasToolMethod(self) -> bool:
        """Lazy getter to know if the Processor's Process has a `tool` method.

        Return:
            True if the Processor's Process has a `tool` method, False otherwise.
        """

        return bool(self.overridedMethods.get(AtConstants.TOOL, False))

    @property
    def rawName(self) -> str:
        """Getter fore the Processor's Process raw name.

        Return:
            The name for the Processor's Process, this will fallback to the class name if no `_name_` is set.
        """

        return self.processClass._name_ or self.processClass.__name__

    @property
    def isEnabled(self) -> bool:
        """Getter for the Processor's state.
        
        Return:
            `True` if the Processor is enabled, `False` Otherwise.
        """

        return self.__isEnabled

    @property
    def isCheckable(self) -> bool:
        """Getter for the Processor's checkable state.
        
        Return:
            `True` if the Processor is checkable, `False` Otherwise. 
        """

        return self.__isCheckable

    @property
    def isFixable(self) -> bool:
        """Getter for the Processor's fixable state.
        
        Return:
            `True` if the Processor is fixable, `False` Otherwise.
        """

        return self.__isFixable

    @property
    def inUi(self) -> bool:
        """Getter for Processor's UI state.

        Return:
            `True` if the Processor can be run in UI mode, `False` Otherwise.
        """

        return self.__inUi
    
    @property
    def inBatch(self) -> bool:
        """Getter for Processor's batch state.

        Return:
            `True` if the Processor can be run in batch mode, `False` Otherwise.
        """

        return self.__inBatch

    @property
    def isNonBlocking(self) -> bool:
        """Getter to know whether the Processor's Process FailStatus are blocking or not.

        Return:
            `False` if the Processor's Process FailStatus are blocking, `True` otherwise.
        """

        return self.__isNonBlocking

    @property
    def category(self) -> str:
        """Get the Processor's category.

        Return:
            The Processor's category name.
        """

        return self._category

    def getArguments(self, method: str) -> Tuple[List[Any], Dict[str, Any]]:
        """Retrieve arguments values for the given method of the Processor's Process.
        
        Parameters:
            method: The method name as str for which to retrieve the arguments and keyword arguments.

        Returns:
            Tuple containing a list of arguments values and a dict of keyword arguments values.

        Notes:
            This method will not raise any error, if no argument is found, return a tuple containing empty
            list and empty dict.
        """

        arguments = self._arguments
        if arguments is None:
            return ([], {})

        arguments = arguments.get(method, None)
        if arguments is None:
            return ([], {})

        return arguments

    def getSetting(setting: str, default: Optional[Any] = None) -> Any:
        """Get the value for a specific setting if it exists.

        Parameters:
            setting: The setting to get from the Processor's settings.
            default: The default value to return if the Processor does not have any value for this setting.

        Return:
            The value for the requested setting or the default value if the requested setting does not exists.
        """

        return self._settings.get(setting, default)

    def getLowestFailStatus(self) -> AtStatus.FailStatus:
        """Get the lowest Fail status from all :class:`~Thread` from the Processor's Process.

        Return:
            The Lowest Fail Status of the Processor's Process accross all it's :class:`~Thread`
        """

        return next(iter(sorted((thread._failStatus for thread in self._threads.values()), key=lambda x: x._priority)), None)

    def getLowestSuccessStatus(self) -> AtStatus.SuccessStatus:
        """Get the lowest Success status from all :class:`~Thread` from the Processor's Process.

        Return:
            The Lowest Success Status of the Processor's Process accross all it's :class:`~Thread`
        """

        return next(iter(sorted((thread._successStatus for thread in self._threads.values()), key=lambda x: x._priority)), None)

    def check(self, links: bool = True, doProfiling: bool = False) -> Tuple[FeedbackContainer, ...]:
        """This is a wrapper for the Processor's Process `check`.

        This will automatically execute the `check` method with it's right parameters and profile the execution if requested. 
        If the `links` attribute is set to `True`, the Processor's :class:`~Link` will also be executed..

        Parameters:
            links: Should the wrapper launch the connected links or not.
            doProfiling: Whether the `check` method must be run with the Processor's Profiler.

        Returns:
            All feedback containers for the Processor's Process post check.
        """

        if not self.hasCheckMethod:
            return None
        
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

        return self.process.getFeedbackContainers()

    def fix(self, links: bool = True, doProfiling: bool = False) -> Tuple[FeedbackContainer, ...]:
        """This is a wrapper for the Processor's Process `fix`.

        This will automatically execute the `fix` method with it's right parameters and profile the execution if requested. 
        If the `links` attribute is set to `True`, the Processor's :class:`~Link` will also be executed..

        Parameters:
            links: Should the wrapper launch the connected links or not.
            doProfiling: Whether the `fix` method must be run with the Processor's Profiler.

        Returns:
            All feedback containers for the Processor's Process post fix.
        """

        if not self.hasFixMethod:
            return None

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

        return self.process.getFeedbackContainers()

    def tool(self, links: bool = True, doProfiling: bool = False) -> Any:
        """This is a wrapper for the Processor's Process `tool`.

        This will automatically execute the `tool` method with it's right parameters and profile the execution if requested.
        If the `links` attribute is set to `True`, the Processor's :class:`~Link` will also be executed..

        Parameters:
            links: Should the wrapper launch the connected links or not.
            doProfiling: Whether the `tool` method must be run with the Processor's Profiler.

        Returns:
            The value returned by the Processor's Process `tool` method. Usually, `None`, but it could be the tool widget
            so it can be parented to the UI this Processor's is runt from.
        """

        if not self.hasToolMethod:
            return None

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

    def runLinks(self, which: Link) -> None:
        """Execute the Processor's links for the given :class:`~Link`.
        
        Parameters:
            which: Which link we want to run.
        """

        for link in self.__linksData[which]:
            link()

    def getParameter(self, parameter: Parameter) -> Any:
        """Get the value for the given :class:`~Parameter` object.

        Return:
            The current value for the given :class:`~Parameter` object.

        Notes:
            Python descriptors are defined on classes but hold different values per instance of the class that owns them, for
            this reason, we can't query the value from the :class:`~Parameter` itself. This method query the value as it knows both the
            class that own the :class:`~Parameter` and the instance for which we want the value.
        """

        return parameter.__get__(self.process, self.processClass)

    def setParameter(self, parameter: Parameter, value: Any) -> Any:
        """Set the given value to the given :class:`~Parameter` object.

        Return:
            The current value for the given :class:`~Parameter` object after being set. This allows to know the exact value the attribute
            was set on after it does it's validation.

        Notes:
            Python descriptors are defined on classes but hold different values per instance of the class that owns them, for
            this reason, we can't set the value from the :class:`~Parameter` itself. This method query the value as it knows both the
            class that own the :class:`~Parameter` and the instance for which we want to set the value.
        """

        parameter.__set__(self.process, value)
        return self.getParameter(parameter)

    def setupTags(self) -> None:
        """Setup the tags used by this Processor to modify the it's behaviour."""

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

    def resolveLinks(self, 
        linkedObjects: List[Optional[Processor], ...], 
        check: Link = AtConstants.CHECK, 
        fix: Link = AtConstants.FIX, 
        tool: Link = AtConstants.TOOL) -> None:
        """Resolve the links between the given objects and the current Processor.

        This need to be called with an ordered list of :class:`~Processor` or None for :class:`~Processor` to skip.
        (e.g. to skip those that should not be linked because they dont have to be run in batch or ui.)

        Parameters:
            linkedObjects: List of all objects used to resolve the current Processor's links. Objects to skip have to be replaced with `None`.
            check: Name of the method to use as check link on the given objects.
            fix: Name of the method to use as fix link on the given objects.
            tool: Name of the method to use as tool link on the given objects.
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
            driven = check if _driven is Link.CHECK else driven
            driven = fix if _driven is Link.FIX else driven
            driven = tool if _driven is Link.TOOL else driven

            linksData[_driver].append(getattr(linkedObjects[id_], driven))

    def _overrideStatus(self, 
        process: Process, 
        overrides: Mapping[str, Mapping[Union[Type[AtStatus.FailStatus], Type[AtStatus.SuccessStatus]], AtStatus.Status]]) -> None:
        """Override the Processor's Process' Threads Statuses based on a dict of overrides.

        Will iter through all Processor's Process' Threads and do the overrides from the dict by replacing the Fail
        or Success Statuses.

        Parameters: 
            process: The Processor's Process instance.
            overrides: The Status Overrides data, define the new FailStatus and/or the new SuccessStatus.
        """

        #FIXME: It's highly likely that this override the statuses owned by the class.
        # This is an issue if we need to  add the process twice.

        if not overrides:
            return

        for threadName, overridesDict in overrides.items():
            if not hasattr(process, threadName):
                raise RuntimeError('Process {0} have no thread named {1}.'.format(process._name_, threadName))
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

    def setProgressbar(self, progressbar: QtWidgets.QProgressBar) -> None:
        """Set the ProgressBar object in the UI to be used by the Processor's Process.

        Made to be called in the ui this method allow to give access to the progress bar in the Processor's Process to 
        give feedback on the execution progress while performing `check` and/or `fix`.

        Parameters:
            progressbar: ProgressBar object object to connect to the process to display check and fix progression.
        """

        self.process.setProgressbar(progressbar)

    def getData(self, key: str, default: Optional[Any] = None) -> Any:
        """Get the Processor's Data for the given key or default value if key does not exists.

        Parameters:
            key: The key to get the data from.
            default: The default value to return if the key does not exists.

        Return:
            The value at the given key in the Processor's data if the key exists. Else the default value is returned.
        """

        return self._data.get(key, default)

    def setData(self, key: str, value: Any) -> None:
        """Set the Processor's Data for the given key

        Parameters:
            key: The key to set the data for.
            value: The value to store as data for the given key.
        """

        self._data[key] = value

    def interupt(self):
        """Register user interuption for the Processor's Process"""
        
        self.process._registerInteruption()


#TODO: Improve the mechanic with `typeCast` and `validate`, maybe include other method to validate type as well.
# Also consider having an `abc.abstractproperty` for the type instead of the class constant to force implementation in 
# sub-classes.
T = TypeVar('T')
class Parameter(abc.ABC):
    """Athena Parameter descriptor that represent a variable value to be used in an Athena :class:`~Process`

    The Parameter is a python descriptor object that must be defined at the class level. It require a value that will be 
    used both as it's default value and it's current value until it's changed.
    The purpose of using a Parameter is to have a variable value the user can tweak to modify how the Process behave.
    It's possible to implement different subtype of Parameter to manage different Python types, for this, it's important
    to implement 2 methods so the Parameter can convert an input value (usually a string) and validate that this value is
    correct.
    """

    TYPE: Type[T]
    """Represent the type of the Parameter and is used for type casting in the :meth:`~Parameter.typeCast` method"""

    def __init__(self, default: T) -> None:
        """Initialize a new instance of Parameter.

        Parameters:
            default: The default value for the current Parameter. Will be set as default and current value.
        """

        self.__default: T = default
        self.__value: T = default
        
        self.__name: str = ''

    def __set_name__(self, owner: Type[Process], name: str) -> None:
        """Mangle the name of the Parameter into the class.
        
        Set a private argument on the class to hold the Parameter's default value.

        Parameters:
            owner: Class object that own the Parameter.
            name: Name of the parameter (name of the parameter attribute on the class)
        """

        self.__name = '__' + name
        setattr(owner, self.__name, self.__default)

    def __get__(self, instance: Optional[Process], owner: Type[Process]) -> T:
        """Descriptor getter for the Parameter value.

        Get the unique Parameter value for the given instance of the owner class.
        If no instance of the owner class is passed, the Parameter instance is returned
        instead to allow internal manipulation.
        
        Parameters:
            instance: The instance for which we want to get the Parameter value.
            owner: The class that owns the Parameter object.

        Return:
            The Parameter's current value for the given instance.
        """

        if instance is None:
            return self
        return getattr(instance, self.__name)

    def __set__(self, instance: Process, value: object) -> None:
        """Descriptor setter for the Parameter value.

        Cast the given value to the right Parameter's type (:obj:`~Parameter.TYPE`) using the
        :meth:`~Parameter.typeCast` method and then, if the value can be validate with the 
        :meth:`~Parameter.validate` method, the value is set for the Parameter on the given instance.

        Parameters:
            instance: The instance for which we want to set the Parameter value.
            value: The new value to set the Parameter's value to.
        """

        castValue = self.typeCast(value)

        if self.validate(castValue):
            setattr(instance, self.__name, castValue)

    def __delete__(self, instance: Process) -> None:
        """Descriptor deleter for the Parameter.

        When deleted, reset te parameter to it's default value.

        Parameters:
            instance: The instance for which we want reset the Parameter value to default.
        """

        setattr(instance, self.__name, self.__default)

    @property
    def name(self) -> str:
        """Getter for the Parameter's nice name.

        Basically, as the name is mangled, remove the 2 leading underscores.

        Return:
            The Parameter's nice name without leading underscores.
        """

        return self.__name[2:]

    @property
    def default(self) -> T:
        """Getter for the Parameter's default value.

        Return:
            The Parameter's default value.
        """

        return self.__default

    @abc.abstractmethod
    def typeCast(self, value: Any) -> T:
        """Cast the input value to the Parameter's type set in :obj:`~Parameter.TYPE`.

        This method is not implemented on the Parameter abstract base class, it needs to be implemented in 
        each an every subclass that are meant to be instanciated and use in an Athena :class:`~Process`.
        The input may be of various type so this method should handle different case of type casting.
        To do so, you can use the the :obj:`~Parameter.TYPE` attribute to convert the input value to the desired type.

        Parameters:
            value: The input value to convert to the Parameter's type.

        Raise:
            NotImplementedError: This is an abstract method of an abstract base class, it needs to be implemented in subclasses.
        """

        raise NotImplementedError()

    @abc.abstractmethod
    def validate(self, value: T) -> bool:
        """Validate that the input value is accepted and therefore can be set to the Parameter's value.

        This method is meant to validate that the given value is an acceptable value for the Parameter.
        For basic Parameter, this test can simply return True, making all values of the Parameter's Type acceptable.

        Parameters:
            value: The value of the Parameter's type to validate.

        Raise:
            NotImplementedError: This is an abstract method of an abstract base class, it needs to be implemented in subclasses.
        """

        raise NotImplementedError()


class BoolParameter(Parameter):
    """A concrete sub-type of Parameter that can be used to represent a boolean value."""

    TYPE: Type[bool] = bool

    def __init__(self, default: bool) -> None:
        """Initialize a new instance of BoolParameter.

        Parameters:
            default: The default boolean value for the Parameter.
        """

        if not isinstance(default, self.TYPE):
            raise ValueError('Value {} does not conform to {} validation.'.format(str(default), self.__class__.__name__))

        super(BoolParameter, self).__init__(default)

    def typeCast(self, value: Any) -> bool:
        """Cast the input value to the `bool` type.
        
        The casting is simple and support `bool`, `str` and `int`, all value of those type that can be considered `True`
        will return True, every other values will be considered False.
        The accepted values are:
            
            * bool: True
            * str: 'True', 'true', 'Yes', 'yes', 'ok', '1'
            * int: 1

        Parameters:
            value: The value to cast to `bool`.

        Returns:
            The input value evaluated as a boolean.
        """

        return value in (True, 'True', 'true', 'Yes', 'yes', 1, '1')

    def validate(self, value: bool) -> bool:
        """Validate that the given bool is valid.

        The given value is valid as long as it's a boolean.

        Parameter:
            value: The value to validate.

        Return:
            Whether or not the input value is valid. (If it's of the right type.)
        """

        return isinstance(value, self.TYPE)


class _NumberParameter(Parameter):
    """A sub-type of Parameter that can be used to represent a numeric value.
    
    _NumberParameter is a protected class, only used internaly, it must not be instantiated due to the abstract nature
    of the `numbers.Number` type.

    Warning:
        This implementation of Parameter is not meant to be instantiated, use the following concrete implementations
        instead:

            * :class:`~IntParameter`
            * :class:`~FloatParameter`
    """

    TYPE: Type[numbers.Number] = numbers.Number

    def __init__(self, 
        default: numbers.Number, 
        minimum: Optional[numbers.Number] = None, 
        maximum: Optional[numbers.Number] = None, 
        keepInRange: bool = False):
        """Initialize a new instance of _NumberParameter.

        Parameters:
            default: The default numeric value for the Parameter.
            minimum: The minimum value accepted for the Parameter. If None, no minimum limit is set.
            maximum: The maximum value accepted for the Parameter. If None, no maximum limit is set.
            keepInRange: Whether or not values below minimum or above maximum are forced to theses limits if they exceed them.
        """

        if not isinstance(default, self.TYPE):
            raise ValueError('Value {} does not conform to {} validation.'.format(str(default), self.__class__.__name__))

        super(_NumberParameter, self).__init__(default)

        self._minimum = minimum
        self._maximum = maximum
        self._keepInRange = keepInRange

    def typeCast(self, value: object) -> numbers.Number:
        """Cast the input value to the `numbers.Number` type.
        
        As the `numbers.Number` type is not instantiable, this method is meant to work wit sub-types that define an
        instantiable type for the :obj:`~Parameter.TYPE`.
        Will convert the input value to the Parameter's type and make sur it's in the range if the `keepInRange` attribute
        is set to `True`.

        Parameters:
            value: The value to cast to the Parameter's type.

        Return:
            The input value converted to the Parameter's type.
        """

        value = self.TYPE(value)

        if self._keepInRange:
            if self._minimum is not None and value < self._minimum:
                return self._minimum
            elif self._maximum is not None and value > self._maximum:
                return self._maximum

        return value

    def validate(self, value: numbers.Number) -> bool:
        """Validate if the input numeric value is withing the Parameter's value range.

        Parameters:
            value: The input value to validate.

        Return:
            Whether or not the value is withing the Parameter's range.
        """

        if self._minimum is not None and value < self._minimum:
            return False
        if self._maximum is not None and value > self._maximum:
            return False

        return True


class IntParameter(_NumberParameter):
    """A concrete sub-type of Parameter that can be used to represent an integer value."""

    TYPE: Type[int] = int


class FloatParameter(_NumberParameter):
    """A concrete sub-type of Parameter that can be used to represent a floating point value."""

    TYPE: Type[float] = float


class StringParameter(Parameter):
    """A concrete sub-type of Parameter that can be used to represent a string value."""

    TYPE: Type[str] = str

    def __init__(self, default: str, validation: Optional[Sequence[str, ...]] = None, caseSensitive: bool = True):
        """Initialize a new instance of StringParameter.

        Parameters:
            default: The default string value for the Parameter.
            validation: List of valid string the Parameter can have or None if all string are accepted.
            caseSensitive: Whether or not the string given in `validation` are case sensitive.
        """

        if not isinstance(default, self.TYPE):
            raise ValueError('Value {} does not conform to {} validation.'.format(str(default), self.__class__.__name__))

        super(StringParameter, self).__init__(default)

        self._validation = validation
        self._caseSensitive = caseSensitive

    def typeCast(self, value: object) -> str:
        """Cast the input value to string.

        Parameters:
            value: The input value to convert to the Parameter's type.

        Return:
            The string representation for the input value.
        """

        return self.TYPE(value.lower())

    def validate(self, value: str) -> bool:
        """Validate if the input value based on the validation if any.

        Parameters:
            value: The input value to validate.

        Return:
            Whether or not the input value respect the validation if any, else True.
        """

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
    DIGIT_PATTERN: str = r'([0-9,.\/]+)'
    DIGIT_REGEX: re.Pattern = re.compile(DIGIT_PATTERN)

    CATEGORIES: Tuple[Tuple[str, str], ...] = (
        ('ncalls', 'Number of calls. Multiple numbers (e.g. 3/1) means the function recursed. it reads: Calls / Primitive Calls.'),
        ('tottime', 'Total time spent in the function (excluding time spent in calls to sub-functions).'), 
        ('percall', 'Quotient of tottime divided by ncalls.'), 
        ('cumtime', 'Cumulative time spent in this and all subfunctions (from invocation till exit). This figure is accurate even for recursive functions.'), 
        ('percall', 'Quotient of cumtime divided by primitive calls.'), 
        ('filename:lineno(function)', 'Data for each function.')
    )

    def __init__(self) -> None:
        """Initialiste a Process Profiler and define the default instance attributes."""
        self._profiles: Dict[str, Dict[str, Union[float, List[Tuple[str, ...], ...]]]] = {} 

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Get a profile log from the given key, or default if key does not exists.
        
        Parameters:
            key: The key to get data from in the profiler's profile data.
            default: The default value to return in case the key does not exists.

        Return:
            The data stored at the given key if exists else the default value is returned.
        """

        return self._profiles.get(key, default)

    def _getCallDataList(self, callData: Sequence[str, ...]) -> None:
        """Format and split `cProfile.Profiler` call data list (each value in the list must be one line.)

        This will mostly remove heading or trailing spaces and return a list of tuple where each values in the
        string is now an entry in the tuple. The order is the same than `athena.AtCore._ProcessProfile.CATEGORIES`.
        
        Parameters:
            callData: Call entries from a `cProfile.Profiler` run.
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

    def profileMethod(self, method: FunctionType, *args: Any, **kwargs: Any) -> Any:
        """Profile the given method execution and return it's result. The profiling result will be stored in the 
        object.

        Try to execute the given method with the given args and kwargs and write the result in a temporary file.
        The result will then be read and each line splited to save a dict in the object `_profiles` attribute using
        the name of the given method as key.
        This dict will hold information like the time when the profiling was done (key = `time`, it can allow to not 
        update data in a ui for instance), the total number of calls and obviously a tuple with each call data (`calls`).
        The raw stats result is also saved under the `rawStats` key if the user want to use it directly.
        
        Parameters:
            method: A callable for which we want to profile the execution and save new data.
            *args: The arguments to call the method with.
            **kwargs: The keyword arguments to call the method with.

        Return:
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

    def getStatsFromProfile(self, profile: cProfile.Profile) -> Dict[str, Union[float, List[Tuple[str, ...], ...]]]:
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
