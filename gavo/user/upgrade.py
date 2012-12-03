"""
Stuff dealing with the upgrade of the database schema.

From software version 0.8.2 on, there is a dc.metastore table with a key
schemaversion.  Each change in the central schema increases the value
(interpreted as an integer) by one, and this module will contain a 
corresponding upgrader.

An upgrader inherits form the Upgrader class.  See there for more details.

This module contains the current schemaversion expected by the software; gavo
upgrade does everything required to bring the what's in the database in sync
with the code (or so I hope).
"""

from gavo import base
from gavo import utils


CURRENT_SCHEMAVERSION = 0


def getDBSchemaVersion():
	"""returns the schemaversion given in the database.

	This will return -1 if no schemaversion is declared.
	"""
	try:
		return int(base.getDBMeta("schemaversion"))
	except (KeyError, base.DBError):
		return -1


class Upgrader(object):
	"""A specification to upgrade from some schema version to another schema 
	version.

	Upgraders live as uninstanciated classes.  Their version attribute gives the
	version their instructions update *from*; their destination version
	therefore is version+1.

	Each upgrader has attributes named u_<seqno>_<something>.  These can
	be either strings, which are then directly executed in the database,
	or class methods, which will be called with a connection argument.  You 
	must not commit this connection.  You must not swallow exceptions
	that have left the connection unready (i.e., require a rollback).

	The individual upgrader classmethods will be run in the sequence
	given by the sequence number.

	The updaters should have 1-line docstrings explaining what they do.

	The update of the schemaversion is done automatically, you don't
	need to worry about it.
	"""
	version = None

	@classmethod
	def updateSchemaversion(cls, connection):
# no docstring, we output our info ourselves
		print "...update schemaversion to %s"%(cls.version+1)
		base.setDBMeta(connection, "schemaversion", cls.version+1)

	@classmethod
	def iterStatements(cls):
		"""returns strings and classmethods that, in all, perform the necessary
		upgrade.
		"""
		for cmdAttr in (s for s in sorted(dir(cls)) if s.startswith("u_")):
			yield getattr(cls, cmdAttr)
		yield cls.updateSchemaversion


class To0Upgrader(Upgrader):
	"""This is executed when there's no schema version defined in the database.

	The assumption is that the database reflects the status of 0.8, so
	it adds the author column in dc.services if necessary (which it's
	not if the software has been updated to 0.8.1).
	"""
	version = -1

	@classmethod
	def u_000_addauthor(cls, connection):
		"""add an author column to dc.services if necessary."""
		if "authors" in list(connection.queryToDicts(
				"SELECT * FROM dc.resources LIMIT 1"))[0]:
			return
		connection.query("alter table dc.resources add column authors")
		for sourceRD, resId in connection.query("select sourcrd, resid"
				" from dc.resources"):
			try:
				res = base.getRD(sourceRD).getById(resid)
				authors = "; ".join(m.getContent("text") 
					for m in res.iterMeta("creator.name", propagate=True))
			except: 
				# don't worry if fetching authors fails; people will notice...
				pass
			else:
				connection.query("update dc.resources set authors=%(authors)s"
					" where resid=%(resId)s and sourcerd=%(sourceRD)s",
					locals())

	@classmethod
	def u_010_makeMetastore(cls, connection):
		"""create the meta store."""
		from gavo import rsc
		from gavo import rscdesc

		td = base.caches.getRD("//dc_tables").getById("metastore")
		table = rsc.TableForDef(td, create=True, connection=connection)


def iterStatements(startVersion, endVersion=CURRENT_SCHEMAVERSION, 
		upgraders=None):
	"""yields all upgraders from startVersion to endVersion in sequence.
	"""
	toRun = []
	for upgrader in utils.iterDerivedClasses(Upgrader, 
			upgraders or globals().values()):
		if startVersion<=upgrader.version<endVersion:
			toRun.append(upgrader)
	toRun.sort(key=lambda upgrader:upgrader.version)
	for upgrader in toRun:
		for statement in upgrader.iterStatements():
			yield statement


def upgrade():
	"""runs all updates necessary to bring a database to the
	CURRENT_SCHEMAVERSION.

	Everything is run in one transaction.  Errors lead to the rollback of
	the whole thing.
	"""
	startVersion = getDBSchemaVersion()
	if startVersion==CURRENT_SCHEMAVERSION:
		return

	with base.getWritableAdminConn() as conn:
		for statement in iterStatements(startVersion, CURRENT_SCHEMAVERSION):
			if callable(statement):
				if statement.__doc__:
					print "...%s"%statement.__doc__
				statement(conn)
			else:
				print "...executing %s"%utils.makeEllipsis(statement, 60)
				conn.query(statement)
		conn.commit()
