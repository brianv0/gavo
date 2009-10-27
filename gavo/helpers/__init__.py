"""
Code to support user scripts working on DC data holdings.
"""

from gavo.helpers.filestuff import iterSources, FileRenamer
from gavo.helpers.fitstricks import replacePrimaryHeader
from gavo.helpers.processing import (procmain, HeaderProcessor, FileProcessor,
	AnetHeaderProcessor, CannotComputeHeader)
