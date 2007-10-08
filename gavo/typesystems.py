"""
Conversions between type systems.

GAVO has to deal with a quite a few type systems:

 * Python
 * SQL
 * VOTable
 * XSD
 * Twisted formal

In general, we keep metadata in the SQL type system (although one could
argue one should use the richest one...).  In this module, we want to
collect functionality to get types in other type systems from these
types (and possibly the other way round).  

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
			mat = re.match(r"(.*)\((\d+)\)", sqlType)
			if mat:
				res = self.mapComplex(mat.group(1), mat.group(2))
		if res==None:
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
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return "char", length


class ToXSDConverter(FromSQLConverter):

	typeSystem = "VOTable"
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
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return "string"


try:
	import formal

	class ToFormalConverter(FromSQLConverter):
		"""is a converter from SQL types to Formal type specifications.

		The result of the conversion is a tuple of formal type.
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
		}

		def mapComplex(self, type, length):
			if type in self._charTypes:
				return formal.String

	sqltypeToFormal = ToFormalConverter().convert
except ImportError:
	pass

sqltypeToVOTable = ToVOTableConverter().convert
sqltypeToXSD = ToXSDConverter().convert
