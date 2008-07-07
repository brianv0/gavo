# -*- encoding: iso-8859-1 -*-
"""
This module contains basic support for manual SQL generation.
"""

import re
import sys
import operator

from gavo import config

debug = False

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
		psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
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
		try:
			conn = psycopg2.connect("dbname='%s' port='%s' host='%s'"
				" user='%s' password='%s'"%(profile.get_database(), 
					profile.get_port(), profile.get_host(), profile.get_user(), 
					profile.get_password()))
			return conn
		except KeyError:
			raise gavo.Error("Insufficient information to connect to database."
				"  The operators need to check their profiles.")



import gavo
from gavo import utils
from gavo import logger
from gavo import datadef


class FieldError(gavo.Error):
	"""is raised by the MetaTableHandler when some operation on 
	fields/columns doesn't work out.
	"""
	pass


# This is the name of the (global) table containing units, ucds, descriptions,
# etc for all table rows of user tables
# XXX TODO: Do we still want this?  If yes, do a real table definition
# through a resource descriptor
metaTableName = "fielddescriptions"


class Error(Exception):
	pass


def getDefaultDbConnection():
	return getDbConnection(config.getDbProfile())


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
	def __init__(self, cursor, commitFunc, rollbackFunc, feedCommand):
		self.cursor, self.commitFunc = cursor, commitFunc
		self.rollbackFunc, self.feedCommand = rollbackFunc, feedCommand
	
	def __call__(self, data):
		try:
			self.cursor.execute(self.feedCommand, data)
		except Exception, exc:
			exc.gavoData = data
			raise
	
	def close(self):
		self.commitFunc()
		nAffected = self.cursor.rowcount
		try:
			self.cursor.close()
		except DbError:  # cursor has been closed before
			pass
		self.cursor = None
		return nAffected

	def rollback(self):
		self.cursor.close()
		self.rollbackFunc()

	def __del__(self):
		try:
			if self.cursor is not None:
				self.close()
				# rollback behaviour is undefined at this point.  Close your cursors...
		except (DbError, gavo.Error): 
			pass # someone else might have closed it


class StandardQueryMixin(object):
	"""is a mixin with some commonly used canned queries.

	The mixin assumes an attribute connection from the parent.
	"""
	def runIsolatedQuery(self, query, data={}, silent=False, raiseExc=True):
		"""runs a query over a connection of its own and returns a rowset of 
		the result if the query is successful.

		Mostly, you'll create all kinds of races if you think you need this.
		Unfortunately, until postgres gets nested transactions, there's little
		I can do.
		"""
		connection = getDbConnection(config.getDbProfile())
		cursor = connection.cursor()
		try:
			if debug:
				print "Executing", query, data
			cursor.execute(query, data)
			if debug:
				print "Finished", cursor.query
		except DbError, msg:
			cursor.close()
			connection.rollback()
			connection.close()
			if not silent:
				sys.stderr.write("Failed query %s with"
					" arguments %s (%s)\n"%(repr(cursor.query), data, str(msg).strip()))
			if raiseExc:
				raise
		except:
			connection.rollback()
			connection.close()
			raise
		else:
			try:
				res = cursor.fetchall()
			except DbError:  # No results to fetch
				res = None
			cursor.close()
			connection.commit()
			connection.close()
			return res

	def query(self, query, data={}):
		"""runs a single query in a new cursor and returns that cursor.

		You will see all exceptions, no transaction management will be
		done.

		Do not simply ignore errors you get from query.  To safely ignore
		errors, use runIsolatedQuery.
		"""
		cursor = self.connection.cursor()
		try:
			if debug:
				print "Executing", query, data
			cursor.execute(query, data)
			if debug:
				print "Finished", cursor.query
		except DbError:
			logger.warning("Failed db query: %s"%getattr(cursor, "query",
				query))
			raise
		return cursor

	def _parseTableName(self, tableName, schema=None):
		"""returns schema, unqualified table name for the arguments.

		schema=None selects the default schema (public for postgresql).

		If tableName is qualified (i.e. schema.table), the schema given
		in the name overrides the schema argument.
		"""
		if schema==None:
			schema = "public"
		if "." in tableName:
			schema, tableName = tableName.split(".")
		return schema, tableName

	def tableExists(self, tableName, schema=None):
		"""returns True if a table tablename exists in schema.
		
		See _parseTableName on the meaning of the arguments.

		** Postgresql specific **
		"""
		schema, tableName = self._parseTableName(tableName, schema)
		matches = self.query("SELECT table_name FROM"
			" information_schema.tables WHERE"
			" table_schema=%(schemaName)s AND table_name=%(tableName)s", {
					'tableName': tableName.lower(),
					'schemaName': schema.lower(),
			}).fetchall()
		return len(matches)!=0

	def hasIndex(self, tableName, indexName, schema=None):
		"""returns True if table tablename has and index called indexName.

		See _parseTableName on the meaning of the arguments.

		** Postgresql specific **
		"""
		schema, tableName = self._parseTableName(tableName, schema)
		res = self.query("SELECT indexname FROM"
			" pg_indexes WHERE schemaname=%(schema)s AND"
			" tablename=%(tableName)s AND"
			" indexname=%(indexName)s", locals()).fetchall()
		return len(res)>0

	def schemaExists(self, schema):
		"""returns True if the named schema exists in the database.

		** Postgresql specific **
		"""
		matches = self.query("SELECT nspname FROM"
			" pg_namespace WHERE nspname=%(schemaName)s", {
					'schemaName': schema,
			}).fetchall()
		return len(matches)!=0


