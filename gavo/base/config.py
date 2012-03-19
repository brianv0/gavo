"""
Definition of DC config options and their management including I/O.
"""

from __future__ import with_statement

import ConfigParser
import cStringIO
import grp
import os
import pkg_resources
import re
import shlex
import sys
import warnings

from gavo import utils
from gavo.base import attrdef
from gavo.base import meta
from gavo.base import structure
from gavo.utils import fancyconfig
from gavo.utils.fancyconfig import ConfigItem, StringConfigItem,\
	EnumeratedConfigItem, IntConfigItem, PathConfigItem, ListConfigItem,\
	BooleanConfigItem, DictConfigItem, Section, DefaultSection, MagicSection,\
	PathRelativeConfigItem, ParseError, SetConfigItem, ExpandedPathConfigItem

defaultSettingsPath = "/etc/gavo.rc"

addMeta = meta.configMeta.addMeta
setMeta = meta.configMeta.setMeta
getMeta = meta.configMeta.getMeta



class RootRelativeConfigItem(PathRelativeConfigItem):
	baseKey = "rootDir"
	typedesc = "path relative to rootDir"


class WebRelativeConfigItem(PathRelativeConfigItem):
	baseKey = "webDir"
	typedesc = "path relative to webDir"


class RelativeURL(StringConfigItem):
	"""is a configuration item that is interpreted relative to
	the server's root URL.
	"""

	_value = ""
	typedesc = "URL fragment relative to the server's root"

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

	typedesc = "path fragment"

	def _parse(self, val):
		return StringConfigItem._parse(self, val).rstrip("/")


class EnsureTrailingSlashesItem(StringConfigItem):
	"""is a config item that must end with a slash.  If no slash is present
	on input, it is added.
	"""

	typedesc = "path fragment"

	def _parse(self, val):
		val = StringConfigItem._parse(self, val)
		if val is not None and not val.endswith("/"):
			val = val+"/"
		return val


class ProfileItem(StringConfigItem):
	"""is a config item within the profiles magic section.
	
	The main point here is to beautify the generated documentation.
	"""
	typedesc = "profile name"
	def __init__(self, name):
		StringConfigItem.__init__(self, name, description="A name of a file"
			" in [db]profilePath")
		self.default = None


class Error(utils.Error):
	pass

class ProfileParseError(Error):
	pass

from ConfigParser import NoOptionError


def _identity(val):
	return val


class DBProfile(structure.Structure):
	"""is a profile for DB access.
	"""
	name_ = "dbProfile"
	profileName = "anonymous"

	_name = attrdef.UnicodeAttribute("name", default=attrdef.Undefined,
		description="An identifier for this profile")
	_host = attrdef.UnicodeAttribute("host", default="", description="Host"
		" the database runs on")
	_port = attrdef.IntAttribute("port", default=None, description=
		"Port the DB server listens on")
	_database = attrdef.UnicodeAttribute("database", default=attrdef.Undefined,
		description="Name of the database to connect to")
	_user = attrdef.UnicodeAttribute("user", default="", description=
		"User to log into DB as")
	_pw = attrdef.UnicodeAttribute("password", default="", description=
		"Password for user")

	def getDsn(self):
		parts = []
		for key, part in [("host", "host"), ("port", "port"), 
				("database", "dbname"), ("user", "user"), ("password", "password")]:
			if getattr(self, part):
				parts.append("%s=%s"%(key, getattr(self, part)))
		return " ".join(parts)
	
	def getArgs(self):
		"""returns a dictionary suitable as keyword arguments to psycopg2's
		connect.
		"""
		res = {}
		for key in ["database", "user", "password", "host", "port"]:
			if getattr(self, key):
				res[key] = getattr(self, key)
		if not res:
			raise utils.logOldExc(utils.StructureError("Insufficient information"
			" to connect to the database in profile '%s'."%(
				self.profileName)))
		return res

	@property
	def roleName(self):
		"""returns the database role used by this profile.

		This normally is user, but in the special case of the empty user,
		we return the logged users' name.
		"""
		if self.user:
			return self.user
		else:
			return os.getlogin()


