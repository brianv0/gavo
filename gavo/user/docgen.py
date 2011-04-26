"""
Generation of system docs by introspection and combination with static
docs.
"""

import inspect
import re
import sys
import textwrap
import traceback

import pkg_resources

from gavo import api
from gavo import base
from gavo import rscdef
from gavo import rscdesc
from gavo import utils
from gavo.base import structure


PUBLIC_MIXINS = ["//products#table", "//scs#positions", "//scs#q3cindex",
	"//siap#bbox", "//siap#pgs", "//ssap#hcd", "//obscore#publish",
	"//obscore#publishSIAP"]

PUBLIC_APPLYS = ["//procs#simpleSelect", "//procs#resolveObject",
	"//procs#mapValue", "//procs#fullQuery", "//siap#computePGS",
	"//siap#computeBbox", "//siap#setMeta", "//ssap#setMeta",
	"//siap#getBandFromFilter"]

PUBLIC_ROWFILTERS = ["//procs#expandComma", "//procs#expandDates",
	"//products#define", "//procs#expandIntegers"]


def _indent(stuff, indent):
	return re.sub("(?m)^", indent, stuff)


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
	"""
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

	def _addMacroDocs(self, klass, content):
		if not issubclass(klass, base.MacroPackage):
			return
		macs = []
		for name in dir(klass):
			if name.startswith("macro_"):
				macs.append((name, getattr(klass, name)))
		content.addHead2("Macros defined on %s"%klass.__name__)
		for name, mac in sorted(macs):
			makeMacroDoc(name[6:], mac, content)
		content.delEmptySection()
		content.makeSpace()

	def _realAddDocsFrom(self, klass):
		if klass.name_ in self.docStructure:
			return
		self.visitedClasses.add(klass)
		content = RSTFragment()
		content.addHead1("Element %s"%klass.name_)
		if klass.__doc__:
			content.addNormalizedPara(klass.__doc__)
		else:
			content.addNormalizedPara("NOT DOCUMENTED")

		content.addRaw(ParentPlaceholder(klass.name_))

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
					children.append(att.childFactory.name_)
					if att.childFactory not in self.visitedClasses:
						self.addDocsFrom(att.childFactory)
			except:
				sys.stderr.write("While gendoccing %s in %s:\n"%(
					att.name_, klass.name_))
				traceback.print_exc()
		self.docStructure.setdefault(klass.name_, []).extend(children)
		content.delEmptySection()
	
		content.addHead2("Other Children")
		for att in self._iterAttsNotOfBase(klass, 
				(base.AtomicAttribute, base.StructAttribute)):
			content.addULItem(att.makeUserDoc())
		content.delEmptySection()
		content.makeSpace()

		self._addMacroDocs(klass, content)

		self.docParts.append((klass.name_, content.content))

	def addDocsFrom(self, klass):
		try:
			self._realAddDocsFrom(klass)
		except:
			sys.stderr.write("Cannot add docs from element %s\n"%klass.name_)
			traceback.print_exc()

	def getDocs(self):
		self.docParts.sort(key=lambda t: t[0].upper())
		resDoc = []
		for title, doc in self.docParts:
			resDoc.extend(doc)
		return resDoc


def makeMacroDoc(name, macFunc, content):
	# macros have args in {}, of course there's no self, and null-arg
	# macros have not {}...
	args, varargs, varkw, defaults = inspect.getargspec(macFunc)
	args = inspect.formatargspec(args[1:], varargs, varkw, defaults
		).replace("(", "{").replace(")", "}").replace("{}", ""
		).replace(", ", "}{")
	content.addRaw("*\\%s%s*\n"%(name, args))
	content.addRaw(utils.fixIndentation(
		macFunc.func_doc or "undocumented", "  ", 1)+"\n")


def getStructDocs(docStructure):
	dm = StructDocMaker(docStructure)
	dm.addDocsFrom(rscdesc.RD)
	return dm.getDocs()


def getStructDocsFromRegistry(registry, docStructure):
	dm = StructDocMaker(docStructure)
	for name, struct in sorted(registry.items()):
		dm.addDocsFrom(struct)
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
	res = []
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
	for par in pars:
		doc = ["* "]
		if par.late:
			doc.append("Late p")
		else:
			doc.append("P")
		doc.append("arameter %s "%par.name)
		if par.content_:
			doc.append("defaults to ``%s``"%par.content_)
		if par.description:
			doc.append(" -- "+par.description)
		content.addRaw(''.join(doc)+"\n")
	content.makeSpace()


def getMixinDocs(docStructure):
	content = RSTFragment()
	for name in sorted(PUBLIC_MIXINS):
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


makeRmkProcDocs = _makeProcsDocumenter(PUBLIC_APPLYS)
makeRowfilterDocs = _makeProcsDocumenter(PUBLIC_ROWFILTERS)



def getMetaTypeDocs():
	from gavo.base import meta
	content = RSTFragment()
	d = meta._metaTypeRegistry
	for typeName in sorted(d):
		content.addDefinition(typeName,
			d[typeName].__doc__ or "NOT DOCUMENTED")
	return content.content


def getMetaTypedNames():
	from gavo.base import meta
	content = RSTFragment()
	d = meta._typesForKeys
	for metaKey in sorted(d):
		content.addDefinition(metaKey, d[metaKey])
	return content.content


_replaceWithResultPat = re.compile(".. replaceWithResult (.*)")

def makeReferenceDocs():
	"""returns a restructured text containing the reference documentation
	built from the template in refdoc.rstx.

	**WARNING**: refdoc.rstx can execute arbitrary code right now.  We
	probably want to change this to having macros here.
	"""
	res, docStructure = [], DocumentStructure()
	f = pkg_resources.resource_stream("gavo", "resources/templates/refdoc.rstx")
	for ln in f:
		mat = _replaceWithResultPat.match(ln)
		if mat:
			res.extend(eval(mat.group(1)))
			res.append("\n")
		else:
			res.append(ln)
	f.close()
	docStructure.fillOut(res)
	return "".join(res)


def main():
	print makeReferenceDocs().replace("\\", "\\\\")


if __name__=="__main__":
	docStructure = DocumentStructure()
	print getRendererDocs(docStructure)
