"""
Conversions between type systems.

The DC software has to deal with a quite a few type systems:

 * Python
 * SQL
 * VOTable
 * XSD
 * Twisted formal
 * numarray

In general, we keep metadata in the SQL type system (although one could
argue one should use the richest one...).  In this module, we want to
collect functionality to get types in other type systems from these
types (and possibly the other way round).

In fact, we use a couple of extensions:

* file -- this corresponds to a file upload from the web (i.e., a pair
  (filename, file object)).  It would be conceivable to turn this into
  blobs at some point, but right now we simply don't touch it.
* vexpr-float, -text, -date -- vizier-like expressions coming in from
  the web.  These are always strings.
* raw -- handed right through, whatever it is.  For target formats that
  can't do this, usually strings are used.

We should move all type conversion code here, and probably figure out
a sane way to concentrate value conversion here as well (though that's
probably tricky).
"""

import datetime
import re
import time

from gavo.utils.excs import Error

class ConversionError(Error):
	pass


class _CoercNode(object):
	"""is an entry in the coercion tree.
	"""
	def __init__(self, name, children=(), aliases=()):
		self.name, self.aliases = name, aliases
		self.parent, self.children = None, children
		for child in self.children:
			child.parent = self

	def getAncestorNames(self):
		if self.parent is None:
			return [self.name]
		res = self.parent.getAncestorNames()
		res.append(self.name)
		return res


class Coercions(object):
	"""is a tree of types that can be used to infer common types.

	The tree is passed in as nested sequences.

	>>> c = Coercions(_CoercNode('bar', (_CoercNode('foo'), _CoercNode('baz',
	...   (_CoercNode('quux'),)))))
	>>> c.getSubsuming([])
	'bar'
	>>> c.getSubsuming(['foo'])
	'foo'
	>>> c.getSubsuming(['foo', 'foo'])
	'foo'
	>>> c.getSubsuming(['foo', 'quux'])
	'bar'
	>>> c.getSubsuming(['foo', 'weird'])
	'bar'
	"""
	def __init__(self, typeTree):
		self.typesIndex = {}
		self.root = typeTree
		def index(node):
			self.typesIndex[node.name] = node
			for a in node.aliases:
				self.typesIndex[a] = node
			for c in node.children:
				index(c)
		index(self.root)

	def _unify(self, n1, n2):
		"""returns the first node that is an ancestor to both n1 and n2.
		"""
		ancestors = set(n1.getAncestorNames())
		while n2:
			if n2.name in ancestors:
				return n2
			n2 = n2.parent
		return self.root

	def getSubsuming(self, typeSeq):
		"""returns the least general type being able to represent all types
		within typeSeq.

		The method returns the root type for both an empty typeSeq or
		a typeSeq containing an unknown type.  We don't want to fail here,
		and the "all-encompassing" type should handle any crap.
		"""
		try:
			startNodes = [self.typesIndex[t] for t in typeSeq]
		except KeyError: # don't know at least one type
			return self.root.name
		try:
			return reduce(self._unify, startNodes).name
		except TypeError: # startNodes is empty
			return self.root.name


N = _CoercNode
_coercions = Coercions(
	N('text', (
		N("double precision", aliases=("double",), children=(
			N("real", aliases=("float",), children=(
				N("bigint", (
					N("integer", aliases=("int",), children=(
						N("smallint"),)),)),)),)),
		N('timestamp', (
			N('date'),
			N('time'),)),
		N('file'),)),)
del N


def getSubsumingType(sqlTypes):
	"""returns an appropirate sql type for a value composed of the types
	mentioned in the sequence sqlTypes.

	Basically, we have the coercion sequence int -> float -> text,
	where earlier types get clobbered by later ones.  And then there's
	messy stuff like dates.  We don't want to fail here, so if all else
	fails, we just make it a text.
	>>> getSubsumingType(["smallint", "integer"])
	'integer'
	>>> getSubsumingType(["double precision", "integer", "bigint"])
	'double precision'
	>>> getSubsumingType(["date", "timestamp", "timestamp"])
	'timestamp'
	>>> getSubsumingType(["date", "boolean", "smallint"])
	'text'
	>>> getSubsumingType(["box", "raw"])
	'text'
	>>> getSubsumingType(["date", "time"])
	'timestamp'
	"""
	return _coercions.getSubsuming(sqlTypes)


