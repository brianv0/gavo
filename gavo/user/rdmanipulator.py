"""
Helpers for manipulating serialised RDs.

The problem here is that RDs typically are formatted with lots of love,
also within elements -- e.g., like this:

	<column name="bla" type="text"
		ucd="foo.bar"
		description="A long text carefully
			broken at the right place"
	/>

There's no way one can coax a normal XML parser into giving events that'd
allow us to preserve this formatting.   Hence, when manipulating
RD sources, I need something less sophisticated -- the dump XML parser
implemented here.

Note that this will accept non-well-formed documents; don't use this except
for the limited purpose of editing supposedly well-formed documents.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import os
import sys

from gavo import base
from gavo import rscdesc
from gavo import utils
from gavo.user import info
from gavo.imp.pyparsing import (CharsNotIn, Forward, Literal, Optional, 
	ParseResults, QuotedString, SkipTo,
	StringEnd, White, Word, ZeroOrMore, alphas, alphanums)


def flatten(arg):
	"""returns a string from a (possibly edited) parse tree.
	"""
	if isinstance(arg, basestring):
		return arg
	elif isinstance(arg, (list, ParseResults)):
		return "".join(flatten(a) for a in arg)
	else:
		return arg.flatten()


def _nodify(s, p, t):
# a parse action to keep pyparsing from flattenting out things into
# a single list
	return [t.asList()]


class Attribute(list):
	"""a sentinel for XML attributes.
	"""
	def __init__(self, t):
		list.__init__(self, t)
		self.name, self.value = t[0], t[2][1:-1]


def getAttribute(parseResult, name):
	"""returns the  Attribute element with name within parseResult.

	If no such attribute exists, a KeyError is raised.
	"""
	for el in parseResult:
		if isinstance(el, Attribute):
			if el.name==name:
				return el
	raise KeyError("No attribute %s in %s"%(name, flatten(parseResult)))


class Element(list):
	"""a sentinel for XML elements.

	These are constructed with lists of the type [tag,...]; the opening (or
	empty) tag is always item 0.
	"""
	def __init__(self, t):
		list.__init__(self, t)
		self.name = t[0][1]

	def getAttribute(self, name):
		"""returns the  Attribute element with name within self.

		If no such attribute exists, a KeyError is raised.
		"""
		return getAttribute(self[0], name)

	def findElement(self, name):
		"""returns the first element called name somewhere within the xml 
		grammar-parsed parseResult

		This is a depth-first search, and it will return None if there
		is no such element.
		"""
		for el in self:
			if isinstance(el, Element):
				if el.name==name:
					return el

				res = el.findElement(name)
				if res is None:
					return res


def getXMLGrammar(manipulator):

	with utils.pyparsingWhitechars("\r"):
		name = Word(alphas+"_:", alphanums+".:_-")
		opener = Literal("<")
		closer = Literal(">")
		value = (QuotedString(quoteChar="'", multiline=True, unquoteResults=False) 
			| QuotedString(quoteChar='"', multiline=True, unquoteResults=False))
		attribute = (name
			+ Literal("=")
			+ value)
		tagOpener = (opener 
			+ name 
			+ ZeroOrMore(White() + attribute)
			+ Optional(White()))

		openingTag = (tagOpener
			+ closer)
		closingTag = (opener
			+ Literal("/")
			+ name
			+ Optional(White())
			+ closer)
		emptyTag =  (tagOpener
			+ Optional(White())
			+ Literal("/>"))

		processingInstruction = (opener 
			+ Literal("?")
			+ SkipTo("?>", include="True"))
		comment = (opener 
			+ Literal("!--")
			+ SkipTo("-->", include="True"))
		cdataSection = (opener 
			+ Literal("![CDATA[")
			+ SkipTo("]]>", include="True"))

		nonTagStuff = CharsNotIn("<", min=1)
	
		docItem = Forward()
		element = (
				(openingTag + ZeroOrMore(docItem) + closingTag)
			| emptyTag)
		docItem << (element
				| processingInstruction
				| comment
				| cdataSection
				| nonTagStuff)

		document = (ZeroOrMore(Optional(White()) + docItem) 
			+ Optional(White()) + StringEnd())
		document.parseWithTabs()
	
		element.addParseAction(manipulator._feedElement)
		tagOpener.addParseAction(manipulator._openElement)
		attribute.addParseAction(lambda s,p,t: [Attribute(t)])
		openingTag.addParseAction(_nodify)
		closingTag.addParseAction(_nodify)
		emptyTag.addParseAction(_nodify)

		del manipulator
		for el in locals().itervalues():
			# this *really* shouldn't be necessary
			el.leaveWhitespace()
		del el

		return locals()


def processXML(document, manipulator):
	"""processes an XML-document with manipulator.

	document is a string containing the XML, and the function returns 
	serialized an XML.  You're doing yourself a favour if document is
	a unicode string.

	manipulator is an instance of a derivation of Manipulator below.
	There's a secret handshake between Manipulator and the grammar, so
	you really need to inherit, just putting in the two methods won't do.
	"""
	syms = getXMLGrammar(manipulator)
#	from gavo.adql import grammar; grammar.enableDebug(syms)
	res = utils.pyparseString(syms["document"], document)
	return flatten(res)


class Manipulator(object):
	"""a base class for processXML manipulators.

	Pass instances of these into processXML.  You must up-call the
	constructor without arguments.

	Override the gotElement(parseResult) method to do what you want.  The
	parseResult is a pyparsing object with the tag name in second position of the
	first matched thing and the attributes barely parsed out (if you need them,
	improve the parsing to get at the attributes with less effort.)

	gotElement receives an entire element with opening tag, content, and
	closing tag (or just an empty tag).  To manipulate the thing, just
	return what you want in the document.

	There's also startElement(parsedOpener) that essentially works
	analogously; you will, however *not* receive startElements for
	empty elements, so that's really intended for bookkeeping.

	You also have a hasParent(tagName) method on Manipulators returning
	whether there's a tagName element somewhere among the ancestors
	of the current tag.
	"""
	def __init__(self):
		self.tagStack = []

	def _openElement(self, s, p, parsedOpener):
		# called by the grammar when an XML element is opened.
		self.tagStack.append(parsedOpener[1])
		return self.startElement(parsedOpener)

	def hasParent(self, name):
		return name in self.tagStack

	def _feedElement(self, s, p, parsedElement):
		# called by the grammar after an XML element has been closed
		self.tagStack.pop()
		parsedElement = Element(parsedElement)
		try:
			return [self.gotElement(parsedElement)]
		except:
			sys.stderr.write("Exception in gotElement:")
			import traceback; traceback.print_exc()

	def startElement(self, parsedOpener):
		return parsedOpener

	def gotElement(self, parsedElement):
		return parsedElement


class _ValuesChanger(Manipulator):
	"""a manipulator fiddling in values limits as returned by iterLimitsForTable.
	"""
	def __init__(self, limits):
		self.tableTriggers = {}
		self.curColumns = None
		for tableName, columnName, min, max in  limits:
			self.tableTriggers.setdefault(tableName, {})[
				columnName] = (min, max)
		Manipulator.__init__(self)

	def startElement(self, parsedTag):
		if parsedTag[1]=="table":
			try:
				tableName = getAttribute(parsedTag, "id").value
				self.curColumns = self.tableTriggers.get(tableName)
			except KeyError:
				pass
		return parsedTag
	
	def _fixValues(self, parsedElement, limits):
		values = parsedElement.findElement("values")
		for attName, val in zip (["min", "max"], limits):
			if val is not None:
				try:
					values.getAttribute(attName)[2] = utils.escapeAttrVal(str(val))
				except (AttributeError, KeyError):
					# user didn't put this limit into RD; let's assume for a reason
					pass

	def gotElement(self, parsedElement):
		if self.curColumns is not None:
			if parsedElement.name=="column":
				for attrName in ["name", "original"]:
					try:
						colName = parsedElement.getAttribute(attrName).value
						if colName in self.curColumns:
							self._fixValues(parsedElement, self.curColumns[colName])
					except KeyError:
						continue
					break

		if parsedElement.name=="table":
			self.curColumns = None  # tables don't nest in DaCHS
	
		return parsedElement


def iterLimitsForTable(tableDef):
	"""returns a list of values to fill in into tableDef.

	This will be empty if the table doesn't exist.  Otherwise, it will be
	a tuple (table-id, column-name, min, max) for every column with
	a reasonably numeric type that has a min and max values.
	"""
	info.annotateDBTable(tableDef, extended=False, requireValues=True)
	for col in tableDef:
		if col.annotations:
			min, max = col.annotations["min"], col.annotations["max"]
			yield (tableDef.id, col.name, min, max)


def iterLimitsForRD(rd):
	"""returns a list of values to fill in for an entire RD.

	See iterLimitsForTable.
	"""
	for td in rd.tables:
		if td.onDisk:
			try:
				for limits in iterLimitsForTable(td):
					yield limits
			except base.ReportableError, msg:
				base.ui.notifyError("Skipping %s: %s"%(td.id, utils.safe_str(msg)))


def getChangedRD(rdId, limits):
	"""returns a string corresponding to the RD with rdId with limits applied.

	Limits is a sequence of (table-id, column-name, min, max) tuples.
	We assume the values elements already exist.
	"""
	_, f = rscdesc.getRDInputStream(rdId)
	content = f.read()
	f.close()
	return processXML(content, _ValuesChanger(limits))


def parseCmdLine():
	from gavo.imp.argparse import ArgumentParser

	parser = ArgumentParser(
		description="Updates existing values min/max items in a referenced"
			" table or RD.")
	parser.add_argument("itemId", help="Cross-RD reference of a table or"
		" RD to update, as in ds/q or ds/q#mytable; only RDs in inputsDir"
		" can be updated.")
	return parser.parse_args()


def main():
	from gavo import api
	args = parseCmdLine()
	item = api.getReferencedElement(args.itemId)

	if isinstance(item, api.TableDef):
		changes = iterLimitsForTable(item)
		rd = item.rd

	elif isinstance(item, api.RD):
		changes = iterLimitsForRD(item)
		rd = item

	else:
		raise base.ReportableError(
			"%s references neither an RD nor a table definition"%args.itemId)
	
	newText = getChangedRD(rd.sourceId, changes)
	destFName = os.path.join(
		api.getConfig("inputsDir"), 
		rd.sourceId+".rd")
	with utils.safeReplaced(destFName) as f:
		f.write(newText)
