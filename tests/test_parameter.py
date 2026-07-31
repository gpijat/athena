"""Tests for the Parameter machinery.

They cover the ParameterSpec and ParameterFactory, the Parameter descriptor, the ParameterPolicy and
UserParameterOverride governance, and the Processor and Blueprint wiring for Blueprint overrides and the
conformance gate. They follow the existing repo convention of pytest with an editable install of athena.
"""

import pytest

from athena import atCore, atExceptions
from athena.atCore import ParameterFactory, ParameterPolicy, UserParameterOverride

from tests.fixtures import parameter_processes


# ---------------------------------------------------------------------------
# Builtin ParameterSpec type_cast / validate (including the fixed bugs).
# ---------------------------------------------------------------------------

class TestParameterSpecs:

    def test_bool_type_cast_accepts_documented_truthy_strings(self):
        spec = ParameterFactory.build('bool', default=False)
        for truthy in (True, 'True', 'true', 'Yes', 'yes', 'ok', 1, '1'):
            assert spec.type_cast(truthy) is True
        for falsy in (False, 'no', 'nope', 0, '0', 'random'):
            assert spec.type_cast(falsy) is False

    def test_bool_default_must_be_bool(self):
        with pytest.raises(atExceptions.AtParameterValidationError):
            ParameterFactory.build('bool', default='not a bool')

    def test_int_type_cast_and_validate(self):
        spec = ParameterFactory.build('int', default=5, minimum=1, maximum=10)
        assert spec.type_cast('7') == 7
        assert spec.type_cast(3.9) == 3
        assert spec.validate(1) and spec.validate(10)
        assert not spec.validate(0)
        assert not spec.validate(11)

    def test_int_keep_in_range_clamps(self):
        spec = ParameterFactory.build('int', default=5, minimum=1, maximum=10, keep_in_range=True)
        assert spec.type_cast(100) == 10
        assert spec.type_cast(-100) == 1

    def test_float_type_cast_and_validate(self):
        spec = ParameterFactory.build('float', default=1.5, minimum=0.0, maximum=2.0)
        assert spec.type_cast('1.25') == 1.25
        assert spec.validate(0.0) and spec.validate(2.0)
        assert not spec.validate(2.01)

    def test_number_rejects_inverted_range(self):
        with pytest.raises(atExceptions.AtParameterValidationError):
            ParameterFactory.build('int', default=5, minimum=10, maximum=1)

    def test_number_rejects_default_outside_range(self):
        with pytest.raises(atExceptions.AtParameterValidationError):
            ParameterFactory.build('int', default=50, minimum=1, maximum=10)
        with pytest.raises(atExceptions.AtParameterValidationError):
            ParameterFactory.build('float', default=-1.0, minimum=0.0, maximum=10.0)

    def test_string_case_sensitive_matches_exactly(self):
        # Regression: the old StringParameter lowercased in type_cast, making
        # case_sensitive=True mathematically unable to ever match.
        spec = ParameterFactory.build('string', default='Foo', validation=('Foo', 'Bar'), case_sensitive=True)
        assert spec.type_cast('Foo') == 'Foo'
        assert spec.validate('Foo')
        assert not spec.validate('foo')

    def test_string_case_insensitive(self):
        spec = ParameterFactory.build('string', default='foo', validation=('Foo', 'Bar'), case_sensitive=False)
        assert spec.validate('FOO')
        assert spec.validate('bar')
        assert not spec.validate('baz')

    def test_string_type_cast_handles_non_str(self):
        # Regression: the old type_cast assumed value had .lower() and crashed on ints.
        spec = ParameterFactory.build('string', default='x')
        assert spec.type_cast(5) == '5'

    def test_string_default_must_pass_validation(self):
        with pytest.raises(atExceptions.AtParameterValidationError):
            ParameterFactory.build('string', default='nope', validation=('a', 'b'))

    def test_unknown_type_raises(self):
        with pytest.raises(atExceptions.AtParameterTypeError):
            ParameterFactory.build('nonexistent', default=1)

    def test_with_overrides_reruns_validation(self):
        spec = ParameterFactory.build('int', default=5, minimum=1, maximum=10)
        tightened = spec.with_overrides(default=8)
        assert tightened.default == 8
        # An override that violates the (also-overridden) range still validates.
        with pytest.raises(atExceptions.AtParameterValidationError):
            spec.with_overrides(default=100)


