
class AthenaException(BaseException):
    """Base Athena Exception, must be inherited by all Athena's Exceptions."""

    pass


class AtProcessExecutionInterrupted(AthenaException, RuntimeError):
    """Exception raised when a process execution is interrupted by the user"""

    pass


class AtParameterValidationError(AthenaException, ValueError):
    """Exception raised when a Parameter value or a spec override does not pass validation."""

    pass


class AtParameterTypeError(AthenaException, KeyError):
    """Exception raised when a Parameter type name is not registered in the ParameterFactory."""

    pass


class AtParameterNotFoundError(AthenaException, KeyError):
    """Exception raised when a Blueprint override references a Parameter name that does not exist on the Process."""

    pass


class AtParameterPolicyError(AthenaException, PermissionError):
    """Exception raised when an action is forbidden by a Parameter's ParameterPolicy.

    This covers setting a locked Parameter, a Blueprint trying to loosen the author's policy, and a
    Blueprint trying to override the spec of a Parameter that is not Blueprint configurable.
    """

    pass
