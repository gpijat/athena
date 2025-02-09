import pytest
from athena import atUtils


def test_camel_case_split():
    assert atUtils.camel_case_split('CamelCaseSplit') == "Camel Case Split"
    assert atUtils.camel_case_split('camelcasesplit') == 'camelcasesplit'
    assert atUtils.camel_case_split('000010000') == '000010000'


def test_get_overriden_methods():
    class Foo():
        def a(self): pass

    class Bar(Foo):
        def a(self): pass

    assert tuple(atUtils.get_overridden_methods(Bar, Foo).keys()) == ('a',)
