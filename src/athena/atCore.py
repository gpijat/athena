from __future__ import annotations

import abc
import enum
import inspect
import numbers
import os
import re
from dataclasses import dataclass, field
from functools import cached_property
from types import ModuleType
from typing import Callable, Type, Iterator, Optional, Union, Any, Dict, List, Tuple, Mapping, Sequence

from athena import atConstants, atExceptions, atStatus, atUtils, atEvent, atProfiling


class AtSession(object, metaclass=atUtils.Singleton):
    """Singleton class representing the Athena's running session.

    This class provides a single instance that manages the session state,
    including a registration system and a development mode toggle.

    Example:
        >>> AtSession().dev = True  # Enable development mode.
    """

    def __init__(self) -> None:
        """Initialize a new instance of __AtSession."""

        self._dev: bool = False

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
            atEvent.dev_mode_enabled()
        else:
            atEvent.dev_mode_disabled()


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
    meaning two instances with the same data (:attr:`~ProtoFeedback.feedback`) will be considered
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
        you should consider reimplementing it if you intend to use a very specific selection mechanism
        or need to deal with advanced selection/deselection. (= A lot of elements to deal with)
    """

    feedback: Thread
    """The FeedbackContainer data must be the Thread for which it contain feedbacks."""

    status: atStatus.Status
    """The FeedbackContainer status represent the result state of the Thread based on the contained feedbacks"""

    def __str__(self) -> str:
        """Simply return the title for the container's Thread"""

        return self.feedback._title

    def select(self, replace: bool = True) -> bool:
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

    def set_status(self, status:atStatus.Status) -> None:
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
        For DCC-specific implementations, refer to :mod:`athena.software`. The list is not exhaustive and emphasizes
        common and global behavior. If you have specific needs for another software or pipeline-specific behavior,
        you can implement your own Feedback subclass.
    """

    def select(self, replace: bool = True) -> bool:
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
        If the feedback is not selectable, it won't do anything, as there are no defined deselection behaviors for
        the default Feedback. If the Feedback is selectable, it cascades to every child and calls their
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
        '_default_fail_status',
        '_fail_status',
        '_default_success_status',
        '_success_status',
        '_documentation',
    )

    def __init__(self, title: str, fail_status: atStatus.FailStatus = atStatus.ERROR, success_status: atStatus.SuccessStatus = atStatus.SUCCESS, documentation: Optional[str] = None):
        """Initialize an instance of Thread.

        This method sets up a Thread instance with the provided parameters, including the thread title,
        default fail and success statuses, and an optional documentation. Their default values are different from their
        actual value.

        Parameters:
            title: The title of the Thread.
            fail_status: The default fail status for the command, will be set as fail_status and defaultFailStatus.
            success_status:The default success status for the command, will be set as success_status and defaultSuccessStatus
            documentation: Optional documentation or description for the Thread.

        Raises:
            atExceptions.StatusException: If the provided fail_status or success_status are not of the valid type.

        Notes:
            The fail_status and success_status parameters should be members of the atStatus.FailStatus and
            atStatus.SuccessStatus enumerations, respectively. If not provided, the default statuses are
            set to atStatus.ERROR and atStatus.SUCCESS, respectively.
        """

        if not isinstance(fail_status, atStatus.FailStatus):
            raise atExceptions.StatusException('`{}` is not a valid fail status.'.format(fail_status._name))
        if not isinstance(success_status, atStatus.SuccessStatus):
            raise atExceptions.StatusException('`{}` is not a valid success status.'.format(success_status._name))

        self._title = title

        self._default_fail_status = fail_status
        self._fail_status = fail_status

        self._default_success_status = success_status
        self._success_status = success_status

        self._documentation = documentation

    @property
    def title(self) -> str:
        """Getter for the Thread's title.

        Return:
            The thread's title.
        """

        return self._title

    @property
    def fail_status(self) -> atStatus.FailStatus:
        """Getter for the Thread's fail status.

        Return:
            The thread's fail status.
        """

        return self._fail_status

    @property
    def success_status(self) -> atStatus.SuccessStatus:
        """Getter for the Thread's success status.

        Return:
            The thread's success status..
        """

        return self._success_status

    def override_fail_status(self, status: atStatus.FailStatus) -> None:
        """Override the actual fail status.

        Parameters:
            status: The Status class to use as new fail status.
        """

        self._fail_status = status

    def override_success_status(self, status: atStatus.SuccessStatus) -> None:
        """Override the actual success status.

        Parameters:
            status: The Status class to use as new success status.
        """

        self._success_status = status

    def status(self, state: bool) -> atStatus.Status:
        """Get the Thread's current status based on given state boolean.

        Return:
            Success status if `state` is true, fail status otherwise.
        """

        if state:
            return self._success_status
        else:
            return self._fail_status


#TODO: On a major update, replace individual process computation with process that subscribe to iteration.
# e.g. AtPolygonIterator -> Iterate over polygons of a mesh and notify subscribers.
class Process(abc.ABC):
    """Abstract class that serves as the foundation for all Athena Processes.

    The `Process` class acts as the base (abstract) class for all user-defined check processes within the Athena framework.
    To create a new process, it's essential to define at least one :class:`~Thread` object as a class attribute. These threads
    manage various feedbacks that the process will inspect and potentially address.

    During the execution of your process's :meth:`~Process.check`, if any issues are detected, you need to create
    instances of the :class:`~Feedback` class (or its subclasses) and register them for the appropriate threads using
    the :meth:`~Process.addFeedback` method. In the :meth:`~Process.fix` method, iterate over these feedback
    instances and implement any necessary actions to automatically resolve fixable issues.

    Additional methods for managing internal feedback are available, allowing you to retrieve feedbacks, iterate over them,
    or check if there are any feedbacks for a specific Thread.

    At the end of the check process, it's crucial to set the state for each Thread. By default, they are all set to the
    :const:`.atStatus._DEFAULT` built-in status. To change a Thread status, you can call the :meth:`~Process.setSuccess`
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
    This is intended to be overridden in a subclass if you're willing to use a different FeedbackContainer implementation.
    """

    _name_: str = ''
    """The Process nice name. If not set, will be set to the value of __name__"""

    _doc_: str = ''
    """The Process user's documentation. If not set, will be set to the value of __doc__"""

    _listen_for_user_interruption: atEvent.AtEvent = atEvent.AtEvent('ListenForUserInterruption')
    """Event that allow to notify subscribers when the user is trying to interrupt the process execution."""

    def __new__(cls, *args: Any, **kwargs: Any) -> Type[Process]:
        """Create a new instance of the Process class.

        This method overrides the default `__new__` method and is responsible for initializing a new instance
        of the class with some private attribute used internally.
        """

        # Create the instance
        instance = super(Process, cls).__new__(cls, *args, **kwargs)

        # Instance internal data (Must not be altered by user)
        instance._feedback_container: Dict[Thread, Type[FeedbackContainer]] = cls.__make_feedback_container()
        instance.__progress_bar: QtWidgets.QProgressBar = None

        instance.__do_interrupt: bool = False

        # Sunder instance attribute (Can be overridden user to custom the process)
        # instance._name_ = cls._name_ or cls.__name__
        # instance._doc_ = cls._doc_ or cls.__doc__

        return instance

    def __repr__(self) -> str:
        """Give a nice representation of the Process with it's nice name."""

        return '<Process `{0}` at {1}>'.format(self._name_, hex(id(self)))

    @classmethod
    def __make_feedback_container(cls) -> Dict[Thread, FeedbackContainer]:
        """Create and initialize a dictionary of :class:`~FeedbackContainers` for each :class:`~Thread`.

        This class method generates a dictionary of FeedbackContainers for each Thread associated with the Process class.
        The FeedbackContainers are initialized with the Thread, True (indicating the container is selectable),
        and :const:`~.atStatus._DEFAULT` (the default status for the containers).

        Return:
            A new dict with an empty FeedbackContainer per Thread with status set to :const:`.atStatus._DEFAULT`

        Note:
            This method is typically used internally within the Process class to initialize the FeedbackContainers for
            each associated Thread.

        See Also:

            * :class:`~Thread`: The class representing a task within the Athena framework.
            * :class:`~FeedbackContainer`: The container for managing feedback associated with a specific Thread.
            * :const:`~atStatus._DEFAULT`: The default status used when initializing FeedbackContainers.
        """

        return {thread: cls.FEEDBACK_CONTAINER_CLASS(thread, True, atStatus._DEFAULT) for thread in cls.threads()}

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

    def set_progress_bar(self, progress_bar: QtWidgets.QProgressBar) -> None:
        """This method should be used to setup the Process progress bar widget.

        Parameters:
            progress_bar: The new progress bar to link to The Process instance.
        """

        self.__progress_bar = progress_bar

    def set_progress(self, value: Optional[bool] = None, text: Optional[bool] = None) -> None:
        """Set the progress value and/or text for the associated QProgressBar.

        This method allows setting the progress value and/or text for the QProgressBar associated with the Process instance.
        It is typically used to provide feedback to the user on the current state of the check or fix progress.

        Parameters:
            value: The progress value to set. If None, the progress value remains unchanged.
            text: The progress text to set. If None, the progress text remains unchanged.
        """

        if value is not None:
            self.set_progress_value(value)

        if text is not None:
            self.set_progress_text(text)

    def set_progress_value(self, value: numbers.Number) -> None:
        """Set the progress value of the Process progress bar if exist.

        Parameters:
            value: The value to set the progress to.

        Raise:
            TypeError: If `value` is not numeric.
        """

        if self.__progress_bar is None:
            return

        #WATCHME: `numbers.Number` is an abstract base class that define operations progressively, the first call to
        # this method will define it for the first time, this is why the profiler can detect some more calls for the
        # first call of the first process to be run. --> We talk about insignificant time but the displayed data will
        # be a bit different. see: https://docs.python.org/2/library/numbers.html
        if not isinstance(value, numbers.Number):
            raise TypeError('Argument `value` is not numeric')

        if value and value != self.__progress_bar.value():
            self.__progress_bar.setValue(float(value))

    def set_progress_text(self, text: str) -> None:
        """Set the label text of the Process progress bar if exist.

        Parameters:
            text: Text to display in the progressBar.
        """

        if self.__progress_bar is None:
            return

        if text and text != self.__progress_bar.text():
            self.__progress_bar.setFormat(atConstants.PROGRESSBAR_FORMAT.format(text))

    def clear_feedback(self) -> None:
        """Clear all feedback associated with the threads in the process.

        This method resets the feedback containers for each thread by creating new instances of FeedbackContainers.
        It effectively clears any previously registered feedback.
        """

        self._feedback_container = self.__make_feedback_container()

    def has_feedback(self, thread) -> None:
        """Check if there is feedback registered for a specific thread.

        Parameters:
            thread: The thread to check for feedback.

        Return:
            True if there is feedback for the specified thread, False otherwise.
        """

        return bool(self._feedback_container[thread].children)

    def add_feedback(self, thread: Thread, feedback: Feedback) -> None:
        """Add feedback to the specified thread's feedback container.

        Parameters:
            thread: The thread to which the feedback will be added.
            feedback: The feedback instance to add.
        """

        self._feedback_container[thread].parent(feedback)

    def iter_feedback(self, thread: Thread) -> Iterator[Feedback]:
        """Iterate over the feedback instances registered for a specific thread.

        Parameters:
            thread: The thread for which to iterate over feedback.

        Return:
            An iterator over the feedback instances for the specified thread.
        """

        return iter(self._feedback_container[thread].children)

    def feedback_count(self, thread: Thread) -> int:
        """Get the count of feedback instances registered for a specific thread.

        Parameters:
            thread: The thread for which to get the feedback count.

        Return:
            The number of feedback instances for the specified thread.
        """

        return len(self._feedback_container[thread].children)

    def get_feedback_containers(self) -> Tuple[FeedbackContainer]:
        """Get a tuple of all feedback containers associated with the threads.

        Return:
            A tuple containing all feedback containers associated with the threads.
        """

        return tuple(self._feedback_container.values())

    def set_success(self, thread: Thread) -> None:
        """Set the success status for a specific thread's feedback container.

        Parameters:
            thread: The thread for which to set the success status.
        """

        self._feedback_container[thread].set_status(thread.status(True))

    def set_fail(self, thread: Thread) -> None:
        """Set the fail status for a specific thread's feedback container.

        Parameters:
            thread: The thread for which to set the fail status.
        """

        self._feedback_container[thread].set_status(thread.status(False))

    def set_skipped(self, thread: Thread) -> None:
        """Set the skipped status for a specific thread's feedback container.

        Parameters:
            thread: The thread for which to set the skipped status.
        """

        self._feedback_container[thread].set_status(atStatus._SKIPPED)

    def listen_for_user_interruption(self) -> None:
        """Trigger an user interruption AtEvent to prematurely end process execution.

        This method triggers the :attr:`~Process._listen_for_user_interruption` AtEvent, which requires a registered callback
        to invoke the :meth:`~Process._register_interruption` method from the Qt Application.

        After triggering the event, if there is a callback to invoke the appropriate method, the boolean value
        for :obj:`~Process.__do_interrupt` will be set to True, and an :exc:`.atExceptions.AtProcessExecutionInterrupted`
        exception will be raised. This exception can be handle in the Qt Application to force the Process Status to
        :const:`.atStatus._ABORTED`.

        Raises:
            atExceptions.AtProcessExecutionInterrupted: If the interruption is caught and propagated.

        Important:
            When the Process is executing, the Qt Event System stacks QEvents, processing them at the end of the
            execution, typically after all process executions are finished. To catch user interactions during
            execution, the Qt Event System must process pending events. The :attr:`~Process._listen_for_user_interruption`
            Event can trigger a call to `QApplication.processEvents`, accomplished by adding it as a callback for this
            Event.

            When this method runs, the callbacks are triggered, allowing the processing of pending interactions, such as a key
            press. A side effect is that the key press becomes part of the Qt UI thread.

            To ensure the raise directly impacts the application and ends the process, it must be done from the main thread.
            Therefore, the :meth:`~Process._register_interruption` method needs to be called from the Qt Application to
            toggle the behavior of this method so it can raise. Typically, this method is called in the check or fix
            method, ensuring that the raise occurs from the main thread.
        """

        if self.__do_interrupt:
            return

        self._listen_for_user_interruption()

        if self.__do_interrupt:
            self.__do_interrupt = False
            raise atExceptions.AtProcessExecutionInterrupted()

    def _register_interruption(self) -> None:
        """Change the value for the private member :attr:`~Process.__do_interrupt` to True.

        This simply allow to change the value of this private member from outside the class.
        """

        self.__do_interrupt = True


