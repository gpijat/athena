from __future__ import annotations

from typing import Tuple


#: Project name string
PROGRAM_NAME: str = 'Athena'

#: Current version of the project. (Following simver convention)
VERSION: str = '1.0.0-beta'

#: Name constant for the `check` function to implement in Process Subclasses.
CHECK: str = 'check'

#: Name constant for the `fix` function to implement in Process Subclasses.
FIX: str = 'fix'

#: Name constant for the `tool` function to implement in Process Subclasses.
TOOL: str = 'tool'

#: All currently supported display modes.
AVAILABLE_DISPLAY_MODE: Tuple[str, str, str] = ('Alphabetically', 'Category', 'Header')

#: Default category for checks, this is used as a fallback an Blueprint should define an accurate category.
DEFAULT_CATEGORY: str = 'Other'

#: Format pattern for a QtWidgets.QProgressBar widget. It allows to add a custom text but force display of progress.
PROGRESSBAR_FORMAT: str = '  %p% - {0}'

#: Template for what's expected inside a Blueprint's description.
BLUEPRINT_TEMPLATE = \
{
    'process': '',  # String
    'category': '',  # String
    'arguments': {'': ([], {})},  # Dict with str key and tuple with a tuple and a dict as value.
    'tags': 0,  # Integer - AtCore.Tag
    'links': (('', '', '')),  # Tuple of tuple that contains three str, the target ID, the source method and the target method.
    'statusOverrides': {'': {}},  # Dict that contains name of the threads to overrides and a dict with new status indexed by status type.
    'settings': {}  # Dict with str key and values.
}

#: Template for what's supported in a Blueprints' setting.
SETTINGS_TEMPLATE = \
{
    'recheck': True,
    'orderFeedbacksByPriority': False,
    'feedbackDisplayWarning': True,
    'feedbackDisplayWarningLimit': 100,
    'allowRequestStop': True,
    'disableSelection': False,
    'globalContextManagers': (),
    'checkContextManagers': (),
    'fixContextManagers': (),
    'toolContextManagers': (),
}

#: Default text for Process documentation.
NO_DOCUMENTATION_AVAILABLE: str = '\nNo documentation available for this process.\n'

#: Link to the Github's Wiki page.
WIKI_LINK: str = 'https://github.com/gpijat/athena'

#: Link to the Github's issues page.
REPORT_BUG_LINK: str = 'https://github.com/gpijat/athena/issues'
