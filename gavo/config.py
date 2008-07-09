"""
This module contains a settings class and a way to fill it from a
simple ini-style file .gavosettings
"""

import ConfigParser
import cStringIO
import os
import re
import shlex
import sys

import gavo
from gavo import meta
from gavo import record

defaultSettingsPath = "/etc/gavo.rc"

addMeta = meta.configMeta.addMeta
getMeta = meta.configMeta.getMeta

_builtinConfig = """
[DEFAULT]
rootDir: /var/gavo
configDir: etc
inputsDir: inputs
cacheDir: cache
logDir: logs
tempDir: tmp
webDir: %(rootDir)s/web
stateDir: %(rootDir)s/state
logLevel: info
operator: gavo@ari.uni-heidelberg.de
platform:
gavoGroup: gavo

[parsing]
xmlFragmentPath: %(inputsDir)s/__common__
dbDefaultProfile: feed

[web]
# serverName is used to qualify relative URLs where necessary.
serverURL: http://localhost:8080
staticURL: /qstatic
# This one's for the old querulator and should die in the end.
rootURL: /ql
# This one's for the new nevow-based service
nevowRoot: 
# match limit for the db when no limit was given
defaultlimit: 100
# hard match limit for the db (empty for no limit)
hardlimit: 1000000
# error page for nv service (debug or something else)
errorPage: debug
# location of global nevow templates in the file system
templateDir=%(webDir)s/templates
# the admin password, leave empty to disable
adminpasswd:
# A short name of your site
sitename=GAVO data center
voplotEnable: True
voplotCodeBase: ~/static/voplot/VOPlot
voplotUserman: ~/static/voplot/docs/VOPlot_UserGuide_1_4.html
# Location of the name map for vanity names
vanityNames=vanitynames.txt
# Default timeout for db queries via the web
sqlTimeout=15
# directory to store cached previews in
previewCache: %(webDir)s/previewcache
# path to a favicon
favicon: None

[querulator]
defaultMaxMatches: 1000
dbProfile: querulator
templateRoot: %(rootDir)s/web/querulator/templates
fitspreview: %(rootDir)s/web/bin/fitspreview

[db]
interface: pgsql
# or psycopg2
profilePath: ~/.gavo:%(configdir)s
msgEncoding: utf-8

[profiles]
feed:feed
querulator:trustedquery
foreignsql:untrustedquery
writable:worldwritable

[ivoa]
# the authority id for this DC
authority: 
registryIdentifier: ivo://org.gavo.dc/static/registryrecs/registry.rr
dalDefaultLimit: 10000

[meta]
# Default curation
publisher: 
publisher.name: 
publisher.email: 
creator.name: 
creator.logo:
contact.name:
contact.address:
contact.email:
contact.telephone:
"""


class Error(gavo.Error):
	pass

class ProfileParseError(Error):
	pass

from ConfigParser import NoOptionError

def _identity(val):
	return val


class DbProfile(record.Record):
	"""is a profile for DB access.
	"""
 	def __init__(self, name):
		self.name = name
		record.Record.__init__(self, {
			"host": "",
			"port": "",
			"database": record.RequiredField,
			"user": "",
			"password": "",
			"allRoles": record.ListField,
			"readRoles": record.ListField,
		})
	
	def getDsn(self):
		parts = []
		for key, part in [("host", "host"), ("port", "port"), 
				("database", "dbname"), ("user", "user"), ("password", "password")]:
			if self.get(part):
				parts.append("%s=%s"%(key, self.get(part)))
		return " ".join(parts)


