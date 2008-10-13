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
from gavo import fancyconfig
from gavo import meta
from gavo import record
from gavo.fancyconfig import ConfigItem, StringConfigItem,\
	EnumeratedConfigItem, IntConfigItem, PathConfigItem, ListConfigItem,\
	BooleanConfigItem, DictConfigItem

defaultSettingsPath = "/etc/gavo.rc"

addMeta = meta.configMeta.addMeta
getMeta = meta.configMeta.getMeta


class PathRelativeConfigItem(StringConfigItem):
	"""is a configuration item that is interpreted relative to a path
	given in the general section.
	
	Basically, this is a replacement for ConfigParser's %(x)s interpolation.
	In addition, we expand ~ in front of a value to the current value of
	$HOME.

	Specify the item in the baseKey class Attribute.
	"""
	baseKey = None
	_value = ""

	def _getValue(self):
		if self._value.startswith("~"):
			return os.environ.get("HOME", "/no_home")+self._value[1:]
		return os.path.join(self.parent.get(self.baseKey), self._value)
	
	def _setValue(self, val):
		self._value = val
	
	value = property(_getValue, _setValue)


class RootRelativeConfigItem(PathRelativeConfigItem):
	baseKey = "rootDir"
	typespec = "path relative to rootDir"


class WebRelativeConfigItem(PathRelativeConfigItem):
	baseKey = "webDir"
	typespec = "path relative to webDir"


class RelativeURL(StringConfigItem):
	"""is a configuration item that is interpreted relative to
	the server's root URL.
	"""

	_value = ""
	typespec = "URL fragment relative to the server's root"

	def _getValue(self):
		if self._value.startswith("http://") or self._value.startswith("/"):
			return self._value
		return self.parent.get("web", "nevowRoot")+self._value

	def _setValue(self, val):
		self._value = val
	
	value = property(_getValue, _setValue)


