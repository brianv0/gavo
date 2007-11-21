# -*- encoding: iso-8859-1 -*-
"""
This module contains basic support for manual SQL generation.

A word on the fieldInfos that are used here: python-gavo has two ways of
defining fields: The DataField from datadef and the fieldInfos from 
sqlsupport.  DataFields are utils.records containing much the same
data that fieldInfos hold in dicts.  The reason that the two are distinct
is historical (DataFields were originally exclusively for parsing), and at 
some point we should probably make sqlsupport use DataFields as well.
"""

import re
import sys
import operator

from gavo import config

usePgSQL = config.get("db", "interface")=="pgsql"

if usePgSQL:
	from pyPgSQL import PgSQL
	from pyPgSQL.PgSQL import OperationalError, DatabaseError
	from pyPgSQL.PgSQL import Error as DbError

	def getDbConnection(profile):
		dsn = "%s:%s:%s"%(profile.get_host(), profile.get_port(), 
			profile.get_database())
		return PgSQL.connect(dsn=dsn, user=profile.get_user(), 
			password=profile.get_password(), client_encoding="utf-8")
else:
	import psycopg2
	import psycopg2.extensions
	try:
		psycopg2.extensions.register_type(psycopg2._psycopg.MXDATETIME)
		psycopg2.extensions.register_type(psycopg2._psycopg.MXINTERVAL)
		psycopg2.extensions.register_type(psycopg2._psycopg.MXDATE)
		psycopg2.extensions.register_type(psycopg2._psycopg.MXTIME)
	except AttributeError:
		sys.stderr.write("WARNING: Your psycopg2 was compiled without"
			" mxDateTime support.\n  Expect trouble when processing dates"
			" or set interface=pgsql\n in your ~/.gavorc.\n")
	try:
		import mod_python.util
		psycopg2.extensions.register_adapter(mod_python.util.StringField, 
			psycopg2.extensions.QuotedString)
	except ImportError:
		pass

	class SqlSetAdapter(object):
		"""is an adapter that formats python sequences as SQL sets.

		-- as opposed to psycopg2's apparent default of building arrays
		out of them.
		"""
		def __init__(self, seq):
			self._seq = seq

		def prepare(self, conn):
			pass

		def getquoted(self):
			qobjs = [str(psycopg2.extensions.adapt(o).getquoted()) 
				for o in self._seq]
			return '(%s)'%(", ".join(qobjs))

		__str__ = getquoted


	class SqlArrayAdapter(object):
		"""is an adapter that formats python sequences as SQL arrays
		"""
		def __init__(self, seq):
			self._seq = seq

		def prepare(self, conn):
			pass

		def getquoted(self):
			if not self._seq:
				return 'NULL'
			qobjs = [str(psycopg2.extensions.adapt(o).getquoted()) 
				for o in self._seq]
			return 'ARRAY[ %s ]'%(", ".join(qobjs))

		__str__ = getquoted

	psycopg2.extensions.register_adapter(tuple, SqlArrayAdapter)
	psycopg2.extensions.register_adapter(list, SqlSetAdapter)
	psycopg2.extensions.register_adapter(set, SqlSetAdapter)
	
	from gavo import coords

	class BoxAdapter(object):
		"""is an adapter for coords.Box instances to SQL boxes.
		"""
		def __init__(self, box):
			self._box = box

		def prepare(self, conn):
			pass

		def getquoted(self):
			# "'(%s,%s)'"%self._box would work as well, but let's be conservative
			# here
			res = "'((%f, %f), (%f, %f))'"%(self._box.x0, self._box.y0,
				self._box.x1, self._box.y1)
			return res

	psycopg2.extensions.register_adapter(coords.Box, BoxAdapter)

	# XXX TODO: I'm using a fixed oid here because I don't want to do
	# a db connection during import to find out OIDs.  This *should*
	# work fine, but really it should be delegated into a "connection set-up"
	# type thing.  I'll do it when I really have persistent db connections.
	BOX_OID = 603

	def castBox(value, cursor):
		"""makes coords.Box instances from SQL boxes.
		"""
		if value:
			vals = map(float, re.match(r"\(([\d.+eE-]+),([\d.+eE-]+)\),"
				"\(([\d.+eE-]+),([\d.+eE-]+)\)", value).groups())
			return coords.Box(vals[0], vals[2], vals[1], vals[3])
	
	_SQLBOX = psycopg2.extensions.new_type((BOX_OID,), "BOX", castBox)
	psycopg2.extensions.register_type(_SQLBOX)

	from psycopg2 import OperationalError, DatabaseError, IntegrityError
	from psycopg2 import Error as DbError

	def getDbConnection(profile):
		return psycopg2.connect("dbname='%s' port='%s' host='%s'"
			" user='%s' password='%s'"%(profile.get_database(), 
				profile.get_port(), profile.get_host(), profile.get_user(), 
				profile.get_password()))



