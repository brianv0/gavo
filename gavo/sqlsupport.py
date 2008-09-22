# -*- encoding: iso-8859-1 -*-
"""
This module contains basic support for manual SQL generation.
"""

import re
import sys
import operator

from gavo import config
from gavo import meta
from gavo import resourcecache  # we need importparser.getRd from there,
# so somebody else has to import it before the metatable can be accessed.

debug = False
feedDebug = False

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
	import psycopg2.extras
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
			qobjs = []
			for o in self._seq:
				if isinstance(o, unicode):
					qobjs.append(psycopg2.extensions.adapt(str(o)).getquoted()) 
				else:
					qobjs.append(psycopg2.extensions.adapt(o).getquoted()) 
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
		if isinstance(profile, basestring):
			profile = config.getDbProfileByName(profile)
		elif profile is None:
			profile = config.getDbProfile()
		try:
			connString = ("dbname='%s' port='%s' host='%s'"
				" user='%s' password='%s'")%(profile.get_database(), 
					profile.get_port(), profile.get_host(), profile.get_user(), 
					profile.get_password())
			conn = psycopg2.connect(connString, 
					connection_factory=psycopg2.extras.InterruptibleConnection)
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
tableSourceName = "dc_tables"


class Error(Exception):
	pass


def getDefaultDbConnection():
	return getDbConnection(config.getDbProfile())


def encodeDbMsg(msg):
	"""returns the string or sql exception msg in ascii.
	"""
	return str(msg).decode(config.get("db", "msgEncoding")
		).encode("ascii", "replace")


_privTable = {
	"arwdRx": "ALL",
	"arwdRxt": "ALL",
	"r": "SELECT",
	"UC": "ALL",
	"U": "USAGE",
}

def parsePGACL(acl):
	"""returns a dict roleName->acl for acl in postgres'
	ACL serialization.

	*** postgres specific ***
	"""
	if acl is None:
		return {}
	res = []
	for acs in re.match("{(.*)}", acl).group(1).split(","):
		role, privs, granter = re.match("([^=]*)=([^/]*)/(.*)", acs).groups()
		res.append((role, _privTable.get(privs, "READ")))
	return dict(res)


def getACLFromRes(thingWithRoles):
	"""returns a dict of (role, ACL) as it is defined in tableDef or RD
	thingWithRoles, in our internal notation.

	*** postgres specific ***
	"""
	res = []
	for role in thingWithRoles.get_allRoles():
		res.append((role, "ALL"))
	if hasattr(thingWithRoles, "get_schema"): # it's an RD
		readRight = "USAGE"
	else:
		readRight = "SELECT"
	for role in thingWithRoles.get_readRoles():
		res.append((role, readRight))
	return dict(res)


def getTablePrivileges(schema, tableName, querier):
	"""returns (owner, readRoles, allRoles) for the relation tableName
	and the schema.

	*** postgres specific ***
	"""
	res = querier.query("SELECT relacl FROM pg_class WHERE"
		" relname=%(tableName)s AND"
		" relnamespace=(SELECT oid FROM pg_namespace WHERE nspname=%(schema)s)",
		locals()).fetchall()
	return parsePGACL(res[0][0])


def getSchemaPrivileges(schema, querier):
	"""returns (owner, readRoles, allRoles) for the relation tableName
	and the schema.

	*** postgres specific ***
	"""
	res = querier.query("SELECT nspacl FROM pg_namespace WHERE"
		" nspname=%(schema)s", locals()).fetchall()
	return parsePGACL(res[0][0])


def _updatePrivileges(objectName, foundPrivs, shouldPrivs, querier):
	"""is a helper for set[Table|Schema]Privileges.

	Requests for granting privileges not known to the database are
	ignored, but a log entry is generated.
	"""
	for role in set(foundPrivs)-set(shouldPrivs):
		querier.query("REVOKE ALL PRIVILEGES ON %s FROM %s"%(
			objectName, role))
	for role in set(shouldPrivs)-set(foundPrivs):
		if querier.roleExists(role):
			querier.query("GRANT %s ON %s TO %s"%(shouldPrivs[role], objectName,
				role))
		else:
			logger.error("Request to grant privileges to non-existing"
				" database user %s dropped"%role)
	for role in set(shouldPrivs)&set(foundPrivs):
		if shouldPrivs[role]!=foundPrivs[role]:
			querier.query("REVOKE ALL PRIVILEGES ON %s FROM %s"%(
				objectName, role))
			querier.query("GRANT %s ON %s TO %s"%(shouldPrivs[role], objectName,
				role))


def setTablePrivileges(tableDef, querier):
	"""sets the privileges defined in tableDef for that table through
	querier.
	"""
	_updatePrivileges(tableDef.getQName(),
		getTablePrivileges(tableDef.rd.get_schema(), tableDef.get_table(),
			querier), 
		getACLFromRes(tableDef), querier)


