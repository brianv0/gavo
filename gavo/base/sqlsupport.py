# -*- encoding: iso-8859-1 -*-
"""
Basic support for communicating with the database server.

This is currently very postgres specific.  If we really wanted to
support some other database, this would need massive refactoring.
"""

import contextlib
import operator
import os
import re
import sys
from itertools import *

from gavo import utils
from gavo.base import caches
from gavo.base import config

debug = "GAVO_SQL_DEBUG" in os.environ

import psycopg2
import psycopg2.extensions
import psycopg2.pool
psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
try:
	psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)
except AttributeError:  # UNICODEARRAY only at psycopg2 >2.0
	pass

from psycopg2.extras import DictCursor

class Error(utils.Error):
	pass


# Keep track of wether we have installed our extensions
# (this is to not require a DB connection on just importing this)
_PSYCOPG_INITED = False

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
psycopg2.extensions.register_adapter(frozenset, SqlSetAdapter)

from psycopg2 import (OperationalError, DatabaseError, IntegrityError,
	ProgrammingError, InterfaceError, DataError)
from psycopg2.extensions import QueryCanceledError
from psycopg2 import Error as DBError


def registerAdapter(type, adapter):
	psycopg2.extensions.register_adapter(type, adapter)


def registerType(oid, name, castFunc):
	newOID = psycopg2.extensions.new_type(oid, name, castFunc)
	psycopg2.extensions.register_type(newOID)


class DebugCursor(psycopg2.extensions.cursor):
	def execute(self, sql, args=None):
		print "Executing %s %s"%(id(self.connection), sql)
		res = psycopg2.extensions.cursor.execute(self, sql, args)
		print "Finished %s %s"%(id(self.connection), self.query)
		return res
	
	def executemany(self, sql, args=[]):
		print "Executing many", sql
		print "%d args, first one:\n%s"%(len(args), args[0])
		res = psycopg2.extensions.cursor.executemany(self, sql, args)
		print "Finished many", self.query
		return res


class DebugConnection(psycopg2.extensions.connection):
	def cursor(self, *args, **kwargs):
		kwargs["cursor_factory"] = DebugCursor
		return psycopg2.extensions.connection.cursor(self, *args, **kwargs)


def getDBConnection(profile, debug=debug, autocommitted=False):
	if isinstance(profile, basestring):
		profile = config.getDBProfileByName(profile)
	elif profile is None:
		profile = config.getDBProfile()

	if debug:
		conn = psycopg2.connect(connection_factory=DebugConnection,
			**profile.getArgs())
		print "NEW CONN using %s"%profile.name, id(conn)
		def closer():
			print "CONNECTION CLOSE", id(conn)
			return DebugConnection.close(conn)
		conn.close = closer
	else:
		try:
			conn = psycopg2.connect(**profile.getArgs())
		except OperationalError, msg:
			raise utils.ReportableError("Cannot connect to the database server."
				" The database library reported:\n\n%s"%msg,
				hint="This usually means you must adapt either the access profiles"
				" in $GAVO_DIR/etc or your database config (in particular,"
				" pg_hba.conf).")

	if not _PSYCOPG_INITED:
		_initPsycopg(conn)
	if autocommitted:
		conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
	conn.set_client_encoding("UTF8")
	return conn


def getDefaultDBConnection(debug=debug):
	return getDBConnection(config.getDBProfile(), debug=debug)


def encodeDBMsg(msg):
	"""returns the string or sql exception msg in ascii.
	"""
	return str(msg).decode(config.get("db", "msgEncoding")
		).encode("ascii", "replace")


def _parseTableName(tableName, schema=None):
		"""returns schema, unqualified table name for the arguments.

		schema=None selects the default schema (public for postgresql).

		If tableName is qualified (i.e. schema.table), the schema given
		in the name overrides the schema argument.
		"""
		if schema is None:
			schema = "public"
		if "." in tableName:
			schema, tableName = tableName.split(".")
		return schema.lower(), tableName.lower()


