"""
Base classes and common code for grammars.
"""

import codecs
import gzip

from gavo import base
from gavo import rscdef
from gavo.rscdef import rowgens
from gavo.rscdef import rowtriggers


class ParseError(base.Error):
	"""is an error raised by grammars if their input is somehow wrong.
	"""
	def __init__(self, msg, location=None, record=None):
		base.Error.__init__(self, msg)
		self.location, self.record = location, record


class MapKeys(base.Structure):
	"""is a specification of how to map grammar keys to exported names.
	"""
	name_ = "mapKeys"

	_content = base.DataContent(description="Simple mappings in the form"
		"<dest>:<src>{,<dest>:<src>}")
	_mappings = base.DictAttribute("maps", keyName="src", description=
		"Map src keys to name in content.", itemAttD=base.UnicodeAttribute("map"),
		copyable=True)

	def _parseShortenedMap(self, literal):
		try:
			for dest, src in (p.split(":") for p in literal.split(",")):
				if dest not in self.maps:
					self.maps[src.strip()] = dest.strip()
				else:
					raise base.LiteralParseError("%s simple map clobbers map to %s"%(
						"%s:%s"%(dest, src), self.maps[src]), "mapKeys",
						src)
		except ValueError:
			raise base.LiteralParseError("'%s' does not have the format"
				" k:v {,k:v}"%self.literal, self.name_, self.literal)

	def onElementComplete(self):
		if self.content_:
			self._parseShortenedMap(self.content_)
		self._onElementCompleteNext(MapKeys)

	def doMap(self, aDict):
		"""returns dict with the keys mapped according to the defined mappings.
		"""
		if self.maps:
			newDict = {}
			for k, v in aDict.iteritems():
				newDict[self.maps.get(k, k)] = v
			return newDict
		else:
			return aDict


class RowIterator(object):
	"""is an object that encapsulates the a source being parsed by a
	grammar.

	RowIterators are returned by Grammars' parse methods.  Iterate
	over them to retrieve the rows contained in the source.

	You can also call getParameters on them to retrieve document-global
	values (e.g., the parameters of a VOTable, a global header of
	a FITS table).

	The getLocator method should return some string that aids the user
	in finding out why something went wrong (file name, line number, etc.)

	This default implementation works for when source is a sequence
	of dictionaries.  You will, in general, want to override 
	_iteRows and getLocator, plus probably __init__ (to prepare external
	resources) and getParameters (if you have them).

	RowIterators are supposed to be self-destructing, i.e., they should 
	release any external resources they hold when _iterRows runs out of
	items.

	_iterRows should arrange for the instance variable recNo to be incremented
	by one for each item returned.
	"""
	def __init__(self, grammar, sourceToken):
		self.grammar, self.sourceToken = grammar, sourceToken
		self.recNo = 0

	def __iter__(self):
		if hasattr(self, "rowgen"):
			baseIter = self._iterRowsProcessed()
		else:
			baseIter = self._iterRows()
		if self.grammar.ignoreOn:
			rowSource = self._filteredIter(baseIter)
		else:
			rowSource = baseIter
		try:
			for row in rowSource:
				yield row
		except:
			base.ui.notifySourceError()
			raise
		base.ui.notifySourceFinished()

	def _filteredIter(self, baseIter):
		for row in baseIter:
			if not self.grammar.ignoreOn(row):
				yield row

	def _iterRowsProcessed(self):
		for row in self._iterRows():
			for procRow in self.rowgen(row, self):
				yield procRow

	def _iterRows(self):
		if False:
			yield None
		self.grammar = None # don't wait for garbage collection

	def getParameters(self):
		return {}
	
	def getLocator(self):
		return "Null grammar"


class FileRowIterator(RowIterator):
	"""is a RowIterator base for RowIterators reading files.

	It analyzes the sourceToken to see if it's a string, in which case
	it opens it as a file name and leaves the file object in self.inputFile.

	Otherwise, it assumes sourceToken already is a file object and binds
	it to self.inputFile.  It then tries to come up with a sensible designation
	for sourceToken.

	It also inspects the parent grammar for a gunzip attribute.  If it is
	present and true, the input file will be unzipped transparently.
	"""
	def __init__(self, grammar, sourceToken):
		RowIterator.__init__(self, grammar, sourceToken)
		self.curLine = 1
		if isinstance(self.sourceToken, basestring):
			if self.grammar.enc:
				self.inputFile = codecs.open(self.sourceToken, "r", self.grammar.enc)
			else:
				self.inputFile = open(self.sourceToken)
		else:
			self.inputFile = self.sourceToken
			self.sourceToken = getattr(self.inputFile, "name", repr(self.sourceToken))
		if hasattr(grammar, "gunzip") and grammar.gunzip:
			self.inputFile = gzip.GzipFile(fileobj=self.inputFile)


