"""
Helpers for resource creation.
"""

import copy

from gavo import base


class DBTableError(base.Error):
	"""is raised when a manipulation of an on-disk table fails.

	It always has a qName attribute containing the qualified name of
	the table causing the trouble.
	"""
	def __init__(self, msg, qName, hint=None):
		base.Error.__init__(self, msg, hint=hint)
		self.qName = qName
		self.args = [msg, qName]


class ParseOptions(object):
	"""see getParseOptions.
	"""
	def change(self, **kwargs):
		"""returns a copy of self with the keyword parameters changed.

		Trying to add attributes in this way will raise an AttributeError.

		>>> p = parseValidating.change(validateRows=False)
		>>> p.validateRows
		False
		>>> p.change(gulp=1)
		Traceback (most recent call last):
		AttributeError: ParseOptions instances have no gulp attributes
		"""
		newInstance = copy.copy(self)
		for key, val in kwargs.iteritems():
			if not hasattr(newInstance, key):
				raise AttributeError("%s instances have no %s attributes"%(
					newInstance.__class__.__name__, key))
			setattr(newInstance, key, val)
		return newInstance


def getParseOptions(validateRows=True, updateMode=False, doTableUpdates=False,
		batchSize=1024, maxRows=None, keepGoing=False, dropIndices=False,
		dumpRows=False, metaOnly=False, buildDependencies=True):
	"""returns an object with some attributes set.

	This object is used in the parsing code in dddef.  It's a standin
	for the the command line options for tables created internally and
	should have all attributes that the parsing infrastructure might want
	from the optparse object.

	So, just configure what you want via keyword arguments or use the
	prebuilt objects parseValidating and and parseNonValidating below.

	See commandline.py for the meaning of the attributes.

	The exception is buildDependencies.  This is true for most internal
	builds of data (and thus here), but false when we need to manually
	control when dependencies are built, as in user.importing and
	while building the dependencies themselves.
	"""
	po = ParseOptions()
	po.validateRows = validateRows
	po.systemImport = False
	po.keepGoing = keepGoing
	po.updateMode = updateMode
	po.dumpRows = dumpRows
	po.doTableUpdates = doTableUpdates
	po.batchSize = batchSize
	po.maxRows = maxRows
	po.dropIndices = dropIndices
	po.metaOnly = metaOnly
	po.buildDependencies = buildDependencies
	return po


parseValidating = getParseOptions(validateRows=True)
parseNonValidating = getParseOptions(validateRows=False)


def _test():
	import doctest, common
	doctest.testmod(common)


if __name__=="__main__":
	_test()
