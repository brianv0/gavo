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
import pkg_resources
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

	Warning: If you change the booster description, you'll need to touch
	the source to recompile.
	"""
	def __init__(self, srcName, recordSize, dataDesc, gzippedInput=False,
			autoNull=None, preFilter=None, ignoreBadRecords=False):
		self.dataDesc = dataDesc
		self.recordSize = recordSize
		self.resdir = dataDesc.getRd().get_resdir()
		self.srcName = os.path.join(self.resdir, srcName)
		self.autoNull, self.preFilter = autoNull, preFilter
		self.ignoreBadRecords = ignoreBadRecords
		self.gzippedInput = gzippedInput
		self.bindir = os.path.join(self.resdir, "bin")
		self.binaryName = os.path.join(self.bindir,
			os.path.splitext(os.path.basename(srcName))[0]+"-"+config.get(
				"platform"))
		self._ensureBinary()

	def _copySources(self, wd):
		def getResource(src, dest):
			inF = pkg_resources.resource_stream('gavo', src)
			outF = open(os.path.join(wd, dest), "w")
			outF.write(inF.read())
			outF.close()
			inF.close()
		getResource("resources/src/boosterskel.c", "boosterskel.c")
		getResource("resources/src/boosterskel.h", "boosterskel.h")
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
		f.write("LDFLAGS += -lm\n"
			"CFLAGS += -DQUERY_N_PARS=%s\n"%query_n_pars)
		if self.recordSize:
			f.write("CFLAGS += -DFIXED_RECORD_SIZE=%s\n"%self.recordSize)
		if self.autoNull:
			f.write("CFLAGS += -DAUTO_NULL='%s'\n"%self.autoNull.replace(
				"\\", "\\\\"))
		if self.ignoreBadRecords:
			f.write("CFLAGS += -DIGNORE_BAD_RECORDS\n")
		f.write("booster: boosterskel.c func.c\n"
			"\t$(CC) $(CFLAGS) $(LDFLAGS) -o booster $^\n")
		f.close()
	
	def _build(self):
		if os.system("make"):
			raise Error("Booster build failed")
	
	def _retrieveBinary(self, od):
		shutil.copyfile("booster", self.binaryName)
		os.chmod(self.binaryName, 0775)

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

		As a side effect, it also sets the attribute self.pipe.  We need
		this to be able to retrieve the command status below.
		"""
		if self.preFilter:
			self.pipe = os.popen("%s '%s' | %s"%(self.preFilter, argName, 
				self.binaryName))
		elif self.gzippedInput:
			self.pipe = os.popen("zcat '%s' | %s"%(argName, self.binaryName))
		else:
			self.pipe = os.popen("%s '%s'"%(self.binaryName, argName))
		return self.pipe
	
	def getStatus(self):
		return self.pipe.close()


class DirectGrammar(record.Record):
	def __init__(self, **attrs):
		self.attrs = attrs
		record.Record.__init__(self, {})

	def _parseUsingCBooster(self, parseContext):
		rD = parseContext.dataSet.dD.rD
		booster = CBooster(self.attrs["cbooster"], self.attrs.get("recordSize"),
			parseContext.getDataSet().getDescriptor(), 
			gzippedInput=self.attrs.has_key("gzippedInput") 
				and record.parseBooleanLiteral(self.attrs["gzippedInput"]),
			preFilter=self.attrs.has_key("preFilter")
				and os.path.join(rD.get_resdir(), self.attrs["preFilter"]),
			autoNull=self.attrs.get("autoNull", None),
			ignoreBadRecords=record.parseBooleanLiteral(
				self.attrs.get("ignoreBadRecords", "False")))
		targetTables = parseContext.getDataSet().getTables()
		assert len(targetTables)==1
		try:
			targetTables[0].tableWriter.copyIn(booster.getOutput(
					parseContext.sourceName))
		except AttributeError:
			raise gavo.Error("Boosters only work on tables with onDisk=True")
		if booster.getStatus():
			raise Error("Booster returned error signature while processing %s."%
				parseContext.sourceName)

	def parse(self, parseContext):
		if self.attrs.has_key("cbooster"):
			return self._parseUsingCBooster(parseContext)
		raise Error("No sufficient DirectGrammar specification")

	def enableDebug(*args, **kwargs):
		pass


