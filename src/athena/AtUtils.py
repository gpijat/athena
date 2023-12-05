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

from athena import AtConstants


LOGGER = logging.getLogger(AtConstants.PROGRAM_NAME)
LOGGER.setLevel(20)


def iterBlueprintsPath(package: str, software: str = 'standalone', verbose: bool = False) -> Iterator[str]:
    """Retrieve available envs from imported packages.

    Retrieve the currently imported packages path that match the pattern to works with this tool: {program}_{prod}
    Then, generate the usual path to the env using the package, the current software for the first sub package and env to the 
    desired package.

    Parameters:
        package: This is the string path to a python package.
        software: The software for which to get envs. (default: 'standalone')
        verbose: Define if the function should log informations about its process.

    Return:
        Return a dict containing all envs for the given package and software.
        The key is the env and the value is a dict containing the imported module object for the env and its str path.
    """

    packagePath = os.path.dirname(package.__file__)
    for loader, moduleName, _ in pkgutil.iter_modules(package.__path__):
        yield os.path.join(packagePath, '{}.py'.format(moduleName))


#WATCME: Not used anymore.
def getPackages() -> Tuple[str, ...]:
    """Get all packages that match the tool convention pattern.

    Loop through all modules in sys.modules.keys() and package those who match the tool convention pattern
    that is `{PROGRAM_NAME}_*`

    Parameters:
        verbose: Define if the function should log informations about its process. (default: False)

    Return:
        Return a dict containing all package that match the pattern of the tool
        The key is the prod and the value is a dict containing the module object and its str path.

    .. deprecated:: 1.0.0
    """

    packages = []

    rules = []
    # Append the rules list with all rules used to get package that end with {PROGRAM_NAME}_?_???
    rules.append(r'.*?')  # Non-greedy match on filler
    rules.append(r'({}_(?:[A-Za-z0-9_]+))'.format(AtConstants.PROGRAM_NAME))  # Match {PROGRAM_NAME}_? pattern.
    rules.append(r'.*?')  # Non-greedy match on filler
    rules.append(r'([A-Za-z0-9_]+)')  # Word that match alpha and/or numerics, allowing '_' character.

    regex = re.compile(''.join(rules), re.IGNORECASE|re.DOTALL)

    for loadedPackage in sys.modules.keys():

        # Ignore all module unrelated to this tool.
        if AtConstants.PROGRAM_NAME not in loadedPackage:
            continue

        search = regex.search(loadedPackage)
        if not search:
            continue

        groups = search.groups()
        if not loadedPackage.endswith('.'.join(groups)):
            continue
        
        packages.append(loadedPackage)

        LOGGER.debug('Package "{}" found'.format(loadedPackage))

    return tuple(packages)


def importProcessModuleFromPath(processStrPath: str) -> ModuleType:
    """Import the :class:`~Process` module from the given process python import string.
    
    Parameters:
        processStrPath: Python import string to a :class:`~Process` class.

    Return:
        The imported module that contains the Process' class.

    Raises:
        ImportError: If the imported :class:`~Process` module is missing the mentionned :class:`~Process` class.
    """

    moduleStrPath, _, processName = processStrPath.rpartition('.')
    module = importFromStr(moduleStrPath)

    if not hasattr(module, processName):
        raise ImportError('Module {0} have no class named {1}'.format(module.__name__, processName))
    
    return module


def getSoftware() -> str:
    """Get the current software from which the tool is executed.

    Fallback on different instruction an try to get the current running software.
    If no software are retrieved, return the default value.

    Returns:
        The current software if any are find else the default value.

    .. deprecated:: 1.0.0
    """

    # Fallback on the most efficient solution if psutil package is available
    if 'psutil' in sys.modules:
        import psutil
        process = psutil.Process(os.getpid())
        if process:
            software = _formatSoftware(softwarePath=process.name())
            if software:
                return software
                
    # Fallback on sys.argv[0] or sys.executable (This depends on the current interpreter)
    pythonInterpreter = sys.executable
    if pythonInterpreter:
        software = _formatSoftware(softwarePath=pythonInterpreter)
        if software:
            return software
    
    # Fallback on PYTHONHOME or _ environment variable
    pythonHome = os.environ.get('PYTHONHOME', os.environ.get('_', ''))
    if pythonHome:
        software = _formatSoftware(softwarePath=pythonHome)
        if software:
            return software

    return 'Standalone'


