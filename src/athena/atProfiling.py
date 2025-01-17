from __future__ import annotations

import cProfile
import os
import pstats
import re
import tempfile
import time
from types import FunctionType
from typing import Optional, Union, Any, Dict, List, Tuple, Sequence


class _AtProcessProfile(object):
    """Profiler that allow to profile the execution of `athena.atCore.Process`"""

    # Match integers, floats (comma or dot) and slash in case there is a separation for primitive calls.
    DIGIT_PATTERN: str = r'([0-9,.\/]+)'
    DIGIT_REGEX: re.Pattern = re.compile(DIGIT_PATTERN)

    CATEGORIES: Tuple[Tuple[str, str], ...] = (
        ('ncalls', 'Number of calls. Multiple numbers (e.g. 3/1) means the function recursed. it reads: Calls / Primitive Calls.'),
        ('tottime', 'Total time spent in the function (excluding time spent in calls to sub-functions).'), 
        ('percall', 'Quotient of tottime divided by ncalls.'), 
        ('cumtime', 'Cumulative time spent in this and all subfunctions (from invocation till exit). This figure is accurate even for recursive functions.'), 
        ('percall', 'Quotient of cumtime divided by primitive calls.'), 
        ('filename:lineno(function)', 'Data for each function.')
    )

    def __init__(self) -> None:
        """Initialize a Process Profiler and define the default instance attributes."""
        self._profiles: Dict[str, Dict[str, Union[float, List[Tuple[str, ...]]]]] = {} 

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Get a profile log from the given key, or default if key does not exists.
        
        Parameters:
            key: The key to get data from in the profiler's profile data.
            default: The default value to return in case the key does not exists.

        Return:
            The data stored at the given key if exists else the default value is returned.
        """

        return self._profiles.get(key, default)

    def _get_call_data_list(self, call_data: Sequence[str]) -> None:
        """Format and split `cProfile.Profiler` call data list (each value in the list must be one line.)

        This will mostly remove heading or trailing spaces and return a list of tuple where each values in the
        string is now an entry in the tuple. The order is the same than `~_AtProcessProfile.CATEGORIES`.
        
        Parameters:
            call_data: Call entries from a `cProfile.Profiler` run.
        """

        data_list = []
        for call in call_data:
            call_data = []

            filtered_data = tuple(filter(lambda x: x, call.strip().split(' ')))
            if not filtered_data:
                continue
            call_data.extend(filtered_data[0:5])

            value = ' '.join(filtered_data[5:len(filtered_data)])
            call_data.append(float(value) if value.isdigit() else value)

            data_list.append(tuple(call_data))

        return data_list

    def profile_method(self, method: FunctionType, *args: Any, **kwargs: Any) -> Any:
        """Profile the given method execution and return it's result. The profiling result will be stored in the 
        object.

        Try to execute the given method with the given args and kwargs and write the result in a temporary file.
        The result will then be read and each line splitted to save a dict in the object `_profiles` attribute using
        the name of the given method as key.
        This dict will hold information like the time when the profiling was done (key = `time`, it can allow to not 
        update data in a ui for instance), the total number of calls and obviously a tuple with each call data (`calls`).
        The raw stats result is also saved under the `rawStats` key if the user want to use it directly.
        
        Parameters:
            method: A callable for which we want to profile the execution and save new data.
            *args: The arguments to call the method with.
            **kwargs: The keyword arguments to call the method with.

        Return:
            The result of the given method with the provided args and kwargs.
        """

        assert callable(method), '`method` must be passed a callable argument.'

        profile = cProfile.Profile()

        # Run the method with `cProfile.Profile.runcall` to profile it's execution only. We define exception before
        # executing it, if an exception occur the except statement will be processed and `exception` will be updated
        # from `None` to the exception that should be raised.
        # At the end of this method exception must be raised in case it should be catch at upper level in the code.
        # This allow to not skip the profiling even if an exception occurred. Of course the profiling will not be complete
        # But there should be all information from the beginning of the method to the exception. May be useful for debugging.
        exception = None
        return_value = None
        try:
            return_value = profile.runcall(method, *args, **kwargs)
            self._profiles[method.__name__] = self.get_stats_from_profile(profile)
            return return_value

        except Exception as exception_:
            self._profiles[method.__name__] = self.get_stats_from_profile(profile)
            raise

    def get_stats_from_profile(self, profile: cProfile.Profile) -> Dict[str, Union[float, List[Tuple[str, ...]]]]:
        """

        """

        # Create a temp file and use it as a stream for the `pstats.Stats` This will allow us to open the file
        # and retrieve the stats as a string. With regex it's now possible to retrieve all the data in a displayable format
        # for any user interface.
        fd, tmp_file = tempfile.mkstemp()
        try:
            with open(tmp_file, 'w') as stat_stream:
                stats = pstats.Stats(profile, stream=stat_stream)
                stats.sort_stats('cumulative')  # cumulative will use the `cumtime` to order stats, seems the most relevant.
                stats.print_stats()
            
            with open(tmp_file, 'r') as stat_stream:
                stats_str = stat_stream.read()
        finally:
            # No matter what happen, we want to delete the file.
            # It happen that the file is not closed here on Windows so we also call `os.close` to ensure it is really closed.
            # WindowsError: [Error 32] The process cannot access the file because it is being used by another process: ...
            os.close(fd)
            os.remove(tmp_file)

        split = stats_str.split('\n')
        method_profile = {
            'time': time.time(),  # With this we will be able to not re-generate widget (for instance) if data have not been updated.
            'calls': self._get_call_data_list(split[5:-1]),
            'rawStats': stats_str,
        }

        # Take care of possible primitive calls in the summary for `ncalls`.
        summary = self.DIGIT_REGEX.findall(split[0])
        method_profile['tottime'] = summary[-1]
        if len(summary) == 3:
            method_profile['ncalls'] = '{0}/{1}'.format(summary[0], summary[1])
        else:
            method_profile['ncalls'] = summary[0]

        return method_profile
