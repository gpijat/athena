from __future__ import annotations

from typing import Type, Union, Iterable

import sys
from dataclasses import dataclass

from athena import atCore

from maya import cmds
from maya.api import OpenMaya, OpenMayaUI


class PauseViewport(object):
    """Maya specific context manager to pause viewport execution during a processing."""

    def __enter__(self) -> None:
        """Pause the viewport"""

        if not cmds.ogs(query=True, pause=True):
            cmds.ogs(pause=True)
        cmds.refresh(suspend=True)

        # self._nodes = {}
        # for node in cmds.ls():
        #   self._nodes[cmds.ls(node, uuid=True)[0]] = (
        #       cmds.getAttr(node+'.frozen'),
        #       cmds.getAttr(node+'.nodeState') 
        #   )
        #   cmds.setAttr(node+'.frozen', True)
        #   cmds.setAttr(node+'.nodeState', 1)
        # cmds.dgdirty(cmds.ls())

    def __exit__(self, *_) -> None:
        """Restore the viewport and force a scene refresh"""
        
        # for node, (frozen, nodeState) in self._nodes.items():
        #   node = next(iter(cmds.ls(node, long=True)), None)
        #   if node is None:  # The node have been deleted.
        #       continue
        #   cmds.setAttr(node+'.frozen', frozen)
        #   cmds.setAttr(node+'.nodeState', nodeState)
        # cmds.dgdirty(cmds.ls())

        # Toggle Viewport 2.0 pause if it's stopped. (a.k.a: Enable it back.)
        if cmds.ogs(query=True, pause=True):
            cmds.ogs(pause=True)
        cmds.refresh(suspend=False)

        # -- Restart
        cmds.dgdirty(cmds.ls())
        cmds.ogs(reset=True)
        cmds.refresh()


def select_in_maya(
    to_select: Iterable[Union[str, OpenMaya.MObject, OpenMaya.MDagPath, OpenMaya.MFnDependencyNode], ...], 
    mode: str ='add', 
    replace: bool = True) -> None:
    """Allow software selection in Maya for different Maya types.

    Parameters:
        to_select: The object(s) to select in Autodesk Maya.
        mode: The selection mode to use. (`add` or `remove`)
        replace: Define whether the function should `replace` or `add` to the current selection.
    
    Notes:
        This function require an Iterable as input, even if there's only one item to select.
        The supported object types are:

            * str
            * MObject
            * MDagPath
            * MFnDependencyNodes (= All subtypes as well)
    """

    selection_list = OpenMaya.MSelectionList()

    for each in to_select:
        # For `str`, `maya.api.OpenMaya.MDagPath` and `maya.api.OpenMaya.MObject`:
        try: selection_list.add(each)
        except: pass

        # For `maya.api.OpenMaya.MFn*`:
        try: selection_list.add(each.object())
        except: pass

    mode = OpenMaya.MGlobal.kAddToList if mode == 'add' else OpenMaya.MGlobal.kRemoveFromList
    if replace:
        mode = OpenMaya.MGlobal.kReplaceList
    
    OpenMaya.MGlobal.setActiveSelectionList(selection_list, mode)


def get_display(object_: Union[str, OpenMaya.MObject, OpenMaya.MDagPath, OpenMaya.MFnDependencyNode]) -> str:
    """Get a clean display name for a Maya object.

    Parameters:
        object_: The object for which we want to get a clean name as a string. If it's already a string, the function 
          will just return it. If it's a Maya api type, it will do different things to get a displayable name.
    
    Return:
        A clean displayable name for the given Maya object.

    Notes:
        Currently supported Maya types:

            * str
            * MObject
            * MDagPath
            * MFnDependencyNodes (= All subtypes as well)
    """

    if isinstance(object_, OpenMaya.MObject):
        handle = OpenMaya.MObjectHandle(object_)
        object_ = OpenMaya.MFnDependencyNode(object_)
    elif isinstance(object_, OpenMaya.MFn):
        handle = OpenMaya.MObjectHandle(object_.object().node())
    elif isinstance(object_, OpenMaya.MDagPath):
        handle = OpenMaya.MObjectHandle(object_.node())
        object_ = OpenMaya.MFnDependencyNode(object_.node())
    else:
        return str(object_)

    if not handle.object().isNull() and handle.isValid() and handle.isAlive():
        return object_.name()


