# -*- encoding: iso-8859-1 -*-
"""
This module contains basic support for manual SQL generation.
"""


from pyPgSQL import PgSQL

import gavo
from gavo import utils
from gavo import config
from gavo import logger


class FieldError(gavo.Error):
	"""is raised when some operation on fields/columns doesn't work out.
	"""
	pass


# This is the name of the (global) table containing units, ucds, descriptions,
# etc for all table rows of user tables
metaTableName = "fielddescriptions"

# This is a schema for the field description table.  WARNING: If you
# change anything here, you'll probably have to change 
# parsing.resource.getMetaRow as well.
metaTableFields = [
	("tableName", "text", {"primary": True, "index": "meta_fields",
		"description": "Name of the table the column is in"}),
	("fieldName", "text", {"primary": True, "index": "meta_fields",
		"description": "SQL identifier for the column"}),
	("unit", "text", {"description": "Unit for the value"}),
	("ucd", "text", {"description": "UCD for the colum"}),
	("description", "text", {"description": "A one-line characterization of"
		" the value"}),
	("tablehead", "text", {"description": "A string suitable as a table heading"
		" for the values"}),
	("longdescr", "text", {"description": "A possibly long information on"
		" the values"}),
	("longmime", "text", {"description": "Mime type of longdescr"}),
# We probably don't want this in here -- it should be used for
# parsing exclusively.
	("literalForm", "text", {"description": "Information on special literal"
		" forms (e.g., blanks within float literals)"}),
	("utype", "text", {"description": "A utype for the column"}),
	("colInd", "integer", {"description": 
		"Index of the column within the table"}),
	("type", "text", {"description": "SQL type of this column"}),
]

class Error(Exception):
	pass

from pyPgSQL.PgSQL import OperationalError

def encodeDbMsg(msg):
	"""returns the string or sql exception msg in ascii.
	"""
	return str(msg).decode(config.settings.get_db_msgEncoding()
		).encode("ascii", "replace")


class _Feeder:
	"""is a callable used for feeding data into a table.

	Don't instanciate this yourself; TableWriter.getFeeder does this
	for you.
	"""
	def __init__(self, cursor, commitFunc, feedCommand):
		self.cursor, self.commitFunc = cursor, commitFunc
		self.feedCommand = feedCommand
	
	def __call__(self, data):
		self.cursor.execute(self.feedCommand, data)
	
	def close(self):
		self.commitFunc()
		self.cursor.close()
		self.cursor = None
	
	def __del__(self):
		if self.cursor is not None:
			self.close()


class StandardQueryMixin:
	"""is a mixin with some commonly used canned queries.

	The mixin assumes an attribute connection from the parent.
	"""
	def runOneQuery(self, query, data={}):
		"""runs a query and returns the cursor used.

		You need to commit yourself if the query changed anything.
		"""
		cursor = self.connection.cursor()
		cursor.execute(query, data)
		return cursor

	def tableExists(self, tableName, schema=None):
		"""returns True if a table tablename exists in schema.

		schema=None selects the default schema (public for postgresql).

		If tableName is qualified (i.e. schema.table), the schema given
		in the name overrides the schema argument.

		** Postgresql specific **
		"""
		if schema==None:
			schema = "public"
		if "." in tableName:
			schema, tableName = tableName.split(".")
		result = self.runOneQuery("SELECT table_name FROM"
			" information_schema.tables WHERE"
			" table_schema=%(schemaName)s AND table_name=%(tableName)s", {
					'tableName': tableName,
					'schemaName': schema,
			})
		matches = result.fetchall()
		result.close()
		return len(matches)!=0

	def schemaExists(self, schema):
		"""returns True if the named schema exists in the database.

		** Postgresql specific **
		"""
		result = self.runOneQuery("SELECT nspname FROM"
			" pg_namespace WHERE nspname=%(schemaName)s", {
					'schemaName': schema,
			})
		numMatches = len(result.fetchall())
		result.close()
		return numMatches!=0