class Register(object):
    """The register is a container that allow the user to load and manage blueprints.

    After initialization the register will not contain any data and you will need to load the :class:`~Blueprint` you
    want for your current Athena Session.
    The role of the register is to act as a loader and data keeper for all existing Blueprints you defined and want your
    user's to be able to use for their sanity checking.
    """

    def __init__(self) -> None:
        """Initialize the Register's internal data."""

        self.__blueprints: List[Blueprint] = []
        self._current_blueprint: Blueprint = None

        atEvent.register_created()

    def __bool__(self) -> bool:
        """Allow to check if the register is empty or not based on the loaded blueprints."""
        return bool(self.__blueprint)

    __nonzero__ = __bool__

    #FIXME: The import system is not easy to use, find a better way to use them.
    #TODO: Find a way to implement this feature and clean the import process.
    # def loadBlueprintFromPythonStr(self, pythonCode, module_name):
    #     module = atUtils.moduleFromStr(pythonCode, name=module_name)
    #     self.load_blueprint_from_module(Blueprint(module))

    def load_blueprints_from_package_str(self, package: str) -> None:
        """Load blueprints from a package name.

        This method calls the loadBlueprintsFromPackage method with the imported package object.

        Parameters:
            package: The python formatted path of the package to load blueprints from.

        Warning:
            This method is **deprecated** as it suppose a specific hierarchy, a feature inherited from
            the early ages of Athena. You're not supposed to have a specific hierarchy in you packages
            to load their blueprints.
        """

        self.load_blueprints_from_package(atUtils.import_from_str(package))

    def load_blueprints_from_package(self, package: ModuleType) -> None:
        """Load blueprints from a package object.

        This method iterates over the blueprints paths in the package and calls the loadBlueprintFromModulePath
        method for each one.

        Parameters:
            package: The package object to load blueprints from.

        Warning:
            This method is #deprecated** as it suppose a specific hierarchy, a feature inherited from
            the early ages of Athena. You're not supposed to have a specific hierarchy in you packages
            to load their blueprints.
        """

        for module_path in atUtils.iter_blueprints_path(package):
            self.load_blueprint_from_module_path(module_path)

    def load_blueprint_from_module_path(self, module_path: str) -> None:
        """Load a blueprint from a module OS path.

        This method converts the module path to a python import path and load blueprints from it..

        Parameters:
            module_path: The path of the module to load a blueprint from.
        """

        self.load_blueprint_from_python_import_path(atUtils.python_import_path_from_path(module_path))

    def load_blueprint_from_python_import_path(self, import_str: str) -> None:
        """Load a blueprint from a module python's import path.

        This method will import the module from the string and load blueprints from it.

        Parameters:
            import_str: The python import path to the Blueprint's module to load.
        """

        self.load_blueprint_from_module(atUtils.import_from_str(import_str))

    def load_blueprint_from_module(self, module: ModuleType) -> None:
        """Load a blueprint from a module object.

        This method creates a Blueprint object from the module and adds it to the list of blueprints.
        If a blueprint with the same name already exists, it replaces it with the new one.

        Parameters:
            module: The module object to load a blueprint from.
        """

        new_blueprint = Blueprint(module)
        for i, blueprint in enumerate(self.__blueprints):
            if blueprint == new_blueprint:
                self.__blueprints[i] = new_blueprint
                break
        else:
            self.__blueprints.append(new_blueprint)

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
    def current_blueprint(self) -> Blueprint:
        """Getter for current blueprint.

        Return:
            The current blueprint.
        """

        return self._current_blueprint

    @current_blueprint.setter
    def current_blueprint(self, blueprint: Blueprint) -> None:
        """Setter for current blueprint

        Set the current blueprint if it's an already registered blueprint recognized by the register.

        Parameters:
            blueprint: The new Blueprint to set as current blueprint.
        """

        if blueprint in self.__blueprints:
            self._current_blueprint = blueprint

    def blueprint_by_name(self, name: str) -> Optional[Blueprint]:
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
                atUtils.reload_module(processor.module)
            self.load_blueprint_from_module(atUtils.reload_module(blueprint._module))

        atEvent.blueprints_reloaded()


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
        """Whether ot not the blueprint contains any processor.

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

        This will create all the processors from the Blueprint's descriptions ordered based on the header and will
        automatically resolve the links for each description in case this is meant to be used in batch.

        Return:
            A tuple containing all :class:`~Processor` for the current Blueprint's description.
        """

        batch_link_resolve = {}
        processor_objects = []

        for id_ in self.header:
            if id_ not in self.descriptions:
                continue

            processor = Processor(**self.descriptions[id_], settings=self.settings)

            processor_objects.append(processor)
            batch_link_resolve[id_] = processor if processor.in_batch else None

        # Default resolve for descriptions if available in batch, call the `resolveLinks` method from descriptions to change the targets functions.
        for processor in processor_objects:
            processor.resolve_links(batch_link_resolve, check=atConstants.CHECK, fix=atConstants.FIX, tool=atConstants.TOOL)

        return tuple(processor_objects)

    def processor_by_name(self, name: str) -> Optional[Processor]:
        """Find a processor from blueprint's processors based on it's name.

        Parameters:
            name: The name of the processor to find.

        Return:
            The processor that match the name, or None if no processor match the given name.
        """

        for processor in self.processors:
            if processor.module_name == name:
                return processor

    @property
    def nonconformant_parameters(self) -> Tuple[Parameter, ...]:
        """Getter for every non-conformant :class:`~Parameter` across all of this Blueprint's Processors.

        This value is computed on each access so that it always reflects the current state of the
        Processors rather than a snapshot taken earlier.

        Return:
            The tuple of Parameters that currently taint conformance across the whole Blueprint.
        """

        return tuple(
            parameter
            for processor in self.processors
            for parameter in processor.nonconformant_parameters
        )

    @property
    def is_conformant(self) -> bool:
        """Getter for the Blueprint's conformance state, aggregated over all its Processors.

        Return:
            True if no Processor in this Blueprint currently has a non-conformant Parameter.
        """

        return not self.nonconformant_parameters


