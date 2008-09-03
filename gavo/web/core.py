"""
This module defines the Core, the standard data structure for handling
requests from the web and from elsewhere.

It also provides a registry for cores.  You should register a core
that's supposed to be accessible from resource descriptors using 
registerCore, and you can query that registry using getStandardCore.
"""

import sets
import weakref

import gavo
from gavo import record


class Core(record.Record):
	"""is something that does computations for a service.

	Its run method takes a DataSet and returns a deferred firing another
	DataSet.

	The input data set should, in general, have a docrec containing 
	some keys from avInputKeys (but, e.g., ComputingCores also look
	at the primary table); the returned DataSet has a primary table
	with fields with names from avOutputKeys.

	Cores knowing more about their data should provide methods getInputFields
	and getOutputFields returning sequences of DataFields.

	Cores can only exist as a part of a service, and services register
	themselves with their cores on adoption.
	"""
	avInputKeys = sets.ImmutableSet()
	avOutputKeys = sets.ImmutableSet()

	def __init__(self, additionalFields={}, initvals={}):
		fields = {
			"outputFields": record.ListField,
			"renderer": record.DictField,    # additional nevow renderers in 
				# the core result.
			"service": None,        # filled in on adoption
		}
		fields.update(additionalFields)
		super(Core, self).__init__(fields, initvals=initvals)

	def __repr__(self):
		return "<%s at %s>"%(self.__class__.__name__, id(self))
	
	def __str__(self):
		return repr(self)

	def set_service(self, svc):
		if self.dataStore["service"]:
			raise gavo.Error("Core cannot be re-adopted")
		self.dataStore["service"] = weakref.proxy(svc)

	def run(self, inputData, queryMeta):
		"""returns a twisted deferred firing the result of running the core on
		inputData.
		"""
		defer.succeed("Core without run")

	def getOutputFields(self):
		return []

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
