"""
This module defines an abstract superclass for all grammars.
"""

from gavo import utils
from gavo import logger
from gavo import parsing
from gavo import sqlsupport
import gavo


class ParseError(gavo.Error):
	pass


class Grammar(utils.Record):
	"""is an abstract grammar.

	The grammar protocol is simple: You add a rowHandler(s) and/or
	documentHandler(s) to functions accepting a dictionary mapping
	preterminal names to their values, and then you pass an open
	file or a file name to parse.

	Implementations of Grammars should not override any of the
	public methods, but they may override the built-in _parse.
	The _parse method of the implementation then has to arrange
	it so that the documentHandlers are called with the preterminal
	values of the entire document in a dict, and the rowHandlers
	with the preterminal values of each row, again in a dictionary.
	The dicts map strings to strings.

	If they don't override the _parse method, they have to provide
	methods 
		* _getDocumentRow() -- returns a dict of toplevel productions
		* _iterRows() -- iterates over all rows in the document, should
		  raise a ParseError for malformed rows.
	
	They may provide methods
	 * _setupParse()
	 * _cleanupParse()
	
	The file that is to be parsed is available (as a file instance)
	in self.inputFile.  The built-in _parse first calls _setupParse,
	then _getDocumentRow, then _iterRows, 

	Grammar classes should also provide an enableDebug method that
	accepts a list of symbol names that they should print some sort
	of debug info for.
	"""
	def __init__(self, fieldDefs):
		fieldDefs.update({
			"macros": utils.ListField,     # macros to be applied
			"rowProcs": utils.ListField,   # row processors to be applied
			"docIsRow": utils.BooleanField, # apply row macros to docdict and ship it?
		})
		utils.Record.__init__(self, fieldDefs)
		self.curInputFileName = None
		self.rowHandlers = []
		self.documentHandlers = []
	
	def _handleInternalError(self, exc, row):
		if parsing.verbose:
			import traceback
			traceback.print_exc()
		msg = ("Internal Error (%s, %s) while parsing row %s -- run with -v to"
			" see traceback."%(exc.__class__.__name__, str(exc), str(row)[:120]))
		gavo.ui.displayError(msg)
		raise gavo.Error(msg)

	def _parse(self, inputFile):
		getattr(self, "_setupParse", lambda: None)()
		counter = gavo.ui.getGoodBadCounter("Importing rows", 100)
		try:
			row = self._getDocumentRow()
			try:
				self.handleDocument(row)
			except gavo.Error:
				raise
			except Exception, msg:
				self._handleInternalError(msg, row)
			lines = self._iterRows()
			# We use this funny loop to handle exceptions raised while the
			# grammar matches a row in the exception handlers below (it would
			# be hard to get an appropriate row count otherwise)
			while 1:
				try:
					row = lines.next()
					self.handleRow(row)
					counter.hit()
				except StopIteration:
					break
				except (gavo.StopOperation, KeyboardInterrupt):
					raise
				except gavo.InfoException, msg:
					logger.info(msg)
				except gavo.parsing.ParseError, msg:
					errmsg = "Parse failure, aborting source (%s). See log."%msg
					counter.hitBad()
					logger.error(errmsg, exc_info=True)
					raise gavo.Error(errmsg)
				except sqlsupport.OperationalError, msg:
					logger.error("Row %s bad (%s).  Ignoring."%(row, msg))
					gavo.ui.displayError("Import of row %s failed (%s). ABORTING"
						" OPERATION."%(row, msg))
					counter.hitBad()
					raise  # XXXXXXXXX should emit err msg wherever this is caught.
				except Exception, msg:
					counter.hitBad()
					self._handleInternalError(msg, row)
		finally:
			getattr(self, "_cleanupParse", lambda: None)()
			counter.close()

	def _runProcessors(self, rowdict):
		"""processes rowdict with all row processors and returns all
		resulting rows.
		"""
		currentRows = [rowdict]
		for proc in self.get_rowProcs():
			newRows = []
			for row in currentRows:
				newRows.extend(proc(rowdict))
			currentRows = newRows
		return currentRows

	def _expandMacros(self, rowdict):
		for macro in self.get_macros():
			macro(rowdict)

	def _process(self, rowdict):
		"""runs row processors and macros on rowdict.
		"""
		for row in self._runProcessors(rowdict):
			self._expandMacros(row)
			yield row

	def parse(self, inputFile):
		"""parses the inputFile and returns the parse result.

		inputFile may be an open file or a file name.
		"""
		if isinstance(inputFile, basestring):
			self.curInputFileName = inputFile
			inputFile = open(inputFile)
		else:
			try:
				self.curInputFileName = inputFile.name
			except AttributeError:
				self.curInputFileName = "<not a disk file>"
		self.inputFile = inputFile
		self._parse(inputFile)
		self.inputFile = None
		self.curInputFileName = None

	def getCurFileName(self):
		"""returns the name of the file that's currently being parsed.

		Of course, all kinds of funny race conditions are possible here.
		You shouldn't care about the name anyway, and if you have to, you're
		hosed anyway.

		The function returns None if no parsing is going on.
		"""
		return self.curInputFileName

	def addRowHandler(self, callable):
		"""causes callable to be called whenever a table line has been
		parsed.

		Callable has to accept a dictionary mapping the names of the 
		nonterminals found to their expansions in the table line.
		"""
		self.rowHandlers.append(callable)
	
	def addDocumentHandler(self, callable):
		"""causes callable to be called with a dictionary of the preterminals
		attached to the global document.
		"""
		self.documentHandlers.append(callable)

	def handleDocument(self, docdict):
		"""should be called by derived classes whenever a new document
		has been parsed.

		The argument is a dict mapping preterminal names to their values.
		"""
		if self.get_docIsRow():
			self.handleRow(docdict)
		else:
			if not self.documentHandlers:
				return
			for handler in self.documentHandlers:
				handler(docdict)

	def handleRow(self, rowdict):
		"""should be called by derived classes whenever a new row
		has been parsed.

		The argument is a dict mapping preterminal names to their values.
		"""
		if not self.rowHandlers:
			return
		for processedDict in self._process(rowdict):
			for handler in self.rowHandlers:
				handler(processedDict)

	def enableDebug(self, aList):
		pass
