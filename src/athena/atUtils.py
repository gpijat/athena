from __future__ import annotations

import importlib
import logging
import os
import pkgutil
import platform
import re
import sys
import traceback

from collections.abc import Collection, Mapping, Sequence
from types import ModuleType, FunctionType
from typing import TypeVar, Type, Optional, Any, Iterator, Tuple, Dict, Hashable

try:
    from importlib import reload  # Python 3.4+
except ImportError:
    from imp import reload  # Python 3.0 - 3.3

from athena import atConstants


LOGGER = logging.getLogger(atConstants.PROGRAM_NAME)
LOGGER.setLevel(20)


def iter_blueprints_path(package: str, software: str = 'standalone', verbose: bool = False) -> Iterator[str]:
    """Retrieve available envs from imported packages.

    Retrieve the currently imported packages path that match the pattern to works with this tool: {program}_{prod}
    Then, generate the usual path to the env using the package, the current software for the first sub package and env to the 
    desired package.

    Parameters:
        package: This is the string path to a python package.
        software: The software for which to get envs. (default: 'standalone')
        verbose: Define if the function should log information about its process.

    Return:
        Return a dict containing all envs for the given package and software.
        The key is the env and the value is a dict containing the imported module object for the env and its str path.
    """

    package_path = os.path.dirname(package.__file__)
    for loader, moduleName, _ in pkgutil.iter_modules(package.__path__):
        yield os.path.join(package_path, '{}.py'.format(moduleName))


#WATCHME: Not used anymore.
def get_packages() -> Tuple[str, ...]:
    """Get all packages that match the tool convention pattern.

    Loop through all modules in sys.modules.keys() and package those who match the tool convention pattern
    that is `{PROGRAM_NAME}_*`

    Parameters:
        verbose: Define if the function should log information about its process. (default: False)

    Return:
        Return a dict containing all package that match the pattern of the tool
        The key is the prod and the value is a dict containing the module object and its str path.

    .. deprecated:: 0.1.0-beta.2
    """

    packages = []

    rules = []
    # Append the rules list with all rules used to get package that end with {PROGRAM_NAME}_?_???
    rules.append(r'.*?')  # Non-greedy match on filler
    rules.append(r'({}_(?:[A-Za-z0-9_]+))'.format(atConstants.PROGRAM_NAME))  # Match {PROGRAM_NAME}_? pattern.
    rules.append(r'.*?')  # Non-greedy match on filler
    rules.append(r'([A-Za-z0-9_]+)')  # Word that match alpha and/or numerics, allowing '_' character.

    regex = re.compile(''.join(rules), re.IGNORECASE|re.DOTALL)

    for loaded_package in sys.modules.keys():

        # Ignore all module unrelated to this tool.
        if atConstants.PROGRAM_NAME not in loaded_package:
            continue

        search = regex.search(loaded_package)
        if not search:
            continue

        groups = search.groups()
        if not loaded_package.endswith('.'.join(groups)):
            continue
        
        packages.append(loaded_package)

        LOGGER.debug('Package "{}" found'.format(loaded_package))

    return tuple(packages)


def import_process_module_from_path(process_str_path: str) -> ModuleType:
    """Import the :class:`~Process` module from the given process python import string.
    
    Parameters:
        process_str_path: Python import string to a :class:`~Process` class.

    Return:
        The imported module that contains the Process' class.

    Raises:
        ImportError: If the imported :class:`~Process` module is missing the mentioned :class:`~Process` class.
    """

    module_str_path, _, process_name = process_str_path.rpartition('.')
    module = import_from_str(module_str_path)

    if not hasattr(module, process_name):
        raise ImportError('Module {0} have no class named {1}'.format(module.__name__, process_name))
    
    return module