# booster source code generating functions

import sys
from optparse import OptionParser

def getNameForItem(item):
	return "fi_"+item.get_dest().lower()


class ColCodeGenerator:
	def __init__(self, option):
		pass
	
	def getSetupCode(self):
		return []

	def getItemParser(self, item):
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
		return ["%s(inputLine, F(%s), start, len);"%(func, getNameForItem(item))]


class SplitCodeGenerator:
	def __init__(self, option):
		self.splitChar = getattr(option, "split", "|")

	def getSetupCode(self):
		return ['char *curCont = strtok(inputLine, "%s");'%self.splitChar]

	def getItemParser(self, item):
		t = item.get_dbtype()
		if t=="smallint":
			cType = "VAL_SHORT"
		elif t=="bigint":
			cType = "VAL_INT_64"
		elif "int" in t:
			cType = "VAL_INT"
		elif t in ["real", "float"]:
			cType = "VAL_FLOAT"
		elif "double" in t:
			cType = "VAL_DOUBLE"
		elif "char"==t:
			cType = "VAL_CHAR"
		elif "char" in t:
			cType = "VAL_TEXT"
		elif "bool" in t:
			cType = "VAL_BOOL"
		else:
			cType = "###No appropriate type###"
		return ["fieldscanf(curCont, %s, %s);"%(getNameForItem(item),
			cType), 
			'curCont = strtok(NULL, "%s");'%self.splitChar]


def getCodeGen(opts):
	if getattr(opts, "split", None):
		return SplitCodeGenerator(opts)
	else:
		return ColCodeGenerator(opts)

def printIndented(stringList, indentChar):
	print indentChar+('\n'+indentChar).join(stringList)


def buildSource(dd, opts):
	codeGen = getCodeGen(opts)
	recs = dd.get_Semantics().get_tableDefs()
	if len(recs)!=1:
		raise Error("Booster can only be defined on Data having exactly one"
			"Record definition.")
	items = recs[0].get_items()
	print '#include <math.h>\n#include <string.h>\n#include "boosterskel.h"\n'
	print "#define QUERY_N_PARS %d\n"%len(items)
	print 'enum outputFields {'
	for item in items:
		desc = item.get_tablehead()
		if not desc:
			desc = item.get_description()
		print "\t%-15s  /* %s, %s */"%(getNameForItem(item)+",",
			desc, item.get_dbtype())
	print '};\n'
	print "Field *getTuple(char *inputLine)\n{"
	print "\tstatic Field vals[QUERY_N_PARS];\n"
	printIndented(codeGen.getSetupCode(), "\t")
	for item in items:
		printIndented(codeGen.getItemParser(item), "\t")
	print "\treturn vals;"
	print "}"


def getDataDesc(rdName, ddId):
	from gavo.parsing import importparser
	try:
		rd = importparser.getRd(rdName)
	except gavo.RdNotFound:
		rd = importparser.getRd(os.path.join(os.getcwd(), rdName))
	return rd.getDataById(ddId)


def parseCmdLine():
	parser = OptionParser(usage = "%prog [options] <rd-name> <data-id>")
	parser.add_option("-s", "--splitter", help="generate a split skeleton"
		" with split string SPLITTER", metavar="SPLITTER", action="store",
		type="string", dest="split")
	(opts, args) = parser.parse_args()
	if len(args)!=2:
		parser.print_help()
		sys.exit(1)
	return opts, args


def main():
# Some rds need db connectivity
	config.setDbProfile("querulator")
	try:
		opts, (rdName, ddId) = parseCmdLine()
		dd = getDataDesc(rdName, ddId)
		src = buildSource(dd, opts)
	except SystemExit, msg:
		sys.exit(msg.code)
	except Exception, msg:
		utils.displayError(msg)
