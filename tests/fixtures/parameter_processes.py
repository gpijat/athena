"""Fixture Process subclasses used by `test_parameter.py`.

They live in their own importable module instead of being defined inside the test module because a
Processor is built from a python import string and imports the Process module itself.
"""

from athena import atCore


class SingleParamProcess(atCore.Process):
    """A Process with a single integer Parameter that keeps the default tainting policy."""

    thread = atCore.Thread(title='fixture thread')

    iterations = atCore.IntParameter(100, minimum=1, maximum=1000)


class MixedPolicyProcess(atCore.Process):
    """A Process with one tainting and one free Parameter.

    It is used to check that overridden and non-conformant are two separate signals.
    """

    thread = atCore.Thread(title='fixture thread')

    # Directly affects the result, so it keeps the default tainting policy.
    iterations = atCore.IntParameter(100, minimum=1, maximum=1000)

    # Cosmetic pacing only, so it is explicitly marked as conformance safe.
    duration = atCore.FloatParameter(
        5.0, minimum=0.0, maximum=60.0,
        policy=atCore.ParameterPolicy(user_override=atCore.UserParameterOverride.FREE),
    )


class LockedParamProcess(atCore.Process):
    """A Process whose Parameter the author declared locked and not Blueprint configurable.

    In other words the Parameter is immutable.
    """

    thread = atCore.Thread(title='fixture thread')

    locked = atCore.IntParameter(
        10, minimum=0, maximum=100,
        policy=atCore.ParameterPolicy(
            blueprint_configurable=False,
            user_override=atCore.UserParameterOverride.LOCKED,
        ),
    )
