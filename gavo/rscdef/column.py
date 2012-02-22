"""
Description of columns (and I/O fields).
"""

import re
import warnings

from gavo import base
from gavo import utils
from gavo.base import literals
from gavo.base import typesystems
from gavo.base.attrdef import *


class TypeNameAttribute(AtomicAttribute):
	"""An attribute with values constrained to types we understand.
	"""
	@property
	def typeDesc_(self):
		return ("a type name; the internal type system is similar to SQL's"
			" with some restrictions and extensions.  The known atomic types"
			" include: %s"%(", ".join(typesystems.ToPythonConverter.simpleMap)))

	def parse(self, value):
		try:
			typesystems.sqltypeToPython(value)
		except base.Error:
			raise base.ui.logOldExc(LiteralParseError(self.name_, value, 
				hint="A supported SQL type was expected here.  If in doubt,"
				" check base/typeconversions.py, in particular ToPythonCodeConverter."))
		return value
	
	def unparse(self, value):
		return value


class ColumnNameAttribute(UnicodeAttribute):
	"""An attribute containing a column name.

	Column names are special in that you can prefix them with "quoted/"
	and then get a delimited identifier.  This is something you probably
	shouldn't use.
	"""
	@property
	def typeDesc_(self):
		return ("a column name within an SQL table.  These have to match"
			" ``%s``.  In a desperate pinch, you can generate delimited identifiers"
			" (that can contain anything) by prefixing the name with 'quoted/' (but"
			" you cannot use rowmakers to fill such tables)."
			)%utils.identifierPattern.pattern
	
	def parse(self, value):
		if value.startswith("quoted/"):
			return utils.QuotedName(value[7:])
		if not utils.identifierPattern.match(value):
			raise base.StructureError("'%s' is not a valid column name"%value)
		return value
	
	def unparse(self, value):
		if isinstance(value, utils.QuotedName):
			return "quoted/"+value.name
		else:
			return value


class TableheadAttribute(UnicodeAttribute):
	"""An attribute defaulting to the parent's name attribute.
	"""
	typeDesc = "table head, defaulting to parent's name"

	def iterParentMethods(self):
		realName = "_real"+self.name_
		attDefault = self.default_
		def getValue(self):
			if hasattr(self, realName):
				return getattr(self, realName)
			else:
				if self.name is not base.Undefined:
					return self.name
		def setValue(self, value):
			if value is not attDefault:
				setattr(self, realName, value)
		yield self.name_, property(getValue, setValue)


class _AttBox(object):
	"""A helper for TableManagedAttribute.

	When a TableManagedAttribute ships off its value into an event
	it packs its value into an _AttBox.  That way, the receiver
	can tell whether the value comes from another TableManagedAttribute
	(which is ok) or comes from an XML parser (which is forbidden).
	"""
	def __init__(self, payload):
		self.payload = payload


class TableManagedAttribute(AttributeDef):
	"""An attribute not settable from XML for holding information
	managed by the parent table.
	
	That's stc and stcUtype here, currently.
	"""
	typeDesc_ = "non-settable internally used value"

	def feed(self, ctx, instance, value):
		if isinstance(value, _AttBox):
			# synthetic event during object copying, accept
			self.feedObject(instance, value.payload)
		else:
			# do not let people set that stuff directly
			raise base.StructureError("Cannot set %s attributes from XML"%self.name_)
	
	def feedObject(self, instance, value):
		setattr(instance, self.name_, value)

	def iterEvents(self, instance):
		val = getattr(instance, self.name_)
		if val!=self.default_:
			yield ("value", self.name_, _AttBox(val))

	def getCopy(self, instance, newParent):
		# these never get copied; the values are potentially shared 
		# between many objects, so the must not be changed anyway.
		return getattr(instance, self.name_)


class RoEmptyDict(dict):
	"""is a read-only standin for a dict.

	It's hashable, though, since it's always empty...  This is used here
	for a default for displayHint.
	"""
	def __setitem__(self, what, where):
		raise TypeError("RoEmptyDicts are immutable")

_roEmptyDict = RoEmptyDict()


