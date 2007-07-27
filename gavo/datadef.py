"""
Classes to define properties of data.
"""

from gavo import record

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
		})
		for key, val in initvals.iteritems():
			self.set(key, val)

	metaColMapping = {
		"fieldName": "dest",
		"longdescr": "longdescription",
		"type": "dbtype",
	}
	externallyManagedColumns = set(["tableName", "colInd"])

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
	DataField(dest="ucd", dbtype="text", description="UCD for the colum"),
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