class ProfileParser:
	r"""is a parser for DB profiles.

	The profiles are specified in simple text files that have a shell-like
	syntax.  Each line either contains an assignment (x=y) or is of the
	form command arg*.  Recognized commands include:

	* include f -- read instructions from file f, searched along profilePath
	* addAllRole u -- add db role u to the list of roles that receive
	  full privileges to all items created.
	* addReadRole u -- add db rule u to the list of roles that receive
	  read (e.g., select, usage) privileges to all items created

	>>> p = ProfileParser()
	>>> p.parse(None, "x", "host=foo.bar\n").get_host()
	'foo.bar'
	>>> p.parse(None, "x", "addAllRole foo\naddAllRole bar\n").get_allRoles()
	['foo', 'bar']
	>>> p.parse(None, "x", "")!=None
	True
	>>> p.parse(None, "x", "host=\n").get_host()
	''
	>>> p.parse(None, "x", "=bla\n")
	Traceback (most recent call last):
	ProfileParseError: "x", line 1: invalid identifier '='
	>>> p.parse(None, "x", "host=bla")
	Traceback (most recent call last):
	ProfileParseError: "x", line 1: unexpected end of file (missing line feed?)
	>>> p.parse(None, "x", "includeAllRole=bla\n")
	Traceback (most recent call last):
	ProfileParseError: "x", line 2: unknown setting 'includeAllRole'
	"""
	def __init__(self, sourcePath=["."]):
		self.commands = {
			"include": self._state_include,
			"addAllRole": self._state_addAllRole,
			"addReadRole": self._state_addReadRole,
		}
		self.sourcePath = sourcePath
	
	def parse(self, profileName, sourceName, stream=None):
		self.tokenStack = []
		self.stateFun = self._state_init
		if stream==None:
			sourceName = self._resolveSource(sourceName)
			stream = open(sourceName)
		elif isinstance(stream, basestring):
			stream = cStringIO.StringIO(stream)
		self.parser = shlex.shlex(stream, sourceName, posix=True)
		self.parser.whitespace = " \t\r"
		self.profile = DbProfile(profileName)
		while True:
			tok = self.parser.get_token()
			if not tok:
				break
			self._feed(tok)
		if self.stateFun!=self._state_init:
			self._raiseError("unexpected end of file (missing line feed?)")
		return self.profile

	def _raiseError(self, msg):
		raise ProfileParseError(self.parser.error_leader()+msg)

	def _state_init(self, token):
		if token in self.commands:
			return self.commands[token]
		if not re.match("[A-Za-z][\w]+$", token):
			self._raiseError("invalid identifier %s"%repr(token))
		self.tokenStack.append(token)
		return self._state_waitForEqual

	def _resolveSource(self, fName):
		for dir in self.sourcePath:
			fqName = os.path.join(dir, fName)
			if os.path.exists(fqName):
				return fqName
		raise ProfileParseError("Requested db profile %s does not exist"%
			repr(fName))

	def _state_include(self, token):
		if token=="\n":
			fName = "".join(self.tokenStack)
			self.tokenStack = []
			fName = self._resolveSource(fName)
			self.parser.push_source(open(fName), fName)
			return self._state_init
		else:
			self.tokenStack.append(token)
			return self._state_include

	def _state_addAllRole(self, token):
		self.profile.addto_allRoles(token)
		return self._state_eol

	def _state_addReadRole(self, token):
		self.profile.addto_readRoles(token)
		return self._state_eol

	def _state_eol(self, token):
		if token!="\n":
			self._raiseError("expected end of line")
		return self._state_init

	def _state_waitForEqual(self, token):
		if token!="=":
			self._raiseError("expected '='")
		return self._state_rval
	
	def _state_rval(self, token):
		if token=="\n":
			key = self.tokenStack.pop(0)
			val = "".join(self.tokenStack)
			self.tokenStack = []
			try:
				self.profile.set(key, val)
			except AttributeError:
				self._raiseError("unknown setting %s"%repr(key))
			return self._state_init
		else:
			self.tokenStack.append(token)
			return self._state_rval

	def _feed(self, token):
		self.stateFun = self.stateFun(token)