# ---------------------------------------------------------------------------
# Parameter descriptor per-instance behavior.
# ---------------------------------------------------------------------------

class TestParameterDescriptor:

    def _make_process_class(self):
        class Proc(atCore.Process):
            thread = atCore.Thread(title='t')
            value = atCore.IntParameter(100, minimum=1, maximum=1000)
        return Proc

    def test_default_returned_before_set(self):
        Proc = self._make_process_class()
        assert Proc().value == 100

    def test_instances_hold_independent_values(self):
        # Regression guard for the "same Process used twice" concern: no shared state.
        Proc = self._make_process_class()
        a, b = Proc(), Proc()
        a.value = 5
        assert a.value == 5
        assert b.value == 100

    def test_set_invalid_raises_not_silent(self):
        Proc = self._make_process_class()
        proc = Proc()
        with pytest.raises(atExceptions.AtParameterValidationError):
            proc.value = 99999
        # The value is unchanged (not silently dropped to some coerced state).
        assert proc.value == 100

    def test_delete_resets_to_default(self):
        Proc = self._make_process_class()
        proc = Proc()
        proc.value = 7
        del proc.value
        assert proc.value == 100

    def test_class_access_returns_descriptor(self):
        Proc = self._make_process_class()
        assert isinstance(Proc.__dict__['value'], atCore.Parameter)
        assert Proc.__dict__['value'].name == 'value'
        assert Proc.__dict__['value'].default == 100


# ---------------------------------------------------------------------------
# ParameterPolicy / UserParameterOverride governance.
# ---------------------------------------------------------------------------

class TestParameterPolicy:

    def test_default_policy(self):
        policy = ParameterPolicy()
        assert policy.blueprint_configurable is True
        assert policy.user_override is UserParameterOverride.TAINTING
        assert policy.immutable is False

    def test_immutable_is_derived(self):
        assert ParameterPolicy(blueprint_configurable=False, user_override=UserParameterOverride.LOCKED).immutable is True
        assert ParameterPolicy(blueprint_configurable=False, user_override=UserParameterOverride.TAINTING).immutable is False
        assert ParameterPolicy(blueprint_configurable=True, user_override=UserParameterOverride.LOCKED).immutable is False

    def test_tighten_each_axis_independently(self):
        policy = ParameterPolicy()
        assert policy.tightened_by(user_override=UserParameterOverride.LOCKED).user_override is UserParameterOverride.LOCKED
        assert policy.tightened_by(blueprint_configurable=False).blueprint_configurable is False

    def test_partial_override_leaves_other_axis_unchanged(self):
        policy = ParameterPolicy(blueprint_configurable=False, user_override=UserParameterOverride.TAINTING)
        tightened = policy.tightened_by(user_override=UserParameterOverride.LOCKED)
        assert tightened.user_override is UserParameterOverride.LOCKED
        assert tightened.blueprint_configurable is False  # untouched

    def test_loosening_user_override_raises(self):
        policy = ParameterPolicy(user_override=UserParameterOverride.LOCKED)
        with pytest.raises(atExceptions.AtParameterPolicyError):
            policy.tightened_by(user_override=UserParameterOverride.FREE)

    def test_loosening_blueprint_configurable_raises(self):
        policy = ParameterPolicy(blueprint_configurable=False)
        with pytest.raises(atExceptions.AtParameterPolicyError):
            policy.tightened_by(blueprint_configurable=True)

    def test_tighten_to_same_is_allowed(self):
        policy = ParameterPolicy(user_override=UserParameterOverride.TAINTING)
        assert policy.tightened_by(user_override=UserParameterOverride.TAINTING).user_override is UserParameterOverride.TAINTING


# ---------------------------------------------------------------------------
# Processor wiring: Blueprint overrides, effective default, reset, conformance.
# ---------------------------------------------------------------------------

def _param(processor, name):
    return {p.name: p for p in processor.parameters}[name]


