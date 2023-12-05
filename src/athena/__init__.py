import sys

from athena import AtCore, AtUtils, AtConstants, AtExceptions

__version__ = AtConstants.VERSION


def __moduleSort(value, tuple_):
    for prefix in tuple_:
        if value == prefix or value.startswith(prefix + '.'):
            return tuple_.index(prefix)
    return len(tuple_)


def _reload(main='__main__', toReload=(), verbose=False):
    """This hidden method is meant to reload all Athena related packages, especially to work on the tool core.

    It should not be used by artist and dev that work on processes. It should only be used to work on the API and 
    everything related to this package.

    Notes:
        Athena loads some modules that contains processes that are subprocess of AtCore.Process. But when this base class is reloaded 
        and not the subclass weird things can happen because we now get two different version of the same class and AtCore.Process can 
        become different to AtCore.Process.
        So the solution is to reload the baseClass and then the process classes to use the same version. This code will clean 
        all Athena related modules in the sys.modules() except submodules that will be reloaded.

    >>>import Athena
    >>>Athena._reload(__name__)
    """
    import time
    reloadStartTime = time.time()

    # ---------- Keep functions from AtUtils and constant from AtConstants available in local variables ---------- #
    # This function will clean all athena packages in sys.modules but we must keep these functions and constants 
    # available while the function is processing.
    _import = AtUtils.importFromStr

    # ---------- Get which modules must be deleted and which must be reloaded ---------- #
    toDelete = []
    toReimport = []
    for moduleName, module in sys.modules.items():
        # Skip all modules in sys.modules if they are not related to Athena and skip Athena main module that will be reloaded after.
        if moduleName == __name__:
            continue

        # Some name contains modules that are None. We prefer to get rid of them.
        if module is None:
            toDelete.append(moduleName)
            continue
        
        # We iterate over the Athena packages (packages containing processes) to know thoses that will ne to be reimported after.
        # If it does not match any of them, we only remove the package from sys.modules().
        for package in toReload:
            if moduleName.startswith(package):
                toDelete.append(moduleName)
                toReimport.append(moduleName)
                break

    toDelete.sort(key=lambda x: __moduleSort(x, toReload))
    toReimport.sort(key=lambda x: __moduleSort(x, toReload))

    # ---------- Delete all Athena modules ---------- #
    # Then we delete all modules that must be deleted. After this, this function is unable to call any of its imported Athena modules.
    for moduleName in toDelete:
        del sys.modules[moduleName]
        if verbose:
            print('Remove {}'.format(moduleName))

    # ---------- Reload current module if it is not main ---------- #
    # Reload the current module to be sure it will be up to date after. Except if the current module is '__main__'.
    if __name__ != '__main__':
        del sys.modules[__name__]
        sys.modules[__name__] = _import(__name__)

    # ---------- Reimport all user Athena packages ---------- #
    # Last, we reimport all Athena packages to make sure the API will detect it.
    for moduleName in toReimport:
        sys.modules[moduleName] = _import(moduleName)
        if verbose:
            print('Reload {}'.format(moduleName))

    # ---------- Restore the reloaded Athena main module in the __main__ module ---------- #
    if __name__ != '__main__':
        for moduleName in toReload:
            if hasattr(sys.modules[main], moduleName):
                setattr(sys.modules[main], moduleName, sys.modules[moduleName])  #FIXME: We can't update all name in local.
        # setattr(sys.modules[main], __name__, sys.modules[__name__])

    # ---------- Display reload time, even if there is no verbose ---------- #
    print('[Reloaded in {:.2f}s]'.format(time.time() - reloadStartTime))