class FromSQLConverter:
	"""is an abstract base class for type converters from the SQL type system.

	Implementing classes have to provide a dict simpleMap mapping sql type
	strings to target types, and a method mapComplex that receives a type
	and a length (both strings, derived from SQL array types) and either
	returns None (no matching type) or the target type.

	Implementing classes should also provide a typeSystem attribute giving
	a short name of the type system they convert to.
	"""
	_charTypes = set(["character varying", "varchar", "character", "char"])

	def convert(self, sqlType):
		res = None
		if sqlType in self.simpleMap:
			res = self.simpleMap[sqlType]
		else:
			mat = re.match(r"(.*)[[(](\d+|\*|)[])]", sqlType)
			if mat:
				res = self.mapComplex(mat.group(1), mat.group(2))
		if res is None:
			if sqlType=="raw":
				return "raw"
			raise ConversionError("No %s type for %s"%(self.typeSystem, sqlType))
		return res

	def mapComplex(self, type, length):
		return


class ToVOTableConverter(FromSQLConverter):

	typeSystem = "VOTable"

	simpleMap = {
		"smallint": ("short", "1"),
		"integer": ("int", "1"),
		"bigint": ("long", "1"),
		"real": ("float", "1"),
		"boolean": ("boolean", "1"),
		"double precision": ("double", "1"),
		"text": ("char", "*"),
		"char": ("char", "1"),
		"date": ("char", "*"),
		"timestamp": ("char", "*"),
		"time": ("char", "*"),
		"box": ("double", "*"),
		"vexpr-string": ("char", "*"),
		"vexpr-date": ("char", "*"),
		"vexpr-float": ("double", "1"),
		"raw": ("unsignedByte", "*"),
	}

	def mapComplex(self, type, length):
		if length=='':
			length = '*'
		if type in self._charTypes:
			return "char", length
		elif type in self.simpleMap:
			return self.simpleMap[type][0], length


class FromVOTableConverter(object):
	typeSystem = "db"
	
	simpleMap = {
		("short", "1"): "smallint",
		("int", "1"): "integer",
		("long", "1"): "bigint",
		("float", "1"): "real",
		("boolean", "1"): "boolean",
		("double", "1"): "double precision",
		("char", "*"): "text",
		("char", "1"): "char",
		("raw", "*"): "raw",
		("short", ""): "smallint",
		("int", ""): "integer",
		("long", ""): "bigint",
		("float", ""): "real",
		("boolean", ""): "boolean",
		("double", ""): "double precision",
		("char", ""): "char",
	}

	def convert(self, type, arraysize):
		if (type, arraysize) in self.simpleMap:
			return self.simpleMap[type, arraysize]
		else:
			return self.mapComplex(type, arraysize)

	def mapComplex(self, type, arraysize):
		if type=="char":
			return "text"