class TestProcessorOverrides:

    FIXTURE = 'tests.fixtures.parameter_processes.SingleParamProcess'
    MIXED = 'tests.fixtures.parameter_processes.MixedPolicyProcess'
    LOCKED = 'tests.fixtures.parameter_processes.LockedParamProcess'

    def test_override_seeds_effective_default_without_touching_class(self):
        overridden = atCore.Processor(process=self.FIXTURE, parameter_overrides={'iterations': {'default': 10}})
        plain = atCore.Processor(process=self.FIXTURE)

        assert overridden.get_effective_default(_param(overridden, 'iterations')) == 10
        assert overridden.get_parameter(_param(overridden, 'iterations')) == 10

        # The Processor without an override uses the same Process class and is unaffected, which shows
        # the class level spec was never mutated.
        assert plain.get_effective_default(_param(plain, 'iterations')) == 100
        assert plain.get_parameter(_param(plain, 'iterations')) == 100

    def test_reset_returns_to_effective_default_not_author_default(self):
        pr = atCore.Processor(process=self.FIXTURE, parameter_overrides={'iterations': {'default': 10}})
        param = _param(pr, 'iterations')

        pr.set_parameter(param, 42)
        assert pr.get_parameter(param) == 42

        assert pr.reset_parameter(param) == 10  # effective (overridden) default, not 100
        assert pr.get_parameter(param) == 10

    def test_del_resets_to_effective_default(self):
        pr = atCore.Processor(process=self.FIXTURE, parameter_overrides={'iterations': {'default': 10}})
        param = _param(pr, 'iterations')
        pr.set_parameter(param, 42)
        param.__delete__(pr.process)
        assert pr.get_parameter(param) == 10

    def test_invalid_override_raises_on_resolution(self):
        pr = atCore.Processor(process=self.FIXTURE, parameter_overrides={'iterations': {'default': 99999}})
        with pytest.raises(atExceptions.AtParameterValidationError):
            pr.parameters

    def test_unknown_override_name_raises(self):
        pr = atCore.Processor(process=self.FIXTURE, parameter_overrides={'does_not_exist': {'default': 1}})
        with pytest.raises(atExceptions.AtParameterNotFoundError):
            pr.parameters

    def test_unknown_policy_name_raises(self):
        pr = atCore.Processor(process=self.FIXTURE, parameter_policies={'does_not_exist': {'user_override': UserParameterOverride.LOCKED}})
        with pytest.raises(atExceptions.AtParameterNotFoundError):
            pr.parameters

    def test_spec_override_on_non_configurable_raises(self):
        # LockedParamProcess declares blueprint_configurable=False on `locked`.
        pr = atCore.Processor(process=self.LOCKED, parameter_overrides={'locked': {'default': 5}})
        with pytest.raises(atExceptions.AtParameterPolicyError):
            pr.parameters

    def test_blueprint_can_lock_a_parameter(self):
        pr = atCore.Processor(process=self.FIXTURE, parameter_policies={'iterations': {'user_override': UserParameterOverride.LOCKED}})
        with pytest.raises(atExceptions.AtParameterPolicyError):
            pr.set_parameter(_param(pr, 'iterations'), 5)


class TestProcessorSetParameterPolicy:

    FIXTURE = 'tests.fixtures.parameter_processes.MixedPolicyProcess'
    LOCKED = 'tests.fixtures.parameter_processes.LockedParamProcess'

    def test_locked_set_raises(self):
        pr = atCore.Processor(process=self.LOCKED)
        with pytest.raises(atExceptions.AtParameterPolicyError):
            pr.set_parameter(_param(pr, 'locked'), 5)

    def test_tainting_set_succeeds(self):
        pr = atCore.Processor(process=self.FIXTURE)
        assert pr.set_parameter(_param(pr, 'iterations'), 7) == 7

    def test_free_set_succeeds(self):
        pr = atCore.Processor(process=self.FIXTURE)
        assert pr.set_parameter(_param(pr, 'duration'), 9.0) == 9.0


