from athena import AtCore, AtConstants

import random
import time

__all__ = ('AthenaExampleProcess',)


class AthenaExampleProcess(AtCore.Process):
    """

    """

    RANDOM_ISSUES: AtCore.Thread = AtCore.Thread(
        title='This is an example thread:',
    )

    iterations: AtCore.IntParameter = AtCore.IntParameter(100, minimum=1, maximum=1e6)
    duration: AtCore.FloatParameter = AtCore.FloatParameter(5.0, minimum=0.0, maximum=60.0)

    def check(self) -> None:
        '''
        '''

        self.clearFeedback()  # Reset the check from it's previous run.

        self.setProgressText('Checking...')  # Set a text to display while checking.
        
        progress = 100 / (self.iterations or 1)  # Compute the progress increment per iteration.
        for i in range(self.iterations):
            self.listenForUserInteruption()  # Allow user interuption during check.
            self.setProgress(i * progress)  # Increment the displayed progress value to give the user some real-time feedback.

            time.sleep(self.duration/self.iterations)  # Fake that something happen so the check process for some time.

            # Randomly (50%) add feedbacks to the process.
            if random.choice((True, False)):
                feedback = AtCore.Feedback('[Placeholder]', True)
                self.addFeedback(self.RANDOM_ISSUES,
                    feedback
                )

        # Toggle the Thread's state based on it's feedbacks.
        if self.hasFeedback(self.RANDOM_ISSUES):
            self.setFail(self.RANDOM_ISSUES)
        else:
            self.setSuccess(self.RANDOM_ISSUES)