class ProfileParser(object):
	r"""is a parser for DB profiles.

	The profiles are specified in simple text files that have a shell-like
	syntax.  Each line either contains an assignment (x=y) or is of the
	form command arg*.  Recognized commands include:

		- include f -- read instructions from file f, searched along profilePath

	>>> p = ProfileParser()
	>>> p.parse(None, "x", "host=foo.bar\n").host
	'foo.bar'
	>>> p.parse(None, "x", "") is not None
	True
	>>> p.parse(None, "x", "host=\n").host
	''
	>>> p.parse(None, "x", "=bla\n")
	Traceback (most recent call last):
	ProfileParseError: "x", line 1: invalid identifier '='
	>>> p.parse(None, "x", "host=bla")
	Traceback (most recent call last):
	ProfileParseError: "x", line 1: unexpected end of file (missing line feed?)
	"""
	profileKeys = set(["host", "port", "database", "user", "password"])

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
		self.profile = DBProfile(None, name=profileName)
		while True:
			tok = self.parser.get_token()
			if not tok:
				break
			self._feed(tok)
		if self.stateFun!=self._state_init:
			self._raiseError("unexpected end of file (missing line feed?)")
		if profileName:
			self.profile.profileName = profileName
		return self.profile

	def _raiseError(self, msg):
		raise utils.logOldExc(
			ProfileParseError(self.parser.error_leader()+msg))
	
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
			if not key in self.profileKeys:
				self._raiseError("unknown setting %s"%repr(key))
			setattr(self.profile, key, val)
			return self._state_init
		else:
			self.tokenStack.append(token)
			return self._state_rval

	def _feed(self, token):
		self.stateFun = self.stateFun(token)