class TestConformance:

    FIXTURE = 'tests.fixtures.parameter_processes.MixedPolicyProcess'

    def test_free_override_is_overridden_but_conformant(self):
        pr = atCore.Processor(process=self.FIXTURE)
        iterations = _param(pr, 'iterations')
        duration = _param(pr, 'duration')

        pr.set_parameter(iterations, 7)   # TAINTING
        pr.set_parameter(duration, 9.0)   # FREE

        overridden = set(pr.overridden_parameters)
        assert overridden == {iterations, duration}

        # Only the TAINTING one counts against conformance.
        assert tuple(pr.nonconformant_parameters) == (iterations,)
        assert pr.is_conformant is False

    def test_only_free_override_stays_conformant(self):
        pr = atCore.Processor(process=self.FIXTURE)
        pr.set_parameter(_param(pr, 'duration'), 9.0)
        assert pr.overridden_parameters == (_param(pr, 'duration'),)
        assert pr.nonconformant_parameters == ()
        assert pr.is_conformant is True

    def test_conformance_is_live_not_sticky(self):
        pr = atCore.Processor(process=self.FIXTURE)
        iterations = _param(pr, 'iterations')

        assert pr.is_conformant is True
        pr.set_parameter(iterations, 7)
        assert pr.is_conformant is False
        pr.reset_parameter(iterations)
        assert pr.is_conformant is True


# ---------------------------------------------------------------------------
# Tag driven advisory state, including the NO_PARAMETERS tag.
# ---------------------------------------------------------------------------

class TestProcessorAllowsTags:

    EXAMPLE = 'athena.examples.process.exampleProcess.AthenaExampleProcess'
    FIXTURE = 'tests.fixtures.parameter_processes.SingleParamProcess'

    def test_allows_parameters_true_by_default(self):
        assert atCore.Processor(process=self.EXAMPLE).allows_parameters is True

    def test_no_parameters_tag_clears_allows_parameters(self):
        pr = atCore.Processor(process=self.EXAMPLE, tags=atCore.Tag.NO_PARAMETERS)
        assert pr.allows_parameters is False

    def test_no_parameters_tag_is_advisory_only(self):
        # The tag hides the panel in the tool, it does not gate set_parameter.
        pr = atCore.Processor(process=self.FIXTURE, tags=atCore.Tag.NO_PARAMETERS)
        iterations = _param(pr, 'iterations')
        assert pr.set_parameter(iterations, 7) == 7

    def test_allows_check_fix_tool_reflect_method_presence(self):
        # The example Process implements only check, so only allows_check is True.
        pr = atCore.Processor(process=self.EXAMPLE)
        assert pr.allows_check is True
        assert pr.allows_fix is False
        assert pr.allows_tool is False

    def test_no_check_tag_clears_allows_check(self):
        pr = atCore.Processor(process=self.EXAMPLE, tags=atCore.Tag.NO_CHECK)
        assert pr.allows_check is False


# ---------------------------------------------------------------------------
# Blueprint aggregation.
# ---------------------------------------------------------------------------

class _FakeProcessor:
    """Minimal stand-in exposing just the surface Blueprint aggregation reads."""

    def __init__(self, nonconformant):
        self._nonconformant = tuple(nonconformant)

    @property
    def nonconformant_parameters(self):
        return self._nonconformant


class TestBlueprintAggregation:

    def _blueprint_with(self, processors):
        blueprint = atCore.Blueprint.__new__(atCore.Blueprint)
        # Seed the `processors` cached_property directly so we don't need a module.
        blueprint.__dict__['processors'] = tuple(processors)
        return blueprint

    def test_aggregates_nonconformant_across_processors(self):
        conformant = _FakeProcessor([])
        nonconformant = _FakeProcessor(['sentinel-a', 'sentinel-b'])
        blueprint = self._blueprint_with([conformant, nonconformant])

        assert blueprint.nonconformant_parameters == ('sentinel-a', 'sentinel-b')
        assert blueprint.is_conformant is False

    def test_all_conformant_processors_make_blueprint_conformant(self):
        blueprint = self._blueprint_with([_FakeProcessor([]), _FakeProcessor([])])
        assert blueprint.nonconformant_parameters == ()
        assert blueprint.is_conformant is True
