from athena import AtConstants
from athena import AtUtils


class AthenaException(BaseException):
    pass


class AtProcessExecutionInterrupted(RuntimeError):
    pass
