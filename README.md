# Athena: Sanity Checking Framework

![PythonVersion](https://img.shields.io/pypi/pyversions/athena-sanity)
![PyPi](https://img.shields.io/pypi/v/athena-sanity)
[![License](https://img.shields.io/badge/License-GPL3.0-blue.svg)](https://opensource.org/license/gpl-3-0/)

Athena is a versatile sanity checking framework designed to simplify the process of creating and running validation procedures, known as Sanity-Check. These checks can be executed in any software environments with Python interpreters, especially in DCC (Digital Content Creation) software, or in standalone across all operating systems.

## Getting Started

To quickly get started with Athena, follow these steps:

### Prerequisites

Ensure you have Python >3.8 installed. Athena has no external dependencies.

### Installing

You can install Athena using pip:
```bash
pip install athena-sanity
```

Or download the latest release [here](https://github.com/gpijat/athena/releases).

### Usage Example

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

Alternatively, you can skip the blueprint and just run a process with a default configuration or use your own by passing extra arguments to the `Processor`:
```py
import athena

processor = athena.AtCore.Processor('athena.examples.process.exampleProcess')

result = processor.check()
for container in result:
    print(container, container.status)
    for feedback in container:
        print('\t' + str(feedback))

```

You can find examples on how to write a Process or Blueprint [here](https://github.com/gpijat/athena/tree/master/src/athena/examples)

## Running the Tests

Full support for unit test will come later.

## Versioning

Athena follows the principles of [Semantic Versioning (SemVer)](http://semver.org/). Check the [tags on this repository](https://github.com/gpijat/athena/tags) for available versions.

## Authors

* **Gregory Pijat** - *Author* - [GitHub](https://github.com/gpijat)

See the list of [contributors](https://github.com/gpijat/athena/contributors) who participated in this project.

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## More

For an enhanced experience, check out the available UI on Gumroad. (Available *soon*)