class GrammarMacroMixin(rscdef.StandardMacroMixin):
	"""is a collection of macros available to rowgens.

	NOTE: All macros should return only one single physical python line,
	or they will mess up the calculation of what constructs caused errors.
	"""
	def macro_inputRelativePath(self):
		"""returns an expression giving the current source's path 
		relative to inputsDir
		"""
		return ('base.getRelativePath(rowIter.sourceToken,'
			' base.getConfig("inputsDir"))')
	
	def macro_rowsProcessed(self):
		"""returns an expression giving the number of records already 
		ingested for this source.
		"""
		return 'rowIter.line'

	def macro_sourceDate(self):
		"""returns an expression giving the timestamp of the current source.
		"""
		return 'datetime.fromtimestamp(os.path.getmtime(rowIter.sourceToken))'
		
	def macro_srcstem(self):
		"""returns the stem of the source file currently parsed.
		
		Example: if you're currently parsing /tmp/foo.bar, the stem is foo.
		"""
		return 'os.path.splitext(os.path.basename(rowIter.sourceToken))[0]'

	def macro_lastSourceElements(self, numElements):
		"""returns an expression calling rmkfuncs.lastSourceElements on
		the current input path.
		"""
		return 'lastSourceElements(rowIter.sourceToken, int(numElements))'

	def macro_rootlessPath(self):
		"""returns an expression giving the current source's path with 
		the resource descriptor's root removed.
		"""
		return ('base.getRelativePath(rowIter.grammar.rd.resdir,'
			' rowIter.sourceToken)')

	def macro_inputSize(self):
		"""returns an expression giving the size of the current source.
		"""
		return 'os.path.getsize(rowIter.sourceToken)'


class Grammar(base.Structure, GrammarMacroMixin):
	"""is an abstract grammar.

	Grammars are configured via their structure parameters.  Their 
	parse(sourceToken) method returns an object that iterates over rawdicts
	(dictionaries mapping keys to (typically) strings) that can then be fed
	through rowmakers; it also has a method getParameters that returns
	global properties of the whole document (like parameters in VOTables;
	this will be empty for many kinds of grammars).

	RowIterators should, if at all possible, return a reference to
	themselves in the raw dicts in the parser_ key.  This is used by
	rowmaker macros.

	What exactly sourceToken is is up to the concrete grammar.  While
	typically it's a file name, it might be a sequence of dictionaries,
	a nevow context, or whatever.
	
	To derive a concrete Grammar, define a RowIterator for your source
	and set the rowIterator class attribute to it.
	"""
	name_ = "grammar"
	yieldsTyped = False

	_encoding = base.UnicodeAttribute("enc", default=None, description=
		"Encoding of strings coming in from source.", copyable=True)
	_rowgen = base.StructAttribute("rowgen", default=None,
		description="row generator for this grammar", 
		childFactory=rowgens.RowGenDef, copyable=True)
	_ignoreOn = base.StructAttribute("ignoreOn", default=None, copyable=True,
		description="Conditions for ignoring certain input records.",
		childFactory=rowtriggers.IgnoreOn)
	_properties = base.PropertyAttribute()
	_rd = rscdef.RDAttribute()

	rowIterator = RowIterator

	def compileRowgen(self):
		call = compile(self.rowgen.getCall(), "generated rowgen code", "eval")
		env = dict([self.rowgen.getDefinition()])
		env.update(self.rowgen._getMoreGlobals())
		def generateRows(row, rowIter):
			try:
				for newRow in eval(call, locals(), env):
					yield newRow
			except base.Error: # Hopefully meaningful
				raise
			except Exception, msg:
				raise base.LiteralParseError("While executing rowgen '%s': %s"%(
					self.rowgen.name, unicode(msg)), "rowgen", self.rowgen.getSource())
		return generateRows

	def parse(self, sourceToken):
		base.ui.notifyNewSource(sourceToken)
		ri = self.rowIterator(self, sourceToken)
		if self.rowgen:
			ri.rowgen = self.compileRowgen()
		return ri
	

class NullGrammar(Grammar):
	"""is a grammar that never returns any rows.
	"""
	name_ = "nullGrammar"
rscdef.registerGrammar(NullGrammar)