class Tag(enum.IntFlag):
    """Tags are modifiers used by athena to affect the way a process behavior.

    Tags are defined in the :class:`~Blueprint` and will be parsed by the :class:`~Processor` which will change
    it's configuration based on them.
    The :class:`~Process` by itself is totally unaware of it's Tags as they are only used by it's wrapper, the Processor.

    Tags allow Process to be optional, non blocking, hide their checks or even be completely disabled or dependant to
    another Process using Link.
    """

    NO_TAG: int = 0
    """This is used as default, representing the absence of any tag"""

    DISABLED: int = enum.auto()
    """Define if a process should be disabled (by default it is enabled)"""

    NO_CHECK: int = enum.auto()
    """This tag will remove the check of a process, it will force the allows_check to False in blueprint."""

    NO_FIX: int = enum.auto()
    """This tag will remove the fix of a process, it will force the allows_fix to False in blueprint."""

    NO_TOOL: int = enum.auto()
    """This tag will remove the tool of a process, it will force the allows_tool to False in blueprint."""

    NO_PARAMETERS: int = enum.auto()
    """This tag will hide the process parameters from the tool, it will force the allows_parameters to False in blueprint."""

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
    :class:`~atStatus.Status` overrides for all Process' :class:`~Thread`. Additionally, it can be made aware of
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
        status_overrides: Optional[Mapping[str, Mapping[Type[atStatus.Status], atStatus.Status]]] = None,
        parameter_overrides: Optional[Mapping[str, Mapping[str, Any]]] = None,
        parameter_policies: Optional[Mapping[str, Mapping[str, Any]]] = None,
        settings: Optional[Mapping[str, Any]] = None,
        **kwargs: Any) -> None:
        """Init the Processor instances attributes and define all the default values. The tags will also be resolved.

        Parameters:
            process: The python path to import the process from, it must be a full import path to the Process class.
            category: The name of the category of the Processor, if no value are provided the category will be :obj:`atConstants.DEFAULT_CATEGORY` (default: `None`)
            arguments: This dict must contain by method name ('__init__', 'check', ...) a tuple containing a tuple for the args and
                a dict for the keyword arguments.
            tags: The tag is an integer where bytes refers to `athena.atCore.Tags`, it must be made of one or more tags. (default: `None`)
            links: The links must contain an ordered sequence of tuple with the name of another Process of the same blueprint, and two
                Links that are the source and the target methods to connect.
            status_override: Status overrides must be a dict with name of process Thread as key (str) and a dict with :class:`atStatus.FailStatus` or
                `atStatus.SuccessStatus` as key (possibly both) and the status for the override as value. (default: `None`)
            parameter_overrides: Blueprint spec overrides for the Process' Parameters. A dict with a Parameter name as key and a
                dict of builder keyword arguments to override as value (e.g. `{'iterations': {'default': 10, 'maximum': 50}}`). (default: `None`)
            parameter_policies: Blueprint policy tightenings for the Process' Parameters. A dict with a Parameter name as key and a
                dict of policy axes to tighten as value (e.g. `{'iterations': {'user_override': UserParameterOverride.LOCKED}}`). (default: `None`)
            settings: Setting is a dict that contain data as value for each setting name as key. (default: `None`)
            **kwargs: All remaining data passed at initialization will automatically be used to init the Processor data.
        """

        self._process_str_path = process
        self._category = category or atConstants.DEFAULT_CATEGORY
        self._arguments = arguments
        self._tags = tags
        self._links = links
        self._status_overrides = status_overrides
        self._parameter_overrides = parameter_overrides or {}
        self._parameter_policies = parameter_policies or {}
        self._settings = settings or {}

        self.__links_data: Dict[Link, List] = {Link.CHECK: [], Link.FIX: [], Link.TOOL: []}

        self.__is_enabled: bool = True

        self.__is_non_blocking: bool = False

        self.__in_ui: bool = True
        self.__in_batch: bool = True

        # -- We setup the tags because this process is really fast and does not require to be lazy.
        # This also give access to more data without the need to build the process instance.
        self.setup_tags()

        # -- Declare a blueprint internal data, these data are directly retrieved from blueprint's non built-in keys.
        self._data = dict(**kwargs)
        self._process_profile: atProfiling._AtProcessProfile = atProfiling._AtProcessProfile()

    def __repr__(self) -> str:
        """Readable representation of the Processor object

        Returns:
            A readable representation of the Processor based on it's process import path and id.
        """

        return '<{0} `{1}` at {2}>'.format(self.__class__.__name__, self._process_str_path.rpartition('.')[2], hex(id(self)))

    @cached_property
    def module_name(self) -> str:
        """Lazy getter for the Processor's Process module name.

        Return:
            The Processor's Process module name.
        """

        return self._process_str_path.split('.')[-2]

    @cached_property
    def module(self) -> ModuleType:
        """Lazy getter that import the Processor's Process module.

        Return:
            The Processor's Process module object that was imported.
        """

        return atUtils.import_process_module_from_path(self._process_str_path)

    @cached_property
    def process_class(self):
        """Lazy getter for the Processor's Process class

        Return:
            The Processor's Process class
        """

        return getattr(self.module, self._process_str_path.rpartition('.')[2])

    @cached_property
    def process(self) -> Type[Process]:
        """Lazy getter for the Processor's Process class

        Return:
            An initialized instance of the Processor's Process class.
        """

        init_args, init_kwargs = self.get_arguments('__init__')
        process = self.process_class(*init_args, **init_kwargs)

        # Install every resolved Blueprint override on the instance and never on the shared class.
        # Changing the class level state would corrupt any other Processor that wraps the same Process.
        resolved_specs, resolved_policies = self.resolved_parameter_overrides
        for parameter, spec in resolved_specs.items():
            setattr(process, parameter._spec_attr, spec)
        for parameter, policy in resolved_policies.items():
            setattr(process, parameter._policy_attr, policy)

        self._override_status(process, self._status_overrides)

        return process

    @cached_property
    def parameters(self) -> Tuple[Parameter, ...]:
        """Lazy getter Processor's Process' Parameters.

        Return:
            All Parameters objects for the Processor's Process.
        """

        # Resolve the overrides eagerly so that an unknown or invalid Blueprint override is reported here
        # instead of being silently ignored. The value is unused, only the resolution side effect matters.
        _ = self.resolved_parameter_overrides

        parameters = []

        for attribute in vars(self.process_class).values():
            if isinstance(attribute, Parameter):
                parameters.append(attribute)

        return tuple(parameters)

    @cached_property
    def resolved_parameter_overrides(self) -> Tuple[Dict[Parameter, ParameterSpec], Dict[Parameter, ParameterPolicy]]:
        """Lazy getter that resolves this Processor's Blueprint level Parameter overrides.

        Every name used in `parameter_overrides` and `parameter_policies` is checked against the real
        Parameters of the Process. For each Parameter, the effective policy is resolved first, tightened
        by the requested policy override when there is one. The overridden spec is only resolved when the
        resolved policy allows it, so a Parameter that is not Blueprint configurable cannot have its spec
        overridden.

        Return:
            A tuple with two dicts, one mapping each overridden Parameter to its resolved
            :class:`~ParameterSpec` and one mapping each policy overridden Parameter to its resolved
            :class:`~ParameterPolicy`. A Parameter with no override does not appear in either dict.

        Raise:
            AtParameterNotFoundError: If an override references a Parameter that does not exist.
            AtParameterPolicyError: If a policy override would loosen the author's policy, or a spec
                override targets a Parameter that is not Blueprint configurable.
            AtParameterValidationError: If a spec override value does not pass validation.
        """

        parameters_by_name = {
            attribute.name: attribute
            for attribute in vars(self.process_class).values()
            if isinstance(attribute, Parameter)
        }

        for source in (self._parameter_overrides, self._parameter_policies):
            for name in source:
                if name not in parameters_by_name:
                    raise atExceptions.AtParameterNotFoundError(
                        'Process {0} has no parameter named {1!r}.'.format(self.raw_name, name)
                    )

        resolved_specs: Dict[Parameter, ParameterSpec] = {}
        resolved_policies: Dict[Parameter, ParameterPolicy] = {}

        for name, parameter in parameters_by_name.items():
            policy_override = self._parameter_policies.get(name)
            spec_override = self._parameter_overrides.get(name)

            # Resolve the effective policy first. The Blueprint tightening is validated here and the
            # resulting policy decides whether a spec override is allowed at all.
            policy = parameter._policy
            if policy_override is not None:
                policy = policy.tightened_by(**policy_override)
                resolved_policies[parameter] = policy

            if spec_override is not None:
                if not policy.blueprint_configurable:
                    raise atExceptions.AtParameterPolicyError(
                        'Parameter {0!r} is not Blueprint-configurable and cannot be spec-overridden.'.format(name)
                    )
                resolved_specs[parameter] = parameter._spec.with_overrides(**spec_override)

        return resolved_specs, resolved_policies

    @cached_property
    def overridden_methods(self) -> List[str]:
        """Lazy getter for the overridden methods of the Processor's Process class.

        Return:
            List of name for each overridden method on the Processor's Process class compared to :class:`~Process`
        """

        return atUtils.get_overridden_methods(self.process_class, Process)

    @cached_property
    def nice_name(self) -> str:
        """Lazy getter for the Processor's Process nice name.

        Return:
            A nice name for the Processor's Process, split if on camelCase.
        """

        return atUtils.camel_case_split(self.raw_name)

    @cached_property
    def docstring(self) -> str:
        """Lazy getter for the Processor's Process docstring

        Use the value in the Processor's :attr:`~Process._doc_` attribute, if it's empty, use class docstring
        :attr:`~Process.__doc__`. If it's also empty, fallback on :const:`~.atConstants.NO_DOCUMENTATION_AVAILABLE`

        Returns:
            The formatted docstring to be more readable and also display the path of the process.
        """

        docstring = self.process_class._doc_ or self.process_class.__doc__ or atConstants.NO_DOCUMENTATION_AVAILABLE
        docstring += '\n {0} '.format(self._process_str_path)

        doc_format = {}
        for match in re.finditer(r'\{(\w+)\}', docstring):
            match_str = match.group(1)
            doc_format[match_str] = self.process_class._doc_format_.get(match_str, '')

        return docstring.format(**doc_format)

    @cached_property
    def has_check_method(self) -> bool:
        """Lazy getter to know if the Processor's Process has a `check` method.

        Return:
            True if the Processor's Process has a `check` method, False otherwise.
        """

        return bool(self.overridden_methods.get(atConstants.CHECK, False))

    @cached_property
    def has_fix_method(self) -> bool:
        """Lazy getter to know if the Processor's Process has a `fix` method.

        Return:
            True if the Processor's Process has a `fix` method, False otherwise.
        """

        return bool(self.overridden_methods.get(atConstants.FIX, False))

    @cached_property
    def has_tool_method(self) -> bool:
        """Lazy getter to know if the Processor's Process has a `tool` method.

        Return:
            True if the Processor's Process has a `tool` method, False otherwise.
        """

        return bool(self.overridden_methods.get(atConstants.TOOL, False))

    @property
    def raw_name(self) -> str:
        """Getter fore the Processor's Process raw name.

        Return:
            The name for the Processor's Process, this will fallback to the class name if no `_name_` is set.
        """

        return self.process_class._name_ or self.process_class.__name__

    @property
    def is_enabled(self) -> bool:
        """Getter for the Processor's state.

        Return:
            `True` if the Processor is enabled, `False` Otherwise.
        """

        return self.__is_enabled

    @property
    def allows_check(self) -> bool:
        """Getter for whether the Processor exposes its check.

        Return:
            `True` if the Processor allows its check, `False` Otherwise.
        """

        return self.__allows_check

    @property
    def allows_fix(self) -> bool:
        """Getter for whether the Processor exposes its fix.

        Return:
            `True` if the Processor allows its fix, `False` Otherwise.
        """

        return self.__allows_fix

    @property
    def allows_tool(self) -> bool:
        """Getter for whether the Processor exposes its tool.

        Return:
            `True` if the Processor allows its tool, `False` Otherwise.
        """

        return self.__allows_tool

    @property
    def allows_parameters(self) -> bool:
        """Getter for whether the Processor exposes its Parameters to the tool.

        This is an advisory state, the same way :attr:`allows_check` is. A tool reads it to decide whether
        to show the Parameter panel to the end user, on top of each Parameter's own :class:`~ParameterPolicy`.
        It does not gate :meth:`set_parameter`, so a Process changing its own Parameters is never affected.

        Return:
            `True` if the Processor allows its Parameters to be shown, `False` Otherwise.
        """

        return self.__allows_parameters

    @property
    def in_ui(self) -> bool:
        """Getter for Processor's UI state.

        Return:
            `True` if the Processor can be run in UI mode, `False` Otherwise.
        """

        return self.__in_ui

    @property
    def in_batch(self) -> bool:
        """Getter for Processor's batch state.

        Return:
            `True` if the Processor can be run in batch mode, `False` Otherwise.
        """

        return self.__in_batch

    @property
    def is_non_blocking(self) -> bool:
        """Getter to know whether the Processor's Process FailStatus are blocking or not.

        Return:
            `False` if the Processor's Process FailStatus are blocking, `True` otherwise.
        """

        return self.__is_non_blocking

    @property
    def category(self) -> str:
        """Get the Processor's category.

        Return:
            The Processor's category name.
        """

        return self._category

    def get_arguments(self, method: str) -> Tuple[List[Any], Dict[str, Any]]:
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

    def get_settings(self, setting: str, default: Optional[Any] = None) -> Any:
        """Get the value for a specific setting if it exists.

        Parameters:
            setting: The setting to get from the Processor's settings.
            default: The default value to return if the Processor does not have any value for this setting.

        Return:
            The value for the requested setting or the default value if the requested setting does not exists.
        """

        return self._settings.get(setting, default)

    def get_lowest_fail_status(self) -> atStatus.FailStatus:
        """Get the lowest Fail status from all :class:`~Thread` from the Processor's Process.

        Return:
            The Lowest Fail Status of the Processor's Process across all it's :class:`~Thread`
        """

        return next(iter(sorted((thread._fail_status for thread in self._threads.values()), key=lambda x: x._priority)), None)

    def get_lowest_success_status(self) -> atStatus.SuccessStatus:
        """Get the lowest Success status from all :class:`~Thread` from the Processor's Process.

        Return:
            The Lowest Success Status of the Processor's Process across all it's :class:`~Thread`
        """

        return next(iter(sorted((thread._success_status for thread in self._threads.values()), key=lambda x: x._priority)), None)

    def check(self, links: bool = True, do_profiling: bool = False) -> Tuple[FeedbackContainer, ...]:
        """This is a wrapper for the Processor's Process `check`.

        This will automatically execute the `check` method with it's right parameters and profile the execution if requested.
        If the `links` attribute is set to `True`, the Processor's :class:`~Link` will also be executed..

        Parameters:
            links: Should the wrapper launch the connected links or not.
            do_profiling: Whether the `check` method must be run with the Processor's Profiler.

        Returns:
            All feedback containers for the Processor's Process post check.
        """

        if not self.has_check_method:
            return None

        args, kwargs = self.get_arguments(atConstants.CHECK)

        try:
            if do_profiling:
                self._process_profile.profile_method(self.process.check, *args, **kwargs)
            else:
                self.process.check(*args, **kwargs)
        except Exception as exception:
            raise
        finally:
            if links:
                self.run_links(Link.CHECK)

        return self.process.get_feedback_containers()

    def fix(self, links: bool = True, do_profiling: bool = False) -> Tuple[FeedbackContainer, ...]:
        """This is a wrapper for the Processor's Process `fix`.

        This will automatically execute the `fix` method with it's right parameters and profile the execution if requested.
        If the `links` attribute is set to `True`, the Processor's :class:`~Link` will also be executed..

        Parameters:
            links: Should the wrapper launch the connected links or not.
            do_profiling: Whether the `fix` method must be run with the Processor's Profiler.

        Returns:
            All feedback containers for the Processor's Process post fix.
        """

        if not self.has_fix_method:
            return None

        args, kwargs = self.get_arguments(atConstants.FIX)

        try:
            if do_profiling:
                self._process_profile.profile_method(self.process.fix, *args, **kwargs)
            else:
                self.process.fix(*args, **kwargs)
        except Exception:
            raise
        finally:
            if links:
                self.run_links(Link.FIX)

        return self.process.get_feedback_containers()

    def tool(self, links: bool = True, do_profiling: bool = False) -> Any:
        """This is a wrapper for the Processor's Process `tool`.

        This will automatically execute the `tool` method with it's right parameters and profile the execution if requested.
        If the `links` attribute is set to `True`, the Processor's :class:`~Link` will also be executed..

        Parameters:
            links: Should the wrapper launch the connected links or not.
            do_profiling: Whether the `tool` method must be run with the Processor's Profiler.

        Returns:
            The value returned by the Processor's Process `tool` method. Usually, `None`, but it could be the tool widget
            so it can be parented to the UI this Processor's is runt from.
        """

        if not self.has_tool_method:
            return None

        args, kwargs = self.get_arguments(atConstants.TOOL)

        try:
            if do_profiling:
                return_value = self._process_profile.profile_method(self.process.tool, *args, **kwargs)
            else:
                return_value = self.process.tool(*args, **kwargs)
        except Exception:
            raise
        finally:
            if links:
                self.run_links(Link.TOOL)

        return return_value

    def run_links(self, which: Link) -> None:
        """Execute the Processor's links for the given :class:`~Link`.

        Parameters:
            which: Which link we want to run.
        """

        for link in self.__links_data[which]:
            link()

    def get_parameter(self, parameter: Parameter) -> Any:
        """Get the value for the given :class:`~Parameter` object.

        Return:
            The current value for the given :class:`~Parameter` object.

        Notes:
            Python descriptors are defined on classes but hold different values per instance of the class that owns them, for
            this reason, we can't query the value from the :class:`~Parameter` itself. This method query the value as it knows both the
            class that own the :class:`~Parameter` and the instance for which we want the value.
        """

        return parameter.__get__(self.process, self.process_class)

    def set_parameter(self, parameter: Parameter, value: Any) -> Any:
        """Set the given value to the given :class:`~Parameter` object.

        Return:
            The current value for the given :class:`~Parameter` object after being set. This allows to know the exact value the attribute
            was set on after it does it's validation.

        Notes:
            Python descriptors are defined on classes but hold different values per instance of the class that owns them, for
            this reason, we can't set the value from the :class:`~Parameter` itself. This method query the value as it knows both the
            class that own the :class:`~Parameter` and the instance for which we want to set the value.

            This is the only externally mediated write path, so it is also the only place where a
            :class:`~ParameterPolicy` is enforced. A `LOCKED` Parameter cannot be set here, while a
            Process changing its own Parameters through the descriptor is never gated.

        Raise:
            AtParameterPolicyError: If the Parameter's effective policy has a `LOCKED` user override.
        """

        policy = parameter._policy_for(self.process)
        if policy.user_override is UserParameterOverride.LOCKED:
            raise atExceptions.AtParameterPolicyError(
                'Parameter {0!r} is locked and cannot be overridden.'.format(parameter.name)
            )

        parameter.__set__(self.process, value)
        return self.get_parameter(parameter)

    def get_effective_default(self, parameter: Parameter) -> Any:
        """Get the effective default for the given :class:`~Parameter` on this Processor.

        Where :attr:`Parameter.default` returns the author's original default, this returns the default
        actually in effect, including any Blueprint spec override installed on this Processor's Process
        instance.

        Parameters:
            parameter: The Parameter to get the effective default for.

        Return:
            The default value currently in effect for this Processor.
        """

        return parameter._spec_for(self.process).default

    def get_effective_policy(self, parameter: Parameter) -> 'ParameterPolicy':
        """Get the effective policy for the given :class:`~Parameter` on this Processor.

        Where :attr:`Parameter.policy` returns the author's class-level policy, this returns the policy
        actually in effect, including any Blueprint tightening installed on this Processor's Process
        instance. A UI can use it to render a `LOCKED` Parameter as read-only up front instead of letting
        an edit reach :meth:`set_parameter` only to be refused.

        Parameters:
            parameter: The Parameter to get the effective policy for.

        Return:
            The :class:`~ParameterPolicy` currently in effect for this Processor.
        """

        return parameter._policy_for(self.process)

    def reset_parameter(self, parameter: Parameter) -> Any:
        """Reset the given :class:`~Parameter` to its effective default on this Processor.

        Parameters:
            parameter: The Parameter to reset.

        Return:
            The Parameter's value after the reset, which is its effective default.
        """

        parameter.__delete__(self.process)
        return self.get_parameter(parameter)

    @property
    def overridden_parameters(self) -> Tuple[Parameter, ...]:
        """Getter for every :class:`~Parameter` whose current value differs from its effective default.

        This is purely informational and ignores the policy, so it includes Parameters that were changed
        freely. It is computed on each access so that it always reflects the current values.

        Return:
            The tuple of Parameters currently overridden on this Processor.
        """

        return tuple(
            parameter for parameter in self.parameters
            if self.get_parameter(parameter) != self.get_effective_default(parameter)
        )

    @property
    def nonconformant_parameters(self) -> Tuple[Parameter, ...]:
        """Getter for the overridden Parameters that count against conformance.

        This is the subset of :attr:`overridden_parameters` whose resolved user override level is not
        `FREE`. A Parameter changed freely is overridden but never non-conformant.

        Return:
            The tuple of overridden Parameters that currently taint conformance.
        """

        return tuple(
            parameter for parameter in self.overridden_parameters
            if parameter._policy_for(self.process).user_override is not UserParameterOverride.FREE
        )

    @property
    def is_conformant(self) -> bool:
        """Getter for the Processor's conformance state.

        The state is computed on each access, so resetting a Parameter back to its effective default makes
        the Processor conformant again.

        Return:
            True if no non-`FREE` Parameter currently differs from its effective default.
        """

        return not self.nonconformant_parameters

    def setup_tags(self) -> None:
        """Setup the tags used by this Processor to modify the it's behavior."""

        self.__is_enabled = True
        self.__allows_check = self.has_check_method
        self.__allows_fix = self.has_fix_method
        self.__allows_tool = self.has_tool_method
        self.__allows_parameters = True
        self.__is_non_blocking = False
        self.__in_batch = True
        self.__in_ui = True

        tags = self._tags

        if tags is None:
            return

        if tags & Tag.DISABLED:
            self.__is_enabled = False

        if tags & Tag.NO_CHECK:
            self.__allows_check = False

        if tags & Tag.NO_FIX:
            self.__allows_fix = False

        if tags & Tag.NO_TOOL:
            self.__allows_tool = False

        if tags & Tag.NO_PARAMETERS:
            self.__allows_parameters = False

        if tags & Tag.NON_BLOCKING:
            self.__is_non_blocking = True

        if tags & Tag.NO_BATCH:
            self.__in_batch = False

        if tags & Tag.NO_UI:
            self.__in_ui = False

    def resolve_links(self,
        linked_objects: List[Optional[Processor]],
        check: Link = atConstants.CHECK,
        fix: Link = atConstants.FIX,
        tool: Link = atConstants.TOOL) -> None:
        """Resolve the links between the given objects and the current Processor.

        This need to be called with an ordered list of :class:`~Processor` or None for :class:`~Processor` to skip.
        (e.g. to skip those that should not be linked because they dont have to be run in batch or ui.)

        Parameters:
            linked_objects: List of all objects used to resolve the current Processor's links. Objects to skip have to be replaced with `None`.
            check: Name of the method to use as check link on the given objects.
            fix: Name of the method to use as fix link on the given objects.
            tool: Name of the method to use as tool link on the given objects.
        """

        self.__links_data = links_data = {Link.CHECK: [], Link.FIX: [], Link.TOOL: []}

        if not linked_objects:
            return

        links = self._links
        if links is None:
            return

        for link in links:
            id_, _driver, _driven = link
            if linked_objects[id_] is None:
                continue

            driven = _driven
            driven = check if _driven is Link.CHECK else driven
            driven = fix if _driven is Link.FIX else driven
            driven = tool if _driven is Link.TOOL else driven

            links_data[_driver].append(getattr(linked_objects[id_], driven))

    def _override_status(self,
        process: Process,
        overrides: Mapping[str, Mapping[Union[Type[atStatus.FailStatus], Type[atStatus.SuccessStatus]], atStatus.Status]]) -> None:
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

        for thread_name, overrides_dict in overrides.items():
            if not hasattr(process, thread_name):
                raise RuntimeError('Process {0} have no thread named {1}.'.format(process._name_, thread_name))
            thread = getattr(process, thread_name)

            # Get the fail overrides for the current name
            status = overrides_dict.get(atStatus.FailStatus, None)
            if status is not None:
                if not isinstance(status, atStatus.FailStatus):
                    raise RuntimeError('Fail feedback status override for {0} "{1}" must be an instance or subclass of {2}'.format(
                        process._name_,
                        thread_name,
                        atStatus.FailStatus
                    ))
                thread.override_fail_status(status)

            # Get the success overrides for the current name
            status = overrides_dict.get(atStatus.SuccessStatus, None)
            if status is not None:
                if not isinstance(status, atStatus.SuccessStatus):
                    raise RuntimeError('Success feedback status override for {0} "{1}" must be an instance or subclass of {2}'.format(
                        process._name_,
                        thread_name,
                        atStatus.SuccessStatus
                    ))
                thread.override_success_status(status)

    def set_progress_bar(self, progress_bar: QtWidgets.QProgressBar) -> None:
        """Set the ProgressBar object in the UI to be used by the Processor's Process.

        Made to be called in the ui this method allow to give access to the progress bar in the Processor's Process to
        give feedback on the execution progress while performing `check` and/or `fix`.

        Parameters:
            progress_bar: ProgressBar object object to connect to the process to display check and fix progression.
        """

        self.process.set_progress_bar(progress_bar)

    def get_data(self, key: str, default: Optional[Any] = None) -> Any:
        """Get the Processor's Data for the given key or default value if key does not exists.

        Parameters:
            key: The key to get the data from.
            default: The default value to return if the key does not exists.

        Return:
            The value at the given key in the Processor's data if the key exists. Else the default value is returned.
        """

        return self._data.get(key, default)

    def set_data(self, key: str, value: Any) -> None:
        """Set the Processor's Data for the given key

        Parameters:
            key: The key to set the data for.
            value: The value to store as data for the given key.
        """

        self._data[key] = value

    def interrupt(self):
        """Register user interruption for the Processor's Process"""

        self.process._register_interruption()