def parseBannerString(bannerString, digits=2):
	"""returns digits from a postgres server banner.

	This hardcodes the response given by postgres 8 and raises a ValueError
	if the expected format is not found.
	"""
	mat = re.match(r"PostgreSQL ([\d.]*)", bannerString)
	if not mat:
		raise ValueError("Cannot make out the Postgres server version from %s"%
			repr(bannerString))
	return ".".join(mat.group(1).split(".")[:digits])


class PostgresQueryMixin(object):
	"""is a mixin containing various useful queries that are postgres specific.

	This mixin expects a parent that mixes is QuerierMixin (that, for now,
	also mixes in PostgresQueryMixin, so you won't need to mix this in).
	"""
	def getServerVersion(self, digits=2):
		"""returns the version of the connection's server to digits numbers.
		"""
		bannerString = list(self.query("SELECT version()"))[0][0]
		return parseBannerString(bannerString, digits)

	def getPrimaryIndexName(self, tableName):
		"""returns the name of the index corresponding to the primary key on 
		(the unqualified) tableName.
		"""
		return ("%s_pkey"%tableName).lower()
	
	def schemaExists(self, schema):
		"""returns True if the named schema exists in the database.
		"""
		matches = self.query("SELECT nspname FROM"
			" pg_namespace WHERE nspname=%(schemaName)s", {
					'schemaName': schema,
			}).fetchall()
		return len(matches)!=0
	
	def hasIndex(self, tableName, indexName, schema=None):
		"""returns True if table tablename has and index called indexName.

		See _parseTableName on the meaning of the arguments.
		"""
		schema, tableName = _parseTableName(tableName, schema)
		res = self.query("SELECT indexname FROM"
			" pg_indexes WHERE schemaname=lower(%(schema)s) AND"
			" tablename=lower(%(tableName)s) AND"
			" indexname=lower(%(indexName)s)", locals()).fetchall()
		return len(list(res))>0

	def _getColIndices(self, relOID, colNames):
		"""returns a sorted tuple of column indices of colNames in the relation
		relOID.

		This really is a helper for foreignKeyExists.
		"""
		colNames = [n.lower() for n in colNames]
		res = [r[0] for r in 
			self.query("SELECT attnum FROM pg_attribute WHERE"
				" attrelid=%(relOID)s and attname IN %(colNames)s",
				locals())]
		res.sort()
		return tuple(res)

	def getForeignKeyName(self, srcTableName, destTableName, srcColNames, 
			destColNames, schema=None):
		"""returns True if there's a foreign key constraint on srcTable's 
		srcColNames using destTableName's destColNames.

		Warning: names in XColNames that are not column names in the respective
		tables are ignored.
		"""
		try:
			srcOID = self.getOIDForTable(srcTableName, schema)
			srcColInds = self._getColIndices(srcOID, srcColNames)
			destOID = self.getOIDForTable(destTableName, schema)
			destColInds = self._getColIndices(destOID, destColNames)
		except Error: # Some of the items related probably don't exist
			return False
		try:
			res = list(self.query("""
				SELECT conname FROM pg_constraint WHERE
				contype='f'
				AND conrelid=%(srcOID)s
				AND confrelid=%(destOID)s
				AND conkey=%(srcColInds)s::SMALLINT[]
				AND confkey=%(destColInds)s::SMALLINT[]""", locals()))
		except ProgrammingError: # probably columns do not exist
			return False
		if len(res)==1:
			return res[0][0]
		else:
			raise DBError("Non-existing or ambiguos foreign key")

	def foreignKeyExists(self, srcTableName, destTableName, srcColNames, 
			destColNames, schema=None):
		try:
			return self.getForeignKeyName(srcTableName, destTableName, srcColNames,
				destColNames, schema)
		except DBError:
			return False
		return True

	def roleExists(self, role):
		"""returns True if there role is known to the database.
		"""
		matches = self.query("SELECT usesysid FROM pg_user WHERE usename="
			"%(role)s", locals()).fetchall()
		return len(matches)!=0
	
	def getOIDForTable(self, tableName, schema=None):
		"""returns the current oid of tableName.

		tableName may be schema qualified.  If it is not, public is assumed.
		"""
		schema, tableName = _parseTableName(tableName, schema)
		res = list(self.query("SELECT oid FROM pg_class WHERE"
			" relname=%(tableName)s AND"
			" relnamespace=(SELECT oid FROM pg_namespace WHERE nspname=%(schema)s)",
			locals()))
		if len(res)!=1:
			raise Error("Table %s does not exist"%tableName)
		return res[0][0]

	def _rowExists(self, query, pars):
		res = self.query(query, pars).fetchall()
		return len(res)!=0

	def temporaryTableExists(self, tableName):
		"""returns True if a temporary table tablename exists in the table's
		connection.

		*** postgres specific ***
		"""
		return self._rowExists("SELECT table_name FROM"
			" information_schema.tables WHERE"
			" table_type='LOCAL TEMPORARY' AND table_name=%(tableName)s", 
			{'tableName': tableName.lower()})

	def tableExists(self, tableName, schema=None):
		"""returns True if a table tablename exists in schema.

		*** postgres specific ***
		"""
		schema, tableName = _parseTableName(tableName, schema)
		return self._rowExists("SELECT table_name FROM"
			" information_schema.tables WHERE"
			" table_schema=%(schemaName)s AND table_name=%(tableName)s", 
			{'tableName': tableName.lower(), 'schemaName': schema.lower()})

	def viewExists(self, tableName, schema=None):
		schema, tableName = _parseTableName(tableName, schema)
		return self._rowExists("SELECT viewname FROM"
			" pg_views WHERE"
			" schemaname=%(schemaName)s AND viewname=%(tableName)s", 
			{'tableName': tableName.lower(), 'schemaName': schema.lower()})

	def getSchemaPrivileges(self, schema):
		"""returns (owner, readRoles, allRoles) for the relation tableName
		and the schema.
		"""
		res = self.query("SELECT nspacl FROM pg_namespace WHERE"
			" nspname=%(schema)s", locals()).fetchall()
		return self.parsePGACL(res[0][0])

	def getTablePrivileges(self, schema, tableName):
		"""returns (owner, readRoles, allRoles) for the relation tableName
		and the schema.

		*** postgres specific ***
		"""
		res = self.query("SELECT relacl FROM pg_class WHERE"
			" lower(relname)=lower(%(tableName)s) AND"
			" relnamespace=(SELECT oid FROM pg_namespace WHERE nspname=%(schema)s)",
			locals()).fetchall()
		try:
			return self.parsePGACL(res[0][0])
		except IndexError: # Table doesn't exist, so no privileges
			return {}

	_privTable = {
		"arwdRx": "ALL",
		"arwdDxt": "ALL",
		"arwdRxt": "ALL",
		"arwdxt": "ALL",
		"r": "SELECT",
		"UC": "ALL",
		"U": "USAGE",
	}

	def parsePGACL(self, acl):
		"""returns a dict roleName->acl for acl in postgres'
		ACL serialization.
		"""
		if acl is None:
			return {}
		res = []
		for acs in re.match("{(.*)}", acl).group(1).split(","):
			if acs!='':  # empty ACLs don't match the RE, so catch them here
				role, privs, granter = re.match("([^=]*)=([^/]*)/(.*)", acs).groups()
				res.append((role, self._privTable.get(privs, "READ")))
		return dict(res)


	def getACLFromRes(self, thingWithRoles):
		"""returns a dict of (role, ACL) as it is defined in tableDef or RD
		thingWithRoles, in our internal notation.
		"""
		res = []
		if hasattr(thingWithRoles, "schema"): # it's an RD
			readRight = "USAGE"
		else:
			readRight = "SELECT"
		for role in thingWithRoles.readRoles:
			res.append((role, readRight))
		for role in thingWithRoles.allRoles:
			res.append((role, "ALL"))
		return dict(res)