def _formatSoftware(softwarePath: str) -> str:
    """Check if there is an available software str in the hiven Path

    Parameters:
        softwarePath: The path to a software executable is expected here, but this works with any str.
        verbose: Define if the function should log informations about its process. (default: False)

    Returns:
        The software found in softwarePath if there is one or an empty string.

    .. deprecated:: 1.0.0
    """

    path = str(softwarePath).lower()
    for soft, regexes in AtConstants.AVAILABLE_SOFTWARE.items():
        for regex in regexes:
            match = re.search(r'\{0}?{1}\{0}?'.format(os.sep, regex), path)
            if match:
                return soft
            
    return ''


def getOs() -> str:
    """Get the current used OS platform.

    If the Process Platform is `Darwin`, return `MacOs` instead for simplicity.

    Return:
        The current os name.
    """

    return platform.system().replace('Darwin', 'MacOs')


def pythonImportPathFromPath(path: str) -> str:
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
    
    incrementalPath = ''
    pythonImportPath = ''
    for i, folder in enumerate(path_.split(os.sep)):
        if i == 0:
            incrementalPath = folder or os.sep
            continue
        else:
            incrementalPath += '{}{}'.format(os.sep, folder)

        if '__init__.py' in os.listdir(incrementalPath):
            pythonImportPath += '{}{}'.format('.' if pythonImportPath else '', folder)
    
    if file_:
        pythonImportPath += '.' + os.path.splitext(file_)[0]
    
    return pythonImportPath


def importFromStr(moduleStr: str, verbose: bool = False) -> ModuleType:
    """Try to import the module from the given string

    Parameters:
        moduleStr: Path to a module to import.
        verbose: Define if the function should log informations about its process. (default: False)

    Return:
        The loaded Module or None if fail.
    """

    module = None  #Maybe QC Error ?
    try:
        module = importlib.import_module(moduleStr) #TODO: if multiple checks come from same module try to load module multiple time
        if verbose: 
            LOGGER.info('import {} success'.format(moduleStr))
    except ImportError as exception:
        if verbose:
            LOGGER.exception('load {} failed'.format(moduleStr))

        raise

    return module


def reloadModule(module: ModuleType) -> ModuleType:
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


def moduleFromStr(pythonCode: str, name: str = 'DummyAthenaModule') -> ModuleType:
    """Build a Module object with the given str as it's code.
    
    This will build a python module object and set's it's `code` so it acts as a normal module and can be loaded into 
    Athena's :class:`~Register`.

    Parameters:
        pythonCode: The Python code for the module as a string.
        name: Name for the created module object.

    Return:
        A python module that contains the given code and can be used the same way any module can.

    .. deprecated:: 1.0.0
    """

    #TODO: Remove dead code.
    # spec = importlib.util.spec_from_loader(name, loader=None)

    # module = importlib.util.module_from_spec(spec)

    # exec(pythonCode, module.__dict__)
    # sys.modules[name] = module

    # return module

    module = ModuleType(name)
    exec(pythonCode, module.__dict__)
    sys.modules[name] = module

    module.__file__ = ''

    return module


def importPathStrExist(importStr: str) -> bool:
    """Tells whether or not the given python import string is valid or not.
    
    Parameters:
        importStr: The python import string path to a module or package.

    Return:
        Whether or not the given import string is valid and could be imported.
    """

    return bool(pkgutil.find_loader(importStr))


T = TypeVar('T')
def getOverridedMethods(instance: T, cls: Type[T]) -> Dict[str, FunctionType]:
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


def camelCaseSplit(toSplit: str) -> str:
    """Format a string write with camelCase convention into a string with space.

    Parameters:
        toSplit: The camelCase string to split and format.

    Return:
        The given string camelCase string splitted from upper cases with whitespaces instead.
    """

    matches = re.finditer('(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', toSplit)
    splitString = []

    previous = 0
    for match in matches:
        splitString.append(toSplit[previous:match.start()])
        previous = match.start()

    splitString.append(toSplit[previous:])

    return ' '.join(splitString)


