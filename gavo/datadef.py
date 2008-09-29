"""
Classes to define properties of data.
"""

import gavo
from gavo import record
from gavo import resourcecache # need importparser.getRd here, so someone else
# needs to import importparser
from gavo import meta
from gavo.parsing import typeconversion



class RoEmptyDict:
	"""is a read-only standin for a dict.

	It's hashable, though, since it's always empty...
	"""
	def get(self, key, default=None):
		return default

	def has_key(self, key):
		return False

	def __hash__(self):
		return hash(id(self))

	def __getitem__(key):
		raise KeyError(key)

	def __setitem__(self, what, where):
		raise TypeError("RoEmptyDicts are immutable")

	def iteritems(self):
		if False:
			yield None
		return

_roEmptyDict = RoEmptyDict()


class DataField(record.Record):
	"""is a description of a data field.

	The primary feature of a data field is dest, which is used for, e.g.,
	the column name in a database.  Thus, they must be unique within
	a TableDef.  The type information is also given for SQL dbs (or
	rather, postgresql), in dbtype.  Types for python or VOTables should
	be derivable from them, I guess.
	"""
	additionalFields = {}
	def __init__(self, **initvals):
		myFields={
			"dest": record.RequiredField,   # Name (used as column name in sql)
			"source": None,      # preterminal name to fill field from
			"default": None,     # constant value to fill field with
			"dbtype": "real",    # SQL type of this field
			"unit": None,        # physical unit of the value
			"ucd": None,         # ucd classification of the value
			"description": None, # short ("one-line") description
			"longdescription": None,  # long description
			"longmime": None,    # mime-type of contents of longdescription
			"tablehead": None,   # name to be used as table heading
			"utype": None,       # a utype
			"optional": record.TrueBooleanField,  # NULL values in this field 
			                                      # don't invalidate record
			"literalForm": None, # special literal form that needs preprocessing
			"primary": record.BooleanField,  # is part of the table's primary key
			"references": None,  # becomes a foreign key in SQL
			"index": None,       # if given, name of index field is part of
			"displayHint": _roEmptyDict, # suggested presentation
			"verbLevel": 30,     # hint for building VOTables
			"id": None,          # Just so the field can be referenced within XML
			"values": None,      # a datadef.Values instance (see below)
			"copy": record.BooleanField,  # Used with TableGrammars
			"property": record.DictField, # User properties
		}