class StandardQueryMixin(object):
	"""is a mixin containing various useful queries that should work
	agains all SQL systems.

	This mixin expects a parent that mixes is QuerierMixin (that, for now,
	also mixes in StandardQueryMixin, so you won't need to mix this in).

	The parent also needs to mix in something like PostgresQueryMixin (I
	might want to define an interface there once I'd like to support
	other databases).
	"""
	def setSchemaPrivileges(self, rd):
		"""sets the privileges defined on rd to its schema.

		This function will never touch the public schema.
		"""
		schema = rd.schema.lower()
		if schema=="public":
			return
		self._updatePrivileges("SCHEMA %s"%schema,
			self.getSchemaPrivileges(schema), self.getACLFromRes(rd))
	
	def setTablePrivileges(self, tableDef):
		"""sets the privileges defined in tableDef for that table through
		querier.
		"""
		self._updatePrivileges(tableDef.getQName(),
			self.getTablePrivileges(tableDef.rd.schema, tableDef.id),
			self.getACLFromRes(tableDef))
	
	def _updatePrivileges(self, objectName, foundPrivs, shouldPrivs):
		"""is a helper for set[Table|Schema]Privileges.

		Requests for granting privileges not known to the database are
		ignored, but a log entry is generated.
		"""
		for role in set(foundPrivs)-set(shouldPrivs):
			self.query("REVOKE ALL PRIVILEGES ON %s FROM %s"%(
				objectName, role))
		for role in set(shouldPrivs)-set(foundPrivs):
			if self.roleExists(role):
				self.query("GRANT %s ON %s TO %s"%(shouldPrivs[role], objectName,
					role))
			else:
				utils.sendUIEvent("Warning", 
					"Request to grant privileges to non-existing"
					" database user %s dropped"%role)
		for role in set(shouldPrivs)&set(foundPrivs):
			if shouldPrivs[role]!=foundPrivs[role]:
				self.query("REVOKE ALL PRIVILEGES ON %s FROM %s"%(
					objectName, role))
				self.query("GRANT %s ON %s TO %s"%(shouldPrivs[role], objectName,
					role))

	def setTimeout(self, timeout):
		"""sets a timeout on queries.

		timeout is in seconds.
		"""
		if timeout==0: # Special instrumentation for testing
			self.query("SET statement_timeout TO 1")
		elif timeout is not None:
			self.query("SET statement_timeout TO %d"%(int(float(timeout)*1000)))