class TableInterface(StandardQueryMixin):
	"""is a base class for table writers and updaters.

	At construction time, you define the database and the table.
	The table definition is used by createTable, but if you do not
	call createTable, there are no checks that the table structure in
	the database actually matches what you passed.

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

	def getIndices(self):
		indices = {}
		for field in self.fields:
			if field.get_index():
				indices.setdefault(field.get_index(), []).append(
					field.get_dest())
		return indices

	def _computePrimaryDef(self):
		primaryCols = [field.get_dest()
			for field in self.fields if field.get_primary()]
		if len(primaryCols)>0:
			return "(%s)"%", ".join(primaryCols)

	def _definePrimaryKey(self):
		primary = self._computePrimaryDef()
		if primary:
			try:
				self.query("ALTER TABLE %s ADD PRIMARY KEY %s"%(
					self.tableName, primary))
			except DbError, msg:
				raise gavo.Error("Primary key %s could not be added (%s)"%(
					primary, repr(str(msg))))

	def _dropPrimaryKey(self):
		"""drops a primary key if it exists.

		*** Postgres specific ***
		"""
		primary = self._computePrimaryDef()
		_, unqualified = self._parseTableName(self.tableName)
		constraintName = "%s_pkey"%unqualified
		if primary and self.hasIndex(self.tableName, constraintName):
			self.query("ALTER TABLE %s DROP CONSTRAINT %s"%(
				self.tableName, constraintName))

	def dropIndices(self):
		self._dropPrimaryKey()
		schema, unqualified = self._parseTableName(self.tableName)
		for indexName, members in self.getIndices().iteritems():
			if self.hasIndex(self.tableName, indexName):
				self.query("DROP INDEX %s.%s"%(schema,
					indexName))

	def makeIndices(self):
		"""creates all indices on the table, including any definition of
		a primary key.
		"""
		gavo.ui.displayMessage("Creating indices on %s."%
			self.tableName)
		self._definePrimaryKey()
		for indexName, members in self.getIndices().iteritems():
			self.query("CREATE INDEX %s ON %s (%s)"%(
				indexName, self.tableName, ", ".join(
					members)))
			if indexName.endswith("_cluster"):
				self.query("CLUSTER %s ON %s"%(indexName, self.tableName))
		if self.tableExists(self.tableName):
			self.query("ANALYZE %s"%self.tableName)

	def deleteMatching(self, matchCondition):
		"""deletes all rows matching matchCondition.

		For now, matchCondition is a 2-tuple of column name and value.
		A row will be deleted if the specified column name is equal to 
		the supplied value.

		If at some point we need more complex conditions, we should probably
		create an SqlExpression object and accept these too.
		"""
		colName, value = matchCondition
		self.query("DELETE FROM %s WHERE %s=%%(value)s"%(self.tableName,
			colName), {"value": value})

	def _getFeederForCmdStr(self, cmdStr, dropIndices):
		if dropIndices:
			self.dropIndices()
		return _Feeder(self.connection.cursor(), self.getFeedFinalizer(
			makeIndices=dropIndices), self.connection.rollback, cmdStr)

	def getFeedFinalizer(self, makeIndices=True):
		def fun():
			if makeIndices:
				self.makeIndices()
		return fun

	def copyIn(self, inFile):
		cursor = self.connection.cursor()
		cursor.copy_expert("COPY %s FROM STDIN WITH BINARY"%self.tableName, inFile)
		cursor.close()

	def copyOut(self, outFile):
		cursor = self.connection.cursor()
		cursor.copy_expert("COPY %s TO STDOUT WITH BINARY"%self.tableName, outFile)
		cursor.close()

	def getTableName(self):
		return self.tableName

	def finish(self):
		self.connection.commit()
		self.connection.close()

	def abort(self):
		self.connection.close()


class TableWriter(TableInterface):
	"""is a moderately high-level interface to feeding data into an
	SQL database.
	"""
	def __init__(self, tableName, fields, dbConnection=None, scriptRunner=None):
		super(TableWriter, self).__init__(tableName, fields, dbConnection)
		self.scriptRunner = scriptRunner

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

	def makeIndices(self):
		if self.scriptRunner:
			self.scriptRunner.runScripts("preIndex", tw=self)
			self.scriptRunner.runScripts("preIndexSQL", connection=self.connection)
		super(TableWriter, self).makeIndices()

	def createTable(self, delete=True, create=True, privs=True):
		"""creates a new table for dataset.

		An existing table is dropped before creating the new one if delete is
		true; analoguosly, you can inhibit or enable the creation or the setting of 
		privileges.  By default. everything is done.

		I don't think create=True without delete=True makes much sense,
		but who knows.
		"""
		def setPrivileges():
			for stmt in getTablePrivSQL(self.tableName):
				self.query(stmt)
	
		if delete:
			if self.tableExists(self.tableName):
				self.query("DROP TABLE %s CASCADE"%(self.tableName))
		if create:
			self.query("CREATE TABLE %s (%s)"%(
				self.tableName,
				", ".join([self._getDDLDefinition(field)
					for field in self.fields])
				))
		if privs:
			setPrivileges()
	
	def ensureSchema(self, schemaName):
		"""makes sure a schema of schemaName exists.

		If it doesn't it will create the schema an set the appropriate
		privileges.
		"""
		if not self.schemaExists(schemaName):
			self.query("CREATE SCHEMA %(schemaName)s"%locals())
			for stmt in getSchemaPrivSQL(schemaName):
				self.query(stmt)
	
	def getFeeder(self, dropIndices=True):
		"""returns a callable object that takes dictionaries containing
		values for the database.

		The callable object has a close method that must be called after
		all db feeding is done.
		"""
		cmdStr = "INSERT INTO %s (%s) VALUES (%s)"%(
			self.tableName, 
			", ".join([f.get_dest() for f in self.fields]),
			", ".join(["%%(%s)s"%f.get_dest() for f in self.fields]))
		return self._getFeederForCmdStr(cmdStr, dropIndices)


class TableUpdater(TableInterface):
	"""is a TableWriter that does updates rather than inserts on
	feed.
	"""
	def getFeeder(self, dropIndices=True):
		"""returns a callable object that takes dictionaries that will
		replace records with the same primary key.
		"""
		primaryCols = [field.get_dest()
			for field in self.fields if field.get_primary()]
		cmdStr = "UPDATE %s SET %s WHERE %s"%(
			self.tableName,
			", ".join(["%s=%%(%s)s"%(f.get_dest(), f.get_dest())
				for f in self.fields]),
			" AND ".join(["%s=%%(%s)s"%(n, n) for n in primaryCols]))
		return self._getFeederForCmdStr(cmdStr, dropIndices)


class SimpleQuerier(StandardQueryMixin):
	"""is a tiny interface to querying the standard database.

	You can query (which makes raises normal exceptions and renders
	the connection unusable after an error), runIsolatedQuery (which
	may catch exceptions and in any case uses a connection of its own
	so your own connection remains usable; however, you'll have race
	conditions with it).

	You have to close() manually; you also have to commit() when you
	change something, finish() does 'em both.
	"""
	def __init__(self, connection=None):
		if connection:
			self.connection = connection
			self.ownedConnection = False
		else:
			self.connection = getDbConnection(config.getDbProfile())
			self.ownedConnection = True

	def rollback(self):
		self.connection.rollback()

	def commit(self):
		self.connection.commit()

	def close(self):
		try:
			self.connection.close()
		except DbError:
			pass

	def finish(self):
		self.commit()
		if self.ownedConnection:
			self.close()

	def __del__(self):
		if self.ownedConnection and self.connection:
			self.close()
		

class MetaTableHandler:
	"""is an interface to the meta table.

	The meta table holds information on all columns of all user tables
	in the database.  Its definition is given in datadef.metaTableFields.
	"""
	def __init__(self, querier=None):
		if querier==None:
			self.querier = SimpleQuerier()
		else:
			self.querier = querier
		self.writer = TableWriter(metaTableName, datadef.metaTableFields,
			dbConnection=self.querier.connection)
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
		feed = self.writer.getFeeder(dropIndices=False)
		for colInd, colDesc in enumerate(columnDescriptions):
			items = {"tableName": tableName, "colInd": colInd}
			items.update(colDesc)
			feed(items)
		feed.close()
		self.writer.finish()

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


def makeRowsetFromDicts(dictList, fieldDefs):
	"""returns a rowset for a list of dicts.
	"""
# Well, maybe we should switch the whole thing to the dict interface to
# the database, then all this crazy dict<->tuple converting wouldn't
# be necessary...  Sigh.
	fieldNames = [f.get_dest() for f in fieldDefs]
	return [tuple(d[name] for name in fieldNames) for d in dictList]


if __name__=="__main__":
	t = TableWriter("test.test", [("f1", "text", {}), ("f2", "text", {})])
	t.ensureSchema("test")
	t.createTable()
	f = t.getFeeder()
	f({"f1": "blabla", "f2": u"önögnü"})
	f.close()
