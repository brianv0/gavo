"""
Code that abstracts the parsing process.

Right now, we either simply call the parse method of the grammar or
start a cgbooster.  More special handling may be necessary
in the future.

cgboosters are C programs that are supposed to implement what ColumnGrammars
do.  Later on, we probably have people drop a C function into the res directory
and compile the stuff automatically.  For now, we hack the stuff such that the
protype (for ppmx) runs.
"""

import os
import sys

import gavo
from gavo import config
from gavo import table
from gavo.parsing import columngrammar
from gavo.parsing import parsehelpers
from gavo.parsing import resource


class BoosterException(gavo.Error):
	pass

class BoosterNotDefined(BoosterException):
	pass

class BoosterNotAvailable(BoosterException):
	pass

class BoosterFailed(BoosterException):
	pass


def _tryBooster(grammar, inputFileName, tableName, descriptor):
	booster = grammar.get_booster()
	if booster==None:
		raise BoosterNotDefined
	connDesc = config.getDbProfile().getDsn()
	booster = os.path.join(descriptor.get_resdir(), booster)
	try:
		f = os.popen("%s '%s' '%s'"%(booster, inputFileName, tableName), "w")
		f.write(connDesc)
		f.flush()
		retval = f.close()
	except IOError, msg:
		if msg.errno==32:
			raise BoosterNotAvailable("Broken pipe")
		else:
			raise
	if retval!=None:
		retval = (retval&0xff00)>>8
	if retval==126: 
		raise BoosterNotAvailable("Invalid binary format")
	if retval==127:
		raise BoosterNotAvailable("Binary not found")
	if retval:
		raise BoosterFailed()

def _tryBooster(parseContext):
	"""checks if we can run a booster and returns True if a booster
	was run successfully and False if not.
	"""
	try:
		grammar = parseContext.getDataSet().getDescriptor().get_Grammar()
		if not isinstance(grammar, columngrammar.ColumnGrammar):
			raise BoosterNotDefined("Boosters only work for ColumnGrammars")
		tables = parseContext.getDataSet().getTables() 
		if len(tables)!=1 or not isinstance(tables[0], table.DirectWritingTable):
			raise BoosterNotDefined("Boosters only work for for single direct"
				" writing tables")
		_runBooster(grammar, src, tables[0].getTableName(), descriptor)
	except BoosterNotDefined:
		return False
	except BoosterNotAvailable, msg:
		gavo.ui.displayMessage("Booster defined, but not available"
			" (%s).  Falling back to normal parse."%msg)
		return False
	except BoosterFailed:
		raise gavo.Error("Booster failed.")
	return True

def _parseSource(parseContext):
	"""actually executes the parse process described by parseContext.

	This is the place to teach the program special tricks to bypass
	the usual source processing using grammars.
	"""
	if not _tryBooster(parseContext):
		parseContext.parse()

def _createTable(dataSet, recordDef):
	if recordDef.get_onDisk():
		TableClass = table.DirectWritingTable
	else:
		TableClass = table.Table
	return TableClass(dataSet, recordDef)

def getDataset(srcDesc, descriptor, dumpOnly=False, debugProductions=[],
			maxRows=None, metaOnly=False, bail=False):
	"""parses the data source described by descriptor returns a DataSet.
	containing the data and the governing semantics.
	"""
	grammar = srcDesc.get_Grammar()
	grammar.enableDebug(debugProductions)
	data = resource.DataSet(srcDesc, _createTable, _parseSource, 
		maxRows=maxRows, bail=False)
	return data
