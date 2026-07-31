from athena.atCore import Tag, Link, UserParameterOverride

# The `header` defines the execution order for all processes in the `Blueprint`.
header = \
(
    'AthenaExampleProcess',
)


# The `description` is where you list all the `processes` with their configuration.
descriptions = \
{
    'AthenaExampleProcess':
        {
            'process': 'athena.examples.process.exampleProcess.AthenaExampleProcess',
            'category': '[Placeholder]',

            # A Blueprint can override a Parameter's spec (default/constraints) per-studio without
            # forking the Process. Each entry is keyed by Parameter name; the value is a dict of
            # builder kwargs to override. Uncomment to lower this studio's default `iterations`:
            # 'parameter_overrides': {'iterations': {'default': 10}},

            # A Blueprint can also *tighten* (never loosen) a Parameter's ParameterPolicy. Uncomment
            # to lock `iterations` so end users can't override it at all in this studio:
            # 'parameter_policies': {'iterations': {'user_override': UserParameterOverride.LOCKED}},
        },
}


# Using the settings you can define some extra "per blueprint" options for your ui or cli to use.
settings = \
{
    'autoOpenOnFailAndError': True
}