class DisplayHintAttribute(AtomicAttribute):
	"""is a display hint.

	Display hint literals are comma-separated key=value sequences.
	Keys are up to the application and evaluated by htmltable, votable, etc.

	The parsed values are simply dictionaries mapping strings to strings, i.e.,
	value validation cannot be performed here (yet -- do we want this?
	A central repository of display hints would be kinda useful...)
	"""
	typeDesc_ = "Display hint"

	def __init__(self, name, description, **kwargs):
		AtomicAttribute.__init__(self, name, default=_roEmptyDict, 
			description=description, **kwargs)

	def parse(self, value):
		if not value.strip():
			return _roEmptyDict
		try:
			return dict([f.split("=") for f in value.split(",")])
		except (ValueError, TypeError):
			raise base.ui.logOldExc(LiteralParseError(self.name_, value, 
				hint="DisplayHints have a format like tag=value{,tag=value}"))

	def unparse(self, value):
		return ",".join(
			["%s=%s"%(k,v) for k,v in value.iteritems()])


class Option(base.Structure):
	"""A value for enumerated columns.

	For presentation purposes, an option can have a title, defaulting to
	the option's value.
	"""
	name_ = "option"

	_title = base.UnicodeAttribute("title", default=base.NotGiven,
		description="A Label for presentation purposes; defaults to val.", 
		copyable=True)
	_val = base.DataContent(copyable=True, description="The value of"
		" the option; this is what is used in, e.g., queries and the like.")

	def __repr__(self):
		# may occur in user messages from formal, so we use title.
		return self.title

	def completeElement(self, ctx):
		if self.title is base.NotGiven:
			self.title = self.content_
		self._completeElementNext(Option, ctx)


def makeOptions(*args):
	"""returns a list of Option instances with values given in args.
	"""
	return [base.makeStruct(Option, content_=arg) for arg in args]


class Values(base.Structure):
	"""Information on a column's values, in particular its domain.

	This is quite like the values element in a VOTable.  In particular,
	to accomodate VOTable usage, we require nullLiteral to be a valid literal
	for the parent's type.
	"""
	name_ = "values"

	_min = UnicodeAttribute("min", default=None, description="Minimum acceptable"
		" value as a datatype literal", copyable=True)
	_max = UnicodeAttribute("max", default=None, description="Maximum acceptable"
		" value as a datatype literal", copyable=True)
	_options = base.StructListAttribute("options", 
		childFactory=Option,
		description="List of acceptable values (if set)", copyable=True)
	_default = UnicodeAttribute("default", default=None, description="A default"
		" value (currently only used for options).", copyable=True)
	_nullLiteral = UnicodeAttribute("nullLiteral", default=None, description=
		"An appropriate value representing a NULL for this column in VOTables"
		" and similar places.  You usually should only set it for integer"
		" types and chars.  Note that rowmakers mak no use of this nullLiteral,"
		" i.e., you can and should choose null values independently of your"
		" your source.  Again, for reals, floats and (mostly) text you probably"
		" do not want to do this.", copyable=True)
	_multiOk = BooleanAttribute("multiOk", False, "Allow selection of"
		" multiple options", copyable=True)
	_fromDB = ActionAttribute("fromdb", "_evaluateFromDB", description=
		"A query fragment returning just one column to fill options from (will"
		" add to options if some are given).  Do not write SELECT or anything,"
		" just the column name and the where clause.")
	_original = base.OriginalAttribute()

	validValues = None

	def makePythonVal(self, literal, sqltype):
		return typesystems.sqltypeToPython(sqltype)(literal)

	def _evaluateFromDB(self, ctx):
		if not getattr(ctx, "doQueries", True):
			return
		try:
			with base.AdhocQuerier(base.getTableConn) as q:
				for row in q.query("SELECT DISTINCT %s"%(self.fromdb)):
					self._options.feedObject(self, base.makeStruct(Option,
						content_=row[0]))
		except base.DBError: # Table probably doesn't exist yet, ignore.
			base.ui.notifyWarning("Values fromdb '%s' failed, ignoring"%self.fromdb)

	def onParentComplete(self):
		"""converts min, max, and options from string literals to python
		objects.
		"""
		dataField = self.parent
		# It would be nicer if we could handle this in properties for min etc, but
		# unfortunately parent might not be complete then.  The only
		# way around that would have been delegations from Column, and that's
		# not very attractive either.
		if self.min:
			self.min = self.makePythonVal(self.min, dataField.type)
		if self.max:
			self.max = self.makePythonVal(self.max, dataField.type)

		if self.options:
			dbt = dataField.type
			for opt in self.options:
				opt.content_ = self.makePythonVal(opt.content_, dbt)
			self.validValues = set([o.content_ for o in self.options])

		if self.nullLiteral:
			try:
				self.makePythonVal(self.nullLiteral, dataField.type)
			except ValueError:
				raise base.LiteralParseError("nullLiteral", self.nullLiteral,
					hint="If you want to *parse* whatever you gave into a NULL,"
					" use the parseWithNull function in a rowmaker.  The null"
					" literal gives what value will be used for null values"
					" when serializing to VOTables and the like.")

	def validateOptions(self, value):
		"""returns false if value isn't either in options or doesn't consist of
		items in options.

		Various null values always validate here; non-null checking is done
		by the column on its required attribute.
		"""
		if value=="None":
			assert False, "Literal 'None' passed as a value to validateOptions"

		if self.validValues is None:
			return True
		if isinstance(value, (list, tuple)):
			for val in value:
				if val and not val in self.validValues:
					return False
		else:
			return value in self.validValues
		return True