class EatTrailingSlashesItem(StringConfigItem):
	"""is a config item that must not end with a slash.  A trailing slash
	on input is removed.
	"""

	typespec = "path fragment"

	def _parse(self, val):
		return StringConfigItem._parse(self, val).rstrip("/")


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

	>>> p = ProfileParser()
	>>> p.parse(None, "x", "host=foo.bar\n").get_host()
	'foo.bar'
	>>> p.parse(None, "x", "") is not None
	True
	>>> p.parse(None, "x", "host=\n").get_host()
	''
	>>> p.parse(None, "x", "=bla\n")
	Traceback (most recent call last):
	ProfileParseError: "x", line 1: invalid identifier '='
	>>> p.parse(None, "x", "host=bla")
	Traceback (most recent call last):
	ProfileParseError: "x", line 1: unexpected end of file (missing line feed?)
	"""
	def __init__(self, sourcePath=["."]):
		self.commands = {
			"include": self._state_include,
		}
		self.sourcePath = sourcePath
	
	def parse(self, profileName, sourceName, stream=None):
		self.tokenStack = []
		self.stateFun = self._state_init
		if stream is None:
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


class Configuration(fancyconfig.Configuration):
	"""is a container for settings.

	It is a fancyconfig.Configuration with the addition of making the
	attributes shared at the class level to ward against multiple imports
	(which may happen if config is imported in a weird way).

	In addition, this class handles the access to database profiles.
	"""
	__sharedState = {}
	def __init__(self, *items):
		self.__dict__ = self.__sharedState
		fancyconfig.Configuration.__init__(self, *items)
		self._dbProfileCache = {}

	def _getProfileParser(self):
		if not hasattr(self, "__profileParser"):
			self.__profileParser = ProfileParser(
				self.get("db", "profilePath"))
		return self.__profileParser

	def getDbProfileByName(self, profileName):
		if profileName is None:
			return self.getDbProfile()
		if not self._dbProfileCache.has_key(profileName):
			try:
				self._dbProfileCache[profileName] = self._getProfileParser().parse(
					profileName, self.get("db", "profiles")[profileName])
			except ConfigParser.NoOptionError:
				raise Error("Undefined DB profile: %s"%profileName)
		return self._dbProfileCache[profileName]

	def setDbProfile(self, profileName):
		self.dbProfile = self.getDbProfileByName(profileName)

	def getDbProfile(self):
		"""returns the *default* db profile.
		"""
		if not hasattr(self, "dbProfile"):
			raise Error("Attempt to access database without having set a profile")
		return self.dbProfile


_config = Configuration(
# general section
	StringConfigItem("rootDir", default="/var/gavo", description=
		"Path to the root of the DC file (all other paths may be"
		" relative to this"),
	RootRelativeConfigItem("configDir", default="etc", 
		description="Path to the DC's non-ini configuration (e.g., DB profiles)"),
	RootRelativeConfigItem("inputsDir", default="inputs",
		description="Path to the DC's data holdings"),
	RootRelativeConfigItem("cacheDir", default="cache",
		description="Path to the DC's persistent scratch space"),
	RootRelativeConfigItem("logDir", default="logs",
		description="Path to the DC's logs (should be local)"),
	RootRelativeConfigItem("tempDir", default="tmp",
		description="Path to the DC's scratch space (should be local)"),
	RootRelativeConfigItem("webDir", default="web",
		description="Path to the DC's web related data (docs, css, js,"
			" templates...)"),
	RootRelativeConfigItem("stateDir", default="state",
		description="Path to the DC's state information (last imported,...)"),
	EnumeratedConfigItem("logLevel", options=["info", "warning",
		"debug", "error"], description="Verboseness of importer"),
	StringConfigItem("operator", description=
		"Mail address of the DC's operator(s)."),
	StringConfigItem("platform", description="Platform string (can be"
		" empty if inputsDir is only accessed by identical machines)"),
	StringConfigItem("gavoGroup", description="Name of the unix group that"
		" administers the DC", default="gavo"),

# parsing section
	RootRelativeConfigItem("xmlFragmentPath", "parsing",
		default="inputs/__common__", description="Path to entity"
			" replacements (deprecated)"),
	RootRelativeConfigItem("dbProfile", "parsing",
		default="admin", description="DB profile used by gavoimp"),

# web section
	StringConfigItem("serverURL", "web", default="http://localhost:8080",
		description="URL fragment used to qualify relative URLs where necessary"),
	IntConfigItem("serverPort", "web", default="None",
		description="Port to bind the server to"),
	EatTrailingSlashesItem("nevowRoot", "web", default="/",
		description="Path fragment to the server's root for operation off the"
			" server's root"),
	StringConfigItem("errorPage", "web", default="debug",
		description="set to 'debug' for error pages with tracebacks, anything"
			" else for a less informative page"),
	WebRelativeConfigItem("templateDir", "web", default="templates",
		description="webDir-relative location of global nevow templates"),
	StringConfigItem("adminpasswd", "web", default="",
		description="Password for online administration, leave empty to disable"),
	StringConfigItem("sitename", "web", "GAVO data center",
		"A short name for your site"),
	BooleanConfigItem("voplotEnable", "web", "True", "Enable the VOPlot"
		" output format (requires some external software)"),
	RelativeURL("voplotCodeBase", "web", "static/voplot/VOPlot",
		"URL of the code base for VOPlot"),
	RelativeURL("voplotUserman", "web",  
		"static/voplot/docs/VOPlot_UserGuide_1_4.html",
		"URL to the documentation of VOPlot"),
	WebRelativeConfigItem("vanityNames", "web", "vanitynames.txt",
		"Webdir-realtive path to the name map for vanity names"),
	IntConfigItem("sqlTimeout", "web", "15",
		"Default timeout for db queries via the web"),
	IntConfigItem("adqlTimeout", "web", "15",
		"Default timeout for adql queries via the web"),
	WebRelativeConfigItem("previewCache", "web", "previewcache",
		"Webdir-relative directory to store cached previews in"),
	WebRelativeConfigItem("favicon", "web", "None",
		"Webdir-relative path to a favicon"),
	BooleanConfigItem("enableTests", "web", "False",
		"Enable test pages (don't if you don't know why)"),

# db section
	StringConfigItem("interface", "db", "psycopg2", "Don't change"),
	PathConfigItem("profilePath", "db", " ~/.gavo:$configDir",
		"Path for locating DB profiles"),
	StringConfigItem("msgEncoding", "db", "utf-8", "Encoding of the"
		" messages coming from the database"),
	ListConfigItem("maintainers", "db", "gavoadmin", "Name(s) of DB roles"
		" that should have full access to gavoimp-created tables by default"),
	ListConfigItem("queryRoles", "db", "gavo", "Name(s) of DB roles that"
		" should be able to read gavoimp-created tables by default"),
	ListConfigItem("adqlRoles", "db", "untrusted", "Name(s) of DB roles that"
		" get access to tables opened for ADQL"),
	DictConfigItem("profiles", "db", "admin:feed,trustedquery:trustedquery,"
		"untrustedquery:untrustedquery,test:test", "Map from internal roles"
			" DB access profiles"),

# ivoa section
	StringConfigItem("authority", "ivoa", "org.gavo.dc", 
		"the authority id for this DC"),
	StringConfigItem("registryIdentifier", "ivoa", 
		"ivo://org.gavo.dc/static/registryrecs/registry.rr", "The IVOA"
			"id for this DC's registry"),
	IntConfigItem("dalDefaultLimit", "ivoa", "10000",
		"Default match limit on DAL queries"),
)


fancyconfig.readConfiguration(_config,
	os.environ.get("GAVOSETTINGS", "/etc/gavo.rc"),
	os.environ.get("GAVOCUSTOM", os.path.join(os.environ.get("HOME", "/no_home"), 
		".gavorc")))

get = _config.get
set = _config.set
setDbProfile = _config.setDbProfile
getDbProfile = _config.getDbProfile
getDbProfileByName = _config.getDbProfileByName


def makeFallbackMeta():
	"""fills meta.configMeta with items from $configDir/defaultmeta.txt.
	"""
	srcPath = os.path.join(get("configDir"), "defaultmeta.txt")
	f = open(srcPath)
	for ln in f:
		ln = ln.strip()
		if not ln or ln.startswith("#"):
			continue
		try:
			key, val = ln.split(":", 1)
		except ValueError:
			raise gavo.Error("Bad line in %s: '%s'"%(srcPath, ln))
		meta.configMeta.addMeta(key.strip(), val.strip())

makeFallbackMeta()


def main():
	try:
		if len(sys.argv)==1:
			print fancyconfig.makeTxtDocs(_config)
		elif len(sys.argv)==2:
			print get(sys.argv[1])
		elif len(sys.argv)==3:
			print get(sys.argv[1], sys.argv[2])
		else:
			sys.stderr.write("Usage: %s [<sect> <key> | <key>]\n")
			sys.exit(1)
	except NoOptionError:
		print ""
		sys.exit(2)


def _test():
	import doctest, config
	doctest.testmod(config)


if __name__=="__main__":
	_test()