class UserParameterOverride(enum.IntEnum):
    """The level of freedom an end user has to override a :class:`~Parameter` value at runtime.

    The members are ordered so that a :class:`~ParameterPolicy` can only tighten (lower) the level and
    never loosen (raise) it. `LOCKED` is the most restrictive level and `FREE` is the least restrictive.
    """

    LOCKED = 0
    """The end user cannot change the value at all."""

    TAINTING = 1
    """The end user can change the value, but changing it away from the effective default taints the
    conformance gate (see :attr:`Processor.is_conformant`)."""

    FREE = 2
    """The end user can change the value freely and it never taints conformance."""


@dataclass(frozen=True)
class ParameterPolicy:
    """Governance for a :class:`~Parameter`, kept separate from its :class:`~ParameterSpec`.

    Where a :class:`~ParameterSpec` decides which values are acceptable, a ParameterPolicy decides who is
    allowed to change the Parameter and whether changing it should count against pipeline trust. A value
    that fails the conformance gate is still a perfectly valid value, the two concerns do not overlap.

    See `docs/adr/0001-parameter-policy.md` for the full rationale.
    """

    blueprint_configurable: bool = True
    """Whether a :class:`~Blueprint` is allowed to override this Parameter's spec (its default and constraints)."""

    user_override: UserParameterOverride = UserParameterOverride.TAINTING
    """How freely an end user can change the value, and what changing it costs in conformance."""

    @property
    def immutable(self) -> bool:
        """Whether neither a Blueprint nor an end user can change this Parameter.

        This value is always derived from the two axes and never stored, so it cannot drift out of sync
        with them.

        Return:
            True if the Parameter is not Blueprint configurable and its user override level is `LOCKED`.
        """

        return not self.blueprint_configurable and self.user_override is UserParameterOverride.LOCKED

    def tightened_by(self, **overrides: Any) -> 'ParameterPolicy':
        """Resolve a Blueprint's requested policy against this policy used as a ceiling.

        A Blueprint can only tighten the author's declared policy, never loosen it. When an override would
        grant more freedom than this policy allows, an :class:`~atExceptions.AtParameterPolicyError` is
        raised instead of silently clamping the value. Raising avoids giving a Blueprint author false
        confidence that a loosening they asked for actually took effect.
        Only the axes present in `overrides` are looked at, so a Blueprint can tighten a single axis
        without having to restate the other one.

        Parameters:
            overrides: Any of `blueprint_configurable` or `user_override` to tighten.

        Return:
            A new ParameterPolicy with the requested axes tightened.

        Raise:
            AtParameterPolicyError: If an override would loosen this policy.
        """

        blueprint_configurable = overrides.get('blueprint_configurable', self.blueprint_configurable)
        user_override = overrides.get('user_override', self.user_override)

        if blueprint_configurable and not self.blueprint_configurable:
            raise atExceptions.AtParameterPolicyError(
                'Cannot make a Parameter Blueprint-configurable when its author declared it is not.'
            )
        if user_override > self.user_override:
            raise atExceptions.AtParameterPolicyError(
                'Cannot loosen a Parameter\'s user override policy from {0!r} to {1!r}; '
                'a Blueprint may only tighten an author\'s declared policy.'.format(self.user_override, user_override)
            )

        return ParameterPolicy(blueprint_configurable=blueprint_configurable, user_override=user_override)


