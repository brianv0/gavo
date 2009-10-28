"""
Grammars for writing into the database without rowmakers.

These actually bypass most of our machinery and should only be used if
performance is paramount.  Otherwise, CustomGrammars play much nicer with
the rest of the DC software.

Currently, only one kind of DirectGrammar is supported: C boosters.
"""

import os
import pkg_resources
import re
import shutil

from gavo import base
from gavo import utils
from gavo import rsc
from gavo import rscdef


class Error(base.Error):
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
		self.resdir = dataDesc.rd.resdir
		self.srcName = os.path.join(self.resdir, srcName)
		self.autoNull, self.preFilter = autoNull, preFilter
		self.ignoreBadRecords = ignoreBadRecords
		self.gzippedInput = gzippedInput
		self.bindir = os.path.join(self.resdir, "bin")
		self.binaryName = os.path.join(self.bindir,
			os.path.splitext(os.path.basename(srcName))[0]+"-"+base.getConfig(
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


class DirectGrammar(base.Structure):
	"""A user-defined external grammar.

	See the separate document on user-defined code on more on direct grammars.

	Also note the program gavomkboost that can help you generate core for
	the C boosters used by direct grammars.
	"""
	name_ = "directGrammar"
	yieldsTyped = True # doesn't matter since it doesn't yield anything.

	_cbooster = rscdef.ResdirRelativeAttribute("cBooster", default=base.Undefined,
		description="resdir-relative path to the booster C source.")
	_gzippedInput = base.BooleanAttribute("gzippedInput", default=False,
		description="Pipe gzip before booster?")
	_autoNull = base.UnicodeAttribute("autoNull", default=None,
		description="Use this string as general NULL value")
	_ignoreBadRecords = base.BooleanAttribute("ignoreBadRecords",
		default=False, description="Let booster ignore invalid records?")
	_recordSize = base.IntAttribute("recordSize", default=None,
		description="Have C booster read that much bytes to obtain a record")
	_preFilter = rscdef.ResdirRelativeAttribute("preFilter", default=None,
		description="Pipe input through this program before handing it to"
			" the booster.")
	_rd = rscdef.RDAttribute()

	def parse(self, sourceToken, targetData=None):
		booster = CBooster(self.cBooster, self.recordSize, self.parent,
			gzippedInput=self.gzippedInput,
			preFilter=self.preFilter,
			autoNull=self.autoNull,
			ignoreBadRecords=self.ignoreBadRecords)
		makes = self.parent.makes
		if len(makes)!=1:
			raise base.StructureError("Directgrammar only work in data having"
				" exactly one table, but data '%s' has %d"%(
					self.parent.id, len(makes)))
		def copyIn(data):
			data.tables.values()[0].copyIn(booster.getOutput(sourceToken))
			if booster.getStatus():
				raise Error("Booster returned error signature while processing %s."%
					sourceToken)
		return copyIn

rscdef.registerGrammar(DirectGrammar)

# booster source code generating functions

import sys

def getNameForItem(item):
	return "fi_"+item.name.lower()


class _CodeGenerator(object):
	def __init__(self, options):
		pass
		
	def getSetupCode(self):
		return []
	
	def getItemParser(self, item):
		return []


class ColCodeGenerator(_CodeGenerator):
	def getItemParser(self, item):
		t = item.type
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


class BinCodeGenerator(_CodeGenerator):
	def getItemParser(self, item):
		t = item.type
		if t=="integer":
			pline = "MAKE_INT32(%s, *(int32_t*)(line+));"
		elif t=="smallint":
			pline = "MAKE_SHORT(%s, *(int16_t*)(line+ ));"
		elif t=="double precision":
			pline = "MAKE_DOUBLE(%s, *(double*)(line+ ));"
		elif t=="real":
			pline = "MAKE_FLOAT(%s, *(float*)(line+ ));"
		elif t=="char":
			pline = "MAKE_CHAR_NULL(%s, *(double*)(line+ ), '<nil>');"
		elif t=="bytea":
			pline = "MAKE_BYTE(%s, *(double*)(line+ ), '<nil>');"
		else:
			pline = "MAKE %s"
		return ["/* %s (%s) */"%(item.description, t), 
			pline%getNameForItem(item)]


class SplitCodeGenerator(_CodeGenerator):
	def __init__(self, options):
		self.splitChar = getattr(options, "split", "|")
		_CodeGenerator.__init__(self, options)

	def getSetupCode(self):
		return ['char *curCont = strtok(inputLine, "%s");'%self.splitChar]

	def getItemParser(self, item):
		t = item.type()
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
	if opts.binParser:
		return BinCodeGenerator(opts)
	if getattr(opts, "split", None):
		return SplitCodeGenerator(opts)
	else:
		return ColCodeGenerator(opts)


def printIndented(stringList, indentChar):
	print indentChar+('\n'+indentChar).join(stringList)


def buildSource(td, opts):
	codeGen = getCodeGen(opts)
	print '#include <math.h>\n#include <string.h>\n#include "boosterskel.h"\n'
	print "#define QUERY_N_PARS %d\n"%len(list(td))
	print 'enum outputFields {'
	for item in td:
		desc = item.tablehead
		if not desc:
			desc = item.description
		print "\t%-15s  /* %s, %s */"%(getNameForItem(item)+",",
			desc, item.type)
	print '};\n'
	print "Field *getTuple(char *inputLine)\n{"
	print "\tstatic Field vals[QUERY_N_PARS];\n"
	printIndented(codeGen.getSetupCode(), "\t")
	for item in td:
		printIndented(codeGen.getItemParser(item), "\t")
	print "\treturn vals;"
	print "}"


def getTableDef(rdName, tdId):
	try:
		rd = base.caches.getRD(rdName)
	except base.RDNotFound:
		rd = base.caches.getRD(os.path.join(os.getcwd(), rdName))
	return rd.getById(tdId)


def parseCmdLine():
	from optparse import OptionParser
	parser = OptionParser(usage = "%prog [options] <rd-name> <table-id>")
	parser.add_option("-s", "--splitter", help="generate a split skeleton"
		" with split string SPLITTER", metavar="SPLITTER", action="store",
		type="string", dest="split")
	parser.add_option("-b", "--binary", help="generate a skeleton for"
		" a binary parser", action="store_true", dest="binParser")
	(opts, args) = parser.parse_args()
	if len(args)!=2:
		parser.print_help()
		sys.exit(1)
	return opts, args


def main():
	from gavo import rscdesc
	from gavo.protocols import basic
# Some rds need db connectivity
	base.setDBProfile("trustedquery")
	try:
		opts, (rdName, tdId) = parseCmdLine()
		td = getTableDef(rdName, tdId)
		src = buildSource(td, opts)
	except SystemExit, msg:
		sys.exit(msg.code)