def setSchemaPrivileges(rd, querier):
	"""sets the privileges defined on rd to its schema.

	This function will never touch the public schema.
	"""
	schema = rd.get_schema().lower()
	if schema=="public":
		return
	_updatePrivileges("SCHEMA %s"%schema,
		getSchemaPrivileges(schema, querier), getACLFromRes(rd), querier)
	

def _makePrivInstruction(instruction, argList):
	"""returns instruction with argList filled into %s, or None if argList is
	empty.
	"""
	if argList:
		return instruction%(", ".join(argList))


class _Feeder:
	"""is a callable used for feeding data into a table.

	Don't instanciate this yourself; TableWriter.getFeeder does this
	for you.
	"""
	def __init__(self, cursor, commitFunc, rollbackFunc, feedCommand):
		self.cursor, self.commitFunc = cursor, commitFunc
		self.rollbackFunc, self.feedCommand = rollbackFunc, feedCommand
		if feedDebug:
			print "Starting feed with", feedCommand
	
	def __call__(self, data):
		if feedDebug:
			print "Feeding", data
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
			if feedDebug:
				print "Feed commited; rows affected:", nAffected
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
	defaultProfile = None

	def runIsolatedQuery(self, query, data={}, silent=False, raiseExc=True,
			timeout=None):
		"""runs a query over a connection of its own and returns a rowset of 
		the result if the query is successful.

		Mostly, you'll create all kinds of races if you think you need this.
		Unfortunately, until postgres gets nested transactions, there's little
		I can do.
		"""
		connection = getDbConnection(self.defaultProfile)
		cursor = connection.cursor()
		try:
			if debug:
				print "Executing", query, data
			if timeout:
				cursor.execute(query, data, timeout=timeout)
			else:
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
		if schema is None:
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

	def getOIDForTable(self, tableName):
		"""returns the current oid of tableName.

		tableName may be schema qualified.  If it is not, public is assumed.
		"""
		schema, tableName = self._parseTableName(tableName, schema)
		res = self.query("SELECT oid FROM pg_class WHERE"
			" relname=%(tableName)s AND"
			" relnamespace=(SELECT oid FROM pg_namespace WHERE nspname=%(schema)s)",
			locals()).fetchall()
		assert len(res)==1
		return res[0][0]

	def roleExists(self, role):
		"""returns True if there role is known to the database.

		** Postgresql specific **
		"""
		matches = self.query("SELECT usesysid FROM pg_user WHERE usename="
			"%(role)s", locals()).fetchall()
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

	A TableInterface is constructed with a parsing.TableDef instance.
	The TableDef instance must be "rooted", i.e. have a non-None rd
	attribute.

	The table definition is through a sequence of datadef.DataField
	instances.
	"""
	def __init__(self, tableDef, dbConnection=None):
		if dbConnection:
			self.connection = dbConnection
		else:
			self.connection = getDbConnection(config.getDbProfile())
		self.tableDef = tableDef
		if self.tableDef.rd is None:
			raise Error("TableDefs without resource descriptor cannot be"
				" used to access database tables")
		self.fields = self.tableDef.get_items()
		self.tableName = self.tableDef.getQName()
		self.ensureSchema(self.tableDef.rd.get_schema())

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

	def getPIName(self):
		"""is the name of the primary index on this table.

		*** Postgres specific ***
		"""
		return "%s_pkey"%self.tableDef.get_table()

	def _dropPrimaryKey(self):
		"""drops a primary key if it exists.

		*** Postgres specific ***
		"""
		primary = self._computePrimaryDef()
		constraintName = self.getPIName()
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

	def ensureTable(self):
		if self.tableExists(self.tableName):
			return
		self.createTable()

	def ensureSchema(self, schemaName):
		"""makes sure a schema of schemaName exists.

		If it doesn't it will create the schema an set the appropriate
		privileges.
		"""
		if not self.schemaExists(schemaName):
			self.query("CREATE SCHEMA %(schemaName)s"%locals())
			setSchemaPrivileges(self.tableDef.rd, self)

	def finish(self):
		self.connection.commit()
		self.connection.close()

	def abort(self):
		self.connection.close()


class TableWriter(TableInterface):
	"""is a moderately high-level interface to feeding data into an
	SQL database.
	"""
	def __init__(self, tableDef, dbConnection=None, meta=True):
		TableInterface.__init__(self, tableDef, dbConnection)
		self.workingOnView = self.tableDef.hasScript("viewCreation")
		self.meta = meta

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
# XXX TODO: views  are just too different from Tables.  Refactor to have
# a ViewWriter and a ViewDefinition in RDs
		if not self.workingOnView:
			self.tableDef.runScripts("preIndex", tw=self)
			self.tableDef.runScripts("preIndexSQL", connection=self.connection)
		if not self.workingOnView:
			TableInterface.makeIndices(self)

	def dropTable(self):
		if self.tableExists(self.tableName):
			self.query("DROP %s %s CASCADE"%(
				{True: "VIEW", False: "TABLE"}[self.workingOnView],
				self.tableName))
			self.tableDef.runScripts("afterDrop", connection=self.connection)
			if self.meta:
				mh = MetaTableHandler()
				mh.clean(self.tableDef, self)

	def createTable(self, delete=True, create=True, privs=True):
		"""creates a new table for dataset.

		An existing table is dropped before creating the new one if delete is
		true; analoguosly, you can inhibit or enable the creation or the setting of 
		privileges.  By default. everything is done.

		I don't think create=True without delete=True makes much sense,
		but who knows.
		"""
		def setPrivileges():
			setTablePrivileges(self.tableDef, self)
	
		if delete:
			self.dropTable()
		if create:
			if self.workingOnView:
				self.tableDef.runScripts("viewCreation", querier=self)
			else:
				self.query("CREATE TABLE %s (%s)"%(
					self.tableName,
					", ".join([self._getDDLDefinition(field)
						for field in self.fields])
					))
		if privs:
			setPrivileges()
		if self.meta:
			mh = MetaTableHandler()
			mh.updateSourceTable(self.tableDef, self)
			mh.defineColumns(self.tableDef, self)

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
	def __init__(self, connection=None, useProfile=None):
		self.defaultProfile = useProfile
		if connection:
			self.connection = connection
			self.ownedConnection = False
		else:
			self.connection = getDbConnection(useProfile or config.getDbProfile())
			self.ownedConnection = True

	def rollback(self):
		self.connection.rollback()

	def commit(self):
		self.connection.commit()

	def close(self):
		try:
			self.connection.close()
			self.connection = None
		except (DbError, AttributeError):
			# Let's assume that is because the connection is alredy gone
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
	in the database.  Its definition is given in the __system__/dc_tables
	RD.
	"""
	def __init__(self, overrideProfile=None):
		self.profile = overrideProfile or "admin"
		self.rd = resourcecache.getRd("__system__/dc_tables")
		self.metaTable = self.rd.getTableDefByName("fielddescriptions")
		self.sourceTable = self.rd.getTableDefByName("dc_tables")
		self.readQuerier = self._getQuerier()

	def _getQuerier(self):
		return SimpleQuerier(getDbConnection(self.profile))

	def cleanSourceTable(self, tableDef, querier):
		if tableDef.getQName()!="public.dc_tables":
			querier.query("DELETE FROM dc_tables WHERE tableName=%(tableName)s",
				{"tableName": tableDef.getQName()})

	def updateSourceTable(self, tableDef, querier):
		self.cleanSourceTable(tableDef, querier)
		writer = TableWriter(self.sourceTable, querier.connection, meta=False)
		feed = writer.getFeeder(dropIndices=False)
		feed({"tableName": tableDef.getQName(), "sourceRd": tableDef.rd.sourceId,
			"adql": tableDef.get_adql(), 
			"tableDesc": meta.getMetaText(tableDef, "description"),
			"resDesc": meta.getMetaText(tableDef.rd, "description"),})
		feed.close()

	def cleanColumns(self, tableDef, querier):
		if tableDef.getQName()!="public.fielddescriptions":
			querier.query("DELETE FROM %s WHERE tableName=%%(tableName)s"%
				self.metaTable.getQName(), {"tableName": tableDef.getQName()})

	def defineColumns(self, tableDef, querier):
		self.cleanColumns(tableDef, querier)
		tableName = tableDef.getQName()
		writer = TableWriter(self.metaTable, querier.connection, meta=False)
		feed = writer.getFeeder(dropIndices=False)
		for colInd, field in enumerate(tableDef.get_items()):
			items = {"tableName": tableName, "colInd": colInd}
			items.update(field.getMetaRow())
			feed(items)
		feed.close()

	def update(self, tableDef):
		querier = self._getQuerier()
		self.updateSourceTable(tableDef, querier)
		self.defineColumns(tableDef, querier)
		querier.finish()

	def clean(self, tableDef, querier):
		self.cleanSourceTable(tableDef, querier)
		self.cleanColumns(tableDef, querier)
		
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
			res = self.readQuerier.query("SELECT * FROM %s WHERE"
				" tableName=%%(tableName)s"
				" AND fieldName=%%(fieldName)s"%self.metaTable.getQName(), {
					"tableName": tableName,
					"fieldName": fieldName,})
			matches = res.fetchall()
		except OperationalError:
			matches = []
		if len(matches)==0:
			raise FieldError("No info for %s in %s"%(fieldName, tableName))
		# since we're querying the primary key, len>1 can't happen
		for fieldDef, val in zip(self.metaTable.get_items(), matches[0]):
			resDict[fieldDef.get_dest()] = val
		return resDict
	
	def getFieldInfos(self, tableName):
		"""returns a field definition list for tableName.
		"""
		res = self.readQuerier.query("SELECT * FROM %s WHERE"
			" tableName=%%(tableName)s"
			" ORDER BY colInd"%self.metaTable.getQName(), {"tableName": tableName})
		fieldInfos = []
		for row in res.fetchall():
			fieldInfos.append(datadef.DataField.fromMetaTableRow(row))
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
