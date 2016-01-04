"""
Conversions between type systems.

The DC software has to deal with a quite a few type systems:

 - Python
 - SQL
 - Postgres pg_type
 - VOTable
 - XSD
 - Twisted formal
 - numpy

Based on the (stinking) framework of utils.typeconversions, this
module contains converters between them as necessary.  The
linuga franca of our type systems is SQL+extensions as laid
down in utils.typeconversions.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import numpy

from gavo import utils
from gavo.base import literals
from gavo.utils.typeconversions import (FromSQLConverter,
	sqltypeToVOTable, voTableToSQLType, ConversionError)


class FromVOTableConverter(object):
	typeSystem = "db"
	
	simpleMap = {
		("short", '1'): "smallint",
		("int", '1'): "integer",
		("long", '1'): "bigint",
		("float", '1'): "real",
		("boolean", '1'): "boolean",
		("double", '1'): "double precision",
		("char", "*"): "text",
		("char", '1'): "char",
		("unsignedByte", '1'): "smallint",
		("raw", '1'): "raw",
	}

	xtypeMap = {
		"adql:POINT": "spoint",
		"adql:REGION": "spoly",
		"adql:TIMESTAMP": "timestamp",
	}

	def convert(self, type, arraysize, xtype=None):
		if self.xtypeMap.get(xtype):
			return self.xtypeMap[xtype]
		if arraysize=="1" or arraysize=="" or arraysize is None:
			arraysize = "1"
		if (type, arraysize) in self.simpleMap:
			return self.simpleMap[type, arraysize]
		else:
			return self.mapComplex(type, arraysize)

	def mapComplex(self, type, arraysize):
		if arraysize=="*":
			arraysize = ""
		if type=="char":
			return "text"
		if type=="unicodeChar":
			return "unicode"
		if type=="unsignedByte" and arraysize!="1":
			return "bytea[]"
		if (type, '1') in self.simpleMap:
			return "%s[%s]"%(self.simpleMap[type, '1'], arraysize)
		raise ConversionError("No SQL type for %s, %s"%(type, arraysize))


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
		"unicode": "string",
		"char": "string",
		"date": "date",
		"timestamp": "dateTime",
		"time": "time",
		"raw": "string",
		"vexpr-mjd": "string",
		"vexpr-date": "string",
		"vexpr-float": "string",
		"vexpr-string": "string",
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return "string"


class ToNumpyConverter(FromSQLConverter):

	typeSystem = "numpy"
	simpleMap = {
		"smallint": numpy.int16,
		"integer": numpy.int32,
		"bigint": numpy.int64,
		"real": numpy.float32,
		"boolean": numpy.bool,
		"double precision": numpy.float64,
		"text": numpy.str,
		"unicode": numpy.unicode,
		"char": numpy.str,
		"date": numpy.float32,
		"timestamp": numpy.float64,
		"time": numpy.float32,
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return numpy.str


class ToADQLConverter(FromSQLConverter):
	typeSystem = "adql"

	simpleMap = {
		"smallint": ("SMALLINT", 1),
		"integer": ("INTEGER", 1),
		"bigint": ("BIGINT", 1),
		"real": ("REAL", 1),
		"boolean": ("INTEGER", 1),
		"double precision": ("DOUBLE", 1),
		"text": ("VARCHAR", None),
		"unicode": ("VARCHAR", None),
		"char": ("CHAR", 1),
		"date": ("VARCHAR", None),
		"timestamp": ("TIMESTAMP", 1),
		"time": ("VARCHAR", None),
		"box": ("REGION", 1),
		"spoint": ("POINT", 1),
		"scircle": ("REGION", 1),
		"spoly": ("REGION", 1),
		"sbox": ("REGION", 1),
		"bytea": ("BLOB", None),
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return ("VARCHAR", None)
		if type=="bytea":
			return ("BLOB", None)
		if type in self.simpleMap:
			return self.simpleMap[type][0], length


class ToPythonBase(FromSQLConverter):
	"""The base for converters turning dealing with turning "simple" literals
	into python values.

	These return the identity for most "complex" types that do not have
	plain literals.  

	What is returned here is a name of a function turning a single literal
	into an object of the desired type; all those reside within base.literals.  

	All such functions should be transparent to None (null value) and to
	objects that already are of the desired type.
	"""
	simpleMap = {
		"smallint": "parseInt",
		"integer": "parseInt",
		"bigint": "parseInt",
		"real": "parseFloat",
		"boolean": "parseBooleanLiteral",
		"double precision": "parseFloat",
		"text": "parseUnicode",
		"char": "parseUnicode",
		"unicode": "parseUnicode",
		"date": "parseDefaultDate",
		"timestamp": "parseDefaultDatetime",
		"time": "parseDefaultTime",
		"spoint": "parseSPoint",
		"scircle": "parseSimpleSTCS", 
		"spoly": "parseSimpleSTCS",
		"sbox": "identity",  # hmha, there's no STC-S for this kind of box...
		"bytea": "identity",
		"raw": "identity",
		"file": "identity",
		"box": "identity",
		"vexpr-mjd": "identity",
		"vexpr-string": "identity",
		"vexpr-float": "identity",
		"vexpr-date": "identity",
		"pql-string": "identity",
		"pql-float": "identity",
		"pql-int": "identity",
		"pql-date": "identity",
		"pql-upload": "identity",

	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return "parseUnicode"
		else:
			return "identity"  # Anything sufficiently complex is python anyway :-)


class ToPythonCodeConverter(ToPythonBase):
	"""returns code templates to turn literals in variables to python objects.

	This is for the rowmakers' src="xx" specification, where no fancy literal
	processing needs to be done.

	The values of the map are simple string interpolation templates, with a
	single %s for the name of the variable to be converted.  

	The code assumes whatever executes those literals has done the equvialent
	of gavo.base.literals import * or use gavo.base.literals.defaultParsers()
	"""
	typeSystem = "pythonsrc"

	def convert(self, sqlType):
		funcName = ToPythonBase.convert(self, sqlType)
		if funcName=="identity":  # probably pointless performance hack
			return "%s"
		return funcName+"(%s)"


class ToPythonConverter(ToPythonBase):
	"""returns constructors making python values from strings.

	This is only for non-fancy applications with controlled input.  For
	more general circumstances, you'll want to use the parsing infrastructure.

	In particular, this will return the identity for most non-trivial stuff.
	Maybe that's wrong, but it will only change as sane literals are defined.
	"""
	typeSystem = "python"

	def convert(self, sqlType):
		funcName = ToPythonBase.convert(self, sqlType)
		return getattr(literals, funcName)


class ToLiteralConverter(object):
	"""returns a function taking some python value and returning stuff that
	can be parsed using ToPythonCodeConverter.
	"""
	typeSystem = "literal"
	simpleMap = {
		"smallint": str,
		"integer": str,
		"bigint": str,
		"real": str,
		"boolean": str,
		"double precision": str,
		"text": str,
		"char": str,
		"unicode": unicode,
		"date": lambda v: v.isoformat(),
		"timestamp": lambda v: utils.formatISODT(v),
		"time": lambda v: v.isoformat(),
		"spoint": lambda v: "%f,%f"%(v.x/utils.DEG, v.y/utils.DEG),
# XXX TODO Fix those
#		"scircle": str,
#		"spoly": str,
#		"sbox": str,
	}

	def convert(self, type):
		if type in self.simpleMap:
			return self.simpleMap[type]
		return utils.identity


class ToPgTypeValidatorConverter(FromSQLConverter):
	"""returns a callable that takes a type code from postgres' pg_type
	that will raise a TypeError if the to types are deemed incompatible.
	"""
	typeSystem = "Postgres pg_types validators"

	def checkInt(pgcode):
		if pgcode not in frozenset(['int2', 'int4', 'int8']):
			raise TypeError("%s is not compatible with an integer column"%pgcode)
	
	def checkFloat(pgcode):
		if pgcode not in frozenset(['float4', 'float8']):
			raise TypeError("%s is not compatible with an integer column"%pgcode)

	def makeChecker(expectedCode):
		def checker(pgcode):
			if expectedCode!=pgcode:
				raise TypeError("Incompatible type in DB: Expected %s, found %s"%(
					expectedCode, pgcode))
		return checker

	def dontCheck(pgcode):
		# should we give a warning that we didn't check a column?
		pass

	def makeAlarmer(typeName):
		def beAlarmed(pgcode):
			raise TypeError("Column with a non-db type %s mapped to db type %s"%(
				typeName, pgcode))
		return beAlarmed

	simpleMap = {
		"smallint": checkInt,
		"integer": checkInt,
		"bigint": checkInt,
		"real": checkFloat,
		"boolean": makeChecker("bool"),
		"double precision": checkFloat,
		"text": makeChecker("text"),
		"char": makeChecker("bpchar"),
		"date": makeChecker("date"),
		"timestamp": makeChecker("timestamp"),
		"time": makeChecker("time"),
		"box": dontCheck, # for now
		"vexpr-mjd": makeAlarmer("vexpr-mjd"),
		"vexpr-string": makeAlarmer("vexpr-string"),
		"vexpr-date": makeAlarmer("vexpr-date"),
		"vexpr-float": makeAlarmer("vexpr-float"),
		"file": makeAlarmer("file"),
		"pql-float": makeAlarmer("pql-float"),
		"pql-string": makeAlarmer("pql-string"),
		"pql-date": makeAlarmer("pql-date"),
		"pql-int": makeAlarmer("pql-int"),
		"pql-upload": makeAlarmer("pql-upload"),
		"raw": makeAlarmer("raw"),
		"bytea": makeChecker("bytea"),
		"spoint": dontCheck, # for now
		"scircle": dontCheck, # for now
		"sbox": dontCheck, # for now
		"spoly": dontCheck, # for now
		"unicode": makeChecker("text"),
	}

	def mapComplex(self, type, length):
		if (length is None or length==1) and type in self.simpleMap:
			return self.simpleMap[type]

		# it seems postgres always has a _ in front of arrays, but char(*)
		# doesn't have it.  We pretend we don't care for now.
		def check(pgcode):
			if pgcode.startswith("_"):
				pgcode = pgcode[1:]
			self.simpleMap[type](pgcode)

		return check


sqltypeToADQL = ToADQLConverter().convert
sqltypeToXSD = ToXSDConverter().convert
sqltypeToNumpy = ToNumpyConverter().convert
sqltypeToPython = ToPythonConverter().convert
sqltypeToPythonCode = ToPythonCodeConverter().convert
sqltypeToPgValidator = ToPgTypeValidatorConverter().convert
pythonToLiteral = ToLiteralConverter().convert


def _test():
	import doctest, typesystems
	doctest.testmod(typesystems)

if __name__=="__main__":
	_test()

__all__ = ["sqltypeToVOTable", "sqltypeToXSD", "sqltypeToNumpy",
	"sqltypeToPython", "sqltypeToPythonCode", "voTableToSQLType",
	"ConversionError", "FromSQLConverter", "pythonToLiteral",
	"sqltypeToPgValidator"]
