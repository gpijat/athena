import sys
import unittest

from athena import AtCore, AtUtils, AtConstants

# if big_O module is available, load it.
try:
    import big_O
except ImportError:
    big_O = None


# ---------------------------------------------------------------------------------------------------------- Test Process


class TestProcess(unittest.TestCase):

    PROCESS = None

    def setUp(self):
        pass

    def test_isProcessSubclass(self):
        self.assertTrue(issubclass(self.PROCESS.__class__, AtCore.Process), msg='A Process must inherit from Athena.AtCore.Process')

    def test_nonOverridedCoreMethods(self):
        nonOverridableAttributesOverrided = self.PROCESS.__class__._Process__NON_OVERRIDABLE_ATTRIBUTES.intersection(set(self.PROCESS.__class__.__dict__.keys()))
        self.assertFalse(bool(nonOverridableAttributesOverrided), msg='Some methods are used for you to interact with the process, or for internal purpose, you should not override them.')

    def test_checkIsImplemented(self):
        self.assertTrue(hasattr(self.PROCESS, 'check'), msg='The process must at least define a `check` method to be able to find errors.')

    def test_hasAtLeastOneThread(self):
        self.assertTrue(bool(self.PROCESS.threads), msg='At least one Thread is requireds for the process to catch errors.')

    def test_processIsDocumented(self):
        self.assertTrue(bool(self.PROCESS._doc_), msg='The process must be documented, write a docstring or define the _doc_ class attribute.')


def __testProcess():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestProcess))
    unittest.TextTestRunner(verbosity=2).run(suite)


def testProcessFromPath(processStrPath, args=[], kwargs={}):
    """Method to process unit tests on a process str

    """
    module, process = AtUtils.importProcessPath(processStrPath)
    TestProcess.PROCESS = process(*args, **kwargs)
    __testProcess()

    
def testFromProcessInstance(processInstance):
    TestProcess.PROCESS = processInstance
    __testProcess()


# ---------------------------------------------------------------------------------------------------------- Test Env


class TestEnv(unittest.TestCase):

    ENV = None

    def setUp(self):
        self.header = ()
        if hasattr(self.ENV, 'header'):
            self.header = getattr(self.ENV, 'header')
        
        self.register = {}
        if hasattr(self.ENV, 'register'):
            self.register = getattr(self.ENV, 'register')

        self.settings = type(AtConstants.SETTINGS_TEMPLATE)()
        if hasattr(self.ENV, 'settings'):
            self.settings = getattr(self.ENV, 'settings')

    def __iterProcessKey(self, processKey):
        for key, value in self.register.items():
            processValue = value.get(processKey, None)
            if processValue is None:
                continue
            yield key, processValue

# - Test Header
    def test_headerIsDefined(self):
        self.assertTrue(bool(self.header), msg='The header must be the defined in the env to define execution order.')
# - #
# - Test Register
    def test_registerIsDefined(self):
        self.assertTrue(bool(self.register), msg='The Env must contain a valid register that define the processes.')

    def test_allRegisterKeysAreDefinedInHeader(self):
        self.assertTrue(all(key in self.header for key in self.register), msg='All keys in the register must be defined in the header.')

    def test_registerKeysExists(self):
        errors = set()
        for key, blueprint in self.register.items():
            for bpKey, bpValue in blueprint.items():
                if bpKey not in AtConstants.BLUEPRINT_TEMPLATE:
                    errors.add(key)
        self.assertFalse(bool(errors), msg='Theses blueprints contains unkown keys. ({0})'.format(', '.join(errors)))
# - #
# - Test Processes
    def test_allRegisterKeyHaveAProcessPath(self):
        errors = []
        for key, blueprint in self.register.items():
            if not 'process' in blueprint:
                errors.append(key)
        self.assertFalse(bool(errors), msg='Defining a process path (full python import path) is required. - ({0})'.format(', '.join(errors)))

    def test_allRegisterKeyProcessPathAreValid(self):
        errors = []
        for key, blueprint in self.register.items():
            if not AtUtils.importPathStrExist(blueprint.get('process', '').rpartition('.')[0]):
                errors.append(key)
        self.assertFalse(bool(errors), msg='Process path for these register entries are not reachable. - ({0})'.format(', '.join(errors)))