# Another bad hack, but I need to inherit from this and want additional
# fields without messing up the constructor signature that's used all over
# the place.
		myFields.update(self.additionalFields)
		super(DataField, self).__init__(myFields, initvals=initvals)

	metaColMapping = {
		"fieldName": "dest",
		"longdescr": "longdescription",
		"type": "dbtype",
	}
	externallyManagedColumns = set(["tableName", "colInd", "displayHint"])

	def isEnumerated(self):
		return self.get_values() and self.get_values().get_options()

	def __repr__(self):
		return "<DataField %s>"%self.get_dest()

	def set_displayHint(self, val):
		if isinstance(val, dict) or val==_roEmptyDict:
			dh = val
		elif val:
			try:
				dh = dict([f.split("=") for f in val.split(",")])
			except (ValueError, TypeError):
				raise gavo.Error("Invalid display hint %s"%repr(val))
		else:
			dh = {}
		self.dataStore["displayHint"] = dh

	def getDisplayHintAsText(self):
		return ",".join(
			["%s=%s"%(k,v) for k,v in self.get_displayHint().iteritems()])

	def set_primary(self, val):
		"""implies a verbLevel of 1 if verbLevel has not been set otherwise.
		"""
		self.dataStore["primary"] = record.parseBooleanLiteral(val)
		if self.get_primary():
			if self.get_verbLevel()==30:
				self.set_verbLevel(1)

	def set_longdescription(self, txt, mime=None):
		if mime is None:
			if isinstance(txt, tuple):
				self.dataStore["longdescription"] = txt[0]
				self.set_longmime(txt[1])
			else:
				self.dataStore["longdescription"] = txt
				self.set_longmime("text/plain")
		else:
			self.dataStore["longdescription"] = txt
			self.set_longmime(mime)

	def set_name(self, name):
		self.set_dest(name)
		self.set_source(name)

	def set_values(self, values):
		# The values attribute needs to convert the literals it is constructed
		# with to self's dbtype.
		if values is not None:
			values.convert(self)
		self.dataStore["values"] = values

	def set_verbLevel(self, value):
		self.dataStore["verbLevel"] = int(value)

	def getValueIn(self, aDict, atExpand=lambda val, _: val):
		"""returns the value the field has within aDict.

		This involves handling nullvalues and such.  atExpand,
		if passed, has to be a callable receiving and returning
		one value (usually, it's going to be the embedding
		descriptor's atExpander)
		"""
		preVal = None
		if self.get_source() is not None:
			preVal = aDict.get(self.get_source())
		if self.get_values() and preVal==self.get_values().get_nullLiteral():
			preVal = None
		if preVal is None:
			preVal = atExpand(self.get_default(), aDict)
		return preVal

	def getMetaRow(self):
		"""returns a dictionary ready for inclusion into the meta table.

		Since MetaTableHandler adds tableName and colInd, we don't return
		them (also, we simply don't know them...).
		"""
		row = {}
		for fInfo in resourcecache.getRd("__system__/dc_tables"
				).getTableDefByName("fielddescriptions").get_items():
			colName = fInfo.get_dest()
			if colName in self.externallyManagedColumns:
				continue
			row[colName] = self.get(self.metaColMapping.get(colName, colName))
		row["displayHint"] = self.getDisplayHintAsText()
		return row

	def validate(self, value):
		"""raises a ValidationError if value does not match the constraints
		given here.
		"""
		if not self.get_optional() and value is None:
			raise gavo.ValidationError(
				"Field %s is empty but non-optional"%self.get_dest(),
				self.get_dest())
		vals = self.get_values()
		if vals:
			if vals.get_options():
				if value and not vals.validateOptions(value):
					raise gavo.ValidationError("Value %s not consistent with"
						" legal values %s"%(value, vals.get_options()), self.get_dest())
			else:
				if vals.get_min() and value<vals.get_min():
					raise gavo.ValidationError("%s too small (must be at least %s)"%(
						value, vals.get_min()), self.get_dest())
				if vals.get_max() and value>vals.get_max():
					raise gavo.ValidationError("%s too large (must be less than %s)"%(
						value, vals.get_max()), self.get_dest())

	def asInfoDict(self):
		"""returns a dictionary of certain, "user-intersting" properties
		of the data field, in a dict of strings.
		"""
		return {
			"name": self.get_dest(), 
			"description": self.get_description() or "N/A",
			"tablehead": self.get_tablehead() or "N/A",
			"unit": self.get_unit() or "N/A",
			"ucd": self.get_ucd() or "N/A",
			"verbLevel": self.get_verbLevel() or "N/A",
			"indexState": self.get_index() and "index" or "noindex",
		}
	
	@classmethod
	def fromDataField(cls, dataField):
		"""constructs a DataField from another DataField.

		This is basically like copy, but is specialized for DataFields.
		It does not inherit properties.  I'm not sure yet if that's something
		we want or something I should change.
		"""
		args = dataField.dataStore.copy()
		del args["property"]
		instance = cls(**args)
		if instance.get_values():
			instance.set_values(instance.get_values().copy())
		return instance

	@classmethod
	def fromMetaTableRow(cls, row):
		"""constructs a DataField from what's in the meta table.
		"""
# XXX todo: use a RowsetGrammar to get this from dc_tables.
		initvals = {}
		for name, index in [("dest", 1), ("source", 1), 
				("unit", 2), ("ucd", 3), ("description", 4), ("tablehead", 5),
				("longdescription", 6), ("utype", 8), ("dbtype", 10),
				("verbLevel", 11), ("displayHint", 12)]:
			initvals[name] = row[index]
		return cls(**initvals)


class OutputField(DataField):
	"""is a DataField for output purposes.
	"""
	additionalFields = {
		"select": None,    # a select clause to use instead of dest
		"renderer": None,  # Python code for a renderer function body
		"wantsRow": record.BooleanField,  # Pass the 
		                                  # formatter/renderer the whole row
	}

	def __repr__(self):
		return "<OutputField %s>"%self.get_dest()

	def get_select(self):
		if self.dataStore["select"]:
			return "(%s) as %s"%(self.dataStore["select"], self.dataStore["dest"])
		return self.dataStore["dest"]

	@classmethod
	def fromDataField(cls, dataField, munge=True):
		instance = super(OutputField, cls).fromDataField(dataField)
		if instance.get_values():
			instance.set_values(instance.get_values().copy())
		if munge:
			instance.set_source(instance.get_dest())
			instance.set_optional(True)
		return instance


def makeCopyingField(field):
	"""returns a copy of field that has field.dest as field.source as well.

	Also, it sets all literalForms to "do not touch".

	That kind of thing is needed with rowsetGrammars.
	"""
	newField = DataField()
	newField.updateFrom(field)
	if newField.get_source()!="None":
		newField.set_source(field.get_dest())
	newField.set_literalForm("do not touch")
	return newField