class Settings(object):
	"""is a container for settings.
	
	It is fed from the builtin config, $GAVOSETTINGS (default: /etc/gavorc) and,
	if available, $GAVOCUSTOM (default: ~/.gavorc), where later settings 
	may override earlier settings.

	To access config items, say config.get(item) for items from the default
	section, or config.get(section, item) for items from named sections.
	All keys except meta are case insensitive.
	"""
	__sharedState = {}
	def __init__(self):
		self.__dict__ = self.__sharedState
		self.rawVals = self._parse()
		self._handleMeta()
		self.valueCache = {}
		self.dbProfileCache = {}

	def _getHome(self):
		return os.environ.get("HOME", "/no_home")

	def _handleMeta(self):
		for key, value in self.rawVals.items("meta"):
			addMeta(key, value)

	def _parse(self):
		confParser =  ConfigParser.ConfigParser()
		confParser.readfp(cStringIO.StringIO(_builtinConfig))
		confParser.read([
			os.environ.get("GAVOSETTINGS", "/etc/gavo.rc"),
			os.environ.get("GAVOCUSTOM", os.path.join(
				self._getHome(), ".gavorc"))])
		return confParser

	def _cookPath(self, val):
		if val.startswith("~"):
			val = self._getHome()+val[1:]
		return os.path.join(self.get("rootDir"), val)
	
	_parse_DEFAULT_configdir = _parse_DEFAULT_inputsdir =\
		_parse_DEFAULT_cachedir = _parse_DEFAULT_logdir =\
		_parse_DEFAULT_tempdir = _parse_DEFAULT_webdir = _cookPath

	def _parse_web_adminpasswd(self, val):
		return val.strip()

	def _parse_web_sqltimeout(self, val):
		return int(val)

	def _parse_web_voplotenable(self, val):
		return record.parseBooleanLiteral(val)

	def _parse_web_voplotcodebase(self, val):
		if val.startswith("~"):
			val = self.get("web", "serverUrl")+self.get("web", "nevowRoot"
				)+val[1:]
		return val
	
	_parse_web_voplotuserman = _parse_web_voplotcodebase

	def _parse_DEFAULT_rootdir(self, val):
		if val.startswith("~"):
			val = self._getHome()+val[1:]
		return val

	def _parse_db_profilepath(self, val):
		res = []
		for dir in val.split(":"):
			if dir.startswith("~"):
				dir = self._getHome()+dir[1:]
			else:
				dir = os.path.join(self.get("rootDir"), dir)
			res.append(dir)
		return res

	def _computeValueFor(self, section, key):
		return getattr(self, "_parse_%s_%s"%(section, key), _identity)(
			self.rawVals.get(section, key))

	def get(self, arg1, arg2=None):
		if arg2==None:
			section, key = "DEFAULT", arg1.lower()
		else:
			section, key = arg1.lower(), arg2.lower()
		if not self.valueCache.has_key((section, key)):
			self.valueCache[section, key] = self._computeValueFor(section, key)
		return self.valueCache[section, key]

	def _getProfileParser(self):
		if not hasattr(self, "__profileParser"):
			self.__profileParser = ProfileParser(
				self.get("db", "profilePath"))
		return self.__profileParser

	def getDbProfileByName(self, profileName):
		if not self.dbProfileCache.has_key(profileName):
			try:
				self.dbProfileCache[profileName] = self._getProfileParser().parse(
					profileName, self.get("profiles", profileName))
			except ConfigParser.NoOptionError:
				raise Error("Undefined DB profile: %s"%profileName)
		return self.dbProfileCache[profileName]

	def setDbProfile(self, profileName):
		self.dbProfile = self.getDbProfileByName(profileName)

	def getDbProfile(self):
		"""returns the *default* db profile.
		"""
		if not hasattr(self, "dbProfile"):
			raise Error("Attempt to access database without having set a profile")
		return self.dbProfile


_config = Settings()
get = _config.get
setDbProfile = _config.setDbProfile
getDbProfile = _config.getDbProfile
getDbProfileByName = _config.getDbProfileByName


def main():
	try:
		if len(sys.argv)==2:
			print get(sys.argv[1])
		elif len(sys.argv)==3:
			print get(sys.argv[1], sys.argv[2])
		else:
			sys.stderr.write("Usage: %s <sect> <key> | <key>\n")
			sys.exit(1)
	except NoOptionError:
		print ""
		sys.exit(2)

def _test():
	import doctest, config
	doctest.testmod(config)


if __name__=="__main__":
	_test()
