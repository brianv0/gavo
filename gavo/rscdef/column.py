"""
Descriptions of the various Field types in the DC.
"""

import warnings

from gavo import base
from gavo.base import typesystems
from gavo.base.attrdef import *



class TypeNameAttribute(AtomicAttribute):
	"""is an attribute with values constrained to types we understand.
	"""
	typeDesc = "type (mostly SQL types)"

	def parse(self, value):
		try:
			typesystems.sqltypeToPythonCode(value)
		except base.Error:
			raise LiteralParseError("%s is not a supported type"%value,
				self.name_, value)
		return value
	
	def unparse(self, value):
		return value


class TableheadAttribute(UnicodeAttribute):
	"""is an attribute defaulting to the parent's name attribute.
	"""
	typeDesc = "table head, defaulting to parent's name"

	def iterParentMethods(self):
		realName = "_real"+self.name_
		attDefault = self.default_
		def getValue(self):
			if hasattr(self, realName):
				return getattr(self, realName)
			else:
				return self.name
		def setValue(self, value):
			if value is not attDefault:
				setattr(self, realName, value)
		yield self.name_, property(getValue, setValue)


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
			raise LiteralParseError("Invalid display hint '%s'"%value,
				self.name_, value)

	def unparse(self, value):
		return ",".join(
			["%s=%s"%(k,v) for k,v in value.iteritems()])


class Option(base.Structure):
	"""is a possible value for enumerated columns.

	For presentation purposes, an option can have a title, defaulting to
	the option's value.
	"""
	name_ = "option"

	_title = base.UnicodeAttribute("title", default=None,
		description="Label for presentation purposes", copyable=True)
	_val = base.DataContent(copyable=True)

	def __repr__(self):
		# may occur in user messages from formal, so we use title.
		return self.title

	def completeElement(self):
		if self.title is None:
			self.title = self.content_
		self._completeElementNext(Option)


def makeOptions(*args):
	"""returns a list of Option instances with values given in args.
	"""
	return [base.makeStruct(Option, content_=arg) for arg in args]


# Adapters to make options work in formal choice widgets (not in class
# since we don't want to require formal and twisted at this point)
try:
	from formal import iformal
	from twisted.python import components
	from zope.interface import implements

	class ToFormalAdapter(object):
		implements(iformal.ILabel, iformal.IKey)

		def __init__(self, original):
			self.original = original

		def label(self):
			return unicode(self.original.title)

		def key(self):
			return unicode(self.original.content_)
	
	components.registerAdapter(ToFormalAdapter, Option, iformal.ILabel)
	components.registerAdapter(ToFormalAdapter, Option, iformal.IKey)
except ImportError: # no formal/twisted -- let's hope we won't need it.
	pass


class Values(base.Structure):
	"""is a model for domains of the values of data fields.

		This is quite like the values element in a VOTable, except that nullLiterals
	of course are strings, where in VOTables nullvalues have the type of
	their field.
	"""
	name_ = "values"

	_min = UnicodeAttribute("min", None, description="Minimum acceptable"
		" value as a datatype literal", copyable=True)
	_max = UnicodeAttribute("max", None, description="Maximum acceptable"
		" value as a datatype literal", copyable=True)
	_options = base.StructListAttribute("options", 
		childFactory=Option,
		description="List of acceptable values (if set)", copyable=True)
	_default = UnicodeAttribute("default", None, description="A default"
		" value (currently only used for options).", copyable=True)
	_nullLiteral = UnicodeAttribute("nullLiteral", None, description=
		"String representing a null for this column in string literals",
		copyable=True)
	_multiOk = BooleanAttribute("multiOk", False, "Allow selection of"
		" multiple options", copyable=True)
	_fromDB = UnicodeAttribute("fromdb", default=None, description=
		"A query returning just one column to fill options from (will"
		" add to options if some are given.)")

	def makePythonVal(self, literal, sqltype):
		return typesystems.sqltypeToPython(sqltype)(literal)

	def completeElement(self):
		# evaluate fromdb
		if self.fromdb:
			try:
				res = base.SimpleQuerier().runIsolatedQuery("SELECT DISTINCT %s"%(
					self.fromdb))
				for row in res:
					self._options.feedObject(self, base.makeStruct(Option,
						content_=row[0]))
			except base.DBError: # Table probably doesn't exist yet, ignore.
				warnings.warn("Values fromdb '%s' failed, ignoring")
		self._completeElementNext(Values)

	def onParentCompleted(self):
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

	def validateOptions(self, value):
		"""returns false if value isn't either in options or doesn't consist of
		items in options.

		Various null values always validate here; non-null checking is done
		by the column on its required attribute.
		"""
		if value=="None":
			return True
		if isinstance(value, (list, tuple)):
			for val in value:
				if val and not val in self.validValues:
					return False
		else:
			return value in self.validValues
		return True