class DataTransformer(record.Record, meta.MetaMixin):
	"""is a generic description of a class receiving data in some format
	and generating data in a different format.

	The transformation is done through a grammar that describes how to
	get a dictionary of global properties of the data and a list of dictionaries
	for the "rows" of the data (the "rowdicts"), and a semantics part that says 
	how to produce output rows complete with metadata for these rows.
	"""
	def __init__(self, parentRD, additionalFields={}, initvals={}):
		baseFields = {
			"Grammar": record.RequiredField,
			"Semantics": record.RequiredField,
			"id": record.RequiredField,        # internal id of the data set.
			"encoding": "ascii", # of string literals coming in
			"constraints": None, # ignored, present for TableDef interface
			"items": record.DataFieldList,
			"macros": record.ListField,
		}
		baseFields.update(additionalFields)
		record.Record.__init__(self, baseFields, initvals)
		self.rd = parentRD
		self.setMetaParent(parentRD)

	def __repr__(self):
		return "<DataDescriptor id=%s>"%self.get_id()

	def __iter__(self):
		"""iterates over all embedded TableDefs.
		"""
		for recDef in self.get_Semantics().get_tableDefs():
			yield recDef

	def set_Grammar(self, val):
		self.dataStore["Grammar"] = val

	def set_Semantics(self, val):
		for tableDef in val.get_tableDefs():
			tableDef.setMetaParent(self)
		self.dataStore["Semantics"] = val

	def validate(self, record):
		"""checks that the docRec record satisfies the constraints given
		by self.items.

		This method reflects that DataTransformers are TableDefs for
		the toplevel productions.
		"""
# XXX TODO: This should probably be unified with TableDef.validate.
		for field in self.get_items():
			field.validate(record.get(field.get_dest()))

	def registerAsMetaParent(self):
		try:
			if self.get_Semantics():
				for recDef in self.get_Semantics().get_tableDefs():
					recDef.setMetaParent(self)
		except (AttributeError, KeyError):  # No children yet
			pass

	def copy(self):
		"""returns a deep copy of self.
		"""
		nd = self.__class__(self.rd,
			source=self.get_source(),
			sourcePat=self.get_sourcePat(),
			encoding=self.get_encoding())
		for item in self.get_items(): nd.addto_items(item)
		for macro in self.get_macros(): nd.addto_macros(macro)
		try:
			nd.set_Grammar(self.get_Grammar().copy())
		except KeyError:
			pass
		try:
			nd.set_Semantics(self.get_Semantics().copy())
		except KeyError:
			pass
		return nd

	def getRd(self):
		return self.rd
	
	def getTableDefByName(self, name):
		"""returns the record definition for the table name.

		It raises a KeyError if the table name is not known.
		"""
		return self.get_Semantics().getTableDefByName(name)

	def getPrimaryTableDef(self):
		return self.get_Semantics().get_tableDefs()[0]

	def getInputFields(self):
		"""returns a sequence of dataFields if this data descriptor takes
		fielded input.

		The method will raise an AttributeError if the grammar does not take
		fielded input.
		"""
		return self.get_Grammar().getInputFields()


# Once we need values with non-ascii characters, we'll need to create
# encoding-aware LiteralParsers, but for now that's too much stress.
makePythonVal = typeconversion.asciiLiteralParser.makePythonVal


class Values(record.Record):
	"""models domains and properties of the values of data fields.

	This is quite like the values element in a VOTable, except that nullLiterals
	of course are strings, where in VOTables nullvalues have the type of
	their field.

	Warning: on the first validate, the options list is "frozen" into a set.
	There currently is no way to re-evaluate options into such a set.
	"""
	def __init__(self, **initvals):
		record.Record.__init__(self, {
			"min": None,   # a *python* value of the minimum acceptable value
			"max": None,   # a *python* value of the maximum acceptable value
			"options": record.ListField, # python values acceptable
			"default": None, # if options are set, this will be the first one 
				# in there unless set explicitely
			"nullLiteral": None, # a string representing null in literals
			"multiOk": record.BooleanField,
		}, initvals)
		self._optionsSet = None
	
	def convert(self, dataField):
		"""converts min, max, and options from string literals to python
		objects.

		This is called by the parent DataDef when it adopts a Values instance.
		"""
		# It would be nicer if we could handle this in set_min etc, but
		# unfortunately we don't know our parent DataDef then.  The only
		# way around that would have been delegations from datadef, and that's
		# not very attractive either.
		if self.get_min():
			self.set_min(makePythonVal(self.get_min(), dataField.get_dbtype(),
				dataField.get_literalForm()))
		if self.get_max():
			self.set_max(makePythonVal(self.get_max(), dataField.get_dbtype(),
				dataField.get_literalForm()))
		if self.get_options():
			if self.get_default() is None and isinstance(self.get_options(), list):
				self.set_default(self.get_options()[0])
			dbt, lf = dataField.get_dbtype(), dataField.get_literalForm()
			self.dataStore["options"] = [makePythonVal(opt, dbt, lf)
				for opt in self.get_options()]

	def validateOptions(self, value):
		"""returns false if value isn't either in options or doesn't consist of
		items in options.
		"""
		if self._optionsSet is None:
			self._optionsSet = set(self.get_options())
		if value=="None":
			return True
		if isinstance(value, (list, tuple)):
			for val in value:
				if val and not val in self._optionsSet:
					return False
		else:
			return value in self._optionsSet
		return True
