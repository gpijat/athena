from athena.atCore import Tag, Link

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
        },
}


# Using the settings you can define some extra "per blueprint" options for your ui or cli to use.
settings = \
{
    'autoOpenOnFailAndError': True
}

