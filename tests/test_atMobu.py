"""Tests for the MotionBuilder software module.

MotionBuilder is not available outside of the application, so `pyfbsdk` and `unbind` are replaced with a minimal
in-memory scene that mimics the behaviors athena relies on: the `Selected` and `LongName` properties, wildcard
name lookup, the model change batching pair and wrappers that raise once their object is destroyed.
"""

import importlib
import re
import sys
import types

import pytest

from athena import atCore, atStatus


class UnboundWrapperError(Exception):
    pass


class FBComponent:

    def __init__(self, scene, long_name, selected=False):
        self._scene = scene
        self._long_name = long_name
        self._selected = selected
        scene.Components.append(self)

    def _check_bound(self):
        if self._scene is None:
            raise UnboundWrapperError('Python WrapperUnbound: SDK Object has been destroyed.')

    @property
    def LongName(self):
        self._check_bound()
        return self._long_name

    @property
    def Selected(self):
        self._check_bound()
        return self._selected

    @Selected.setter
    def Selected(self, value):
        self._check_bound()
        self._selected = value

    def FBDelete(self):
        self._scene.Components.remove(self)
        self._scene = None
        # Like MotionBuilder, the destroyed wrapper changes class but still passes `isinstance` checks.
        self.__class__ = type('FBComponent_Unbound', (FBComponent,), {})


class FakeScene:

    def __init__(self):
        self.Components = []
        self.change_depth = 0


def make_fake_pyfbsdk(scene):
    module = types.ModuleType('pyfbsdk')
    module.FBComponent = FBComponent
    module.FBComponentList = list
    module.FBSystem = lambda: types.SimpleNamespace(Scene=scene)

    def find_objects_by_name(pattern, matches, include_namespace, models_only):
        regex = re.compile('^' + '.*'.join(re.escape(part) for part in pattern.split('*')) + '$')
        for component in scene.Components:
            name = component.LongName if include_namespace else component.LongName.rpartition(':')[2]
            if regex.match(name):
                matches.append(component)

    def begin_change_all_models():
        scene.change_depth += 1

    def end_change_all_models():
        scene.change_depth -= 1

    module.FBFindObjectsByName = find_objects_by_name
    module.FBBeginChangeAllModels = begin_change_all_models
    module.FBEndChangeAllModels = end_change_all_models

    return module


@pytest.fixture
def scene():
    return FakeScene()


@pytest.fixture
def atMobu(scene, monkeypatch):
    unbind = types.ModuleType('unbind')
    unbind.UnboundWrapperError = UnboundWrapperError

    monkeypatch.setitem(sys.modules, 'pyfbsdk', make_fake_pyfbsdk(scene))
    monkeypatch.setitem(sys.modules, 'unbind', unbind)
    monkeypatch.delitem(sys.modules, 'athena.software.atMobu', raising=False)

    module = importlib.import_module('athena.software.atMobu')
    yield module

    assert scene.change_depth == 0, 'FBBeginChangeAllModels was not closed by FBEndChangeAllModels.'
    sys.modules.pop('athena.software.atMobu', None)


def selected_names(scene):
    return sorted(component.LongName for component in scene.Components if component.Selected)