@dataclass(frozen=True)
class ParameterSpec:
    """The swappable core of a :class:`~Parameter`.

    A ParameterSpec holds everything that used to be baked into a Parameter subclass at class definition
    time: the `type_cast` and `validate` callables, the `default` value and the raw `constraints`. It is
    a frozen value object, so a Blueprint override produces a new spec through :meth:`with_overrides` and
    installs it on a Process instance without ever mutating the class level spec.
    """

    type_name: str
    """The registry key the spec was built from, for example `'int'`."""

    type_cast: Callable[[Any], Any]
    """The callable that coerces an input value to this Parameter's type."""

    validate: Callable[[Any], bool]
    """The callable that returns whether a cast value is acceptable."""

    default: Any
    """The default value in effect for this spec."""

    constraints: Mapping[str, Any] = field(default_factory=dict)
    """The raw constraint values, for example `{'minimum': 0, 'maximum': 10}`.

    This exists so that a UI or a tool can read the min, max or validation list without having to reverse
    engineer a closure."""

    kwargs: Mapping[str, Any] = field(default_factory=dict)
    """The original builder keyword arguments.

    They are kept so that :meth:`with_overrides` can run the same builder again, and therefore the same
    validation, instead of patching fields by hand and letting an override bypass validation."""

    def with_overrides(self, **overrides: Any) -> 'ParameterSpec':
        """Build a new :class:`~ParameterSpec` from this spec's builder with the given overrides applied.

        The overrides are merged over the original builder keyword arguments and the same
        :class:`~ParameterFactory` builder is run again, so the result is validated exactly like the
        original spec was.

        Parameters:
            overrides: The builder keyword arguments to override, for example `default=10`.

        Return:
            A new ParameterSpec with the overrides applied.
        """

        return ParameterFactory.build(self.type_name, **{**self.kwargs, **overrides})


