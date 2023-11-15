PROGRAM_NAME = 'Athena'

VERSION = '0.0.0'

CHECK = 'check'

FIX = 'fix'

TOOL = 'tool'

AVAILABLE_DISPLAY_MODE = ('Alphabetically', 'Category', 'Header')

DEFAULT_CATEGORY = 'Other'

PROGRESSBAR_FORMAT = '  %p% - {0}'

# If types change, unit tests from AtTest must be updated too.
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

NO_DOCUMENTATION_AVAILABLE = '\nNo documentation available for this process.\n'

WIKI_LINK = 'https://github.com/gpijat/Athena'
REPORT_BUG_LINK = 'https://github.com/gpijat/Athena/issues'
