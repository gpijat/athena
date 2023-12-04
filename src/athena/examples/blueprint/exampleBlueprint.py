from athena.AtCore import Tag, Link

header = \
(
    'AthenaExampleProcess',
)


descriptions = \
{
    'AthenaExampleProcess':
        {
            'process': 'athena.examples.process.exampleProcess.AthenaExampleProcess', 
            'category': '[Placeholder]',
        },
}


class ExampleContext(object):
    def __enter__(self, *args, **kwargs):
        pass

    def __exit__(self, *args, **kwargs):
        pass

settings = \
{
    'context': ExampleContext,
    'autoOpenOnFailAndError': True
}