def dictifyRowset(descr, rows):
	"""turns a standard, tuple-based rowset into a list of dictionaries,
	the keys of which are taken from descr (a cursor.description).
	"""
	keys = [cd[0] for cd in descr]
	return [dict(izip(keys, row)) for row in rows]


class QuerierMixin(PostgresQueryMixin, StandardQueryMixin):
	"""is a mixin for "queriers", i.e., objects that maintain a db connection.

	The mixin assumes an attribute connection from the parent.
	"""
	defaultProfile = None

	def configureConnection(self, settings):
		cursor = self.connection.cursor()
		for key, val in settings:
			cursor.execute("SET %s=%%(val)s"%key, {"val": val})
		cursor.close()

	def runIsolatedQuery(self, query, data={}, silent=False, raiseExc=True,
			timeout=None, asDict=False, settings=()):
		"""runs a query over a connection of its own and returns a rowset of 
		the result if the query is successful.

		Mostly, you'll create all kinds of races if you think you need this.
		Unfortunately, until postgres gets nested transactions, there's little
		I can do.
		"""
		connection = getDBConnection(self.defaultProfile)
		self.configureConnection(settings)
		cursor = connection.cursor()
		try:
			if timeout:  # *** Postgres specific ***
				cursor.execute("SET statement_timeout TO %d"%int(timeout*1000))
			cursor.execute(query, data)
		except DBError, msg:
			cursor.close()
			connection.rollback()
			connection.close()
			if not silent:
				utils.sendUIEvent("Warning", "Failed query %s with"
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
				descr = cursor.description
			except DBError:  # No results to fetch
				res = None
			cursor.close()
			connection.commit()
			connection.close()
			if asDict:
				return dictifyRowset(descr, res)
			else:
				return res

	def enableAutocommit(self):
		self.connection.set_isolation_level(
			psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

	def query(self, query, data={}):
		"""runs a single query in a new cursor and returns that cursor.

		You will see all exceptions, no transaction management will be
		done.

		Do not simply ignore errors you get from query.  To safely ignore
		errors, use runIsolatedQuery.
		"""
		cursor = self.connection.cursor()
		try:
			cursor.execute(query, data)
		except DBError:
			utils.sendUIEvent("Info", "Failed db query: '%s'"%
				getattr(cursor, "query", query))
			raise
		return cursor

	def finish(self):
		self.connection.commit()
		self.connection.close()

	def abort(self):
		self.connection.close()


class SimpleQuerier(QuerierMixin):
	"""is a tiny interface to querying the standard database.

	You can query (which makes raises normal exceptions and renders
	the connection unusable after an error), runIsolatedQuery (which
	may catch exceptions and in any case uses a connection of its own
	so your own connection remains usable; however, you'll have race
	conditions with it).

	You have to close() manually; you also have to commit() when you
	change something, finish() does 'em both.

	You can also use the SimpleQuerier as a context manager; in that case,
	the connection gets commited if everything worked out, and rolled
	back otherwise.  In either case, a connection allocated by the 
	SimpleQuerier gets closed, a connection passed in is left alone.
	"""
	def __init__(self, connection=None, useProfile=None):
		self.defaultProfile = useProfile
		if connection:
			self.ownedConnection = False
			self.connection = connection
		else:
			self.ownedConnection = True
			self.connection = getDBConnection(useProfile or config.getDBProfile())

	def __enter__(self):
		return self
	
	def __exit__(self, *exc_info):
		if exc_info==(None, None, None):
			if not self.connection.closed:
				self.commit()
		else:
			if not self.connection.closed:
				self.rollback()
		if self.ownedConnection:
			self.connection.close()

	def rollback(self):
		self.connection.rollback()

	def commit(self):
		self.connection.commit()

	def close(self):
		try:
			self.connection.close()
			self.connection = None
		except (DBError, AttributeError):
			# Let's assume that is because the connection is alredy gone
			pass

	def finish(self):
		self.commit()
		if self.ownedConnection:
			self.close()

	def __del__(self):
		if self.ownedConnection and self.connection:
			if not self.connection.closed:
				self.close()


def _initPsycopg(conn):
# collect all DB setup in this function.  XXX TODO: in particular, the
# Box mess from coords (if we still want it)
	global _PSYCOPG_INITED
	from gavo.utils import pgsphere
	pgsphere.preparePgSphere(conn)
	_PSYCOPG_INITED = True


_TQ_POOL = None

@contextlib.contextmanager
def getTableConn():
	"""a context manager returning a pooled and autocommitted 
	trustedquery connection.
	"""
	# create global connection pool when necessary.  We need to delay this
	# because gavo init imports sqlsupport, and thus the trustedquery
	# profile may not yet exist during sqlsupport import.
	global _TQ_POOL
	if _TQ_POOL is None:
		_TQ_POOL = psycopg2.pool.ThreadedConnectionPool(1, 400, 
			**config.getDBProfileByName("trustedquery").getArgs())
	conn = _TQ_POOL.getconn()
	conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
# Use this when we can rely on recent enough psycopg2:
#	conn.set_session(
#		isolation_level=psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT,
#		readonly=True)
	yield conn
	_TQ_POOL.putconn(conn)

