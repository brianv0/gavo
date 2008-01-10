"""
Grammars for directly writing into the database.

These guys aren't grammars at all in that they don't deliver rowdicts to
some process.  Indeed, DirectGrammars don't (and can't) even implement
the interface needed by the classes in resource.py.  They are just
here since in resource descriptors, they stand where usually there are 
grammars.

Currently, only one kind of DirectGrammar is supported: C boosters.  Other
kinds might be supported later.  They would be distinguished by having other
attributes.
"""

import os
import re
import shutil

import gavo
from gavo import config
from gavo import record
from gavo import utils


class Error(gavo.Error):
	pass


class CBooster:
	"""is a wrapper for an import booster written in C using the DC booster
	infrastructure.
	"""
	def __init__(self, srcName, dataDesc):
		self.dataDesc = dataDesc
		self.resdir = dataDesc.getRD().get_resdir()
		self.srcName = os.path.join(self.resdir, srcName)
		self.bindir = os.path.join(self.resdir, "bin")
		self.binaryName = os.path.join(self.bindir,
			os.path.splitext(os.path.basename(srcName))[0]+"-"+config.get(
				"platform"))
		self._ensureBinary()

	def _copySources(self, wd):
		shutil.copyfile(
			os.path.join(config.get("rootDir"), "src", "boosterskel.c"),
			os.path.join(wd, "boosterskel.c"))
		shutil.copyfile(
			os.path.join(config.get("rootDir"), "src", "boosterskel.h"),
			os.path.join(wd, "boosterskel.h"))
		shutil.copyfile(self.srcName, os.path.join(wd, "func.c"))
		# Ouch.  We now need to hack QUERY_N_PARS out of the function source.
		# It's ugly, but the alternatives aren't prettier.  The thing just needs 
		# to be a macro.
		mat = re.search("(?m)^#define QUERY_N_PARS\s+(\d+)", 
			open(self.srcName).read())
		if not mat:
			raise Error("Booster function doesn't define QUERY_N_PARS")
		query_n_pars = mat.group(1)
		f = open(os.path.join(wd, "Makefile"), "w")
#		f.write("CFLAGS := $(CFLAGS) -Wall -I ${shell pg_config --includedir} -g\n"
#			"LDFLAGS := $(LDFLAGS) -L ${shell pg_config --libdir} -lm -lpq\n")
		f.write("LDFLAGS += -lm\n"
			"CFLAGS += -DQUERY_N_PARS=%s\n"
			"booster: boosterskel.c func.c\n"
			"\t$(CC) $(CFLAGS) $(LDFLAGS) -o booster $^\n"%query_n_pars)
		f.close()
	
	def _build(self):
		if os.system("make"):
			raise Error("Booster build failed")
	
	def _retrieveBinary(self, od):
		shutil.copyfile("booster", self.binaryName)

	def _ensureBinary(self):
		"""makes sure the booster binary exists and is up-to-date.
		"""
		if not os.path.exists(self.bindir):
			os.makedirs(self.bindir)
		try:
			if os.path.getmtime(self.srcName)<os.path.getmtime(self.binaryName):
				return
		except os.error:
			pass
		utils.runInSandbox(self._copySources, self._build, self._retrieveBinary)

	def getOutput(self, argName):
		"""returns a pipe you can read the booster's output from.
		"""
		return os.popen("%s '%s'"%(self.binaryName, argName))


class DirectGrammar(record.Record):
	def __init__(self, **attrs):
		if attrs.has_key("cbooster"):
			self.boosterSrc = attrs["cbooster"]
		else:
			raise Error("DirectGrammars must have a cbooster attribute")
		record.Record.__init__(self, {})

	def _parseUsingCBooster(self, parseContext):
		booster = CBooster(self.boosterSrc, 
			parseContext.getDataSet().getDescriptor())
		targetTables = parseContext.getDataSet().getTables()
		assert len(targetTables)==1
		targetTables[0].tableWriter.copyIn(booster.getOutput(
			parseContext.sourceName))

	def parse(self, parseContext):
		self._parseUsingCBooster(parseContext)

	def enableDebug(*args, **kwargs):
		pass


# booster source code generating functions

import sys
from optparse import OptionParser

def getNameForItem(item):
	return "fi_"+item.get_dest().lower()


def getParseCodeBoilerplate(item):
	t = item.get_dbtype()
	if "int" in t:
		func = "parseInt"
	elif t in ["real", "float"]:
		func = "parseFloat"
	elif "double" in t:
		func = "parseDouble"
	elif "char" in t:
		func = "parseString"
	elif "bool" in t:
		func = "parseBlankBoolean"
	else:
		func = "parseWhatever"
	return "%s(inputLine, F(%s), start, end)"%(func, getNameForItem(item))


def buildSource(dd):
	recs = dd.get_Semantics().get_recordDefs()
	if len(recs)!=1:
		raise Error("Booster can only be defined on Data having exactly one"
			"Record definition.")
	items = recs[0].get_items()
	print '#include <math.h>\n#include "boosterskel.h"\n'
	print "#define QUERY_N_PARS %d\n"%len(items)
	print 'enum outputFields {'
	for item in items:
		print "\t%-15s  /* %s, %s */"%(getNameForItem(item)+",",
			item.get_tablehead(), item.get_dbtype())
	print '}\n'
	print "Field *getTuple(char *inputLine)\n{"
	print "\tstatic Field vals[QUERY_N_PARS];\n"
	for item in items:
		print "\t%s;"%getParseCodeBoilerplate(item)
	print "}"


def getDataDesc(rdName, ddId):
	from gavo.parsing import importparser
	try:
		rd = importparser.getRd(rdName)
	except IOError:
		rd = importparser.getRd(os.path.join(os.getcwd(), rdName))
	return rd.getDataById(ddId)


def parseCmdLine():
	parser = OptionParser(usage = "%prog [options] <rd-name> <data-id>")
	(opts, args) = parser.parse_args()
	if len(args)!=2:
		parser.print_help()
		sys.exit(1)
	return opts, args


def main():
	try:
		opts, (rdName, ddId) = parseCmdLine()
		dd = getDataDesc(rdName, ddId)
		src = buildSource(dd)
	except SystemExit, msg:
		sys.exit(msg.code)
	except Exception, msg:
		utils.displayError(msg)