import gavo
from gavo import utils
from gavo import logger
from gavo import datadef


class FieldError(gavo.Error):
	"""is raised when some operation on fields/columns doesn't work out.
	"""
	pass


# This is the name of the (global) table containing units, ucds, descriptions,
# etc for all table rows of user tables
metaTableName = "fielddescriptions"


class Error(Exception):
	pass



def encodeDbMsg(msg):
	"""returns the string or sql exception msg in ascii.
	"""
	return str(msg).decode(config.get("db", "msgEncoding")
		).encode("ascii", "replace")


def _makePrivInstruction(instruction, argList):
	"""returns instruction with argList filled into %s, or None if argList is
	empty.
	"""
	if argList:
		return instruction%(", ".join(argList))


def getTablePrivSQL(tableName):
	"""returns a sequence of SQL statements that grant the default privileges 
	for the installation on table tableName.
	"""
	dbProfile = config.getDbProfile()
	return filter(operator.truth, [
		_makePrivInstruction("GRANT ALL PRIVILEGES ON %s TO %%s"%tableName,
			dbProfile.get_allRoles()),
		_makePrivInstruction("GRANT SELECT ON %s TO %%s"%tableName,
			dbProfile.get_readRoles())])


def getSchemaPrivSQL(schema):
	"""returns a sequence of SQL statements that grant the default privileges 
	for the installation to schema.
	"""
	dbProfile = config.getDbProfile()
	return filter(operator.truth, [
		_makePrivInstruction("GRANT USAGE, CREATE ON SCHEMA %s TO %%s"%schema,
			dbProfile.get_allRoles()),
		_makePrivInstruction("GRANT USAGE ON SCHEMA %s TO %%s"%schema,
			dbProfile.get_readRoles())])


class _Feeder:
	"""is a callable used for feeding data into a table.

	Don't instanciate this yourself; TableWriter.getFeeder does this
	for you.
	"""
	def __init__(self, cursor, commitFunc, feedCommand):
		self.cursor, self.commitFunc = cursor, commitFunc
		self.feedCommand = feedCommand
	
	def __call__(self, data):
		try:
			self.cursor.execute(self.feedCommand, data)
		except Exception, exc:
			exc.gavoData = data
			raise
	
	def close(self):
		self.commitFunc()
		nAffected = self.cursor.rowcount
		self.cursor.close()
		self.cursor = None
		return nAffected
	
	def __del__(self):
		if self.cursor is not None:
			self.close()


