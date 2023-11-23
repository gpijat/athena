import os
import re
import sys
import pkgutil
import logging
import importlib
import traceback
import platform

from types import ModuleType, FunctionType
from typing import TypeVar, Type, Optional, Any, Iterator, Tuple, Dict, Hashable

from collections.abc import Collection
from collections.abc import Sequence
from collections.abc import Mapping

try:
    from importlib import reload  # Python 3.4+
except ImportError:
    from imp import reload  # Python 3.0 - 3.3

from athena import AtConstants

LOGGER = logging.getLogger(AtConstants.PROGRAM_NAME)
LOGGER.setLevel(10)


def iterBlueprintsPath(package: str, software: str = 'standalone', verbose: bool = False) -> Iterator[str]:
    """Retrieve available envs from imported packages.

    Retrieve the currently imported packages path that match the pattern to works with this tool: {program}_{prod}
    Then, generate the usual path to the env using the package, the current software for the first sub package and env to the 
    desired package.

    parameters
    -----------
    package: str
        This is the string path to a python package.
    software: str, optional
        The software for which to get envs. (default: 'standalone')
    verbose: bool
        Define if the function should log informations about its process.

    Returns
    --------
    dict
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
    that is {PROGRAM_NAME}_???

    parameters
    -----------
    verbose: bool
        Define if the function should log informations about its process. (default: False)

    Returns
    --------
    dict
        Return a dict containing all package that match the pattern of the tool
        The key is the prod and the value is a dict containing the module object and its str path.
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

    moduleStrPath, _, processName = processStrPath.rpartition('.')
    module = importFromStr(moduleStrPath)

    if not hasattr(module, processName):
        raise ImportError('Module {0} have no class named {1}'.format(module.__name__, processName))
    
    return module


#WATCME: Not used anymore.
def getSoftware() -> str:
    """Get the current software from which the tool is executed.

    Fallback on different instruction an try to get the current running software.
    If no software are retrieved, return the default value.

    Returns
    --------
    str
        Return the current software if any are find else the default value.
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


def getOs() -> str:
    return platform.system().replace('Darwin', 'MacOs')


#WATHCME: Not used anymore.
def _formatSoftware(softwarePath: str) -> str:
    """Check if there is an available software str in the hiven Path

    parameters
    -----------
    softwarePath: str
        The path to a software executable is expected here, but this works with any str.
    verbose: bool
        Define if the function should log informations about its process. (default: False)

    Returns
    --------
    str
        Return the software found in softwarePath if there is one or an empty string.
    """
    path = str(softwarePath).lower()
    for soft, regexes in AtConstants.AVAILABLE_SOFTWARE.items():
        for regex in regexes:
            match = re.search(r'\{0}?{1}\{0}?'.format(os.sep, regex), path)
            if match:
                return soft
            
    return ''


def pythonImportPathFromPath(path: str) -> str:
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

    parameters
    -----------
    moduleStr: str
        Path to a module to import.
    verbose: bool
        Define if the function should log informations about its process. (default: False)

    Returns
    --------
    str
        Return the loaded module or None if fail.
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
    return reload(module)


def moduleFromStr(pythonCode: str, name: str = 'DummyAthenaModule') -> ModuleType:
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


def importPathStrExist(moduleStr: str) -> bool:
    return bool(pkgutil.find_loader(moduleStr))


# could be only with instance of class. (get inheritance and return dict with each one as key and list of overriden as value)
T = TypeVar('T')
def getOverridedMethods(instance: T, cls: Type[T]) -> Dict[str, FunctionType]:
    """Detect all methods that have been overridden from a subclass of a class

    Parameters
    -----------
    instance: object
        An instance of a subclass of cls.
    cls: object
        An object type to compare the instance to.

    Returns
    --------
    list
        Return a list containing all method that have been overridden from the instance in the given class.
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

    Parameters
    -----------
    toSplit: str
        The string to split and format

    Returns
    --------
    str
        Return the given string with spaces.
    """

    matches = re.finditer('(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', toSplit)
    splitString = []

    # Index of beginning of slice
    previous = 0
    for match in matches:
        # get slice
        splitString.append(toSplit[previous:match.start()])

        # advance index
        previous = match.start()

    # get remaining string
    splitString.append(toSplit[previous:])

    return ' '.join(splitString)


