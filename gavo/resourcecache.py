"""
Accessor functions for the various immutables an archive service might
deal with.

The main purpose of this module is to keep caches of resource descriptors,
templates, etc., the parsing of which may take some time.
"""

from twisted.enterprise import adbapi

from gavo import config


class _DbConnection:
	connPools = {}
	def _makeConnPool(self, profile):
		connStr = ("dbname='%s' port='%s' host='%s'"
			" user='%s' password='%s'")%(profile.get_database(), 
			profile.get_port(), profile.get_host(), profile.get_user(), 
			profile.get_password())
		return adbapi.ConnectionPool("psycopg2", connStr)

# XXX ugly -- if the default profile changes, we'd have to delete
# connPools[None] but we don't...
	def getConnection(self, profileName=None):
		if not self.connPools.has_key(profileName):
			if profileName:
				profile = config.getDbProfileByName(profileName)
			else:
				profile = config.getDbProfile()
			self.connPools[profileName] = self._makeConnPool(profile)
		return self.connPools[profileName]
_ = _DbConnection()
getDbConnection = _.getConnection


class CacheRegistry:
	"""is a registry for caches kept to be able to clear them.

	A cache is assumed to be a dicitonary here.
	"""
	def __init__(self):
		self.knownCaches = []
	
	def clearall(self):
		for cache in self.knownCaches:
			for key in cache.keys():
				del cache[key]
	
	def register(self, cache):
		self.knownCaches.append(cache)


_cacheRegistry = CacheRegistry()
clearCaches = _cacheRegistry.clearall


def _makeCache(creator):
	"""returns a callable that returns a resource and caches its results.

	The creator has to be a function taking an id and returning the 
	designated object.
	"""
	cache = {}
	_cacheRegistry.register(cache)
	def func(id):
		if not id in cache:
			cache[id] = creator(id)
		return cache[id]
	return func


def makeCache(name, callable):
	"""creates a new function name to cache results to calls to callable.
	"""
	globals()[name] = _makeCache(callable)