def get_software() -> str:
    """Get the current software from which the tool is executed.

    Fallback on different instruction an try to get the current running software.
    If no software are retrieved, return the default value.

    Returns:
        The current software if any are find else the default value.

    .. deprecated:: 0.1.0-beta.2
    """

    # Fallback on the most efficient solution if psutil package is available
    if 'psutil' in sys.modules:
        import psutil
        process = psutil.Process(os.getpid())
        if process:
            software = _format_software(software_path=process.name())
            if software:
                return software
                
    # Fallback on sys.argv[0] or sys.executable (This depends on the current interpreter)
    python_interpreter = sys.executable
    if python_interpreter:
        software = _format_software(software_path=python_interpreter)
        if software:
            return software
    
    # Fallback on python_home or _ environment variable
    python_home = os.environ.get('python_home', os.environ.get('_', ''))
    if python_home:
        software = _format_software(software_path=python_home)
        if software:
            return software

    return 'Standalone'


def _format_software(software_path: str) -> str:
    """Check if there is an available software str in the given Path

    Parameters:
        software_path: The path to a software executable is expected here, but this works with any str.
        verbose: Define if the function should log information about its process. (default: False)

    Returns:
        The software found in software_path if there is one or an empty string.

    .. deprecated:: 0.1.0-beta.2
    """

    path = str(software_path).lower()
    for soft, regexes in atConstants.AVAILABLE_SOFTWARE.items():
        for regex in regexes:
            match = re.search(r'\{0}?{1}\{0}?'.format(os.sep, regex), path)
            if match:
                return soft
            
    return ''


def get_os() -> str:
    """Get the current used OS platform.

    If the Process Platform is `Darwin`, return `MacOs` instead for simplicity.

    Return:
        The current os name.
    """

    return platform.system().replace('Darwin', 'MacOs')


def python_import_path_from_path(path: str) -> str:
    """Generate a python import string path from a system path to a python Module or Package.

    Iterate through all directories in the path and include it in the python import string if it contains an `__init__.py` module.

    Parameters:
        path: The system path to convert to a python import string path.

    Returns:
        The python import string path generated from the given system path.

    Raises:
        IOError: If the given system path does not exists.
    """

    if not os.path.exists(path):
        raise IOError('Path `{}` does not exists.'.format(path))

    path_, file_ = None, None    
    if os.path.isfile(path):
        path_, _, file_ = path.rpartition(os.sep)
    elif os.path.isdir(path):
        path_, file_ = path, None
    
    incremental_path = ''
    python_import_path = ''
    for i, folder in enumerate(path_.split(os.sep)):
        if i == 0:
            incremental_path = folder or os.sep
            continue
        else:
            incremental_path += '{}{}'.format(os.sep, folder)

        if '__init__.py' in os.listdir(incremental_path):
            python_import_path += '{}{}'.format('.' if python_import_path else '', folder)
    
    if file_:
        python_import_path += '.' + os.path.splitext(file_)[0]
    
    return python_import_path


def import_from_str(module_str: str, verbose: bool = False) -> ModuleType:
    """Try to import the module from the given string

    Parameters:
        module_str: Path to a module to import.
        verbose: Define if the function should log information about its process. (default: False)

    Return:
        The loaded Module or None if fail.
    """

    module = None  #Maybe QC Error ?
    try:
        module = importlib.import_module(module_str) #TODO: if multiple checks come from same module try to load module multiple time
        if verbose: 
            LOGGER.info('import {} success'.format(module_str))
    except ImportError as exception:
        if verbose:
            LOGGER.exception('load {} failed'.format(module_str))

        raise

    return module


def reload_module(module: ModuleType) -> ModuleType:
    """Reload the given module object using the right `reload` function, whether it's from `imp` or `importLib`.
    
    Python 3.4 and above use the `reload` function from the `importLib` module while previous version use whether the 
    `reload` function from the `imp` module (>3.0 <3.4) or the built-in function directly (<3.0).

    Parameter:
        module: The module to reload.

    Return:
        The reloaded module given to the function, for convenience.

    Notes:
        This function exists as an helper to simplify Athena's module reloading without having to deal with which reload 
        function to use.
    """

    return reload(module)