@dataclass(frozen=True)
class MayaFeedbackContainer(atCore.FeedbackContainer):
    """Maya specific :class:`~FeedbackContainer` that implement optimized selection and deselection.

    This is a Maya's custom implementation of a :class:`~FeedbackContainer`. While it's not necessary to use this subtype
    of :class:`~FeedbackContainer` for a Maya Process, it allow for a more optimized selection/deselection behavior, 
    especially when there's a lot of feedback to selection.
    """

    def select(self, replace:bool = True) -> bool:
        """Implement Maya's in-scene selection of the current :class:`~MayaFeedbackContainer`.

        If the :class:`~MayaFeedbackContainer` is not selectable, it will be skipped.
        On the other hand, if it is, it will do one single selection of all Feedbacks in the container, this allow for
        better performance than selecting each feedback one by one when there's a lot of them.

        Parameters:
            replace: Whether or not the new elements must replace the current selection.

        Return:
            The state for the replace boolean. This allow to know if a chained selection must be replace again or not.
            Usually, it must replace for the first item, and then add, if not, we would end up with only the latest element.
        """

        if not self.selectable:
            return replace
        
        # with PauseViewport():
        if self.children:
            select_in_maya(tuple(child.feedback for child in self.children), mode='add', replace=replace)
            replace = False

        return replace

    def deselect(self) -> None:
        """Implement Maya's in-scene deselection of the current :class:`~MayaFeedbackContainer`.

        If the :class:`~MayaFeedbackContainer` is not selectable, it will be skipped.
        On the other hand, if it is, it will do one single deselection of all Feedbacks in the container, this allow for
        better performance than deselecting each feedback one by one when there's a lot of them.
        """

        if not self.selectable:
            return
        
        # with PauseViewport():
        if self.children:
            select_in_maya(tuple(child.feedback for child in self.children), mode='remove', replace=False)


@dataclass(frozen=True)
class MayaFeedback(atCore.Feedback):
    """Represent a single Maya Feedback, this allows for better display and selection/deselection behavior.

    Using a MayaFeedback is not mandatory when doing a Maya :class:`~Process`, and it can be used alongside normal 
    :class:`~Feedback`. The benefits of using a Maya Feedback is that they allow for in-scene selection and return a clean
    display for complexes Maya API types.
    """

    def __str__(self) -> str:
        """Clean display name for the feedback, whether it's already a string (`maya.cmds`) or a Maya API type.
        
        Return:
            A readable display name for the :obj:`~MayaFeedback.feedback` attribute.
        """

        return get_display(self.feedback)

    def select(self, replace: bool = True) -> bool:
        """Implement Maya's in-scene selection of the current :class:`~MayaFeedback`.

        If the :class:`~MayaFeedback` is selectable, it will be selected in the scene.

        Parameters:
            replace: Whether or not the new element must replace the current selection.

        Return:
            The result of the parent's class implementation.
        """

        if self.selectable:
            select_in_maya((self.feedback,), mode='add', replace=replace)
            replace = False

        return super().select(replace=replace)

    def deselect(self) -> None:
        """Implement Maya's in-scene deselection of the current :class:`~MayaFeedback`.

        If the :class:`~MayaFeedback` is selectable, it will be deselected in the scene.
        """

        super().deselect()

        if self.selectable:
            select_in_maya((self.feedback,), mode='remove', replace=False)


class MayaProcess(atCore.Process):
    """A custom Process implementation to be used in Maya which define the best :class:`~FeedbackContainer` subclass to use.

    It's not mandatory to create a Maya Process using this :class:`~Process` subclass, the only thing it does is making
    sure to override the :class:`~Process` default :class:`~FeedbackContainer` is replace with a :class:`MayaFeedbackContainer`
    which implement a better selection behavior.
    By using this the user's won't have to figure out which :class:`FeedbackContainer` to use and implement it on all their
    :class:`~Process`.
    """

    FEEDBACK_CONTAINER_CLASS: Type[MayaFeedbackContainer] = MayaFeedbackContainer
