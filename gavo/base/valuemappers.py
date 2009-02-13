"""
ValueMappers, their factories and a registry.

A value mapper is a function used for serialization of (python) values
to strings, e.g., for HTML or VOTables.

They are produced by factories that in turn are registered in 
ValueMapperFactoryRegistries.  These can be queried for mappers for
a colProps value; this is a dictionary specifying certain properties
of a column and a sample value.

See ValueMapperFactoryRegistry.

The module also defines a defaultMFRegistry.  It should be suitable
for serializing to VOTables and similar data machine-oriented data 
formats.
"""

import urllib
import urlparse

from gavo import utils
from gavo.base import config
from gavo.base import typesystems


class ValueMapperFactoryRegistry(object):
	"""is an object clients can ask for functions fixing up values
	for encoding.

	A mapper factory is just a function that takes a "representative"
	instance and the column properties It must return either None
	(for "I don't know how to make a function for this combination
	of value and column properties") or a callable that takes a
	value of the given type and returns a mapped value.

	To add a mapper, call registerFactory.  To find a mapper for a
	set of column properties, call getMapper -- column properties should
	be an instance of ColProperties, but for now a dictionary with the
	right keys should mostly do.

	Mappers have both the sql type (in the sqltype entry) and the votable type
	(in the datatype and arraysize entries) to base their decision on.

	Mapper factories are tried in the reverse order of registration,
	and the first that returns non-None wins, i.e., you should
	register more general factories first.  If no registred mapper declares
	itself responsible, getMapper returns an identity function.  If
	you want to catch such a situation, you can use somthing like
	res = vmfr.getMapper(...); if res is vmfr.identity ...
	"""
	def __init__(self, factories=None):
		if factories is None:
			self.factories = []
		else:
			self.factories = factories[:]

	def getFactories(self):
		"""returns the list of factories.

		This is *not* a copy.  It may be manipulated to remove or add
		factories.
		"""
		return self.factories

	def registerFactory(self, factory):
		self.factories.insert(0, factory)

	def identity(self, val):
		return val

	def getMapper(self, colProps):
		"""returns a mapper for values with the python value instance, 
		according to colProps.

		This method may change colProps (which is the usual dictionary
		mapping column property names to their values).

		We do a linear search here, so you shouldn't call this function too
		frequently.
		"""
		for factory in self.factories:
			mapper = factory(colProps)
			if mapper:
				colProps["winningFactory"] = factory
				break
		else:
			mapper = self.identity
		return mapper


defaultMFRegistry = ValueMapperFactoryRegistry()
_registerDefaultMF = defaultMFRegistry.registerFactory


# Default nullvalues we use when we don't know anything about the ranges,
# by VOTable types.  The nullvalues should never be used, but the keys
# are used to recognize types with special nullvalue handling.
_defaultNullvalues = {
	"unsignedByte": 255,
	"char": '~',
	"short": -9999,
	"int": -999999999,
	"long": -9999999999,
}


def _intMapperFactory(colProps):
	if colProps["datatype"] in _defaultNullvalues:
		if not colProps.get("hasNulls"):
			return
		try:
			colProps.computeNullvalue()
		except AttributeError:
			colProps["nullvalue"] = _defaultNullvalues[colProps["datatype"]]
		def coder(val, nullvalue=colProps["nullvalue"]):
			if val is None:
				return nullvalue
			return val
		return coder
_registerDefaultMF(_intMapperFactory)


def _booleanMapperFactory(colProps):
	if colProps["dbtype"]=="boolean":
		def coder(val):
			if val:
				return "1"
			else:
				return "0"
		return coder
_registerDefaultMF(_booleanMapperFactory)


def _floatMapperFactory(colProps):
	if colProps["dbtype"]=="real" or colProps["dbtype"].startswith("double"):
		naN = float("NaN")
		def coder(val):
			if val is None:
				return naN
			return val
		return coder
_registerDefaultMF(_floatMapperFactory)


