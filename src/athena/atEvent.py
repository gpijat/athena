from __future__ import annotations

import abc
from typing import Callable

from athena import atUtils


class AtEvent(object):
    """A simple event system for handling callbacks.

    This class allows you to create an event object that can be called like a function.
    Registered callbacks will be invoked when the event is called.
    """

    def __init__(self, name: str) -> None:
        """Initializes an AtEvent with a given name.

        Parameters:
            name: The name of the event.
        """

        self._name = name
        self._callbacks = []

    def __call__(self, *args, **kwargs) -> None:
        """Invokes all registered callbacks with the provided arguments."""

        for callback in self._callbacks:
            callback(*args, **kwargs)

    def add_callback(self, callback: Callable) -> bool:
        """Adds a callback function to the event's list of callbacks.

        Parameters:
            callback: The callback function to be registered.

        Return:
            True if the callback was successfully registered, False otherwise.

        Warnings:
            If the provided callback is not callable, a warning message is logged,
            and the callback is not registered.
        """

        if not callable(callback):
            atUtils.LOGGER.warning(
                'AtEvent "{0}" failed to register callback: Object "{1}" is not callable.'.format(self.name, callback)
            )
            return False

        self._callbacks.append(callback)

        return True


#: AtEvent triggered when a new Register instance is created.
register_created = AtEvent('RegisterCreated')

#: AtEvent triggered when Blueprints are reloaded.
blueprints_reloaded = AtEvent('BlueprintsReloaded')

#: AtEvent triggered when development mode is enabled.
dev_mode_enabled = AtEvent('DevModeEnabled')

#: AtEvent triggered when development mode is disabled.
dev_mode_disabled = AtEvent('DevModeDisabled')