# - #
# - Test links
    def test_linksDataTypeAreCompliant(self):
        errors = []
        for key, links in self.__iterProcessKey('links'):
            if not isinstance(links, (tuple, list)):
                errors.append(key)
                continue

            for linkTuple in links:
                if len(linkTuple) != 3:
                    errors.append(key)

        self.assertFalse(bool(errors), msg='Link must be a tuple of 3 values. The target process, the source method and the target method. - ({0})'.format(', '.join(errors)))

    def test_linksTargetAreInRegister(self):
        errors = []
        for key, links in self.__iterProcessKey('links'):
            self.assertIsInstance(links, (tuple, list), msg='See `test_linksDataTypeAreCompliant`. Abort without completing test.')

            for linkTuple in links:
                if linkTuple[0] not in self.register:
                    errors.append(key)

        self.assertFalse(bool(errors), msg='Link target must be in the register. ({0})'.format(', '.join(errors)))

    def test_linksSourceAndTargetMethodsAreValid(self):
        errors = []
        for key, links in self.__iterProcessKey('links'):
            self.assertIsInstance(links, (tuple, list), msg='See `test_linksDataTypeAreCompliant`. Abort without completing test.')

            for linkTuple in links:
                if linkTuple[1] not in AtCore.Link:
                    errors.append(key)
                if linkTuple[2] not in AtCore.Link:
                    errors.append(key)

        self.assertFalse(bool(errors), msg='Link source and/or target methods are not linkable. ({0})'.format(', '.join(errors)))
# - # 
# - Test arguments
    def test_argumentsDataTypeAreCompliant(self):
        errors = []
        for key, argumentsData in self.__iterProcessKey('arguments'):
            if not isinstance(argumentsData, dict):
                errors.append(key)
                continue

            for method, arguments in argumentsData.items():
                if not isinstance(arguments, (tuple, list)) or len(arguments) != 2:
                    errors.append(key)
                    continue
                if not isinstance(arguments[0], (tuple, list)) or not isinstance(arguments[1], dict):
                    errors.append(key)
                    continue

        self.assertFalse(
            bool(errors), 
            msg='Arguments type for these blueprints are not compliant. ({0})'.format(', '.join(errors))
        )

    def test_argumentsMethodsAreValid(self):
        errors = []
        for key, argumentsData in self.__iterProcessKey('arguments'):
            self.assertIsInstance(argumentsData, dict, msg='See `test_argumentsDataTypeAreCompliant`. Abort without completing test.')

            for method, arguments in argumentsData.items():
                if method not in ('__init__', 'check', 'fix', 'tool'):
                    errors.append(key)
                    continue

        self.assertFalse(
            bool(errors), 
            msg='Arguments keys must be one of these methods: `__init__`, `check`, `fix`, `tool`. ({0})'.format(', '.join(errors))
        )
# - #
# - Test Status overrides
    def test_statusOverridesTypeAreCompliant(self):
        errors = []
        for key, statusOverridesData in self.__iterProcessKey('statusOverrides'):
            if not isinstance(statusOverridesData, dict):
                errors.append(key)
                continue

            for threadName, overrides in statusOverridesData.items():
                if not isinstance(threadName, (str, unicode)):
                    errors.append(key)
                    continue

                if not isinstance(overrides, dict):
                    errors.append(key)
                    continue

        self.assertFalse(
            bool(errors), 
            msg='Status overrides type for these blueprints are not compliant. ({0})'.format(', '.join(errors))
        )

    def test_statusOverridesAreStatusSubclasses(self):
        errors = []
        for key, statusOverridesData in self.__iterProcessKey('statusOverrides'):
            self.assertIsInstance(statusOverridesData, dict, msg='See `test_statusOverridesTypeAreCompliant`. Abort without completing test.')

            for threadName, overrides in statusOverridesData.items():
                self.assertIsInstance(overrides, dict, msg='See `test_statusOverridesTypeAreCompliant`. Abort without completing test.')

                for statusType, newStatus in overrides.items():
                    if statusType not in (AtCore.Status.FailStatus, AtCore.Status.SuccessStatus):
                        errors.append(key)
                        continue

                    if not isinstance(newStatus, (AtCore.Status.FailStatus, AtCore.Status.SuccessStatus)):
                        errors.append(key)
                        continue

        self.assertFalse(
            bool(errors), 
            msg='Status overrides are not instances of AtCore.Status.FailStatus or AtCore.Status.SuccessStatus ordered by their types. ({0})'.format(', '.join(errors))
        )
# - #


def __testEnv():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestEnv))
    unittest.TextTestRunner(verbosity=2).run(suite)


def testEnvFromPath(contextStrPath, envStr):
    """Method to process unit tests on a process instance
    """
    envs = AtUtils.getEnvs(contextStrPath, software=AtUtils.getSoftware())
    env = envs.get(envStr)

    TestEnv.ENV = AtUtils.importFromStr(env['import'])
    __testEnv()


# ---------------------------------------------------------------------------------------------------------- Test __main__


if __name__ == '__main__':
    
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestProcess))

    unittest.TextTestRunner(verbosity=1).run(suite)