class Configuration(fancyconfig.Configuration):
	"""A container for settings.

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

	def getDBProfileByName(self, profileName):
		if profileName is None:
			return self.getDBProfile()
		if not self._dbProfileCache.has_key(profileName):
			try:
				self._dbProfileCache[profileName] = self._getProfileParser().parse(
					profileName, self.get("profiles", profileName))
			except utils.NoConfigItem:
				raise ProfileParseError("Undefined DB profile: %s"%profileName)
		return self._dbProfileCache[profileName]

	def setDBProfile(self, profileName):
		"""is the same as config.set("defaultProfileName", ...)
		"""
		self.getDBProfileByName(profileName)
		self.set("defaultProfileName", profileName)

	def getDBProfile(self):
		"""returns the current db profile.
		"""
		if not self.get("defaultProfileName"):
			raise ProfileParseError("Empty default profile name")
		return self.getDBProfileByName(self.get("defaultProfileName"))


_config = Configuration(
	DefaultSection('Paths and other general settings.',
		ExpandedPathConfigItem("rootDir", default="/var/gavo", description=
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
		RootRelativeConfigItem("uwsWD", default="state/uwsjobs",
			description="Directory to keep uws jobs in.  This may need lots"
				" of space if your users do large queries"),
		EnumeratedConfigItem("logLevel", options=["info", "warning",
			"debug", "error"], description="How much should be logged?"),
		StringConfigItem("operator", description=
			"Deprecated and ignored.  Use contact.email in defaultmeta.txt instead."),
		StringConfigItem("platform", description="Platform string (can be"
			" empty if inputsDir is only accessed by identical machines)"),
		StringConfigItem("gavoGroup", description="Name of the unix group that"
			" administers the DC", default="gavo"),
		StringConfigItem("defaultProfileName", description="Default profile name"
			" (used to construct system entities)", default="admin"),
		StringConfigItem("group", description="Name of the group that may write"
			" into the log directory", default="gavo"),
		PathConfigItem("xsdclasspath", description="Classpath necessary"
			" to validate XSD using an xsdval java class.  You want GAVO's"
			" VO schemata collection for this.", default="None"),
		),

	Section('web', 'Settings related to serving content to the web.',
		StringConfigItem("serverURL", default="http://localhost:8080",
			description="URL fragment used to qualify relative URLs where necessary"),
		StringConfigItem("bindAddress", default="127.0.0.1", description=
			"Interface to bind to"),
		IntConfigItem("serverPort", default="8080",
			description="Port to bind the server to"),
		StringConfigItem("user", default="gavo", description="Run server as"
			" this user."),
		EnsureTrailingSlashesItem("nevowRoot", default="/",
			description="Path fragment to the server's root for operation off the"
				" server's root"),
		StringConfigItem("realm", default="Gavo", description="Authentication"
			" realm to be used (currently, only one, server-wide, is supported)"),
		WebRelativeConfigItem("templateDir", default="templates",
			description="webDir-relative location of global nevow templates"),
		StringConfigItem("adminpasswd", default="",
			description="Password for online administration, leave empty to disable"),
		StringConfigItem("sitename", "GAVO data center",
			"A short name for your site"),
		RelativeURL("voplotCodeBase", "None",
			"Deprecated and ignored."),
		RelativeURL("voplotUserman",  
			"Deprecated and ignored",
			"URL to the documentation of VOPlot"),
		IntConfigItem("sqlTimeout", "15",
			"Default timeout for db queries via the web"),
		WebRelativeConfigItem("previewCache", "previewcache",
			"Webdir-relative directory to store cached previews in"),
		WebRelativeConfigItem("favicon", "None",
			"Webdir-relative path to a favicon"),
		BooleanConfigItem("enableTests", "False",
			"Enable test pages (don't if you don't know why)"),
		IntConfigItem("maxPreviewWidth", "300", "Hard limit for the width"
			" of previews (necessary because previews on protected items"
			" are free)"),
		ListConfigItem("graphicMimes", "image/fits,image/jpeg", "MIME types"
			" considered as graphics (for SIAP, mostly)"),
		StringConfigItem("adsMirror", 
			"http://ads.g-vo.org/",
			"Root URL of ADS mirror to be used"),
		IntConfigItem("maxUploadSize",
			"20000000",
			"Maximal size of file uploads in bytes."),
	),

	Section('adql', "Settings concerning the built-in ADQL core",
		IntConfigItem("webDefaultLimit", "2000",
			"Default match limit for ADQL queries via a web form"),
	),

	Section('async', "Settings concerning TAP, UWS, and friends",
		IntConfigItem("defaultExecTimeSync", "60", "Default timeout"
			" for synchronous UWS jobs, in seconds"),
		IntConfigItem("defaultExecTime", "3600", "Default timeout"
			" for UWS jobs, in seconds"),
		IntConfigItem("maxTAPRunning", "2", "Maximum number of"
			" TAP jobs running at a time"),
		IntConfigItem("defaultLifetime", "172800", "Default"
			" time to destruction for UWS jobs, in seconds"),
		IntConfigItem("defaultMAXREC", "2000",
			"Default match limit for ADQL queries via the UWS/TAP"),
		IntConfigItem("hardMAXREC", "20000000",
			"Default match limit for ADQL queries via the UWS/TAP"),
		StringConfigItem("csvDialect", "excel", "CSV dialect as defined"
			" by the python csv module used when writing CSV files."),
),

	Section('ui', "Settings concerning the local user interface",
		StringConfigItem("outputEncoding", "iso-8859-1",
			"Encoding for system messages.  This should match what your"
			" terminal emulator is set to"),
	),

	Section('db', 'Settings concerning database access.',
		StringConfigItem("interface", "psycopg2", "Don't change"),
		PathConfigItem("profilePath", " ~/.gavo:$configDir",
			"Path for locating DB profiles"),
		StringConfigItem("msgEncoding", "utf-8", "Encoding of the"
			" messages coming from the database"),
		SetConfigItem("maintainers", "admin", "Name(s) of profiles"
			" that should have full access to gavoimp-created tables by default"),
		SetConfigItem("queryProfiles", "trustedquery", "Name(s) of profiles that"
			" should be able to read gavoimp-created tables by default"),
		SetConfigItem("adqlProfiles", "untrustedquery", "Name(s) of profiles that"
			" get access to tables opened for ADQL"),
		IntConfigItem("defaultLimit", "100", "Default match limit for DB queries"),
	),
	
	MagicSection('profiles', 'Mapping of DC profiles to profile definitions.',
		itemFactory=ProfileItem,
		defaults=(("admin", "feed"), ("trustedquery", "trustedquery"),
			("untrustedquery", "untrustedquery"))),

	Section('ivoa', 'The interface to the Greater VO.',
		StringConfigItem("authority", "x-unregistred", 
			"The authority id for this DC"),
		IntConfigItem("dalDefaultLimit", "10000",
			"Default match limit on DAL queries"),
		IntConfigItem("dalHardLimit", "10000000",
			"Hard match limit on DAL queries"),),
)

def loadConfig():
	try:
		fancyconfig.readConfiguration(_config,
			os.environ.get("GAVOSETTINGS", "/etc/gavo.rc"),
			os.environ.get("GAVOCUSTOM", 
				os.path.join(os.environ.get("HOME", "/no_home"), ".gavorc")))
	except fancyconfig.ConfigError, ex:
		# This is usually not be protected by top-level exception catcher
		sys.exit("Bad configuration item in %s.  %s"%(
			ex.fileName, unicode(ex).encode("utf-8")))

loadConfig()


if os.environ.has_key("GAVO_INPUTSDIR"):
	_config.set("inputsDir", os.environ["GAVO_INPUTSDIR"])

get = _config.get
set = _config.set
setDBProfile = _config.setDBProfile
getDBProfile = _config.getDBProfile
getDBProfileByName = _config.getDBProfileByName


def makeFallbackMeta(reload=False):
	"""fills meta.configMeta with items from $configDir/defaultmeta.txt.
	"""
	srcPath = os.path.join(get("configDir"), "defaultmeta.txt")
	if not os.path.exists(srcPath):
		# python warning rather than event interface since this is very early
		# init.
		warnings.warn("%s does not exist, registry interface  will be broken"%
			srcPath)
		return
	with open(srcPath) as f:
		content = f.read().decode("utf-8", "ignore")
	meta.parseMetaStream(meta.configMeta, content, clearItems=reload)

makeFallbackMeta()


##########################################################
# A few utility functions -- we should have a better
# place for them, really.

def makeSitePath(path):
	"""returns a rooted local part for a server-internal URL.

	uri itself needs to be server-absolute (i.e., start with a slash).
	"""
	return str(get("web", "nevowRoot")+path.lstrip("/"))


def makeAbsoluteURL(path):
	"""returns a fully qualified URL for a rooted local part.
	"""
	return str(get("web", "serverURL")+makeSitePath(path))


def getBinaryName(baseName):
	"""returns the name of a binary it thinks is appropriate for the platform.

	To do this, it asks config for the platform name, sees if there's a binary
	<bin>-<platname> if platform is nonempty.  If it exists, it returns that name,
	in all other cases, it returns baseName unchanged.
	"""
	platform = get("platform")
	if platform:
		platName = baseName+"-"+platform
		if os.path.exists(platName):
			return platName
	return baseName


def openDistFile(name):
	"""returns an open file for a "dist resource", i.e., a file distributed
	with DaCHS.

	This is like pkg_resources, except it also checks in 
	$GAVO_DIR/override/<name> and returns that file if present.  Thus, you
	can usually override DaCHS built-in files (but there's not too many
	places in which that's used so far).
	"""
	userPath = os.path.join(get("rootDir"), "overrides/"+name)
	if os.path.exists(userPath):
		return open(userPath)
	else:
		return pkg_resources.resource_stream('gavo', "resources/"+name)


def getGroupId():
	"""returns the numerical group id of the GAVO group.
	"""
	gavoGroup = _config.get("group")
	try:
		return grp.getgrnam(gavoGroup)[2]
	except KeyError, ex:
		raise utils.ReportableError("Group %s does not exist"%str(ex),
			"You should have created this (unix) group when you created the server"
			" user (usually, 'gavo').  Just do it now and re-run this program.")


def main():
	try:
		if len(sys.argv)==1:
			print fancyconfig.makeTxtDocs(_config, underlineChar="'")
			sys.exit(0)
		elif len(sys.argv)==2:
			item = _config.getitem(sys.argv[1])
		elif len(sys.argv)==3:
			item = _config.getitem(sys.argv[1], sys.argv[2])
		else:
			sys.stderr.write("Usage: %s [<sect> <key> | <key>]\n")
			sys.exit(1)
	except NoOptionError:
		print ""
		sys.exit(2)
	print item.getAsString()


def _test():
	import doctest, config
	doctest.testmod(config)


if __name__=="__main__":
	_test()
