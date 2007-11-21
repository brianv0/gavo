"""
This module defines the Core, the standard data structure for handling
requests from the web and from elsewhere.

It also provides a registry for cores.  You should register a core
that's supposed to be accessible from resource descriptors using 
registerCore, and you can query that registry using getStandardCore.
"""

from gavo import record


class Core(record.Record):
	"""is something that does computations for a service.
	"""
	def __init__(self, additionalFields={}, initvals={}):
		fields = {
			"table": record.RequiredField,
		}
		fields.update(additionalFields)
		super(Core, self).__init__(fields, initvals=initvals)


	def run(self, inputData, queryMeta):
		"""returns a twisted deferred firing the result of running the core on
		inputData.
		"""

_coresRegistry = {}

def registerCore(name, klass):
	_coresRegistry[name] = klass

def getStandardCore(coreName):
	return _coresRegistry[coreName]


_condDescRegistry = {}

def registerCondDesc(name, condDesc):
	_condDescRegistry[name] = condDesc

def getCondDesc(name):
	return _condDescRegistry[name]
