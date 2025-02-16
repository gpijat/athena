import pytest
from athena import atUtils


@pytest.mark.parametrize('to_split,expected', (
    ('CamelCaseSplit', 'Camel Case Split'),  # Normal input in CamelCase
    ('Camel Case Split', 'Camel Case Split'),  # Input already split must be returned in the same state.
    ('camelcasesplit', 'camelcasesplit'),  # Full lowercase must not be alterred.
    ('000010000', '000010000'),  # Numeric has no uppercase so no split.
))
def test_camel_case_split(to_split, expected):
    assert atUtils.camel_case_split(to_split) == expected


def test_get_overriden_methods():
    class Foo():
        def a(self): pass

    class Bar(Foo):
        def a(self): pass

    assert tuple(atUtils.get_overridden_methods(Bar, Foo).keys()) == ('a',)


def test_python_import_path_from_path():
    assert atUtils.python_import_path_from_path(atUtils.__file__) == 'athena.atUtils'


def test_import_from_str():
    assert atUtils.import_from_str('athena.atUtils') is atUtils


@pytest.mark.skip(reason='WIP test, a better implementation is required.')
def test_map_mapping():
    input_mapping = {'0': 0.0, '1': {1.1: 1.1, 2.1: 2}}
    expected_mapping = {'0': 0, '1': {1.1: 1, 2.1: 2}}
    assert atUtils.map_mapping(int, input_mapping) == expected_mapping
