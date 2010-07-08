"""
Code to support DC-external code (preprocessing, testing...)
"""

from gavo.helpers.filestuff import iterSources, FileRenamer
from gavo.helpers.fitstricks import replacePrimaryHeader
from gavo.helpers.processing import (procmain, HeaderProcessor, FileProcessor,
	AnetHeaderProcessor, CannotComputeHeader)