class ParameterFactory:
    """Registry that maps a Parameter type name to a builder returning a :class:`~ParameterSpec`.

    This takes over the guarantee that every Parameter type knows how to cast and validate its values. A
    builder that does not return a well formed :class:`~ParameterSpec` fails as soon as it is used,
    instead of failing silently later at runtime.
    """

    _registry: Dict[str, Callable[..., ParameterSpec]] = {}

    @classmethod
    def register(cls, name: str, builder: Callable[..., ParameterSpec]) -> None:
        """Register a builder function under a type name.

        Parameters:
            name: The registry key to register the builder under, for example `'int'`.
            builder: A callable that returns a :class:`~ParameterSpec`.
        """

        cls._registry[name] = builder

    @classmethod
    def build(cls, name: str, **kwargs: Any) -> ParameterSpec:
        """Build a :class:`~ParameterSpec` from a registered builder.

        Parameters:
            name: The registry key of the Parameter type to build.
            kwargs: The keyword arguments forwarded to the registered builder.

        Return:
            The :class:`~ParameterSpec` returned by the builder.

        Raise:
            AtParameterTypeError: If no builder is registered under the given name.
        """

        if name not in cls._registry:
            raise atExceptions.AtParameterTypeError('No Parameter type registered as "{0}".'.format(name))
        return cls._registry[name](**kwargs)