def _stringMapperFactory(colProps):
	if colProps.get("optional", True) and ("char(" in colProps["dbtype"] or 
			colProps["dbtype"]=="text"):
		if isinstance(colProps["sample"], str):
			constructor = str
		else:
			constructor = unicode
		def coder(val):
			if val is None:
				return ""
			return constructor(val)
		return coder
_registerDefaultMF(_stringMapperFactory)


def _charMapperFactory(colProps):
	if colProps["dbtype"]=="char":
		def coder(val):
			if val is None:
				return "\0"
			return str(val)
		return coder
_registerDefaultMF(_charMapperFactory)


import datetime

def datetimeMapperFactory(colProps):
	import time

	def dtToMJdn(val):
		"""returns the modified julian date number for the dateTime instance val.
		"""
		return utils.dateTimeToJdn(val)-2400000.5
	
	if isinstance(colProps["sample"], (datetime.date, datetime.datetime)):
		unit = colProps["unit"]
		if "MJD" in colProps.get("ucd", ""):  # like VOX:Image_MJDateObs
			colProps["unit"] = "d"
			fun, destType = lambda val: val and dtToMJdn(val), (
				"double", None)
		elif unit=="yr" or unit=="a":
			fun, destType = lambda val: val and utils.dateTimeToJYear(val), (
				"double", None)
		elif unit=="d":
			fun, destType = lambda val: val and utils.dateTimeToJdn(val), (
				"double", None)
		elif unit=="s":
			fun, destType = lambda val: val and time.mktime(val.timetuple()), (
				"double", None)
		elif unit=="Y:M:D" or unit=="Y-M-D":
			fun, destType = lambda val: val and val.isoformat(), ("char", "*")
		elif unit=="iso":
			fun, destType = lambda val: val and val.isoformat(), ("char", "*")
		else:   # Fishy, but not our fault
			fun, destType = lambda val: val and utils.dateTimeToJdn(val), (
				"double", None)
		colProps["datatype"], colProps["arraysize"] = destType
		return fun
_registerDefaultMF(datetimeMapperFactory)



def _productMapperFactory(colProps):
	"""is a factory for columns containing product keys.

	The result are links to the product delivery.
	"""
	from nevow import url
	if colProps["ucd"]=="VOX:Image_AccessReference":
		def mapper(val):
			if val is None:
				return ""
			else:
				return urlparse.urljoin(
					urlparse.urljoin(config.get("web", "serverURL"),
						config.get("web", "nevowRoot")),
					"getproduct?key=%s&siap=true"%urllib.quote(val))
		return mapper
_registerDefaultMF(_productMapperFactory)


def getMapperRegistry():
	"""returns a copy of the default value mapper registry.
	"""
	return ValueMapperFactoryRegistry(
		defaultMFRegistry.getFactories())


class _CmpType(type):
	"""is a metaclass for *classes* that always compare in one way.
	"""
# Ok, that's just posing.  It's fun anyway.
	def __cmp__(cls, other):
		return cls.cmpRes


class _Comparer(object):
	__metaclass__ = _CmpType
	def __init__(self, *args, **kwargs):
		raise Error("%s classes can't be instanciated."%self.__class__.__name__)


class _Infimum(_Comparer):
	"""is a *class* smaller than anything.

	This will only work as the first operand.

	>>> _Infimum<-2333
	True
	>>> _Infimum<""
	True
	>>> _Infimum<None
	True
	>>> _Infimum<_Infimum
	True
	"""
	cmpRes = -1


class _Supremum(_Comparer):
	"""is a *class* larger than anything.

	This will only work as the first operand.

	>>> _Supremum>1e300
	True
	>>> _Supremum>""
	True
	>>> _Supremum>None
	True
	>>> _Supremum>_Supremum
	True
	"""
	cmpRes = 1



