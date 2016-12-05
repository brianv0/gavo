"""
Generation of system docs by introspection and combination with static
docs.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import locale
import inspect
import re
import sys
import textwrap
import traceback

import pkg_resources

from gavo import base
from gavo import rscdef
from gavo import rscdesc
from gavo import utils
from gavo.base import structure
from gavo.user.common import Arg, exposedFunction, makeParser


def _indent(stuff, indent):
	return re.sub("(?m)^", indent, stuff)


def _decodeStrings(stringList):
	"""replaces all byte strings within stringList with unicode objects.

	Everything not already a unicode object is, for now, assumed to be
	iso-8859-1, since that is what code is encoded in when it's not ASCII.
	"""
	for ind, s in enumerate(stringList):
		if not isinstance(s, unicode):
			stringList[ind] = s.decode("iso-8859-1", "replace")
	

class RSTFragment(object):
	"""is a collection of convenience methods for generation of RST.
	"""
	level1Underliner = "'"
	level2Underliner = "."

	def __init__(self):
		self.content = []

	def makeSpace(self):
		"""adds an empty line unless the last line already is empty.
		"""
		if self.content and self.content[-1]!="\n":
			self.content.append("\n")

	def addHead(self, head, underliner):
		self.makeSpace()
		self.content.append(head+"\n")
		self.content.append(underliner*len(head)+"\n")
		self.content.append("\n")
	
	def addHead1(self, head):
		self.addHead(head, self.level1Underliner)

	def addHead2(self, head):
		self.addHead(head, self.level2Underliner)

	def delEmptySection(self):
		"""deletes something that looks like a headline if it's the last
		thing in our content list.
		"""
		try:
			# we suspect a headline if the last two contributions are a line
			# made up of on char type and an empty line.
			if self.content[-1]=="\n" and len(set(self.content[-2]))==2:
				self.content[-3:] = []
		except IndexError:  # not enough material to take something away
			pass

	def addULItem(self, content, bullet="*"):
		if content is None:
			return
		initialIndent = bullet+" "
		self.content.append(textwrap.fill(content, initial_indent=initialIndent,
			subsequent_indent=" "*len(initialIndent))+"\n")

	def addDLItem(self, term, definition):
		self.content.append("**%s**\n"%term)
		self.content.append(textwrap.fill(definition, 
			initial_indent="  ", subsequent_indent="  "))
		self.content.append("\n")

	def addDefinition(self, defHead, defBody):
		"""adds a definition list-style item .

		defBody is re-indented with two spaces, defHead is assumed to only
		contain a single line.
		"""
		self.content.append(defHead+"\n")
		self.content.append(utils.fixIndentation(defBody, "  ",
			governingLine=2)+"\n")

	def addNormalizedPara(self, stuff):
		"""adds stuff to the document, making sure it's not glued to any
		previous material and removing whitespace as necessary for docstrings.
		"""
		self.makeSpace()
		self.content.append(utils.fixIndentation(stuff, "", governingLine=2)+"\n")

	def addRaw(self, stuff):
		self.content.append(stuff)
	

class ParentPlaceholder(object):
	"""is a sentinel left in the proto documentation, to be replaced by
	docs on the element parents found while processing.
	"""
	def __init__(self, elementName):
		self.elementName = elementName


class DocumentStructure(dict):
	"""is a dict keeping track of what elements have been processed and
	which children they had.

	From this information, it can later fill out the ParentPlaceholders
	left in the proto reference doc.

	This also keeps track of what macros can be used where.
	"""
	def __init__(self):
		dict.__init__(self)
		self.knownMacros = KnownMacros()

	def _makeDoc(self, parents):
		return "May occur in %s.\n"%", ".join("`Element %s`_"%name
			for name in parents)

	def fillOut(self, protoDoc):
		parentDict = {}
		for parent, children in self.iteritems():
			for child in children:
				parentDict.setdefault(child, []).append(parent)

		for index, item in enumerate(protoDoc):
			if isinstance(item, ParentPlaceholder):
				if item.elementName in parentDict:
					protoDoc[index] = self._makeDoc(parentDict[item.elementName])
				else:
					protoDoc[index] = ""


def getDocName(klass):
	return getattr(klass, "docName_", klass.name_)


class StructDocMaker(object):
	"""A class encapsulating generation of documentation from structs.
	"""

	def __init__(self, docStructure):
		self.docParts = []
		self.docStructure = docStructure
		self.visitedClasses = set()

	def _iterMatchingAtts(self, klass, condition):
		for att in sorted((a for a in klass.attrSeq 
					if condition(a)),
				key=lambda att: att.name_):
			yield att

	def _iterAttsOfBase(self, klass, base):
		return self._iterMatchingAtts(klass, lambda a: isinstance(a, base))
	
	def _iterAttsNotOfBase(self, klass, base):
		return self._iterMatchingAtts(klass, lambda a: not isinstance(a, base))

	_noDefaultValues = set([base.Undefined, base.Computed])
	def _hasDefault(self, att):
		try:
			return att.default_ not in self._noDefaultValues
		except TypeError: # unhashable default is a default
			return True

	def _addMacroDocs(self, klass, content, docStructure):
		if not issubclass(klass, base.MacroPackage):
			return

		macNames = []
		for attName in dir(klass):
			if attName.startswith("macro_"):
				name = attName[6:]
				docStructure.knownMacros.addMacro(name, 
					getattr(klass, attName), klass)
				macNames.append(name)

		content.addNormalizedPara("Macros predefined here: "+", ".join(
			"`Macro %s`_"%name for name in sorted(macNames)))
		content.makeSpace()

	def _realAddDocsFrom(self, klass, docStructure):
		name = getDocName(klass)
		if name in self.docStructure:
			return
		self.visitedClasses.add(klass)
		content = RSTFragment()
		content.addHead1("Element %s"%name)
		if klass.__doc__:
			content.addNormalizedPara(klass.__doc__)
		else:
			content.addNormalizedPara("NOT DOCUMENTED")

		content.addRaw(ParentPlaceholder(name))

		content.addHead2("Atomic Children")
		for att in self._iterAttsOfBase(klass, base.AtomicAttribute):
			content.addULItem(att.makeUserDoc())
		content.delEmptySection()
	
		children = []
		content.addHead2("Structure Children")
		for att in self._iterAttsOfBase(klass, base.StructAttribute):
			try:
				content.addULItem(att.makeUserDoc())
				if isinstance(getattr(att, "childFactory", None), structure.StructType):
					children.append(getDocName(att.childFactory))
					if att.childFactory not in self.visitedClasses:
						self.addDocsFrom(att.childFactory, docStructure)
			except:
				sys.stderr.write("While gendoccing %s in %s:\n"%(
					att.name_, name))
				traceback.print_exc()
		self.docStructure.setdefault(name, []).extend(children)
		content.delEmptySection()
	
		content.addHead2("Other Children")
		for att in self._iterAttsNotOfBase(klass, 
				(base.AtomicAttribute, base.StructAttribute)):
			content.addULItem(att.makeUserDoc())
		content.delEmptySection()
		content.makeSpace()

		self._addMacroDocs(klass, content, docStructure)

		self.docParts.append((klass.name_, content.content))

	def addDocsFrom(self, klass, docStructure):
		try:
			self._realAddDocsFrom(klass, docStructure)
		except:
			sys.stderr.write("Cannot add docs from element %s\n"%klass.name_)
			traceback.print_exc()

	def getDocs(self):
		self.docParts.sort(key=lambda t: t[0].upper())
		resDoc = []
		for title, doc in self.docParts:
			resDoc.extend(doc)
		return resDoc


class MacroDoc(object):
	"""documentation for a macro, including the objects that know about
	it.
	"""
	def __init__(self, name, macFunc, foundIn):
		self.name = name
		self.macFunc = macFunc
		self.inObjects = [foundIn]

	def addObject(self, macFunc, obj):
		"""declares that macFunc is also available on the python object obj.

		If also checks implements the "see <whatever>" mechanism described
		in KnownMacros.
		"""
		self.inObjects.append(obj)
		if (self.macFunc.func_doc or "").startswith("see "):
			self.macFunc = macFunc

	def makeDoc(self, content):
		"""adds documentation of macFunc to the RSTFragment content.
		"""
		# macros have args in {}, of course there's no self, and null-arg
		# macros have not {}...
		args, varargs, varkw, defaults = inspect.getargspec(self.macFunc)
		args = inspect.formatargspec(args[1:], varargs, varkw, defaults
			).replace("(", "{").replace(")", "}").replace("{}", ""
			).replace(", ", "}{")
		content.addRaw("::\n\n  \\%s%s\n\n"%(self.name, args))
		content.addRaw(utils.fixIndentation(
			self.macFunc.func_doc or "undocumented", "", 1).replace("\\", "\\\\"))
		content.addNormalizedPara("Available in "+", ".join(
				sorted(
					"`Element %s`_"%c.name_ for c in self.inObjects)))


class KnownMacros(object):
	"""An accumulator for all macros known to the various DaCHS objects.

	Note that macros with identical names are supposed to do essentially
	the same things.  In particular, they must all have the same signature
	or the documentation will be wrong.

	When macros share names, all but one implementation should have
	a docstring just saying "see <whatever>"; that way, the docstring
	actually chosen is deterministic.
	"""
	def __init__(self):
		self.macros = {}
	
	def addMacro(self, name, macFunc, foundIn):
		"""registers macFunc as expanding name in the element foundIn.

		macFunc is the method, foundIn is the python class it's defined on.
		"""
		if name in self.macros:
			self.macros[name].addObject(macFunc, foundIn)
		else:
			self.macros[name] = MacroDoc(name, macFunc, foundIn)

	def getDocs(self):
		"""returns RST lines describing all macros fed in in addMacro.
		"""
		content = RSTFragment()
		for macName in sorted(self.macros):
			content.addHead1("Macro %s"%macName)
			self.macros[macName].makeDoc(content)
			content.makeSpace()
		return content.content


def formatKnownMacros(docStructure):
	return docStructure.knownMacros.getDocs()


def getStructDocs(docStructure):
	dm = StructDocMaker(docStructure)
	dm.addDocsFrom(rscdesc.RD, docStructure)
	return dm.getDocs()


def getStructDocsFromRegistry(registry, docStructure):
	dm = StructDocMaker(docStructure)
	for name, struct in sorted(registry.items()):
		dm.addDocsFrom(struct, docStructure)
	return dm.getDocs()


def getGrammarDocs(docStructure):
	registry = dict((n, rscdef.getGrammar(n)) for n in rscdef.GRAMMAR_REGISTRY)
	return getStructDocsFromRegistry(registry, docStructure)
		

def getCoreDocs(docStructure):
	from gavo.svcs import core
	registry = dict((n, core.getCore(n)) for n in core.CORE_REGISTRY)
	return getStructDocsFromRegistry(registry, docStructure)


def getActiveTagDocs(docStructure):
	from gavo.base import activetags
	return getStructDocsFromRegistry(activetags.getActiveTag.registry,
		docStructure)


def getRendererDocs(docStructure):
	from gavo.svcs import RENDERER_REGISTRY, getRenderer
	content = RSTFragment()
	for rendName in sorted(RENDERER_REGISTRY):
		rend = getRenderer(rendName)
		if rend.__doc__:
			content.addHead1("The %s Renderer"%rendName)
			metaStuff = "*This renderer's parameter style is \"%s\"."%(
				rend.parameterStyle)
			if not rend.checkedRenderer:
				metaStuff += "  This is an unchecked renderer."
			content.addNormalizedPara(metaStuff+"*")
			content.addNormalizedPara(rend.__doc__)
	return content.content


def getTriggerDocs(docStructure):
	from gavo.rscdef import rowtriggers
	return getStructDocsFromRegistry(rowtriggers._triggerRegistry, docStructure)


def _documentParameters(content, pars):
	content.makeSpace()
	for par in sorted(pars, key=lambda p: p.key):
		if par.late:
			doc = ["Late p"]
		else:
			doc = ["P"]
		doc.append("arameter *%s*\n"%par.key)
		if par.content_:
			doc.append("  defaults to ``%s``;\n"%par.content_)
		if par.description:
			doc.append(utils.fixIndentation(par.description, "  "))
		else:
			doc.append("   UNDOCUMENTED")
		content.addRaw(''.join(doc)+"\n")
	content.makeSpace()


def getMixinDocs(docStructure, mixinIds):
	content = RSTFragment()
	for name in sorted(mixinIds):
		mixin = base.resolveId(None, name)
		content.addHead1("The %s Mixin"%name)
		if mixin.doc is None:
			content.addNormalizedPara("NOT DOCUMENTED")
		else:
			content.addNormalizedPara(mixin.doc)
		if mixin.pars:
			content.addNormalizedPara(
				"This mixin has the following parameters:\n")
			_documentParameters(content, mixin.pars)
	return content.content


def _getModuleFunctionDocs(module):
	"""returns documentation for all functions marked with @document in the
	namespace module.
	"""
	res = []
	for name in dir(module):
		if name.startswith("_"):
			# ignore all private attributes, whatever else happens
			continue

		ob = getattr(module, name)
		if hasattr(ob, "buildDocsForThis"):
			if ob.func_doc is None:  # silently ignore if no docstring
				continue
			res.append(
				"*%s%s*"%(name, inspect.formatargspec(*inspect.getargspec(ob))))
			res.append(utils.fixIndentation(ob.func_doc, "  ", 1))
			res.append("")
	return "\n".join(res)


def getRmkFuncs(docStructure):
	from gavo.rscdef import rmkfuncs
	return _getModuleFunctionDocs(rmkfuncs)


def getRegtestAssertions(docStructure):
	from gavo.rscdef import regtest
	return _getModuleFunctionDocs(regtest.RegTest)


def _getProcdefDocs(procDefs):
	"""returns documentation for the ProcDefs in the sequence procDefs.
	"""
	content = RSTFragment()
	for id, pd in procDefs:
		content.addHead2(id)
		if pd.doc is None:
			content.addNormalizedPara("NOT DOCUMENTED")
		else:
			content.addNormalizedPara(pd.doc)
		content.makeSpace()
		if pd.getSetupPars():
			content.addNormalizedPara("Setup parameters for the procedure are:\n")
			_documentParameters(content, pd.getSetupPars())
	return content.content


def _makeProcsDocumenter(idList):
	def buildDocs(docStructure):
		return _getProcdefDocs([(id, base.resolveId(None, id))
			for id in sorted(idList)])
	return buildDocs


def _makeTableDoc(tableDef):
	content = RSTFragment()
	content.addHead1(tableDef.getQName())
	content.addNormalizedPara("Defined in %s"%
		tableDef.rd.sourceId.replace("__system__", "/"))
	content.addNormalizedPara(base.getMetaText(tableDef, 
		"description", default="UNDOCUMENTED"))
	content.makeSpace()
	for col in tableDef:
		content.addDLItem(col.name,
			"(%s) -- %s"%(col.type, col.description))
	content.makeSpace()
	return "".join(content.content)


def makeSystemTablesList(docStructure):
	parts = []
	for rdName in pkg_resources.resource_listdir(
			"gavo", "resources/inputs/__system__"):
		if not rdName.endswith(".rd"):
			continue

		try:
			for tableDef in base.caches.getRD("//"+rdName).tables:
				if tableDef.onDisk:
					parts.append((tableDef.getQName(), _makeTableDoc(tableDef)))
		except base.Error:
			base.ui.notifyError("Bad system RD: %s"%rdName)
	
	return "\n".join(content for _, content in sorted(parts))


def getStreamsDoc(idList):
	content = RSTFragment()
	for id in idList:
		stream = base.resolveId(None, id)
		content.addHead2(id)
		if stream.doc is None:
			raise base.ReportableError("Stream %s has no doc -- don't include in"
				" reference documentation."%id)
		content.addNormalizedPara(stream.doc)
		content.makeSpace()

		if stream.DEFAULTS and stream.DEFAULTS.defaults:
			content.addNormalizedPara("*Defaults* for macros used in this stream:")
			content.makeSpace()
			for key, value in sorted(stream.DEFAULTS.defaults.iteritems()):
				content.addULItem("%s: '%s'"%(key, value))
			content.makeSpace()

	return content.content


def getMetaKeyDocs():
	from gavo.base import meta
	content = RSTFragment()
	d = meta.META_CLASSES_FOR_KEYS
	for metaKey in sorted(d):
		content.addDefinition(metaKey,
			d[metaKey].__doc__ or "NOT DOCUMENTED")
	return content.content


_replaceWithResultPat = re.compile(".. replaceWithResult (.*)")

def makeReferenceDocs():
	"""returns a restructured text containing the reference documentation
	built from the template in refdoc.rstx.

	**WARNING**: refdoc.rstx can execute arbitrary code right now.  We
	probably want to change this to having macros here.
	"""
	res, docStructure = [], DocumentStructure()
	f = pkg_resources.resource_stream("gavo", 
		"resources/templates/refdoc.rstx")
	
	parseState = "content"
	code = []

	for lnCount, ln in enumerate(f):
		if parseState=="content":
			mat = _replaceWithResultPat.match(ln)
			if mat:
				code.append(mat.group(1))
				parseState = "code"
			else:
				res.append(ln.decode("utf-8"))
		
		elif parseState=="code":
			if ln.strip():
				code.append(ln)
			else:
				try:
					res.extend(eval(" ".join(code)))
				except Exception:
					sys.stderr.write("Invalid code near line %s: '%s'\n"%(
						lnCount, " ".join(code)))
					raise
				code = []
				parseState = "content"
				res.append("\n")

		else:
			# unknown state
			assert False

	f.close()
	docStructure.fillOut(res)
	_decodeStrings(res)
	return "".join(res)



@exposedFunction([], help="Writes ReStructuredText for the reference"
	" documentation to stdout")
def refdoc(args):
	print makeReferenceDocs(
		).replace("\t", "  "
		).encode("utf-8")


@exposedFunction([Arg(help="Input file name", dest="src")],
	help="Turns ReStructured text (with DaCHS extensions) to LaTeX source")
def latex(args):
	from docutils import core
	locale.setlocale(locale.LC_ALL, '')
	sys.argv[1:] = (
		"--documentoptions=11pt,a4paper --stylesheet stylesheet.tex"
		" --use-latex-citations").split()
	sys.argv.append(args.src)

	core.publish_cmdline(writer_name='latex', description="(DaCHS rst2latex)")
	

@exposedFunction([Arg(help="Input file name", dest="src")],
	help="Turns ReStructured text (with DaCHS extensions) to HTML")
def html(args):
	from  docutils import core
	locale.setlocale(locale.LC_ALL, '')
	# TODO: actually determine template path
	sys.argv[1:] = ("--template rst2html-template.txt --stylesheet ref.css"
		" --link-stylesheet").split()
	sys.argv.append(args.src)
	core.publish_cmdline(writer_name='html', description="(DaCHS rst2html)")


def main():
	args = makeParser(globals()).parse_args()
	args.subAction(args)

if __name__=="__main__":
	docStructure = DocumentStructure()
	print getRendererDocs(docStructure)