class TableWriter(StandardQueryMixin):
	"""is a moderately high-level interface to feeding data into an
	SQL database.

	The access parameters are taken from config, which usually gets
	them from ~/.gavosettings (or $GAVOSETTINGS).

	At construction time, you define the database and the table.
	The table definition is used by createTable, but if you do not
	call createTable, there are no checks that the table structure in
	the database actually matches what you passed.	In particualar,
	we don't touch any indices.

	Table names are not parsed.  If they include a schema, you need
	to make sure it exists (ensureSchema) before creating the table.

	The table definition is through a list of triples (fieldname,
	type, options), where options is a dictionary.

	Keywords recognized in options include

	 * default -- the value has to be a valid SQL expression for a
	 column's default

	 * notnull -- if the key notnull is defined regardless of its
	 value, NULL values are forbidden for that field.

	 * primary -- if the key primary is defined regardless of its
	 value, the field will be added to the fields comprising the primary key

	 * index -- tablewriter will request an index on the field.
	 The value is name of the index (and thus has to be a valid
	 SQL identifier), fields with identical strings will be
	 indexed together.  These names are db global and will *not*
	 be prefixed by the scheme.  You should therefore use a prefix
	 like schema_table_ or something.

	 * references -- the same as in SQL, the value has to legal SQL
	 """
	def __init__(self, tableName, fieldDef):
		self.connection = PgSQL.connect(dsn=config.settings.get_db_dsn(),
			user=config.settings.get_db_user(), 
			password=config.settings.get_db_password(),
			client_encoding="utf-8")
		self.tableName = tableName
		self.fieldDef = fieldDef

	def _sendSQL(self, cmd, args={}, failok=False):
		"""sends raw SQL, using a new cursor.

		We probably need more abstraction here:-)
		"""
		cursor = self.connection.cursor()
		try:
			cursor.execute(cmd, args)
		except PgSQL.Error, msg:
			if not failok:
				raise Error("Bad SQL in %s (%s)"%(repr(cmd), msg))
			else:
				logger.warning("Ignoring SQL error %s for %s since you asked"
					" me to."%(msg, repr(cmd)))
		cursor.close()
		self.connection.commit()

	def _getSqlFieldDesc(self, fieldDef):
		name, type, options = fieldDef
		items = [name, type]
		if "notnull" in options:
			items.append("NOT NULL")
		if "default" in options:
			items.append("DEFAULT %s"%options["default"])
		if "references" in options:
			items.append("REFERENCES %s ON DELETE CASCADE"%options["references"])
		return " ".join(items)

	def createTable(self, delete=True, create=True, privs=True,
			primaryDef=True, indices=True):
		"""creates a new table for dataset.

		An existing table is dropped before creating the new one if delete is
		true; analoguosly, you can inhibit or enable the creation, setting of 
		privileges, setting of the primary key, and definition of indices.
		By default. everything is done.
		"""
		def setPrivileges():
			for role in config.settings.get_db_allroles():
				self._sendSQL("GRANT ALL PRIVILEGES ON %s TO %s"%(self.tableName,
					role))
			for role in config.settings.get_db_readroles():
				self._sendSQL("GRANT SELECT ON %s TO %s"%(self.tableName,
					role))
		
		def computePrimaryDef():
			primaryCols = [fieldName 
					for fieldName, _, options in self.fieldDef
				if "primary" in options]
			if primaryCols:
				return ", PRIMARY KEY (%s)"%(",".join(primaryCols))
			else:
				return ""

		def makeIndices():
			indices = {}
			for fieldName, _, options in self.fieldDef:
				if "index" in options:
					indices.setdefault(options["index"], []).append(fieldName)
			for indexName, members in indices.iteritems():
				self._sendSQL("CREATE INDEX %s ON %s (%s)"%(
					indexName, self.tableName, ", ".join(
						members)))

		if delete:
			self._sendSQL("DROP TABLE %s CASCADE"%(self.tableName),
				failok=True)
		if create:
			self._sendSQL("CREATE TABLE %s (%s%s)"%(
				self.tableName,
				", ".join([self._getSqlFieldDesc(fd)
					for fd in self.fieldDef]),
				computePrimaryDef(),
				))
		if privs:
			setPrivileges()
		if indices:
			makeIndices()

	def createIfNew(self):
		"""creates the target table if it does not yet exist.

		If it does, this is a no-op.
		"""
		if not self.tableExists(self.tableName):
			self.createTable()

	def ensureSchema(self, schemaName):
		"""makes sure a schema of schemaName exists.

		If it doesn't it will create the schema an set the appropriate
		privileges.
		"""
		if not self.schemaExists(schemaName):
			self._sendSQL("CREATE SCHEMA %(schemaName)s"%locals(),
				failok=False)
			for role in config.settings.get_db_allroles():
				self._sendSQL("GRANT USAGE, CREATE ON SCHEMA %s TO %s"%(schemaName,
					role))
			for role in config.settings.get_db_readroles():
				self._sendSQL("GRANT USAGE ON SCHEMA %s TO %s"%(schemaName,
					role))
	
	def deleteMatching(self, matchCondition):
		"""deletes all rows matching matchCondition.

		For now, matchCondition is a 2-tuple of column name and value.
		A row will be deleted if the specified column name is equal to 
		the supplied value.

		If at some point we need more complex conditions, we should probably
		create an SqlExpression object and accept these too.
		"""
		colName, value = matchCondition
		self._sendSQL("DELETE FROM %s WHERE %s=%%(value)s"%(self.tableName,
			colName), {"value": value})

	def getFeeder(self):
		"""returns a callable object that takes dictionaries containing
		values for the database.

		The callable object has a close method that must be called after
		all db feeding is done.
		"""
		cmdString = "INSERT INTO %s (%s) VALUES (%s)"%(
			self.tableName, 
			", ".join([name for name, _, _ in self.fieldDef]),
			", ".join(["%%(%s)s"%name for name, _, _ in self.fieldDef]))
		return _Feeder(self.connection.cursor(), self.connection.commit,
			cmdString)

	def close(self):
		self.connection.commit()
		self.connection.close()


