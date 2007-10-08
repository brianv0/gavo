"""
Classes to define properties of data.
"""

from gavo import record
from gavo.parsing import meta

class DataField(record.Record):
	"""is a description of a data field.

	The primary feature of a data field is dest, which is used for, e.g.,
	the column name in a database.  Thus, they must be unique within
	a RecordDef.  The type information is also given for SQL dbs (or
	rather, postgresql), in dbtype.  Types for python or VOTables should
	be derivable from them, I guess.
	"""
	def __init__(self, **initvals):
		record.Record.__init__(self, {
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
			"nullvalue": "",     # value to interpret as NULL/None
			"optional": record.TrueBooleanField,  # NULL values in this field 
			                                     # don't invalidate record
			"literalForm": None, # special literal form that needs preprocessing
			"primary": record.BooleanField,  # is part of the table's primary key
			"references": None,  # becomes a foreign key in SQL
			"index": None,       # if given, name of index field is part of
			"displayHint": "string", # suggested presentation, see queryrun.Format
			"verbLevel": 30,     # hint for building VOTables
			"id": None,          # Just so the field can be referenced within XML
			"copy": record.BooleanField,  # Used with TableGrammars
		})
		for key, val in initvals.iteritems():
			self.set(key, val)

	metaColMapping = {
		"fieldName": "dest",
		"longdescr": "longdescription",
		"type": "dbtype",
	}
	externallyManagedColumns = set(["tableName", "colInd"])

	def __repr__(self):
		return "<DataField %s>"%self.get_dest()

	def set_primary(self, val):
		"""implies a verbLevel of 1 if verbLevel has not been set otherwise.
		"""
		self.dataStore["primary"] = record.parseBooleanLiteral(val)
		if self.get_primary():
			if self.get_verbLevel()==30:
				self.set_verbLevel(1)

	def set_longdescription(self, txt, mime=None):
		if mime==None:
			if isinstance(txt, tuple):
				self.dataStore["longdescription"] = txt[0]
				self.set_longmime(txt[1])
			else:
				self.dataStore["longdescription"] = txt
				self.set_longmime("text/plain")
		else:
			self.dataStore["longdescription"] = txt
			self.set_longmime(mime)

	def getValueIn(self, aDict, atExpand=lambda val, _: val):
		"""returns the value the field has within aDict.

		This involves handling nullvalues and such.  atExpand,
		if passed, has to be a callable receiving and returning
		one value (usually, it's going to be the embedding
		descriptor's atExpander)
		"""
		preVal = None
		if self.get_source()!=None:
			preVal = aDict.get(self.get_source())
		if preVal==self.get_nullvalue():
			preVal = None
		if preVal==None:
			preVal = atExpand(self.get_default(), aDict)
		return preVal

	def getMetaRow(self):
		"""returns a dictionary ready for inclusion into the meta table.

		Since MetaTableHandler adds tableName and colInd, we don't return
		them (also, we simply don't know them...).
		"""
		row = {}
		for fInfo in metaTableFields:
			colName = fInfo.get_dest()
			if colName in self.externallyManagedColumns:
				continue
			row[colName] = self.get(self.metaColMapping.get(colName, colName))
		return row


# This is a schema for the field description table used by
# sqlsupport.MetaTableHandler.  WARNING: If you change anything here, you'll
# probably have to change DataField, too (plus, of course, the schema of
# any meta tables you may already have).

metaTableFields = [
	DataField(dest="tableName", dbtype="text", primary=True, 
		description="Name of the table the column is in"),
	DataField(dest="fieldName", dbtype="text", primary=True,
		description="SQL identifier for the column"),
	DataField(dest="unit", dbtype="text", description="Unit for the value"),
	DataField(dest="ucd", dbtype="text", description="UCD for the column"),
	DataField(dest="description", dbtype="text", 
		description="A one-line characterization of the value"),
	DataField(dest="tablehead", dbtype="text", 
		description="A string suitable as a table heading for the values"),
	DataField(dest="longdescr", dbtype="text", 
		description="A possibly long information on the values"),
	DataField(dest="longmime", dbtype="text", 
		description="Mime type of longdescr"),
	DataField(dest="displayHint", dbtype="text", 
		description="Suggested presentation format"),
	DataField(dest="utype", dbtype="text", description="A utype for the column"),
	DataField(dest="colInd", dbtype="integer", description=
		"Index of the column within the table"),
	DataField(dest="type", dbtype="text", description="SQL type of this column"),
	DataField(dest="verbLevel", dbtype="integer", 
		description="Level of verbosity at which to include this column"),
]


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
			"items": record.ListField,
			"macros": record.ListField,
		}
		baseFields.update(additionalFields)
		record.Record.__init__(self, baseFields, initvals)
		self.rD = parentRD

	def __repr__(self):
		return "<DataDescriptor id=%s>"%self.get_id()

	def _validate(self, record):
		"""checks that the docRec record satisfies the constraints given
		by self.items.

		This method reflects that DataTransformers are RecordDefs for
		the toplevel productions.
		"""
		for field in self.get_items():
			if not field.get_optional() and record.get(field.get_dest())==None:
				raise resource.ValidationError(
					"%s is None but non-optional"%field.get_dest())

	def registerAsMetaParent(self):
		# This is called by the MetaMixin
		if self.get_Semantics():
			for recDef in self.get_Semantics().get_recordDefs():
				recDef.setMetaParent(self)

	def copy(self):
		"""returns a deep copy of self.
		"""
		nd = DataDescriptor(self.rD,
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

	def getRD(self):
		return self.rD
	
	def getRecordDefByName(self, name):
		"""returns the record definition for the table name.

		It raises a KeyError if the table name is not known.
		"""
		return self.get_Semantics().getRecordDefByName(name)

	def getInputFields(self):
		"""returns a sequence of dataFields if this data descriptor takes
		fielded input.

		The method will raise an AttributeError if the grammar does not take
		fielded input.
		"""
		return self.get_Grammar().getInputFields()

