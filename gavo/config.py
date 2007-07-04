"""
This module contains a settings class and a way to fill it from a
simple ini-style file .gavosettings

We currently support:

In section db:

* dsn -- the dsn of the target database as <host>:<port>:<dbname>
* user -- username for db auth
* password -- password for user
* allroles -- when creating tables and schemas, all users in this 
comma separated list are granted all privileges on them
* readroles -- when creating tables and schemas, all users in this 
comma separated list are granted read/usage privileges on them
* msgencoding -- the encoding the DB uses for its messages

in section querulator:

* defaultmaxmatches -- the default limit of matched rows in querulator
"""

import os
import ConfigParser

from gavo import utils


class Settings(utils.Record):
	"""is a container for source-global user-specifiable settings.

	The settings should be hierarchic, with individual items separated
	by "_" (so valid names for set_XXX and get_XXX result).  Probably
	only two levels should be used.  These are mapped to sections and
	items, respectively, in the ini-style config file that probably
	usually is the source for these settings.

	All keys should be lowercase only.  Values can be converted to any
	type by the setter.
	"""
	def __init__(self):
		utils.Record.__init__(self, {
			"db_dsn": None,
			"db_user": None,
			"db_password": None,
			"db_allroles": "",
			"db_readroles": "",
			"db_msgEncoding": "utf-8",
			"querulator_defaultmaxmatches": 1000,
		})

	def get_db_allroles(self):
		return [s.strip() for s in self.dataStore["db_allroles"].split(",")
			if s.strip()]
	
	def get_db_readroles(self):
		return [s.strip() for s in self.dataStore["db_readroles"].split(",")
			if s.strip()]


def _parseSettings(srcfile=None):
	p = ConfigParser.ConfigParser()
	s = Settings()
	if srcfile==None:
		srcfile = os.environ.get("GAVOSETTINGS", os.path.join(
			os.environ.get("HOME", "/no_home"), ".gavosettings"))
	p.read(srcfile)
	for sect in p.sections():
		for name, value in p.items(sect):
			s.set("%s_%s"%(sect, name), value)
	return s

def loadSettings(srcfile):
	global settings
	settings = _parseSettings(srcfile)

settings = _parseSettings()
