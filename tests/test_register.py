import os

import pytest
from collections.abc import Sequence

import athena
from athena import atCore


class TestRegister:

    def setup_method(self, method):
        self.register = atCore.Register()

    def teardown_method(self, method):
        del self.register

    def test_load_blueprint_from_module_path(self):
        module_path = os.path.join(athena.__file__.replace('__init__.py', ''), 'examples', 'blueprint', 'exampleBlueprint.py')
        self.register.load_blueprint_from_module_path(module_path)

        assert isinstance(self.register.blueprints, Sequence) and not isinstance(self.register.blueprints, str)
        assert all(isinstance(each, atCore.Blueprint) for each in self.register.blueprints)

    def test_load_blueprints_from_package_str(self):
        self.register.load_blueprints_from_package_str('athena.examples.blueprint')

        assert isinstance(self.register.blueprints, Sequence) and not isinstance(self.register.blueprints, str)
        assert all(isinstance(each, atCore.Blueprint) for each in self.register.blueprints)

