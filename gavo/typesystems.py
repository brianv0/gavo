"""
Conversions between type systems.

GAVO has to deal with a quite a few type systems:

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

We should move all type conversion code here, and probably figure out
a sane way to concentrate value conversion here as well (though that's
probably tricky).
"""

import re

from gavo import Error


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
			raise Error("No %s type for %s"%(self.typeSystem, sqlType))
		return res

	def mapComplex(self, type, length):
		return


class ToVOTableConverter(FromSQLConverter):

	typeSystem = "VOTable"

	simpleMap = {
		"smallint": ("short", "1"),
		"integer": ("int", "1"),
		"int": ("int", "1"),
		"bigint": ("long", "1"),
		"real": ("float", "1"),
		"float": ("float", "1"),
		"boolean": ("boolean", "1"),
		"double precision": ("double", "1"),
		"double": ("double", "1"),
		"text": ("char", "*"),
		"char": ("char", "1"),
		"date": ("char", "*"),
		"timestamp": ("char", "*"),
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


class FromVOTableConverter:
	typeSystem = "db"
	
	simpleMap = {
		("short", "1"): "smallint",
		("int", "1"): "integer",
		("int", "1"): "int",
		("long", "1"): "bigint",
		("float", "1"): "real",
		("boolean", "1"): "boolean",
		("double", "1"): "double precision",
		("char", "*"): "text",
		("char", "1"): "char",
		("raw", "*"): "raw",
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
		"int": "int",
		"bigint": "long",
		"real": "float",
		"float": "float",
		"boolean": "boolean",
		"double precision": "double",
		"double": "double",
		"text": "string",
		"char": "string",
		"date": "date",
		"timestamp": "dateTime",
		"raw": "string",
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return "string"


class ToNumarrayConverter(FromSQLConverter):

	typeSystem = "numarray"
	simpleMap = {
		"smallint": "Int16",
		"integer": "Int32",
		"int": "Int32",
		"bigint": "Int64",
		"real": "Float32",
		"float": "Float32",
		"boolean": "Bool",
		"double precision": "Float64",
		"double": "Float64",
		"text": "string",
		"char": "string",
		"date": "Float32",
		"timestamp": "Float32",
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return "string"

try:
	import formal
	from web import gwidgets

	class ToFormalConverter(FromSQLConverter):
		"""is a converter from SQL types to Formal type specifications.

		The result of the conversion is a tuple of formal type and widget factory.
		"""
		typeSystem = "Formal"
		simpleMap = {
			"smallint": (formal.Integer, formal.TextInput),
			"integer": (formal.Integer, formal.TextInput),
			"int": (formal.Integer, formal.TextInput),
			"bigint": (formal.Integer, formal.TextInput),
			"real": (formal.Float, formal.TextInput),
			"float": (formal.Float, formal.TextInput),
			"boolean": (formal.Boolean, formal.Checkbox),
			"double precision": (formal.Float, formal.TextInput),
			"double": (formal.Float, formal.TextInput),
			"text": (formal.String, formal.TextInput),
			"char": (formal.String, formal.TextInput),
			"date": (formal.Date, formal.widgetFactory(formal.DatePartsInput,
				twoCharCutoffYear=50, dayFirst=True)),
			"timestamp": (formal.Date, formal.widgetFactory(formal.DatePartsInput,
				twoCharCutoffYear=50, dayFirst=True)),
			"vexpr-float": (formal.String, gwidgets.NumericExpressionField),
			"vexpr-date": (formal.String, gwidgets.DateExpressionField),
			"vexpr-string": (formal.String, gwidgets.StringExpressionField),
			"file": (formal.File, None),
		}

		def mapComplex(self, type, length):
			if type in self._charTypes:
				return formal.String

	sqltypeToFormal = ToFormalConverter().convert
except ImportError:
	pass

sqltypeToVOTable = ToVOTableConverter().convert
sqltypeToXSD = ToXSDConverter().convert
sqltypeToNumarray = ToNumarrayConverter().convert
voTableToSQLType = FromVOTableConverter().convert
