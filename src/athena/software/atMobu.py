"""Autodesk MotionBuilder implementation of Athena's software specific features.

Feedbacks handled by this module can hold any :class:`pyfbsdk.FBComponent` (models, materials, constraints,
characters, ...) or a component long name as a `str` (`namespace:name`, or just `name` when there's no namespace).

Notes:
    MotionBuilder names are not unique, so a long name resolves to every component that has this exact long name.
    Components that have been deleted from the scene since the feedback was created are skipped when selecting, and
    displayed as `<deleted ClassName>`.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator, List, Type, Union

import contextlib
from dataclasses import dataclass

from athena import atCore

import pyfbsdk
from unbind import UnboundWrapperError


_UNBOUND_SUFFIX = '_Unbound'


@contextlib.contextmanager
def _batched_model_changes() -> Iterator[None]:
    """Batch selection changes so MotionBuilder only fires its model change callbacks once.

    `FBBeginChangeAllModels` must always be closed by `FBEndChangeAllModels`, or MotionBuilder stops reacting to
    model changes, hence the `finally`.
    """

    pyfbsdk.FBBeginChangeAllModels()
    try:
        yield
    finally:
        pyfbsdk.FBEndChangeAllModels()


def _is_bound(component: pyfbsdk.FBComponent) -> bool:
    """Check whether the given wrapper still points to a live MotionBuilder object.

    Parameters:
        component: The wrapper to check.

    Return:
        `False` if the MotionBuilder object has been destroyed, `True` otherwise.
    """

    # An unbound wrapper still passes `isinstance` checks and is truthy, only accessing it reveals its state.
    try:
        component.LongName
    except UnboundWrapperError:
        return False

    return True


def _find_components_by_long_name(long_name: str) -> List[pyfbsdk.FBComponent]:
    """Find all scene components with exactly the given long name.

    Parameters:
        long_name: The long name (`namespace:name`) of the components to find.

    Return:
        All components whose long name is exactly `long_name`.
    """

    matches = pyfbsdk.FBComponentList()
    pyfbsdk.FBFindObjectsByName(long_name, matches, True, False)

    # `FBFindObjectsByName` treats `*` as a wildcard, only keep exact matches.
    return [component for component in matches if component.LongName == long_name]


def _resolve_components(
    objects: Union[str, pyfbsdk.FBComponent, Iterable[Union[str, pyfbsdk.FBComponent]]]
) -> List[pyfbsdk.FBComponent]:
    """Resolve the given objects to live MotionBuilder components.

    Parameters:
        objects: A component, a component long name, or an iterable of any of them.

    Return:
        The live components for all the given objects. Deleted components and names that match nothing are skipped.

    Raises:
        TypeError: If one of the objects is neither a `str` nor a :class:`pyfbsdk.FBComponent`. Nothing is resolved
            in this case, so callers can rely on it to leave the scene untouched.
    """

    # A `str` is iterable too, without this a single name would be resolved character by character.
    if isinstance(objects, (str, pyfbsdk.FBComponent)):
        objects = (objects,)

    components = []
    for object_ in objects:
        if isinstance(object_, str):
            components.extend(_find_components_by_long_name(object_))
        elif isinstance(object_, pyfbsdk.FBComponent):
            if _is_bound(object_):
                components.append(object_)
        else:
            raise TypeError(
                'Cannot resolve {0!r} of type `{1}` to a MotionBuilder component: expected a `pyfbsdk.FBComponent` '
                'or the long name (`namespace:name`) of one as a `str`.'.format(object_, type(object_).__name__)
            )

    return components


def _clear_selection() -> None:
    """Deselect every component in the scene, not only models."""

    for component in pyfbsdk.FBSystem().Scene.Components:
        if component.Selected:
            component.Selected = False


def select(
    to_select: Union[str, pyfbsdk.FBComponent, Iterable[Union[str, pyfbsdk.FBComponent]]],
    replace: bool = True) -> None:
    """Allow software selection in MotionBuilder.

    Parameters:
        to_select: The component(s) to select, as :class:`pyfbsdk.FBComponent` or long names. A single component or
            name can be given directly, without wrapping it in an iterable.
        replace: Whether the given components must replace the current selection or be added to it.

    Raises:
        TypeError: If an object is neither a `str` nor a :class:`pyfbsdk.FBComponent`. The selection is left
            untouched in this case.

    Notes:
        Deleted components and names that match nothing are skipped. With `replace`, the current selection is
        still cleared even if nothing could be resolved.
    """

    components = _resolve_components(to_select)

    with _batched_model_changes():
        if replace:
            _clear_selection()

        for component in components:
            component.Selected = True


def deselect(to_deselect: Union[str, pyfbsdk.FBComponent, Iterable[Union[str, pyfbsdk.FBComponent]]]) -> None:
    """Allow software deselection in MotionBuilder.

    Parameters:
        to_deselect: The component(s) to deselect, as :class:`pyfbsdk.FBComponent` or long names. A single component
            or name can be given directly, without wrapping it in an iterable.

    Raises:
        TypeError: If an object is neither a `str` nor a :class:`pyfbsdk.FBComponent`. The selection is left
            untouched in this case.

    Notes:
        Deleted components and names that match nothing are skipped.
    """

    components = _resolve_components(to_deselect)

    with _batched_model_changes():
        for component in components:
            component.Selected = False


def get_display(object_: Any) -> str:
    """Get a clean display name for a MotionBuilder object.

    Parameters:
        object_: The object to get a displayable name for. For a :class:`pyfbsdk.FBComponent`, its long name is used
            since short names are not unique in MotionBuilder. Anything else is converted to `str`.

    Return:
        A clean displayable name for the given object. A deleted component is displayed as `<deleted ClassName>`.
    """

    if not isinstance(object_, pyfbsdk.FBComponent):
        return str(object_)

    try:
        return object_.LongName
    except UnboundWrapperError:
        # Once unbound, the wrapper's class is renamed from `ClassName` to `ClassName_Unbound`.
        class_name = type(object_).__name__
        if class_name.endswith(_UNBOUND_SUFFIX):
            class_name = class_name[:-len(_UNBOUND_SUFFIX)]

        return '<deleted {0}>'.format(class_name)


def _iter_selectable_feedback(feedbacks: Iterable[atCore.ProtoFeedback]) -> Iterator[Any]:
    """Yield the data of every feedback that would be selected by the default selection cascade.

    A selectable feedback yields its own data, a non-selectable one is a group and yields its children's data instead.

    Parameters:
        feedbacks: The feedbacks to walk through.

    Yields:
        The data of each feedback to select or deselect.
    """

    for feedback in feedbacks:
        if feedback.selectable:
            yield feedback.feedback
        else:
            yield from _iter_selectable_feedback(feedback.children)


@dataclass(frozen=True)
class MobuFeedbackContainer(atCore.FeedbackContainer):
    """MotionBuilder specific :class:`~FeedbackContainer` that implement optimized selection and deselection.

    While it's not necessary to use this subtype of :class:`~FeedbackContainer` for a MotionBuilder Process, it
    selects or deselects all its feedbacks in one single batched operation instead of one by one. This matters a lot
    in MotionBuilder where each selection change triggers scene callbacks.

    Notes:
        Non-selectable feedbacks are treated as groups, like in the default selection cascade: their children are
        selected instead. Custom `select`/`deselect` implementations on the children are bypassed.
    """

    def select(self, replace: bool = True) -> bool:
        """Implement MotionBuilder's in-scene selection of the current :class:`~MobuFeedbackContainer`.

        If the :class:`~MobuFeedbackContainer` is not selectable, it will be skipped.

        Parameters:
            replace: Whether or not the new elements must replace the current selection.

        Return:
            The state for the replace boolean. This allow to know if a chained selection must replace again or not.
            Usually, it must replace for the first item, and then add, if not, we would end up with only the latest
            element.
        """

        if not self.selectable:
            return replace

        to_select = tuple(_iter_selectable_feedback(self.children))
        if to_select:
            select(to_select, replace=replace)
            replace = False

        return replace

    def deselect(self) -> None:
        """Implement MotionBuilder's in-scene deselection of the current :class:`~MobuFeedbackContainer`.

        If the :class:`~MobuFeedbackContainer` is not selectable, it will be skipped.
        """

        if not self.selectable:
            return

        to_deselect = tuple(_iter_selectable_feedback(self.children))
        if to_deselect:
            deselect(to_deselect)


@dataclass(frozen=True)
class MobuFeedback(atCore.Feedback):
    """Represent a single MotionBuilder Feedback, this allows for better display and selection/deselection behavior.

    Using a MobuFeedback is not mandatory when doing a MotionBuilder :class:`~Process`, and it can be used alongside
    normal :class:`~Feedback`. Its data can be a :class:`pyfbsdk.FBComponent` or a component long name, it allows
    for in-scene selection and returns a clean display, even when the component has been deleted.
    """

    def __str__(self) -> str:
        """Clean display name for the feedback.

        Return:
            A readable display name for the :obj:`~MobuFeedback.feedback` attribute.
        """

        return get_display(self.feedback)

    def select(self, replace: bool = True) -> bool:
        """Implement MotionBuilder's in-scene selection of the current :class:`~MobuFeedback`.

        If the :class:`~MobuFeedback` is selectable, it will be selected in the scene.

        Parameters:
            replace: Whether or not the new element must replace the current selection.

        Return:
            The result of the parent's class implementation.
        """

        if self.selectable:
            select(self.feedback, replace=replace)
            replace = False

        return super().select(replace=replace)

    def deselect(self) -> None:
        """Implement MotionBuilder's in-scene deselection of the current :class:`~MobuFeedback`.

        If the :class:`~MobuFeedback` is selectable, it will be deselected in the scene.
        """

        super().deselect()

        if self.selectable:
            deselect(self.feedback)


class MobuProcess(atCore.Process):
    """A custom Process implementation to be used in MotionBuilder which define the best :class:`~FeedbackContainer`.

    It's not mandatory to create a MotionBuilder Process using this :class:`~Process` subclass, the only thing it
    does is replacing the :class:`~Process` default :class:`~FeedbackContainer` with a
    :class:`~MobuFeedbackContainer` which implement a better selection behavior.
    By using this, users won't have to figure out which :class:`~FeedbackContainer` to use and implement it on all
    their :class:`~Process`.
    """

    FEEDBACK_CONTAINER_CLASS: Type[MobuFeedbackContainer] = MobuFeedbackContainer