# class lazyProperty(object):
#     def __init__(self, fget: FunctionType) -> None:
#         self.fget = fget

#     def __get__(self, instance: T, cls: Type[T]) -> Any:
#         value = self.fget(instance)
#         setattr(instance, self.fget.__name__, value)
#         return value


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

    @classmethod
    def __instancecheck__(mcls, instance):
        if instance.__class__ is mcls:
            return True
        else:
            return isinstance(instance.__class__, mcls)


class SearchPattern(object):

    MATCH_NONE: str = '^$'

    TEXT_PATTERN: str = r'(?!#|@)(^.+?)(?:(?=\s(?:#|@)[a-zA-Z]+)|$|\s$)'
    TEXT_REGEX: re.Pattern = re.compile(TEXT_PATTERN)

    HASH_PATTERN: str = r'(?:^|\s)?#([a-zA-Z\s]+)(?:\s|$)'
    HASH_REGEX: re.Pattern = re.compile(HASH_PATTERN)

    CATEGORY_PATTERN: str = r'(?:^|\s)?@([a-zA-Z\s]+)(?:\s|$)'
    CATEGORY_REGEX: re.Pattern = re.compile(CATEGORY_PATTERN)

    def __init__(self, rawPattern: str = MATCH_NONE) -> None:

        self._rawPattern = rawPattern

        self._pattern: str = None
        self._regex: re.Pattern = None
        self._isValid: bool = False

        self.setPattern(rawPattern)

    @property
    def pattern(self) -> str:
        return self._pattern

    @property
    def regex(self) -> re.Pattern:
        return self._regex      

    @property
    def isValid(self) -> bool:
        return self._isValid

    def setPattern(self, pattern: str) -> None:
        match = self.TEXT_REGEX.match(pattern)
        self._pattern = pattern = '.*' if not match else match.group(0)

        try:
            self._regex = re.compile(pattern)
            self._isValid = True
        except Exception:
            self._regex = re.compile(self.MATCH_NONE)
            self._isValid = False

    def iterHashTags(self) -> Iterator[str]:
        for match in self.HASH_REGEX.finditer(self._rawPattern):
            yield match.group(1)

    def iterCategories(self) -> Iterator[str]:
        for match in self.CATEGORY_REGEX.finditer(self._rawPattern):
            yield match.group(1)        

    def search(self, text: str) -> Optional[re.Match]:
        if not self._isValid:
            return None

        return self._regex.search(text)


def formatException(exception: Exception) -> str:
    traceback_ = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    return '# ' + '# '.join(traceback_.rstrip().splitlines(True))


def createNewAthenaPackageHierarchy(rootDirectory: str) -> None:

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


def mapMapping(function, mapping):
    newMapping = {}
    for key, value in mapping.items():
        if isinstance(value, Mapping):
            newMapping[key] = mapMapping(function, value)
        elif isinstance(value, Sequence):
            newMapping[key] = mapSequence(function, value)
        else:
            newMapping[key] = function(value)
    return type(mapping)(newMapping)
            
def mapSequence(function, sequence):

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

def deepMap(function, collection):
    if not isinstance(collection, Collection):
        raise TypeError('{} must be a subtype of {}. (Sequence: {} or Mapping: {})'.format(collection, Collection, Sequence, Mapping))
    if not callable(function):
        raise TypeError('{} object is not callable')

    if isinstance(collection, Sequence):
        return mapSequence(function, collection)
    elif isinstance(collection, Mapping):
        return mapMapping(function, collection)