def module_from_str(python_code: str, name: str = 'DummyAthenaModule') -> ModuleType:
    """Build a Module object with the given str as it's code.
    
    This will build a python module object and set's it's `code` so it acts as a normal module and can be loaded into 
    Athena's :class:`~Register`.

    Parameters:
        python_code: The Python code for the module as a string.
        name: Name for the created module object.

    Return:
        A python module that contains the given code and can be used the same way any module can.

    .. deprecated:: 0.1.0-beta.2
    """

    #TODO: Remove dead code.
    # spec = importlib.util.spec_from_loader(name, loader=None)

    # module = importlib.util.module_from_spec(spec)

    # exec(python_code, module.__dict__)
    # sys.modules[name] = module

    # return module

    module = ModuleType(name)
    exec(python_code, module.__dict__)
    sys.modules[name] = module

    module.__file__ = ''

    return module


def import_path_str_exist(import_str: str) -> bool:
    """Tells whether or not the given python import string is valid or not.
    
    Parameters:
        import_str: The python import string path to a module or package.

    Return:
        Whether or not the given import string is valid and could be imported.
    """

    return bool(pkgutil.find_loader(import_str))


T = TypeVar('T')
def get_overridden_methods(instance: T, cls: Type[T]) -> Dict[str, FunctionType]:
    """Get all methods that have been overridden from a the given instance and the given type.

    Parameters:
        instance: An instance of a subclass of cls.
        cls: An object type to compare the instance to.

    Return:
        All method that have been overridden from the instance in the given class.
    """

    res = {}
    for key, value in instance.__dict__.items():

        if isinstance(value, classmethod):
            value = callable(getattr(instance, key))

        if isinstance(value, (FunctionType, classmethod)):
            method = getattr(cls, key, None)
            if method is not None and callable(method) is not value:
                res[key] = value

    return res


def camel_case_split(to_split: str) -> str:
    """Format a string write with camelCase convention into a string with space.

    Parameters:
        to_split: The camelCase string to split and format.

    Return:
        The given string camelCase string splitted from upper cases with whitespaces instead.
    """

    matches = re.finditer('(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', to_split)
    split_str = []

    previous = 0
    for match in matches:
        split_str.append(to_split[previous:match.start()])
        previous = match.start()

    split_str.append(to_split[previous:])

    return ' '.join(split_str)


T = TypeVar('T')
class Singleton(type):
    """Singleton Metaclass to implement the design pattern in different class definition."""

    _instances = {}
    """Keep track of the classes instances and prevent multiple instantiation"""

    def __call__(cls, *args, **kwargs):
        """Override the call behavior and therefore a new class instantiation.

        If no instance of the given class exists, one is created and cached. 
        If one already exists, it's returned instead.

        Parameters:
            *args: Variable length argument list used to instantiate the class.
            **kwargs: Variable length keyword argument dict to instantiate the class.

        Return:
            A new or already existing instance of the given class, always the same and unique instance as expected from 
            the Singleton's design pattern.
        """

        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

    @classmethod
    def __instancecheck__(m_cls: Type[T], instance: T) -> bool:
        """Implement behavior on instance check."""

        if instance.__class__ is m_cls:
            return True
        else:
            return isinstance(instance.__class__, m_cls)