T = TypeVar('T')
class Singleton(type):
    """Singleton Metaclass to implement the design pattern in different class definition."""

    _instances = {}
    """Keep track of the classes instances and prevent multiple instantiation"""

    def __call__(cls, *args, **kwargs):
        """Override the call behavior and therefore a new class instantion.

        If no instance of the given class exists, one is created and cached. 
        If one already exists, it's returned instead.

        Parameters:
            *args: Variable length argument list used to instantiate the class.
            **kwargs: Variable length keyword argument dict to instantiate the class.

        Return:
            A new or already existing instance of the given class, always the same and unique instand as expected from 
            the Singleton's design pattern.
        """

        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

    @classmethod
    def __instancecheck__(mcls: Type[T], instance: T) -> bool:
        """Implement behavior on instance check."""

        if instance.__class__ is mcls:
            return True
        else:
            return isinstance(instance.__class__, mcls)


def createNewAthenaPackageHierarchy(rootDirectory: str) -> None:
    """Create a new Athena's package hierarchy at the given root directory.

    Parameters:
        rootDirectory: The root directory at which to create a new Athena's package hierarchy.
    
    .. deprecated:: 1.0.0
    """

    if os.path.exists(rootDirectory):
        raise OSError('`{}` already exists. Abort {0} package creation.'.format(AtConstants.PROGRAM_NAME))
    os.mkdir(rootDirectory)

    blueprintDirectory = os.path.join(rootDirectory, 'blueprints')
    os.mkdir(blueprintDirectory)
    processesDirectory = os.path.join(rootDirectory, 'processes')
    os.mkdir(processesDirectory)

    initPyFiles = (
        os.path.join(rootDirectory, '__init__.py'),
        os.path.join(blueprintDirectory, '__init__.py'),
        os.path.join(processesDirectory, '__init__.py')
        )
    
    header = '# Generated from {0} - Version {1}\n'.format(AtConstants.PROGRAM_NAME, AtConstants.VERSION)
    for file in initPyFiles:
        with open(file, 'w') as file:
            file.write(header)

    dummyProcessPath = os.path.join(processesDirectory, 'dummyProcess.py')
    with open(dummyProcessPath, 'w') as file:
        file.write(header + AtConstants.DUMMY_PROCESS_TEMPLATE)

    dummyBlueprintPath = os.path.join(blueprintDirectory, 'dummyBlueprint.py')
    with open(dummyBlueprintPath, 'w') as file:
        file.write(header + AtConstants.DUMMY_BLUEPRINT_TEMPLATE)


T = TypeVar("T")
R = TypeVar("R")

def mapMapping(function: Callable[[T], R], mapping: Mapping[T]) -> Mapping[R]:
    """Execute the given function on all values inside the given Mapping object.

    Parameters:
        function: The function to call for each value and sub-value of the given mapping.
        mapping: The Mapping object to recursively iterate on and execute the function for each of it's values.

    Return:
        Equivalent of the input mapping with all values and sub-values modified through the given function.

    Notes:
        This method will iterate recursively on the mapping and it's values from top to bottom.
    """

    newMapping = {}
    for key, value in mapping.items():
        if isinstance(value, Mapping):
            newMapping[key] = mapMapping(function, value)
        elif isinstance(value, Sequence):
            newMapping[key] = mapSequence(function, value)
        else:
            newMapping[key] = function(value)
    
    return type(mapping)(newMapping)
          

def mapSequence(function: Callable[[T], R], sequence: Sequence[T]) -> Sequence[R]:
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
            newSequence.append(mapSequence(function, each))
        elif isinstance(each, Mapping):
            newSequence.append(mapMapping(function, each))
        else:
            newSequence.append(function(each))
    
    return type(sequence)(newSequence)


def deepMap(function: Callable[[T], R], collection: Collection[T]) -> Collection[R]:
    """Execute the given function on all values inside the given Collection object.

    This will automatically call :func:`~mapSequence` or :func:`~mapMapping` based on the input collection or sub-collection
    inside it. It should be prefered to those method when you're not aware of your input collection type or that this type
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
        return mapSequence(function, collection)
    elif isinstance(collection, Mapping):
        return mapMapping(function, collection)