class SimpleQuerier(StandardQueryMixin):
	"""is a tiny interface to querying the standard database.
	"""
	def __init__(self):
		self.connection = PgSQL.connect(dsn=config.settings.get_db_dsn(),
			user=config.settings.get_db_user(), 
			password=config.settings.get_db_password(),
			client_encoding="utf-8")

	def query(self, query, data={}):
		return self.runOneQuery(query, data)

	def commit(self):
		self.connection.commit()


class ScriptRunner:
	"""is an interface to run simple static scripts on the SQL data base.

	The script should be a string containing one command per line.  We
	should define a continuation character, but I'm not yet decided what
	a good choice would be.

	Also, we abort and raise an exception on any error in the script.
	We will probably define some syntax to have errors ignored.
	"""
	def __init__(self):
		self.connection = PgSQL.connect(dsn=config.settings.get_db_dsn(),
			user=config.settings.get_db_user(), 
			password=config.settings.get_db_password(),
			client_encoding="utf-8")

	def run(self, script):
		cursor = self.connection.cursor()
		for query in script.split("\n"):
			failOk = False
			query = query.strip()
			if query.startswith("-"):
				failOk = True
				query = query[1:]
			try:
				cursor.execute(query)
			except OperationalError, msg:
				if failOk:
					gavo.logger.debug("SQL script operation %s failed (%s) -- ignoring"
						" error on your request."%(query, encodeDbMsg(msg)))
				else:
					gavo.logger.error("SQL script operation %s failed (%s) --"
						" aborting script."%(query, encodeDbMsg(msg)))
					raise
		cursor.close()
	
	def commit(self):
		self.connection.commit()


class MetaTableHandler:
	"""is an interface to the meta table.

	The meta table holds information on all columns of all user tables
	in the database.  Its definition is given in metaTableFields.
	"""
	def __init__(self):
		self.writer = TableWriter(metaTableName, metaTableFields)
		self.querier = SimpleQuerier()
		self._ensureTable()
	
	def _ensureTable(self):
		if self.querier.tableExists(metaTableName):
			return
		self.writer.createTable()
	
	def defineColumns(self, tableName, columnDescriptions):
		self.querier.query(
			"DELETE FROM %s WHERE tableName=%%(tableName)s"%metaTableName,
			{"tableName": tableName}).close()
		self.querier.commit()
		feed = self.writer.getFeeder()
		for colInd, colDesc in enumerate(columnDescriptions):
			items = {"tableName": tableName, "colInd": colInd}
			items.update(colDesc)
			feed(items)
		feed.close()

	def _fixColumnHead(self, resDict):
		"""computes a suitable table heading for the column description resDict
		if necessary.
		"""
		if resDict["tablehead"]:
			return
		resDict["tablehead"]= resDict["fieldName"]

	def getFieldInfo(self, fieldName, tableName=""):
		"""returns a dictionary with the information available
		for fieldName.

		fieldName can be "fully qualified", i.e. given as <schema>.<table>.<column>
		of <table>.<column> (which implies the public schema).  If they are
		not, tableName will be used for the query instead.

		Table names are opaque to MetaTableHandler but will
		usually include a schema.
		"""
		resDict = {}
		try:
			res = self.querier.query("SELECT * FROM %s WHERE tableName=%%(tableName)s"
				" AND fieldName=%%(fieldName)s"%metaTableName, {
					"tableName": tableName,
					"fieldName": fieldName,})
			matches = res.fetchall()
		except OperationalError:
			matches = []
		if len(matches)==0:
			raise FieldError("No info for %s in %s"%(fieldName, tableName))
		# since we're querying the primary key, len>1 can't happen
		for fieldDef, val in zip(metaTableFields, matches[0]):
			resDict[fieldDef[0]] = val
		self._fixColumnHead(resDict)
		return resDict
	
	def getFieldDefs(self, tableName):
		"""returns a field definition list for tableName.
		
		Each field definition is a dictionary, the keys of which are given by
		metaTableFields above.
		"""
		res = self.querier.query("SELECT * FROM %s WHERE tableName=%%(tableName)s"%
			metaTableName, {"tableName": tableName})
		fieldDefs = []
		for row in res.fetchall():
			valdict = dict([(fieldDef[0], val) 
				for fieldDef, val in zip(metaTableFields, row)])
			fieldDefs.append((valdict["fieldName"], valdict["type"], valdict))
		fieldDefs.sort(lambda a, b: cmp(a[2]["colInd"], b[2]["colInd"]))
		return fieldDefs


if __name__=="__main__":
	t = TableWriter("test.test", [("f1", "text", {}), ("f2", "text", {})])
	t.ensureSchema("test")
	t.createTable()
	f = t.getFeeder()
	f({"f1": "blabla", "f2": u"önögnü"})
	f.close()