class Parameter:
    """Athena Parameter descriptor that represent a variable value to be used in an Athena :class:`~Process`.

    The Parameter is a python descriptor object that must be defined at the class level. It is a single
    concrete class that handles the descriptor protocol and the per instance storage, while the swappable
    part (casting, validation, default and constraints) lives in a :class:`~ParameterSpec` and the
    governance lives in a :class:`~ParameterPolicy`.

    Both the active spec and the current value are resolved the same way, an instance level override
    first and the class level value as a fallback. This symmetry is what makes a reset to default with
    `del` return the Blueprint's overridden default instead of the author's original one.
    """

    def __init__(self, spec: ParameterSpec, policy: Optional['ParameterPolicy'] = None) -> None:
        """Initialize a new instance of Parameter.

        Parameters:
            spec: The class level :class:`~ParameterSpec` used as fallback for casting, validation,
                default and constraints.
            policy: The class level :class:`~ParameterPolicy` used as fallback. When not provided, a fully
                open policy with a `TAINTING` user override is used.
        """

        self._spec = spec
        self._policy = policy or ParameterPolicy()
        self._value_attr = ''
        self._spec_attr = ''
        self._policy_attr = ''

    def __set_name__(self, owner: Type[Process], name: str) -> None:
        """Compute the per instance attribute names used to store this Parameter's state.

        The owner class name is included in the attribute names so that two unrelated Parameters that
        share the same name across a mixin or a multiple inheritance hierarchy cannot collide on the same
        backing attribute.

        Parameters:
            owner: Class object that own the Parameter.
            name: Name of the parameter (name of the parameter attribute on the class).
        """

        self._value_attr = '_{0}__{1}'.format(owner.__name__, name)
        self._spec_attr = '_{0}__{1}_spec'.format(owner.__name__, name)
        self._policy_attr = '_{0}__{1}_policy'.format(owner.__name__, name)

    def _spec_for(self, instance: Process) -> ParameterSpec:
        """Resolve the effective :class:`~ParameterSpec` for the given instance.

        Parameters:
            instance: The instance to resolve the spec for.

        Return:
            The instance level spec override if one was installed, else the class level spec.
        """

        return getattr(instance, self._spec_attr, self._spec)

    def _policy_for(self, instance: Process) -> 'ParameterPolicy':
        """Resolve the effective :class:`~ParameterPolicy` for the given instance.

        Parameters:
            instance: The instance to resolve the policy for.

        Return:
            The instance level policy override if one was installed, else the class level policy.
        """

        return getattr(instance, self._policy_attr, self._policy)

    def __get__(self, instance: Optional[Process], owner: Type[Process]) -> Any:
        """Descriptor getter for the Parameter value.

        Get the unique Parameter value for the given instance of the owner class. If no instance of the
        owner class is passed, the Parameter instance is returned instead to allow internal manipulation.
        When the value was never set on the instance, the effective spec's default is returned.

        Parameters:
            instance: The instance for which we want to get the Parameter value.
            owner: The class that owns the Parameter object.

        Return:
            The Parameter's current value for the given instance, or the Parameter itself when no instance
            is passed.
        """

        if instance is None:
            return self
        if not hasattr(instance, self._value_attr):
            return self._spec_for(instance).default
        return getattr(instance, self._value_attr)

    def __set__(self, instance: Process, value: Any) -> None:
        """Descriptor setter for the Parameter value.

        Cast the given value with the effective spec, validate it and, when it is valid, set it on the
        given instance. An invalid value raises instead of being silently dropped.

        This setter is deliberately unaware of the :class:`~ParameterPolicy`. It is the mechanism a
        Process uses to change its own state, for example `self.iterations = x` inside `check`, which must
        never be gated. The policy is enforced in a single place, the :meth:`Processor.set_parameter`
        boundary, which is the only externally mediated write path in this framework. See
        `docs/adr/0001-parameter-policy.md`.

        Parameters:
            instance: The instance for which we want to set the Parameter value.
            value: The new value to set the Parameter's value to.

        Raise:
            AtParameterValidationError: If the cast value does not pass validation.
        """

        spec = self._spec_for(instance)
        cast_value = spec.type_cast(value)
        if not spec.validate(cast_value):
            raise atExceptions.AtParameterValidationError(
                'Value {0!r} is not valid for parameter (type {1!r}).'.format(value, spec.type_name)
            )
        setattr(instance, self._value_attr, cast_value)

    def __delete__(self, instance: Process) -> None:
        """Descriptor deleter for the Parameter.

        When deleted, reset the Parameter to its effective default by dropping the per instance value, so
        that the next read falls back to the effective spec's default, including a Blueprint override when
        one was installed on the instance.

        Parameters:
            instance: The instance for which we want reset the Parameter value to default.
        """

        if hasattr(instance, self._value_attr):
            delattr(instance, self._value_attr)

    @property
    def name(self) -> str:
        """Getter for the Parameter's nice name.

        Return:
            The Parameter's attribute name, without the mangling prefix.
        """

        return self._value_attr.rpartition('__')[2]

    @property
    def spec(self) -> ParameterSpec:
        """Getter for the Parameter's class level :class:`~ParameterSpec`.

        This is the author's spec and is not aware of any instance or Blueprint override. Use
        `parameter._spec_for(process)`, or go through the :class:`~Processor`, to get the spec actually in
        effect for a given instance.

        Return:
            The Parameter's class level ParameterSpec.
        """

        return self._spec

    @property
    def default(self) -> Any:
        """Getter for the Parameter's default value.

        This is the author's class level default and is not aware of any instance or Blueprint override.
        Use :meth:`Processor.get_effective_default` to get the default actually in effect for a given
        Processor.

        Return:
            The Parameter's class level default value.
        """

        return self._spec.default

    @property
    def policy(self) -> 'ParameterPolicy':
        """Getter for the Parameter's class level :class:`~ParameterPolicy`.

        This is the author's policy and is not aware of any Blueprint tightening. Use
        `parameter._policy_for(processor.process)`, or go through the :class:`~Processor`, to get the
        policy actually in effect.

        Return:
            The Parameter's class level ParameterPolicy.
        """

        return self._policy


