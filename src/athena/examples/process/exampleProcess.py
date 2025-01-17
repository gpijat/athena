from athena import atCore

import random
import time

__all__ = ('AthenaExampleProcess',)


class AthenaExampleProcess(atCore.Process):
    """This is an Example check, it won't do anything else than generating `fake` errors.

    This check will iterate as much as the `iterations` value is set and generate fakes errors to showcase the 
    framework behavior and how to write a simple check Process.
    """

    RANDOM_ISSUES: atCore.Thread = atCore.Thread(
        title='This is an example thread:',
    )

    iterations: atCore.IntParameter = atCore.IntParameter(100, minimum=1, maximum=1000)
    duration: atCore.FloatParameter = atCore.FloatParameter(5.0, minimum=0.0, maximum=60.0)

    def check(self) -> None:
        """Iterate as much as :obj:`AthenaExampleProcess.iterations` dictate to generate example feedbacks.
        
        The total check duration is defined with the :obj:`AthenaExampleProcess.duration` :class:`~Parameter`, it will
        wait for a fraction of this duration per iteration so that it reach this total duration at the end of all iterations.
        """

        self.clear_feedback()  # Reset the check from it's previous run.

        self.set_progress_text('Checking...')  # Set a text to display while checking.
        
        progress = 100 / (self.iterations or 1)  # Compute the progress increment per iteration.
        for i in range(self.iterations):
            self.listen_for_user_interruption()  # Allow user interruption during check.
            self.set_progress(i * progress)  # Increment the displayed progress value to give the user some real-time feedback.

            time.sleep(self.duration/self.iterations)  # Fake that something happen so the check process for some time.

            # Randomly (50%) add feedbacks to the process.
            if random.choice((True, False)):
                feedback = atCore.Feedback('[Placeholder]', True)
                self.add_feedback(self.RANDOM_ISSUES,
                    feedback
                )

        # Toggle the Thread's state based on it's feedbacks.
        if self.has_feedback(self.RANDOM_ISSUES):
            self.set_fail(self.RANDOM_ISSUES)
        else:
            self.set_success(self.RANDOM_ISSUES)