class Column(base.Structure):
	name_ = "column"

	_name = UnicodeAttribute("name", default=base.Undefined,
		description="Name of the column (should be SQL-valid)",
		copyable=True, before="type")
	_type = TypeNameAttribute("type", default="real", description=
		"datatype for the column (SQL-like type system)",
		copyable=True, before="unit")
	_unit = UnicodeAttribute("unit", default="", description=
		"Unit of the values", copyable=True, before="ucd")
	_ucd = UnicodeAttribute("ucd", default="", description=
		"UCD of the column", copyable=True, before="description")
	_description = UnicodeAttribute("description", 
		default="", description="Short (one-line) description", copyable=True)
	_tablehead = TableheadAttribute("tablehead",
		description="Terse phrase to put into table headers for this"
			" column", copyable=True)
	_utype = UnicodeAttribute("utype", default=None, description=
		"utype for this column", copyable=True)
	_required = BooleanAttribute("required", default=False,
		description="Record becomes invalid when this column is NULL", 
		copyable=True)
	_references = UnicodeAttribute("references", default=None,
		description="Raw SQL used as a references clause in DDL statements.",
		copyable=True)
	_displayHint = DisplayHintAttribute("displayHint", 
		description="Suggested presentation", copyable=True)
	_verbLevel = IntAttribute("verbLevel", default=30,
		description="Minimal verbosity level at which to include this column", 
		copyable=True)
	_values = base.StructAttribute("values", default=None,
		childFactory=Values, description="Specification of legal values", 
		copyable=True)
	_longdescr = UnicodeAttribute("longdescr", description=
		"Longish documentation for this column", copyable=True)
	_longmime = UnicodeAttribute("longmime", 
		description="Mime type for longdescr", copyable=True)
	_properties = base.PropertyAttribute()
	_original = base.OriginalAttribute()

	def isEnumerated(self):
		return self.values and self.values.options

	def __repr__(self):
		return "<Column %s>"%self.name

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

	def asInfoDict(self):
		"""returns a dictionary of certain, "user-intersting" properties
		of the data field, in a dict of strings.
		"""
		indexState = "unknown"
		if self.parent and hasattr(self.parent, "indexedColumns"):
				# parent is something like a TableDef
			if self.name in self.parent.indexedColumns:
				indexState = "indexed"
			else:
				indexState = "notIndexed"
		return {
			"name": self.name,
			"description": self.description or "N/A",
			"tablehead": self.tablehead,
			"unit": self.unit or "N/A",
			"ucd": self.ucd or "N/A",
			"verbLevel": self.verbLevel,
			"indexState": indexState
		}
	
	def getDDL(self):
		"""returns SQL describing this column ready for inclusion in a 
		DDL statement.
		"""
		items = [self.name, self.type]
		if self.required:
			items.append("NOT NULL")
		if self.references:
			items.append("REFERENCES %s ON DELETE CASCADE"%self.references)
		return " ".join(items)

	def getDisplayHintAsString(self):
		return self._displayHint.unparse(self.displayHint)

	@classmethod
	def fromMetaTableRow(cls, metaRow):
		"""returns a Column instance for a row from the meta table.
		"""
		col = cls(None)
		for (dest, src) in [("description", "description"), 
				("unit", "unit"), ("ucd", "ucd"), ("tablehead", "tablehead"),
				("longmime", "longmime"), ("utype", "utype"), 
				("verbLevel","verbLevel"), ("type", "type"), ("name", "fieldName"),
				("displayHint", "displayHint")]:
			col.feedEvent(None, "value", dest, metaRow[src])
		return col