class TestSelect:

    def test_replace_drops_previous_selection(self, atMobu, scene):
        cube = FBComponent(scene, 'ns:cube')
        FBComponent(scene, 'ns:sphere', selected=True)
        FBComponent(scene, 'material', selected=True)

        atMobu.select([cube], replace=True)

        assert selected_names(scene) == ['ns:cube']

    def test_add_keeps_previous_selection(self, atMobu, scene):
        cube = FBComponent(scene, 'ns:cube')
        FBComponent(scene, 'ns:sphere', selected=True)

        atMobu.select([cube], replace=False)

        assert selected_names(scene) == ['ns:cube', 'ns:sphere']

    def test_single_name_is_not_split_into_characters(self, atMobu, scene):
        FBComponent(scene, 'ns:cube')
        FBComponent(scene, 'c')

        atMobu.select('ns:cube')

        assert selected_names(scene) == ['ns:cube']

    def test_name_matches_exact_long_name_only(self, atMobu, scene):
        FBComponent(scene, 'ns:cube')
        FBComponent(scene, 'other:cube')
        FBComponent(scene, 'ns:cube_extra')

        atMobu.select(['cube', 'ns:cub*'])
        assert selected_names(scene) == []

        atMobu.select(['ns:cube'])
        assert selected_names(scene) == ['ns:cube']

    def test_name_selects_every_component_sharing_it(self, atMobu, scene):
        FBComponent(scene, 'ns:cube')
        FBComponent(scene, 'ns:cube')

        atMobu.select('ns:cube')

        assert len([component for component in scene.Components if component.Selected]) == 2

    def test_deleted_component_is_skipped(self, atMobu, scene):
        deleted = FBComponent(scene, 'deleted')
        cube = FBComponent(scene, 'cube')
        deleted.FBDelete()

        atMobu.select([deleted, cube])

        assert selected_names(scene) == ['cube']

    def test_unsupported_type_raises_and_leaves_selection_untouched(self, atMobu, scene):
        cube = FBComponent(scene, 'cube')
        FBComponent(scene, 'sphere', selected=True)

        with pytest.raises(TypeError, match='int'):
            atMobu.select([cube, 42])

        assert selected_names(scene) == ['sphere']


class TestDeselect:

    def test_deselect_only_given_components(self, atMobu, scene):
        cube = FBComponent(scene, 'cube', selected=True)
        FBComponent(scene, 'sphere', selected=True)
        FBComponent(scene, 'ns:cone', selected=True)

        atMobu.deselect([cube, 'ns:cone'])

        assert selected_names(scene) == ['sphere']


class TestGetDisplay:

    def test_component_displays_long_name(self, atMobu, scene):
        assert atMobu.get_display(FBComponent(scene, 'ns:cube')) == 'ns:cube'

    def test_deleted_component_displays_class_name(self, atMobu, scene):
        cube = FBComponent(scene, 'cube')
        cube.FBDelete()

        assert atMobu.get_display(cube) == '<deleted FBComponent>'

    def test_other_objects_are_converted_to_str(self, atMobu):
        assert atMobu.get_display('ns:cube') == 'ns:cube'
        assert atMobu.get_display(42) == '42'


class TestFeedback:

    def test_feedback_select_and_deselect(self, atMobu, scene):
        cube = FBComponent(scene, 'cube')
        FBComponent(scene, 'sphere', selected=True)
        feedback = atMobu.MobuFeedback(cube, True)

        assert feedback.select(replace=True) is False
        assert selected_names(scene) == ['cube']

        feedback.deselect()
        assert selected_names(scene) == []

    def test_feedback_str_uses_long_name(self, atMobu, scene):
        assert str(atMobu.MobuFeedback(FBComponent(scene, 'ns:cube'), True)) == 'ns:cube'


class TestFeedbackContainer:

    def make_container(self, atMobu, scene):
        container = atMobu.MobuFeedbackContainer(atCore.Thread('thread'), True, atStatus._DEFAULT)
        group = atCore.Feedback('A group label that matches no component', False)
        group.parent(atMobu.MobuFeedback(FBComponent(scene, 'grouped'), True))
        container.parent(atMobu.MobuFeedback(FBComponent(scene, 'cube'), True), group)
        return container

    def test_select_cascades_through_non_selectable_groups(self, atMobu, scene):
        FBComponent(scene, 'previous', selected=True)
        container = self.make_container(atMobu, scene)

        assert container.select(replace=True) is False
        assert selected_names(scene) == ['cube', 'grouped']

    def test_deselect_cascades_through_non_selectable_groups(self, atMobu, scene):
        container = self.make_container(atMobu, scene)
        FBComponent(scene, 'other', selected=True)
        container.select(replace=False)

        container.deselect()

        assert selected_names(scene) == ['other']

    def test_non_selectable_container_does_nothing(self, atMobu, scene):
        FBComponent(scene, 'previous', selected=True)
        container = atMobu.MobuFeedbackContainer(atCore.Thread('thread'), False, atStatus._DEFAULT)
        container.parent(atMobu.MobuFeedback(FBComponent(scene, 'cube'), True))

        assert container.select(replace=True) is True
        assert selected_names(scene) == ['previous']