def _build_bool(default: bool) -> ParameterSpec:
    """Build a :class:`~ParameterSpec` for a boolean value.

    Parameters:
        default: The default boolean value for the Parameter.

    Return:
        The boolean ParameterSpec.

    Raise:
        AtParameterValidationError: If the default value is not a boolean.
    """

    if not isinstance(default, bool):
        raise atExceptions.AtParameterValidationError(
            'Value {0!r} does not conform to bool validation.'.format(default)
        )

    # The accepted truthy string forms. `'ok'` is documented as accepted and is now part of the tuple.
    truthy = (True, 'True', 'true', 'Yes', 'yes', 'ok', 1, '1')

    def type_cast(value: Any) -> bool:
        return value in truthy

    def validate(value: Any) -> bool:
        return isinstance(value, bool)

    return ParameterSpec(
        type_name='bool',
        type_cast=type_cast,
        validate=validate,
        default=default,
        constraints={},
        kwargs={'default': default},
    )


def _build_number(
    type_: Type,
    type_name: str,
    default: numbers.Number,
    minimum: Optional[numbers.Number],
    maximum: Optional[numbers.Number],
    keep_in_range: bool,
) -> ParameterSpec:
    """Build a :class:`~ParameterSpec` for a numeric value, shared by the `int` and `float` types.

    The constraints are checked when the spec is built. The minimum must not be greater than the maximum
    and the default must satisfy the range, otherwise the spec cannot be built. This prevents a Parameter
    from being declared with an invalid or unreachable default.

    Parameters:
        type_: The concrete numeric type to cast values to, `int` or `float`.
        type_name: The registry key for the built spec.
        default: The default numeric value for the Parameter.
        minimum: The minimum accepted value, or None for no lower bound.
        maximum: The maximum accepted value, or None for no upper bound.
        keep_in_range: Whether values below minimum or above maximum are forced back to those bounds.

    Return:
        The numeric ParameterSpec.

    Raise:
        AtParameterValidationError: If the default is not numeric, the range is inverted or the default is
            outside the range.
    """

    if not isinstance(default, numbers.Number):
        raise atExceptions.AtParameterValidationError(
            'Value {0!r} does not conform to {1} validation.'.format(default, type_name)
        )

    if minimum is not None and maximum is not None and minimum > maximum:
        raise atExceptions.AtParameterValidationError(
            'Invalid {0} parameter range: minimum {1!r} is greater than maximum {2!r}.'.format(type_name, minimum, maximum)
        )

    if minimum is not None and default < minimum:
        raise atExceptions.AtParameterValidationError(
            'Default {0!r} is below the minimum {1!r} for {2} parameter.'.format(default, minimum, type_name)
        )
    if maximum is not None and default > maximum:
        raise atExceptions.AtParameterValidationError(
            'Default {0!r} is above the maximum {1!r} for {2} parameter.'.format(default, maximum, type_name)
        )

    def type_cast(value: Any) -> numbers.Number:
        value = type_(value)
        if keep_in_range:
            if minimum is not None and value < minimum:
                return minimum
            elif maximum is not None and value > maximum:
                return maximum
        return value

    def validate(value: Any) -> bool:
        if minimum is not None and value < minimum:
            return False
        if maximum is not None and value > maximum:
            return False
        return True

    return ParameterSpec(
        type_name=type_name,
        type_cast=type_cast,
        validate=validate,
        default=default,
        constraints={'minimum': minimum, 'maximum': maximum, 'keep_in_range': keep_in_range},
        kwargs={'default': default, 'minimum': minimum, 'maximum': maximum, 'keep_in_range': keep_in_range},
    )


def _build_int(
    default: int,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
    keep_in_range: bool = False,
) -> ParameterSpec:
    """Build a :class:`~ParameterSpec` for an integer value. See :func:`_build_number`."""

    return _build_number(int, 'int', default, minimum, maximum, keep_in_range)


def _build_float(
    default: float,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    keep_in_range: bool = False,
) -> ParameterSpec:
    """Build a :class:`~ParameterSpec` for a floating point value. See :func:`_build_number`."""

    return _build_number(float, 'float', default, minimum, maximum, keep_in_range)


def _build_string(
    default: str,
    validation: Optional[Sequence[str]] = None,
    case_sensitive: bool = True,
) -> ParameterSpec:
    """Build a :class:`~ParameterSpec` for a string value.

    Unlike the previous StringParameter, the cast does not lowercase the value. Lowercasing before
    validation made `case_sensitive=True` unable to ever match, so case is now handled entirely in
    validation and the cast simply converts the value with `str`.

    Parameters:
        default: The default string value for the Parameter.
        validation: The list of accepted strings, or None to accept any string.
        case_sensitive: Whether the strings in `validation` are matched with case sensitivity.

    Return:
        The string ParameterSpec.

    Raise:
        AtParameterValidationError: If the default is not a string or does not pass the validation list.
    """

    if not isinstance(default, str):
        raise atExceptions.AtParameterValidationError(
            'Value {0!r} does not conform to string validation.'.format(default)
        )

    def type_cast(value: Any) -> str:
        return str(value)

    if validation is None:
        def validate(value: Any) -> bool:
            return isinstance(value, str)
    elif case_sensitive:
        accepted = tuple(validation)

        def validate(value: Any) -> bool:
            return value in accepted
    else:
        accepted_lower = {item.lower() for item in validation}

        def validate(value: Any) -> bool:
            return value.lower() in accepted_lower

    if not validate(default):
        raise atExceptions.AtParameterValidationError(
            'Default {0!r} does not conform to the string validation {1!r}.'.format(default, validation)
        )

    return ParameterSpec(
        type_name='string',
        type_cast=type_cast,
        validate=validate,
        default=default,
        constraints={'validation': None if validation is None else tuple(validation), 'case_sensitive': case_sensitive},
        kwargs={'default': default, 'validation': validation, 'case_sensitive': case_sensitive},
    )


ParameterFactory.register('bool', _build_bool)
ParameterFactory.register('int', _build_int)
ParameterFactory.register('float', _build_float)
ParameterFactory.register('string', _build_string)


def BoolParameter(default: bool, policy: Optional[ParameterPolicy] = None) -> Parameter:
    """Create a boolean :class:`~Parameter`.

    Parameters:
        default: The default boolean value for the Parameter.
        policy: An optional :class:`~ParameterPolicy` to govern the Parameter.

    Return:
        A Parameter backed by a boolean :class:`~ParameterSpec`.
    """

    return Parameter(ParameterFactory.build('bool', default=default), policy=policy)


def IntParameter(
    default: int,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
    keep_in_range: bool = False,
    policy: Optional[ParameterPolicy] = None,
) -> Parameter:
    """Create an integer :class:`~Parameter`.

    Parameters:
        default: The default integer value for the Parameter.
        minimum: The minimum accepted value, or None for no lower bound.
        maximum: The maximum accepted value, or None for no upper bound.
        keep_in_range: Whether values below minimum or above maximum are forced back to those bounds.
        policy: An optional :class:`~ParameterPolicy` to govern the Parameter.

    Return:
        A Parameter backed by an integer :class:`~ParameterSpec`.
    """

    return Parameter(
        ParameterFactory.build('int', default=default, minimum=minimum, maximum=maximum, keep_in_range=keep_in_range),
        policy=policy,
    )


def FloatParameter(
    default: float,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    keep_in_range: bool = False,
    policy: Optional[ParameterPolicy] = None,
) -> Parameter:
    """Create a floating point :class:`~Parameter`.

    Parameters:
        default: The default floating point value for the Parameter.
        minimum: The minimum accepted value, or None for no lower bound.
        maximum: The maximum accepted value, or None for no upper bound.
        keep_in_range: Whether values below minimum or above maximum are forced back to those bounds.
        policy: An optional :class:`~ParameterPolicy` to govern the Parameter.

    Return:
        A Parameter backed by a floating point :class:`~ParameterSpec`.
    """

    return Parameter(
        ParameterFactory.build('float', default=default, minimum=minimum, maximum=maximum, keep_in_range=keep_in_range),
        policy=policy,
    )


def StringParameter(
    default: str,
    validation: Optional[Sequence[str]] = None,
    case_sensitive: bool = True,
    policy: Optional[ParameterPolicy] = None,
) -> Parameter:
    """Create a string :class:`~Parameter`.

    Parameters:
        default: The default string value for the Parameter.
        validation: The list of accepted strings, or None to accept any string.
        case_sensitive: Whether the strings in `validation` are matched with case sensitivity.
        policy: An optional :class:`~ParameterPolicy` to govern the Parameter.

    Return:
        A Parameter backed by a string :class:`~ParameterSpec`.
    """

    return Parameter(
        ParameterFactory.build('string', default=default, validation=validation, case_sensitive=case_sensitive),
        policy=policy,
    )


if __name__ == "__main__":
    session = AtSession()

    for each in range(20):
        print(each)

    print(session.dev)
