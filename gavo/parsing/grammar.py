"""
This module defines an abstract superclass for all grammars.
"""

from gavo import utils
from gavo import logger
from gavo import parsing
import gavo


class ParseError(gavo.Error):
	pass


class Grammar(utils.Record):
	"""is an abstract grammar.

	The grammar protocol is simple: You set a rowHandler and/or
	documentHandler to a function accepting a dictionary mapping
	preterminal names to their values, and then you pass an open
	file or a file name to parse.

	Implementations of Grammars should not override any of the
	public methods, but they may override the built-in _parse.
	The _parse method of the implementation then has to arrange
	it so that the documentHandler is called with the preterminal
	values of the entire document in a dict, and the rowHandler
	with the preterminal values of each row, again in a dictionary.
	The dicts map strings to strings.  Grammar classes have to be
	able to cope with either of the handlers being None.

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
		})
		utils.Record.__init__(self, fieldDefs)
		self.curInputFileName = None
		self.rowHandlers = []
		self.documentHandlers = []

	def _parse(self, inputFile):
		getattr(self, "_setupParse", lambda: None)()
		rowHandler = self.rowHandler or (lambda row: None)
		counter = gavo.ui.getGoodBadCounter("Importing rows", 100)
		try:
			row = self._getDocumentRow()
			self.documentHandler(row)

			for row in self._iterRows():
				counter.hit()
				try:
					rowHandler(row)
				except gavo.InfoException, msg:
					logger.info(msg)
				except gavo.Error, msg:
					logger.error(msg)
					counter.hitBad()
		finally:
			getattr(self, "_cleanupParse", lambda: None)()
			counter.close()

	def _runProcessors(self, rowdict, procType):
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

	def _expandMacros(self, rowdict, procType):
		for macro in self.get_macros():
			macro(rowdict)

	def _process(self, rowdict, procType):
		"""runs row processors and macros on rowdict.

		procType may be row or doc to select only processors for the
		respective production (not implemented yet).
		"""
		for row in self._runProcessors(rowdict, procType):
			try:
				self._expandMacros(rowdict, procType)
				yield rowdict
			except KeyboardInterrupt:
				raise
			except Exception, msg:
				if parsing.verbose:
					import traceback
					traceback.print_exc()
				raise gavo.Error("Invalid macro expansion (%s, %s) -- ignoring"%(
					msg.__class__.__name__, str(msg)))


	def parse(self, inputFile):
		"""parses the inputFile and returns the parse result.

		inputFile may be an open file or a file name.
		"""
		if isinstance(inputFile, basestring):
			self.curInputFileName = inputFile
			inputFile = open(inputFile)
		else:
			self.curInputFileName = inputFile.name
		self.inputFile = inputFile
		self._parse(inputFile)
		self.curInputFile = None

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

	def documentHandler(self, docdict):
		"""should be called by derived classes whenever a new document
		has been parsed.

		The argument is a dict mapping preterminal names to their values.
		"""
		for processedDict in self._process(docdict, "doc"):
			for handler in self.documentHandlers:
				handler(processedDict)

	def rowHandler(self, rowdict):
		"""should be called by derived classes whenever a new row
		has been parsed.

		The argument is a dict mapping preterminal names to their values.
		"""
		for processedDict in self._process(rowdict, "row"):
			for handler in self.rowHandlers:
				handler(processedDict)

	def enableDebug(self, aList):
		pass