class Column(base.Structure):
	"""A database column.
	
	Columns contain almost all metadata to describe a column in a database
	table or a VOTable (the exceptions are for column properties that may
	span several columns, most notably indices).

	Note that the type system adopted by the DC software is a subset
	of postgres' type system.  Thus when defining types, you have to
	specify basically SQL types.  Types for other type systems (like
	VOTable, XSD, or the software-internal representation in python values)
	are inferred from them.

	Columns can have delimited identifiers as names.  Don't do this, it's
	no end of trouble.  For this reason, however, you should not use name
	but rather key to programmatially obtain field's values from rows.

	Properties evaluated:

	- std -- set to 1 to tell the tap schema importer to have the column's
	  std column in TAP_SCHEMA 1 (it's 0 otherwise).
	"""
	name_ = "column"

	_name = ColumnNameAttribute("name", default=base.Undefined,
		description="Name of the column",
		copyable=True, before="type")
	_type = TypeNameAttribute("type", default="real", description=
		"datatype for the column (SQL-like type system)",
		copyable=True, before="unit")
	_unit = UnicodeAttribute("unit", default="", description=
		"Unit of the values", copyable=True, before="ucd")
	_ucd = UnicodeAttribute("ucd", default="", description=
		"UCD of the column", copyable=True, before="description")
	_description = NWUnicodeAttribute("description", 
		default="", copyable=True,
		description="A short (one-line) description of the values in this column.")
	_tablehead = TableheadAttribute("tablehead", default=base.NotGiven,
		description="Terse phrase to put into table headers for this"
			" column", copyable=True)
	_utype = UnicodeAttribute("utype", default=None, description=
		"utype for this column", copyable=True)
	_required = BooleanAttribute("required", default=False,
		description="Record becomes invalid when this column is NULL", 
		copyable=True)
	_displayHint = DisplayHintAttribute("displayHint", 
		description="Suggested presentation; the format is "
			" <kw>=<value>{,<kw>=<value>}, where what is interpreted depends"
			" on the output format.  See, e.g., documentation on HTML renderers"
			" and the formatter child of outputFields.", copyable=True)
	_verbLevel = IntAttribute("verbLevel", default=30,
		description="Minimal verbosity level at which to include this column", 
		copyable=True)
	_values = base.StructAttribute("values", default=None,
		childFactory=Values, description="Specification of legal values", 
		copyable=True)
	_fixup = UnicodeAttribute("fixup", description=
		"A python expression the value of which will replace this column's"
		" value on database reads.  Write a ___ to access the original"
		' value.  You can use macros for the embedding table.'
		' This is for, e.g., simple URL generation'
		' (fixup="\'\\internallink{/this/svc}\'+___").'
		' It will *only* kick in when tuples are deserialized from the'
		" database, i.e., *not* for values taken from tables in memory.",
		default=None, copyable=True)
	_note = UnicodeAttribute("note", description="Reference to a note meta"
		" on this table explaining more about this column", default=None,
		copyable=True)
	_xtype = UnicodeAttribute("xtype", description="VOTable xtype giving"
		" the serialization form", default=None, copyable=True)
	_stc = TableManagedAttribute("stc", description="Internally used"
		" STC information for this column (do not assign to)",
		default=None, copyable=True)
	_stcUtype = TableManagedAttribute("stcUtype", description="Internally used"
		" STC information for this column (do not assign to)",
		default=None, copyable=True)
	_properties = base.PropertyAttribute(copyable=True)
	_original = base.OriginalAttribute()

	restrictedMode = False

	def __repr__(self):
		return "<Column %s>"%repr(self.name)

	def onParentComplete(self):
		# we need to resolve note on construction since columns are routinely
		# copied to other tables and  meta info does not necessarily follow.
		if isinstance(self.note, basestring):
			try:
				self.note = self.parent.getNote(self.note)
			except base.NotFoundError: # non-existing notes silently ignored
				self.note = None

	def completeElement(self, ctx):
		self.restrictedMode = getattr(ctx, "restricted", False)
		if isinstance(self.name, utils.QuotedName):
			self.key = self.name.name
			if ')' in self.key:
				# No '()' allowed in key for that breaks the %()s syntax (sigh!).
				# Work around with the following quick hack that would break
				# if people carefully chose proper names.  Anyone using delim.
				# ids in SQL deserves a good spanking anyway.
				self.key = self.key.replace(')', "__").replace('(', "__")
		else:
			self.key = self.name
		self._completeElementNext(Column, ctx)

	def isEnumerated(self):
		return self.values and self.values.options

	def validate(self):
		self._validateNext(Column)
		if self.restrictedMode and self.fixup:
			raise base.RestrictedElement("fixup")

	def validateValue(self, value):
		"""raises a ValidationError if value does not match the constraints
		given here.
		"""
		if value is None:
			if self.required:
				raise base.ValidationError(
					"Field %s is empty but non-optional"%self.name, self.name)
			return
		vals = self.values
		if vals:
			if vals.options:
				if value and not vals.validateOptions(value):
					raise base.ValidationError("Value %s not consistent with"
						" legal values %s"%(value, vals.options), self.name)
			else:
				if vals.min and value<vals.min:
					raise base.ValidationError("%s too small (must be at least %s)"%(
						value, vals.min), self.name)
				if vals.max and value>vals.max:
					raise base.ValidationError("%s too large (must be less than %s)"%(
						value, vals.max), self.name)

	def isIndexed(self):
		"""returns a guess as to whether this column is part of an index.

		This may return True, False, or None (unknown).
		"""
		if self.parent and hasattr(self.parent, "indexedColumns"):
				# parent is something like a TableDef
			if self.name in self.parent.indexedColumns:
				return True
			else:
				return False

	def isPrimary(self):
		"""returns a guess as to whether this column is a primary key of the
		embedding table.

		This may return True, False, or None (unknown).
		"""
		if self.parent and hasattr(self.parent, "primary"):
				# parent is something like a TableDef
			if self.name in self.parent.primary:
				return True
			else:
				return False

	_indexedCleartext = {
		True: "indexed",
		False: "notIndexed",
		None: "unknown",
	}

	def asInfoDict(self):
		"""returns a dictionary of certain, "user-interesting" properties
		of the data field, in a dict of strings.
		"""
		return {
			"name": self.name,
			"description": self.description or "N/A",
			"tablehead": self.tablehead,
			"unit": self.unit or "N/A",
			"ucd": self.ucd or "N/A",
			"verbLevel": self.verbLevel,
			"indexState": self._indexedCleartext[self.isIndexed()],
			"note": self.note,
		}
	
	def getDDL(self):
		"""returns SQL describing this column ready for inclusion in a 
		DDL statement.
		"""
		items = [str(self.name), self.type]
		if self.required:
			items.append("NOT NULL")
		return " ".join(items)

	def getDisplayHintAsString(self):
		return self._displayHint.unparse(self.displayHint)

	def getLabel(self):
		"""returns a short label for this column.

		The label is either the tablehead or, missing it, the capitalized
		column name.
		"""
		if self.tablehead is not None:
			return self.tablehead
		return self.name.capitalize()
		
	@classmethod
	def fromMetaTableRow(cls, metaRow):
		"""returns a Column instance for a row from the meta table.
		"""
		col = cls(None)
		for (dest, src) in [("description", "description"), 
				("unit", "unit"), ("ucd", "ucd"), ("tablehead", "tablehead"),
				("utype", "utype"), 
				("verbLevel","verbLevel"), ("type", "type"), ("name", "fieldName"),
				("displayHint", "displayHint")]:
			col.feedEvent(None, "value", dest, metaRow[src])
		return col


