"""
Classes to define properties of data.
"""

from gavo import utils

class DataField(utils.Record):
	"""is a description of a data field.

	The primary feature of a data field is dest, which is used for, e.g.,
	the column name in a database.  Thus, they must be unique within
	a RecordDef.  The type information is also given for SQL dbs (or
	rather, postgresql), in dbtype.  Types for python or VOTables should
	be derivable from them, I guess.
	"""
	def __init__(self, **initvals):
		utils.Record.__init__(self, {
			"dest": utils.RequiredField,   # Name (used as column name in sql)
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
			"optional": utils.TrueBooleanField,  # NULL values in this field 
			                                     # don't invalidate record
			"literalForm": None, # special literal form that needs preprocessing
			"primary": utils.BooleanField,  # is part of the table's primary key
			"references": None,  # becomes a foreign key in SQL
			"index": None,       # if given, name of index field is part of
		})
		for key, val in initvals.iteritems():
			self.set(key, val)

	def getMetaRow(self):
		"""returns a dictionary ready for inclusion into the meta table.

		The keys have to match the definition sqlsupport.metaTableFields,
		so if these change, you will have to mirror these changes here.

		Since MetaTableHandler adds the tableName itself, we don't return
		it (also, we simply don't know it...).
		"""
		return {
			"fieldName": self.get_dest(),
			"unit": self.get_unit(),
			"ucd": self.get_ucd(),
			"description": self.get_description(),
			"tablehead": self.get_tablehead(),
			"longdescr": self.get_longdescription(),
			"longmime": self.get_longmime(),
			"literalForm": self.get_literalForm(),
			"utype": self.get_utype(),
			"type": self.get_dbtype(),
		}
