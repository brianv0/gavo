"""
Generation of system docs by introspection and combination with static
docs.
"""

import re
import sys
import textwrap
import traceback

import pkg_resources

from gavo import api
from gavo import base
from gavo import rscdesc


class RSTFragment(object):
	"""is a collection of convenience methods for generation of RST.
	"""
	def __init__(self, level1, level2):
		self.level1, self.level2 = level1, level2
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
		self.addHead(head, self.level1)

	def addHead2(self, head):
		self.addHead(head, self.level2)

	def delEmptySection(self):
		"""deletes something that looks like a headline if it's the last
		thing in our content list.
		"""
		try:
			# we suspect a headline if the last two contributions are a line
			# make up of on char type and an empty line.
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

	def addNormalizedPara(self, stuff):
		"""adds stuff to the document, making sure it's not glued to any
		previous material and removing whitespace as necessary for docstrings.
		"""
		self.makeSpace()
		self.content.append(base.fixIndentation(stuff, "", governingLine=2)+"\n")

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
	"""is a class encapsulating generation of documentation from structs.
	"""
	def __init__(self, docStructure, level1="'", level2="."):
		self.level1, self.level2 = level1, level2
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

	def _realAddDocsFrom(self, klass):
		if klass.name_ in self.docStructure:
			return
		self.visitedClasses.add(klass)
		content = RSTFragment(self.level1, self.level2)
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
			content.addULItem(att.makeUserDoc())
			if hasattr(att, "childFactory"):
				children.append(att.childFactory.name_)
				if att.childFactory not in self.visitedClasses:
					self.addDocsFrom(att.childFactory)
		self.docStructure.setdefault(klass.name_, []).extend(children)
		content.delEmptySection()
	
		content.addHead2("Other Children")
		for att in self._iterAttsNotOfBase(klass, 
				(base.AtomicAttribute, base.StructAttribute)):
			content.addULItem(att.makeUserDoc())
		content.delEmptySection()
		content.makeSpace()

		self.docParts.append((klass.name_, content.content))

	def addDocsFrom(self, klass):
		try:
			self._realAddDocsFrom(klass)
		except:
			sys.stderr.write("Cannot add docs from element %s\n"%klass.name_)
			traceback.print_exc()

	def getDocs(self):
		self.docParts.sort()
		resDoc = []
		for title, doc in self.docParts:
			resDoc.extend(doc)
		return resDoc

# XXX TODO: Check for macros.

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
	from gavo.rscdef import dddef
	return getStructDocsFromRegistry(dddef._grammarRegistry, docStructure)
		

def getCoreDocs(docStructure):
	from gavo.svcs import core
	return getStructDocsFromRegistry(core._coreRegistry, docStructure)


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
	print makeReferenceDocs()


if __name__=="__main__":
	print  getGrammarDocs(DocumentStructure())