def create_new_athena_package_hierarchy(root_directory: str) -> None:
    """Create a new Athena's package hierarchy at the given root directory.

    Parameters:
        root_directory: The root directory at which to create a new Athena's package hierarchy.
    
    .. deprecated:: 0.1.0-beta.2
    """

    if os.path.exists(root_directory):
        raise OSError('`{}` already exists. Abort {0} package creation.'.format(atConstants.PROGRAM_NAME))
    os.mkdir(root_directory)

    blueprint_directory = os.path.join(root_directory, 'blueprints')
    os.mkdir(blueprint_directory)
    processes_directory = os.path.join(root_directory, 'processes')
    os.mkdir(processes_directory)

    init_py_files = (
        os.path.join(root_directory, '__init__.py'),
        os.path.join(blueprint_directory, '__init__.py'),
        os.path.join(processes_directory, '__init__.py')
        )
    
    header = '# Generated from {0} - Version {1}\n'.format(atConstants.PROGRAM_NAME, atConstants.VERSION)
    for file in init_py_files:
        with open(file, 'w') as file:
            file.write(header)

    dummy_process_path = os.path.join(processes_directory, 'dummyProcess.py')
    with open(dummy_process_path, 'w') as file:
        file.write(header + atConstants.DUMMY_PROCESS_TEMPLATE)

    dummy_blueprint_path = os.path.join(blueprint_directory, 'dummyBlueprint.py')
    with open(dummy_blueprint_path, 'w') as file:
        file.write(header + atConstants.DUMMY_BLUEPRINT_TEMPLATE)


T = TypeVar("T")
R = TypeVar("R")

def map_mapping(function: Callable[[T], R], mapping: Mapping[T]) -> Mapping[R]:
    """Execute the given function on all values inside the given Mapping object.

    Parameters:
        function: The function to call for each value and sub-value of the given mapping.
        mapping: The Mapping object to recursively iterate on and execute the function for each of it's values.

    Return:
        Equivalent of the input mapping with all values and sub-values modified through the given function.

    Notes:
        This method will iterate recursively on the mapping and it's values from top to bottom.
    """

    new_mapping = {}
    for key, value in mapping.items():
        if isinstance(value, Mapping):
            new_mapping[key] = map_mapping(function, value)
        elif isinstance(value, Sequence):
            new_mapping[key] = map_sequence(function, value)
        else:
            new_mapping[key] = function(value)
    
    return type(mapping)(new_mapping)
          

def map_sequence(function: Callable[[T], R], sequence: Sequence[T]) -> Sequence[R]:
    """Execute the given function on all values inside the given Sequence object.

    Parameters:
        function: The function to call for each value of the given sequence.
        sequence: The Sequence object to recursively iterate on and execute the function for each of it's values.

    Return:
        Equivalent of the input sequence with all values modified through the given function.

    Notes:
        
        * This method will iterate recursively on the sequence and it's values from top to bottom.
        * As `str` is technically a sub-type of `Sequence`, the first step is to do an instance check and early return if 
          the `sequence` is a string. The function will still be called with this string though and the result value returned
          like it would be for any other type.
    """

    # `str` in python is a sequence, but substring are also `str`.
    # This is meant to prevent RecursionError to occur as even the
    # shortest substring is a `str` and so is a `Sequence` by itself.
    if isinstance(sequence, str):
        return function(sequence)

    newSequence = []
    for each in sequence:
        if isinstance(each, Sequence):
            newSequence.append(map_sequence(function, each))
        elif isinstance(each, Mapping):
            newSequence.append(map_mapping(function, each))
        else:
            newSequence.append(function(each))
    
    return type(sequence)(newSequence)


def deep_map(function: Callable[[T], R], collection: Collection[T]) -> Collection[R]:
    """Execute the given function on all values inside the given Collection object.

    This will automatically call :func:`~map_sequence` or :func:`~map_mapping` based on the input collection or sub-collection
    inside it. It should be preferred to those method when you're not aware of your input collection type or that this type
    is different from one iteration to the other.

    Parameters:
        function: The function to call for each value and sub-value of the given collection.
        collection: The Collection object to recursively iterate on and execute the function for each of it's values.

    Return:
        Equivalent of the input collection with all values and sub-values modified through the given function.

    Notes:
        This method will iterate recursively on the collection and it's values from top to bottom.
    """

    if not isinstance(collection, Collection):
        raise TypeError('{} must be a subtype of {}. (Sequence: {} or Mapping: {})'.format(collection, Collection, Sequence, Mapping))
    if not callable(function):
        raise TypeError('{} object is not callable')

    if isinstance(collection, Sequence):
        return map_sequence(function, collection)
    elif isinstance(collection, Mapping):
        return map_mapping(function, collection)