class ColProperties(dict):
	"""is a container for properties of columns in a table.

	Specifically, it gives maxima, minima and if null values occur.

	One of the main functions of this class is that instances can/should
	be used to query ValueMapperFactoryRegistries for value mappers.
	"""
	_nullvalueRanges = {
		"char": (' ', '~'),
		"unsignedByte": (0, 255),
		"short": (-2**15, 2**15-1),
		"int": (-2**31, 2**31-1),
		"long": (-2**63, 2**63-1),
	}
	def __init__(self, column):
		self["min"], self["max"] = _Supremum, _Infimum
		self["hasNulls"] = True # Safe default
		self.nullSeen = False
		self["sample"] = None
		self["name"] = column.name
		self["dbtype"] = column.type
		self["description"] = (column.description or 
			column.tablehead or "")
		self["ID"] = column.name  # XXX TODO: qualify this guy
		type, size = typesystems.sqltypeToVOTable(column.type)
		self["datatype"] = type
		self["arraysize"] = size
		self["displayHint"] = column.displayHint
		for fieldName in ["ucd", "utype", "unit"]:
			self[fieldName] = getattr(column, fieldName)

	def feed(self, val):
		if val is None:
			self.nullSeen = True
		else:
			if self["min"]>val:
				self["min"] = val
			if self["max"]<val:
				self["max"] = val

	def finish(self):
		"""has to be called after feeding is done.
		"""
		self.computeNullvalue()
		self["hasNulls"] = self.nullSeen

	def computeNullvalue(self):
		"""tries to come up with a null value for integral data.

		This is called by finish(), but you could call it yourself to find out
		if a nullvalue can be computed.
		"""
		if self["datatype"] not in self._nullvalueRanges:
			return
		if self["min"]>self._nullvalueRanges[self["datatype"]][0]:
			self["nullvalue"] = self._nullvalueRanges[self["datatype"]][0]
		elif self["max"]<self._nullvalueRanges[self["datatype"]][1]:
			self["nullvalue"] = self._nullvalueRanges[self["datatype"]][1]
		else:
			raise Error("Cannot compute nullvalue for column %s,"
				"range is %s..%s"%(self["name"], self["min"], self["max"]))


def acquireSamples(colPropsIndex, table):
	"""fills the values in the colProps-valued dict colPropsIndex with non-null
	values from tables.
	"""
# this is a q'n'd version of what's done in 
# votable.TableData._computeColProperties
# -- that method should be refactored anyway.  You can then fold in this
# function.
	noSampleCols = set(colPropsIndex)
	for row in table:
		newSampleCols = set()
		for col in noSampleCols:
			if row[col] is not None:
				newSampleCols.add(col)
				colPropsIndex[col]["sample"] = row[col]
		noSampleCols.difference_update(newSampleCols)
		if not noSampleCols:
			break

def getColProps(table):
	"""returns a sequence of ColProperties instances for the fields of table.
	"""
	colProps = [ColProperties(column) 
		for column in table.tableDef]
	acquireSamples(dict([(cp["name"], cp) for cp in colProps]), table)
	return colProps


def getMappers(colProps, mfRegistry=defaultMFRegistry):
	"""returns a sequence of mappers of the sequence of ColProperties colProps.

	The ColProperties should already have samples filled in.
	"""
	return tuple(mfRegistry.getMapper(cp) for cp in colProps)


def getMappedValues(table, mfRegistry=defaultMFRegistry):
	"""iterates over the table's rows with values mapped as defined by 
	mfRegistry.
	"""
	colLabels = [f.name for f in table.tableDef]
	if not colLabels:
		yield ()
		return
	mappers = getMappers(getColProps(table), mfRegistry)
	exec ",".join(["map%d"%col for col in range(len(mappers))])+ ", = mappers"\
		in locals()

	funDef = ["def buildRec(rowDict):"]
	for index, label in enumerate(colLabels):
		if mappers[index] is not mfRegistry.identity:
			funDef.append("\trowDict[%r] = map%d(rowDict[%r])"%(
				label, index, label))
	funDef.append("\treturn rowDict")
	exec "\n".join(funDef) in locals()

	for row in table:
		yield buildRec(row)


def _test():
	import doctest, valuemappers
	doctest.testmod(valuemappers)


if __name__=="__main__":
	_test()