class ToXSDConverter(FromSQLConverter):

	typeSystem = "XSD"
	simpleMap = {
		"smallint": "short",
		"integer": "int",
		"bigint": "long",
		"real": "float",
		"boolean": "boolean",
		"double precision": "double",
		"text": "string",
		"char": "string",
		"date": "date",
		"timestamp": "dateTime",
		"time": "time",
		"raw": "string",
		"vexpr-date": "string",
		"vexpr-float": "string",
		"vexpr-string": "string",
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return "string"


class ToNumarrayConverter(FromSQLConverter):

	typeSystem = "numarray"
	simpleMap = {
		"smallint": "Int16",
		"integer": "Int32",
		"bigint": "Int64",
		"real": "Float32",
		"boolean": "Bool",
		"double precision": "Float64",
		"text": "string",
		"char": "string",
		"date": "Float32",
		"timestamp": "Float32",
		"time": "Float32",
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return "string"


######## Helpers for conversion to python values

def toPythonTimeDelta(days=0, hours=0, minutes=0, seconds=0):
	return datetime.timedelta(days, hours, minutes, seconds)


def toPythonDate(datestr, datePatterns=[
		re.compile("(?P<y>\d\d\d\d)-(?P<m>\d\d)-(?P<d>\d\d)$"),
		re.compile("(?P<m>\d\d)/(?P<d>\d\d)/(?P<y>\d\d\d\d)$"),
		re.compile("(?P<m>\d\d)/(?P<d>\d\d)/(?P<y>\d\d)$"),
		]):
	"""guesses a datetime.date from a number of date formats.
	"""
	if not isinstance(datestr, basestring):
		return datestr
	for pat in datePatterns:
		mat = pat.search(datestr)
		if mat:
			yearS, monthS, dayS = mat.group("y"), mat.group("m"), mat.group("d")
			if len(yearS)==2:
				yearS = "19"+yearS
			break
	else:
		raise ConversionError("Date %s has unsupported format"%datestr)
	return datetime.date(int(yearS), int(monthS), int(dayS))


def toPythonTime(literal):
	"""returns a datetime.time object from an ISO timestamp.
	"""
	if not isinstance(literal, basestring):
		return literal
	return datetime.time(*time.strptime(literal, "%H:%M:%S")[3:6])


def toPythonDateTime(literal):
	"""returns a datetime.datetime object from an ISO timestamp.
	"""
	if not isinstance(literal, basestring):
		return literal
	try:
		return datetime.datetime(*time.strptime(literal, "%Y-%m-%dT%H:%M:%S")[:6])
	except ValueError:
		return datetime.datetime(*time.strptime(literal, "%Y-%m-%d")[:3])


########## End Helpers for conversion to python values


class ToPythonConverter(FromSQLConverter):
	"""returns constructors making python values from strings.

	This is only for non-fancy applications with controlled input.  For
	more general circumstances, you'll want to use the parsing infrastructure.
	"""
	typeSystem = "python"
	simpleMap = {
		"smallint": int,
		"integer": int,
		"bigint": int,
		"real": float,
		"float": float,
		"boolean": int,
		"double precision": float,
		"text": unicode,
		"char": unicode,
		"date": toPythonDate,
		"time": toPythonTime,
		"timestamp": toPythonDateTime,
		"raw": lambda x: x,
		"vexpr-string": str,
		"vexpr-date": str,
		"vexpr-float": str,
		"file": lambda x: x,
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return unicode


class ToPythonCodeConverter(FromSQLConverter):
	"""returns code templates to turn literals in variables to python objects.

	This is for the rowmakers' src="xx" specification, where no fancy literal
	processing needs to be done.

	The values of the map are simple string interpolation templates, with a
	single %s for the name of the variable to be converted.  

	The code assumes whatever executes those literals has done a
	from gavo.base.literals import *.
	"""
	typeSystem = "pythonsrc"
	simpleMap = {
		"smallint": "parseInt(%s)",
		"integer": "parseInt(%s)",
		"bigint": "parseInt(%s)",
		"real": "parseFloat(%s)",
		"boolean": "parseBooleanLiteral(%s)",
		"double precision": "parseFloat(%s)",
		"text": "parseUnicode(%s)",
		"char": "parseUnicode(%s)",
		"date": "parseDefaultDate(%s)",
		"timestamp": "parseDefaultDatetime(%s)",
		"time": "parseDefaultTime(%s)",
		"raw": "%s",
		"file": "%s",
		"box": "%s",
		"vexpr-string": "%s",
		"vexpr-float": "%s",
		"vexpr-date": "%s",
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return "unicode(%s)"
		else:
			return "%s"  # Anything sufficiently complex is python anyway :-)



sqltypeToVOTable = ToVOTableConverter().convert
sqltypeToXSD = ToXSDConverter().convert
sqltypeToNumarray = ToNumarrayConverter().convert
sqltypeToPython = ToPythonConverter().convert
sqltypeToPythonCode = ToPythonCodeConverter().convert
voTableToSQLType = FromVOTableConverter().convert


def _test():
	import doctest, typesystems
	doctest.testmod(typesystems)

if __name__=="__main__":
	_test()

__all__ = ["sqltypeToVOTable", "sqltypeToXSD", "sqltypeToNumarray",
	"sqltypeToPython", "sqltypeToPythonCode", "voTableToSQLType",
	"ConversionError", "FromSQLConverter"]
