
class AthenaException(BaseException):
    """Base Athena Exception, must be inherited by all Athena's Exceptions."""

    pass


class AtProcessExecutionInterrupted(AthenaException, RuntimeError):
    """Exception raised when a process execution is interrupted by the user"""

    pass