class ParamBase(Column):
	"""A basic parameter.

	This is the base for both Param and InputKey.
	"""
	_value = base.DataContent(description="The value of parameter."
		" It is parsed according to the param's type using the default"
		" parser for the type as in rowmakers.", default=base.NotGiven,
		copyable=True)

	_valueCache = base.Undefined

	# we need to fix null literal handling of params.  Meanwhile:
	nullLiteral = ""

	def __repr__(self):
		return "<%s %s=%s>"%(self.__class__.__name__, 
			self.name, repr(self.content_))

	def completeElement(self, ctx):
		if not self.values:
			self.values = base.makeStruct(Values, parent_=self)

		if self.values.nullLiteral is None:
			if self.type=="text":
				self.values.nullLiteral = "__NULL__"
			if self.type=="real" or self.type=="double precision":
				self.values.nullLiteral = "NaN"

		self._completeElementNext(ParamBase, ctx)
	
	def onElementComplete(self):
		self._onElementCompleteNext(ParamBase)
		if self.content_ is base.NotGiven:
			if self.values.default:
				self.set(self.values.default)
		else:
			self.set(self.content_)

	@property
	def value(self):
		if self._valueCache is base.Undefined:
			if self.content_ is base.NotGiven:
				self._valueCache = None
			else:
				self._valueCache = self._parse(self.content_)
		return self._valueCache

	def set(self, val):
		"""sets this parameter's value.

		val can be a python value, or string literal.  In the second
		case, this string literal will be preserved in string serializations
		of this param.

		If val is an invalid value for this item, a ValidationError is
		raised and the item's value will be Undefined.
		"""
		if isinstance(val, basestring):
			self._valueCache = base.Undefined
		else:
			self._valueCache = base.Undefined
			val = self._unparse(val)

		if not self.values.validateOptions(self._parse(val)):
			raise base.ValidationError("%s is not a valid value for %s"%(
				val, self.name), self.name)

		self.content_ = val

	def _parse(self, literal):
		"""parses literal using the default value parser for this param's
		type.

		If literal is not a string, it will be returned unchanged.
		"""
		if not isinstance(literal, basestring):
			return literal
		try:
			if literal==self.values.nullLiteral:
				return None
			return base.sqltypeToPython(self.type)(literal)
		except ValueError:
			raise base.ValidationError("%s is not a valid literal for %s"%(
				repr(literal), self.name), self.name)

	def _unparse(self, value):
		"""returns a string representation of value appropriate for this
		type.

		Actually, for certain types only handled internally (like file or raw),
		this is not a string representation at all but just the python stuff.

		Plus, right now, for sequences we're not doing anything.  We probably
		should.
		"""
		if isinstance(value, (list, tuple)):
			return value
		if value is None:
			return self.values.nullLiteral
		else:
			return base.pythonToLiteral(self.type)(value)


