# Athena: Sanity Checking Framework

Athena is a versatile sanity checking framework designed to simplify the process of creating and running validation procedures, known as `Process`. These processes can be executed in software environments with Python interpreters, especially in DCC (Digital Content Creation) software, or in standalone across various operating systems.

## Getting Started

To quickly get started with Athena, follow these steps:

### Prerequisites

Ensure you have Python >3.7 installed. Athena has no external dependencies.

### Installing

You can install Athena using pip:

```bash
pip install athena
```

### Example

You can load a blueprint and run all it's processes, or query one single process to run:
```python
import athena

register = athena.AtCore.AtSession().register
register.loadBlueprintFromPythonImportPath('athena.examples.blueprint.exampleBlueprint')
blueprint = register.blueprintByName('exampleBlueprint')
# processor = blueprint.processorByName('exampleProcess')  # To get a single processor.

for processor in blueprint.processors:
    result = processor.check()
    
    for container in result:
        print(container, container.status)
        for feedback in container:
            print('\t' + str(feedback))

```

Alternatively, you can skip the blueprint and just run a process with a default configuration or use your own:
```py
import athena

processor = athena.AtCore.Processor('athena.examples.process.exampleProcess')

result = processor.check()
for container in result:
    print(container, container.status)
    for feedback in container:
        print('\t' + str(feedback))

```

## Running the Tests

Full support for unit test will come later.

## Built With

* [Python](https://www.python.org/) - The programming language used

## Versioning

Athena follows the principles of [Semantic Versioning (SemVer)](http://semver.org/). Check the [tags on this repository](https://github.com/your/project/tags) for available versions.

## Authors

* **Gregory Pijat** - *Author* - [GitHub](https://github.com/gpijat)

See the list of [contributors](https://github.com/your/project/contributors) who participated in this project.

## License

This project is licensed under the GPT-3.0 License - see the [LICENSE.md](LICENSE.md) file for details.

## Acknowledgments

* Hat tip to anyone whose code was used
* Inspiration
* etc

For an enhanced experience, check out the available on Gumroad.
