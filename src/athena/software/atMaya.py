from __future__ import annotations

from typing import Type, Union, Sequence

import sys
from dataclasses import dataclass

from athena import AtCore

from functools import partial
from shiboken2 import wrapInstance
from PySide2 import QtWidgets

from maya import cmds
from maya.api import OpenMaya, OpenMayaUI


class PauseViewport(object):

    __IS_RUNNING: bool = False

    def __enter__(self) -> None:

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
        
        # for node, (frozen, nodeState) in self._nodes.items():
        #   node = next(iter(cmds.ls(node, long=True)), None)
        #   if node is None:  # The node have been deleted.
        #       continue
        #   cmds.setAttr(node+'.frozen', frozen)
        #   cmds.setAttr(node+'.nodeState', nodeState)
        # cmds.dgdirty(cmds.ls())

        # 
        if cmds.ogs(query=True, pause=True):
            cmds.ogs(pause=True)
        cmds.refresh(suspend=False)

        # -- Restart
        cmds.dgdirty(cmds.ls())
        cmds.ogs(reset=True)
        cmds.refresh()


def selectInMaya(
    toSelect: Sequence[Union[str | OpenMaya.MObject | OpenMaya.MDagPath | OpenMaya.MFnDependencyNode], ...], 
    mode: str ='add', 
    replace: bool = True) -> None:

    selList = OpenMaya.MSelectionList()

    for each in toSelect:
        # For `str` or `maya.api.OpenMaya.MObject`
        try: selList.add(each)
        except: pass

        # For `maya.api.OpenMaya.MFn`
        try: selList.add(each.object())
        except: pass

    mode = OpenMaya.MGlobal.kAddToList if mode == 'add' else OpenMaya.MGlobal.kRemoveFromList
    if replace:
        mode = OpenMaya.MGlobal.kReplaceList
    
    OpenMaya.MGlobal.setActiveSelectionList(selList, mode)


def getDisplay(object_: Union[str | OpenMaya.MObject | OpenMaya.MDagPath | OpenMaya.MFnDependencyNode]) -> str:
    # For `str` or `maya.api.OpenMaya.MObject`
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


#DEPRECATED: Remove this as it won't be used.
def toViewportHUD(widget):
    # Create an instance of the M3dView class and get the 3D view from the modelPanel4 in Maya
    view = OpenMayaUI.M3dView.active3dView()

    # Get the model view as a QtWidget for python2 and python3
    if sys.version_info.major < 3:
        viewportWidget = wrapInstance(long(view.widget()), QtWidgets.QWidget)
    else:
        viewportWidget = wrapInstance(int(view.widget()), QtWidgets.QWidget)

    # Required for resizing !!
    widget.setParent(viewportWidget)

    widget.show()


@dataclass(frozen=True)
class MayaFeedbackContainer(AtCore.FeedbackContainer):

    def select(self, replace:bool = True) -> bool:
        if not self.selectable:
            return replace
        
        # with PauseViewport():
        if self.children:
            selectInMaya(tuple(child.feedback for child in self.children), mode='add', replace=replace)
            replace = False

        return replace

    def deselect(self) -> None:
        if not self.selectable:
            return
        
        # with PauseViewport():
        if self.children:
            selectInMaya(tuple(child.feedback for child in self.children), mode='remove', replace=False)


@dataclass(frozen=True)
class MayaFeedback(AtCore.Feedback):

    def __str__(self) -> str:
        return getDisplay(self.feedback)

    def select(self, replace: bool = True) -> bool:
        if self.selectable:
            selectInMaya((self.feedback,), mode='add', replace=replace)
            replace = False

        return super().select(replace=replace)

    def deselect(self) -> None:
        super().deselect()

        if self.selectable:
            selectInMaya((self.feedback,), mode='remove', replace=False)


class MayaProcess(AtCore.Process):

    FEEDBACK_CONTAINER_CLASS: Type[MayaFeedbackContainer] = MayaFeedbackContainer
