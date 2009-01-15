"""
Helpers for resource creation.
"""

from gavo import base


class ResourceError(base.Error):
	pass


class DbTableError(ResourceError):
	"""is raised when a manipulation of an on-disk table fails.

	It always has a qName attribute containing the qualified name of
	the table causing the trouble.
	"""
	def __init__(self, msg, qName):
		ResourceError.__init__(self, msg)
		self.qName = qName


class ParseOptions(object):
	"""see getParseOptions.
	"""


def getParseOptions(validateRows=True, updateMode=False, doTableUpdates=False,
		batchSize=1024):
	"""returns an object with some attributes set.

	This object is used in the parsing code in dddef.  It's a standin
	for the the command line options for tables created internally and
	should have all attributes that the parsing infrastructure might want
	from the optparse object.

	So, just configure what you want via keyword arguments or use the
	prebuilt objects parseValidating and and parseNonValidating below.

	See commandline.py for the meaning of the attributes.
	"""
	po = ParseOptions()
	po.validateRows = validateRows
	po.systemImport = False
	po.ignoreBadSources = False
	po.updateMode = updateMode
	po.dumpRows = False
	po.doTableUpdates = doTableUpdates
	po.batchSize = batchSize
	return po


parseValidating = getParseOptions(validateRows=True)
parseNonValidating = getParseOptions(validateRows=False)