class Param(ParamBase):
	"""A table parameter.

	This is like a column, except that it conceptually applies to all
	rows in the table.  In VOTables, params will be rendered as
	PARAMs.  
	
	While we validate the values passed using the DC default parsers,
	at least the VOTable params will be literal copies of the string
	passed in.

	You can obtain a parsed value from the value attribute.

	Null value handling is tricky with params.  An empty param (like 
	``<param name="x"/>)`` will have a NotGiven value; this means it will not
	even be rendered in VOTables.  To set a PARAM to NULL, use null values as
	bodies.  For strings, there's the default __NULL__, for floats, it's NaN;
	ints have not default null literals.

	You can set custom null literals using a values child, like::

		<param name="x" type="integer"><values nullLiteral="-1"/>-1</params>
	
	The value attribute for NULL params is None.
	"""
	name_ = "param"

	def validate(self):
		self._validateNext(Param)
		if self.required and self.content_ is base.NotGiven:
			raise base.StructureError("Required value not given for param"
				" %s"%self.name)
		# the value property will bomb on malformed literals
		try:
			_ = self.value
		except ValueError, msg:
			raise base.LiteralParseError(self.name, self.content_,
				hint="Param content must be parseable by the DC default parsers."
					"  The value you passed caused the error: %s"%msg)
	
	def set(self, val):
		"""sets the value of the parameter.

		Macros will be expanded if the parent object supports macro
		expansion.
		"""
		if (isinstance(val, basestring)
				and "\\" in val 
				and hasattr(self.parent, "expand")):
			val = self.parent.expand(val)
		return ParamBase.set(self, val)