class StandardQueryMixin:
	"""is a mixin with some commonly used canned queries.

	The mixin assumes an attribute connection from the parent.
	"""
	def runOneQuery(self, query, data={}, silent=False):
		"""runs a query and returns the cursor used.

		You need to commit yourself if the query changed anything.
		"""
		cursor = self.connection.cursor()
		try:
			cursor.execute(query, data)
		except DatabaseError, msg:
			if not silent:
				sys.stderr.write("Failed query %s with"
					" arguments %s (%s)\n"%(repr(cursor.query), data, str(msg).strip()))
			raise
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

	At construction time, you define the database and the table.
	The table definition is used by createTable, but if you do not
	call createTable, there are no checks that the table structure in
	the database actually matches what you passed.	In particualar,
	we don't touch any indices.

	Table names are not parsed.  If they include a schema, you need
	to make sure it exists (ensureSchema) before creating the table.

	The table definition is through a sequence of datadef.DataField
	instances.
	"""
	def __init__(self, tableName, fields, dbConnection=None):
		if dbConnection:
			self.connection = dbConnection
		else:
			self.connection = getDbConnection(config.getDbProfile())
			
		self.tableName = tableName
		self.fields = fields

	def _sendSQL(self, cmd, args={}, failok=False):
		"""sends raw SQL, using a new cursor.
		"""
		try:
			cursor = self.runOneQuery(cmd, args, silent=failok)
		except DbError, msg:
			logger.warning("Ignoring SQL error %s for %s since you asked"
				" me to."%(msg, repr(cmd)))
		else:
			cursor.close()
		self.connection.commit()

	def _getDDLDefinition(self, field):
		"""returns an sql fragment for defining the field described by the 
		DataField field.
		"""
		items = [field.get_dest(), field.get_dbtype()]
		if not field.get_optional():
			items.append("NOT NULL")
		if field.get_references():
			items.append("REFERENCES %s ON DELETE CASCADE"%field.get_references())
		return " ".join(items)

	def getIndices(self):
		indices = {}
		for field in self.fields:
			if field.get_index():
				indices.setdefault(field.get_index(), []).append(
					field.get_dest())
		return indices

	def dropIndices(self):
		try:
			schema, _ = self.tableName.split(".")
		except ValueError:
			schema = "public"
		for indexName, members in self.getIndices().iteritems():
			self._sendSQL("DROP INDEX %s.%s"%(schema,
				indexName), failok=True)

	def makeIndices(self):
		gavo.ui.displayMessage("Creating indices on %s."%
			self.tableName)
		for indexName, members in self.getIndices().iteritems():
			self._sendSQL("CREATE INDEX %s ON %s (%s)"%(
				indexName, self.tableName, ", ".join(
					members)))

	def createTable(self, delete=True, create=True, privs=True):
		"""creates a new table for dataset.

		An existing table is dropped before creating the new one if delete is
		true; analoguosly, you can inhibit or enable the creation, setting of 
		privileges, setting of the primary key, and definition of indices.
		By default. everything is done.
		"""
		def setPrivileges():
			for stmt in getTablePrivSQL(self.tableName):
				self._sendSQL(stmt)
		
		def computePrimaryDef():
			primaryCols = [field.get_dest()
					for field in self.fields if field.get_primary()]
			if primaryCols:
				return ", PRIMARY KEY (%s)"%(",".join(primaryCols))
			else:
				return ""

		if delete:
			self._sendSQL("DROP TABLE %s CASCADE"%(self.tableName),
				failok=True)
		if create:
			self._sendSQL("CREATE TABLE %s (%s%s)"%(
				self.tableName,
				", ".join([self._getDDLDefinition(field)
					for field in self.fields]),
				computePrimaryDef(),
				))
		if privs:
			setPrivileges()

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
			self._sendSQL("CREATE SCHEMA %(schemaName)s"%locals())
			for stmt in getSchemaPrivSQL(schemaName):
				self._sendSQL(stmt)
	
	def deleteMatching(self, matchCondition):
		"""deletes all rows matching matchCondition.

		For now, matchCondition is a 2-tuple of column name and value.
		A row will be deleted if the specified column name is equal to 
		the supplied value.

		If at some point we need more complex conditions, we should probably
		create an SqlExpression object and accept these too.

		WARNING: This drops all indices on the table without restoring them.
		That shouldn't be a problem since you'll usually get a feeder of
		the table later on.
		"""
		self.dropIndices()
		colName, value = matchCondition
		self._sendSQL("DELETE FROM %s WHERE %s=%%(value)s"%(self.tableName,
			colName), {"value": value})

	def getFeeder(self):
		"""returns a callable object that takes dictionaries containing
		values for the database.

		The callable object has a close method that must be called after
		all db feeding is done.
		"""
		self.dropIndices()
		cmdString = "INSERT INTO %s (%s) VALUES (%s)"%(
			self.tableName, 
			", ".join([f.get_dest() for f in self.fields]),
			", ".join(["%%(%s)s"%f.get_dest() for f in self.fields]))
		return _Feeder(self.connection.cursor(), self.finalizeFeeder,
			cmdString)

	def getTableName(self):
		return self.tableName

	def close(self):
		self.connection.commit()
		self.connection.close()
	
	def finalizeFeeder(self):
		self.makeIndices()
		self.connection.commit()


class TableUpdater(TableWriter):
	"""is a TableWriter that does update request rather than inserts on
	feed.
	"""
# XXX TODO: refactor so TableWriter and this have a common base class
	def getFeeder(self):
		"""returns a callable object that takes dictionaries that will
		replace records with the same primary key.
		"""
		self.dropIndices()
		primaryCols = [field.get_dest()
			for field in self.fields if field.get_primary()]
		cmdString = "UPDATE %s SET %s WHERE %s"%(
			self.tableName,
			", ".join(["%s=%%(%s)s"%(f.get_dest(), f.get_dest())
				for f in self.fields]),
			" AND ".join(["%s=%%(%s)s"%(n, n) for n in primaryCols]))
		return _Feeder(self.connection.cursor(), self.finalizeFeeder,
			cmdString)


class SimpleQuerier(StandardQueryMixin):
	"""is a tiny interface to querying the standard database.
	"""
	def __init__(self):
		self.connection = getDbConnection(config.getDbProfile())

	def query(self, query, data={}):
		return self.runOneQuery(query, data)

	def commit(self):
		self.connection.commit()
	
	def close(self):
		self.connection.close()


class ScriptRunner:
	"""is an interface to run simple static scripts on the SQL data base.

	The script should be a string containing one command per line.  You
	can use the backslash as a continuation character.  Leading whitespace
	on a continued line is ignored, the linefeed becomes a single blank.

	Also, we abort and raise an exception on any error in the script.
	We will probably define some syntax to have errors ignored.
	"""
	def __init__(self):
		self.connection = getDbConnection(config.getDbProfile())

	def run(self, script):
		script = re.sub(r"\\\n\s*", " ", script)
		cursor = self.connection.cursor()
		for query in script.split("\n"):
			query = query.strip()
			if not query:
				continue
			failOk = False
			query = query.strip()
			if query.startswith("-"):
				failOk = True
				query = query[1:]
			try:
				cursor.execute(query)
			except DbError, msg:
				if failOk:
					gavo.logger.debug("SQL script operation %s failed (%s) -- ignoring"
						" error on your request."%(query, encodeDbMsg(msg)))
				else:
					gavo.logger.error("SQL script operation %s failed (%s) --"
						" aborting script."%(query, encodeDbMsg(msg)))
					raise
		cursor.close()
		self.commit()
	
	def commit(self):
		self.connection.commit()


class MetaTableHandler:
	"""is an interface to the meta table.

	The meta table holds information on all columns of all user tables
	in the database.  Its definition is given in datadef.metaTableFields.
	"""
	def __init__(self, querier=None):
		self.writer = TableWriter(metaTableName, datadef.metaTableFields)
		if querier==None:
			self.querier = SimpleQuerier()
		else:
			self.querier = querier
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

	def _fixFieldInfo(self, resDict):
		"""does some ad-hoc changes to amend fieldInfos coming
		from the database.

		Right now, it only computes a suitable table heading
		for the column description resDict if necessary.
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
		parts = fieldName.split(".")
		if len(parts)==2:
			tableName, fieldName = parts
		elif len(parts)==3:
			tableName = ".".join(parts[:2])
			fieldName = parts[2]
		elif len(parts)!=1:
			raise FieldError("Invalid column specification: %s"%fieldName)
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
		for fieldDef, val in zip(datadef.metaTableFields, matches[0]):
			resDict[fieldDef.get_dest()] = val
		self._fixFieldInfo(resDict)
		return resDict
	
	def getFieldInfos(self, tableName):
		"""returns a field definition list for tableName.
		
		Each field definition is a dictionary, the keys of which are given by
		datadef.metaTableFields.  The sequence is in database column order.
		"""
		res = self.querier.query("SELECT * FROM %s WHERE tableName=%%(tableName)s"%
			metaTableName, {"tableName": tableName})
		fieldInfos = []
		for row in res.fetchall():
			fieldInfos.append(dict([(metaFieldInfo.get_dest(), val) 
				for metaFieldInfo, val in zip(datadef.metaTableFields, row)]))
			self._fixFieldInfo(fieldInfos[-1])
		fieldInfos.sort(lambda a, b: cmp(a["colInd"], b["colInd"]))
		return fieldInfos


if __name__=="__main__":
	t = TableWriter("test.test", [("f1", "text", {}), ("f2", "text", {})])
	t.ensureSchema("test")
	t.createTable()
	f = t.getFeeder()
	f({"f1": "blabla", "f2": u"önögnü"})
	f.close()
