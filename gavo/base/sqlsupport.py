# -*- encoding: iso-8859-1 -*-
"""
This module contains basic support for manual SQL generation.
"""

import re
import sys
import operator
import warnings

from gavo.base import excs
from gavo.base import config

debug = False

import psycopg2
import psycopg2.extras
import psycopg2.extensions
psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)

from psycopg2.extras import DictCursor

class Error(excs.Error):
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

from psycopg2 import OperationalError, DatabaseError, IntegrityError
from psycopg2 import Error as DBError


def registerAdapter(type, adapter):
	psycopg2.extensions.register_adapter(type, adapter)


def registerType(oid, name, castFunc):
	newOID = psycopg2.extensions.new_type(oid, name, castFunc)
	psycopg2.extensions.register_type(newOID)


def getDBConnection(profile):
	if isinstance(profile, basestring):
		profile = config.getDBProfileByName(profile)
	elif profile is None:
		profile = config.getDBProfile()
	try:
		connString = ("dbname='%s' port='%s' host='%s'"
			" user='%s' password='%s'")%(profile.database, 
				profile.port, profile.host, profile.user, 
				profile.password)
		conn = psycopg2.connect(connString,
				connection_factory=psycopg2.extras.InterruptibleConnection)
		return conn
	except KeyError:
		raise Error("Insufficient information to connect to database."
			"  The operators need to check their profiles.")


def getDefaultDBConnection():
	return getDBConnection(config.getDBProfile())


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
		return schema, tableName



class PostgresQueryMixin(object):
	"""is a mixin containing various useful queries that are postgres specific.

	This mixin expects a parent that mixes is QuerierMixin (that, for now,
	also mixes in PostgresQueryMixin, so you won't need to mix this in).
	"""
	def getPrimaryIndexName(self, tableName):
		"""returns the name of the index corresponding to the primary key on 
		(the unqualified) tableName.
		"""
		return "%s_pkey"%tableName
	
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
			" pg_indexes WHERE schemaname=%(schema)s AND"
			" tablename=%(tableName)s AND"
			" indexname=%(indexName)s", locals()).fetchall()
		return len(res)>0
	
	def roleExists(self, role):
		"""returns True if there role is known to the database.
		"""
		matches = self.query("SELECT usesysid FROM pg_user WHERE usename="
			"%(role)s", locals()).fetchall()
		return len(matches)!=0
	
	def getOIDForTable(self, tableName):
		"""returns the current oid of tableName.

		tableName may be schema qualified.  If it is not, public is assumed.
		"""
		schema, tableName = _parseTableName(tableName, schema)
		res = self.query("SELECT oid FROM pg_class WHERE"
			" relname=%(tableName)s AND"
			" relnamespace=(SELECT oid FROM pg_namespace WHERE nspname=%(schema)s)",
			locals()).fetchall()
		assert len(res)==1
		return res[0][0]
	
	def tableExists(self, tableName, schema=None):
		"""returns True if a table tablename exists in schema.
		
		See _parseTableName on the meaning of the arguments.
		"""
		schema, tableName = _parseTableName(tableName, schema)
		matches = self.query("SELECT table_name FROM"
			" information_schema.tables WHERE"
			" table_schema=%(schemaName)s AND table_name=%(tableName)s", {
					'tableName': tableName.lower(),
					'schemaName': schema.lower(),
			}).fetchall()
		return len(matches)!=0
	
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
			" relname=%(tableName)s AND"
			" relnamespace=(SELECT oid FROM pg_namespace WHERE nspname=%(schema)s)",
			locals()).fetchall()
		try:
			return self.parsePGACL(res[0][0])
		except IndexError: # Table doesn't exist, so no privileges
			return {}

	_privTable = {
		"arwdRx": "ALL",
		"arwdRxt": "ALL",
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
				warnings.warn("Request to grant privileges to non-existing"
					" database user %s dropped"%role)
		for role in set(shouldPrivs)&set(foundPrivs):
			if shouldPrivs[role]!=foundPrivs[role]:
				self.query("REVOKE ALL PRIVILEGES ON %s FROM %s"%(
					objectName, role))
				self.query("GRANT %s ON %s TO %s"%(shouldPrivs[role], objectName,
					role))


class QuerierMixin(PostgresQueryMixin, StandardQueryMixin):
	"""is a mixin for "queriers", i.e., objects that maintain a db connection.

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
		connection = getDBConnection(self.defaultProfile)
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
		except DBError, msg:
			cursor.close()
			connection.rollback()
			connection.close()
			if not silent:
				warnings.warn("Failed query %s with"
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
			except DBError:  # No results to fetch
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
		except DBError:
			warnings.warn("Failed db query: '%s'"%getattr(cursor, "query",
				query))
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
	"""
	def __init__(self, connection=None, useProfile=None):
		self.ownedConnection = False
		self.connection = None
		self.defaultProfile = useProfile
		if connection:
			self.connection = connection
		else:
			self.connection = getDBConnection(useProfile or config.getDBProfile())
			self.ownedConnection = True

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
			self.close()
		

if __name__=="__main__":
	t = TableWriter("test.test", [("f1", "text", {}), ("f2", "text", {})])
	t.ensureSchema("test")
	t.createTable()
	f = t.getFeeder()
	f({"f1": "blabla", "f2": u"önögnü"})
	f.close()
