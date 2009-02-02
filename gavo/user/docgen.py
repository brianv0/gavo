"""
Generation of system docs by introspection and combination with static
docs.
"""

import textwrap

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
		if self.content and self.content[-1]!="":
			self.content.append("")

	def addHead(self, head, underliner):
		self.makeSpace()
		self.content.append(head)
		self.content.append(underliner*len(head))
		self.content.append("")
	
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
			if self.content[-1]=="" and len(set(self.content[-2]))==1:
				self.content[-3:] = []
		except IndexError:  # not enough material to take something away
			pass

	def addULItem(self, content, bullet="*"):
		initialIndent = bullet+" "
		self.content.append(textwrap.fill(content, initial_indent=initialIndent,
			subsequent_indent=" "*len(initialIndent)))

	def addNormalizedPara(self, stuff):
		"""adds stuff to the document, making sure it's not glued to any
		previous material and removing whitespace as necessary for docstrings.
		"""
		self.makeSpace()
		self.content.append(base.fixIndentation(stuff, "", governingLine=1))

	def addRaw(self, stuff):
		self.content.append(stuff)
	
	def getRST(self):
		return "\n".join(self.content)


class StructDocMaker(object):
	"""is a class encapsulating generation of documentation from structs.
	"""
	def __init__(self, level1="'", level2="."):
		self.level1, self.level2 = level1, level2
		self.docParts = []
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

	def addDocsFrom(self, klass):
		self.visitedClasses.add(klass)
		content = RSTFragment(self.level1, self.level2)
		content.addHead1("Element %s"%klass.name_)
		if klass.__doc__:
			content.addNormalizedPara(klass.__doc__)
		else:
			content.addNormalizedPara("NOT DOCUMENTED")

		content.addHead2("Atomic Children")
		for att in self._iterAttsOfBase(klass, base.AtomicAttribute):
			if att.name_!="id":
				content.addULItem(att.makeUserDoc())
		content.delEmptySection()
		
		content.addHead2("Structure Children")
		for att in self._iterAttsOfBase(klass, base.StructAttribute):
			if not hasattr(att, "childFactory"):
				content.addULItem("Polymorphous attribute %s; see separate"
					" description."%att.name_)
			else:
				content.addULItem("%s (contains `Element %s`_) -- %s"%(
					att.name_, att.childFactory.name_, att.description_))
				if att.childFactory not in self.visitedClasses:
					self.addDocsFrom(att.childFactory)
		content.delEmptySection()
	
		content.addHead2("Other Children")
		for att in self._iterAttsNotOfBase(klass, 
				(base.AtomicAttribute, base.StructAttribute)):
			content.addULItem(att.makeUserDoc())
		content.delEmptySection()
		content.makeSpace()

		self.docParts.append((klass.name_, content.getRST()))

	def getDocs(self):
		self.docParts.sort()
		return "\n".join(doc for title, doc in self.docParts)


def getStructDocs():
	dm = StructDocMaker()
	dm.addDocsFrom(rscdesc.RD)
	return dm.getDocs()


if __name__=="__main__":
	print getStructDocs()
