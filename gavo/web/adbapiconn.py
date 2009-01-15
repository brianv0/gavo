"""
A wrapper for twisted enterprise's adbapi to register it with 
base.caches and to have it time out after a config-specified amount
of time.
"""

from psycopg2 import extras
from twisted.enterprise import adbapi

from gavo import base

class _DbConnection:
	"""is a cache of twisted enterprise connection *pools*, each
	corresponding to a different profile.
	"""
	connPools = {}
	def _makeConnPool(self, profile):
		connStr = ("dbname='%s' port='%s' host='%s'"
			" user='%s' password='%s'")%(profile.database, 
			profile.port, profile.host, profile.user, 
			profile.password)
		return adbapi.ConnectionPool("psycopg2", connStr, cp_noisy=False,
			cp_reconnect=True, connection_factory=extras.InterruptibleConnection)

	def getConnection(self, profileName=None):
		if profileName is None:
			profileName = base.getDBProfile().name
		if not self.connPools.has_key(profileName):
			self.connPools[profileName] = self._makeConnPool(
				base.getDBProfileByName(profileName))
		return self.connPools[profileName]

_ = _DbConnection()
base.caches.makeCache("getADBConn", _.getConnection)
