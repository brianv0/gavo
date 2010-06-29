"""
xmlstan elements of VOTable.
"""

import re

from gavo import utils
from gavo.utils import ElementTree
from gavo.utils.stanxml import Element


VOTableNamespace = "http://www.ivoa.net/xml/VOTable/v1.2"


class VOTable(object):
	"""The container for VOTable elements.
	"""
	class _VOTElement(Element):
		namespace = VOTableNamespace
		local = True

	class _DescribedElement(_VOTElement):
		a_ID = None
		a_ref = None
		a_name = None
		a_ucd = None
		a_utype = None
		mayBeEmpty = True

		def getDesignation(self):
			"""returns something to "call" this element.

			This is a name, if possible, else the id.  Weird characters are
			replaced, so the result should be safe to embed in code.
			"""
			name = self.a_name
			if name is None:
				name = self.a_ID
			if name is None:
				name = "UNIDENTIFIED"

		def getDesignation(self):
			"""returns some name-like thing for a FIELD or PARAM.
			"""
			if self.a_name:
				res = self.a_name
			elif self.a_ID:
				res = self.a_ID
			else:
				res = "%s_%s"%(self.__class__.__name__, "%x"%id(self))
			return res.encode("ascii", "ignore")



	class _ValuedElement(_DescribedElement):
		a_unit = None
		a_xtype = None

	class _TypedElement(_ValuedElement):
		a_ref = None
		a_arraysize = None
		a_datatype = None
		a_precision = None
		a_ref = None
		a_type = None
		a_width = None

		def isScalar(self):
			return self.a_arraysize is None or self.a_arraysize=='1'

		def hasVarLength(self):
			return self.a_arraysize and self.a_arraysize.endswith("*")

		def getLength(self):
			"""returns the number of items one should expect in value, or
			None for variable-length arrays.
			"""
			if self.a_arraysize is None:
				return 1
			if self.a_arraysize.endswith("*"):
				return None
			elif "x" in self.a_arraysize: # multidimensional, my ass.
				return reduce(lambda a, b: a*b, map(int, self.a_arraysize.split("x")))
			else:
				return int(self.a_arraysize)

		def getShape(self):
			"""returns a numpy-compatible shape.
			"""
			if self.a_arraysize is None:
				return None
			if self.a_datatype=="char" and not "x" in self.a_arraysize:
				# special case: 1d char arrays are just scalar strings
				return None
			if self.a_arraysize=="*":
				return None  # What should we really return here?
			val = self.a_arraysize.replace("*", "")
			if "x" in val:
				if val.endswith("x"):  # variable last dimension
					val = val+'1'
				tuple(int(d) for d in val.split("x"))
			else:
				return (int(val),)

	class _RefElement(_ValuedElement):
		a_ref = None
		a_ucd = None
		a_utype = None
		childSequence = []

	class _ContentElement(_VOTElement):
		"""An element containing tabular data.

		These are usually serialized using some kind of streaming.

		See votable.tablewriter for details.
		"""
		def write(self, file):
			raise NotImplementedError("This _ContentElement cannot write yet")


	class BINARY(_ContentElement):
		childSequence = ["STREAM"]
		encoding = "base64"
		
		def write(self, file):
			# To be able to write incrementally, encode chunks of multiples
			# of 57 bytes until the stream is finished.
			blockSize = 57
			buf, bufFil, flushThreshold = [], 0, blockSize*20
			file.write('<BINARY>')
			file.write('<STREAM encoding="base64">')
			for data in self.iterSerialized():
				buf.append(data)
				bufFil + len(data)
				if bufFil>flushThreshold:
					curData = ''.join(buf)
					curBlockLen = (len(curData)//blockSize)*blockSize
					file.write(toOutput[:curBlockLen].encode("base64"))
					buf = [curData[curBlockLen:]]
			file.write("".join(buf).encode("base64"))
			file.write("</STREAM>")
			file.write('</BINARY>')


	class COOSYS(_VOTElement):
		a_ID = None
		a_epoch = None
		a_equinox = None
		a_system = None

	class DATA(_VOTElement):
		childSequence = ["INFO", "TABLEDATA", "BINARY", "FITS"]
	
	class DEFINITIONS(_VOTElement):
		pass

	class DESCRIPTION(_VOTElement):
		childSequence = [None]

	class FIELD(_TypedElement):
		childSequence = ["DESCRIPTION", "VALUES", "LINK"]

	class FIELDref(_RefElement): pass
	
	class FITS(_VOTElement):
		childSequence = ["STREAM"]
	
	class GROUP(_DescribedElement):
		a_ref = None
		childSequence = ["DESCRIPTION", "PARAM", "FIELDref", "PARAMref", "GROUP"]


	class INFO(_ValuedElement):
		a_ref = None
		a_value = None
		childSequence = [None]

		def isEmpty(self):
			return self.a_value is None

	
	class LINK(_VOTElement):
		a_ID = None
		a_action = None
		a_content_role = None
		content_role_name = "content-role"
		a_content_type = None
		content_type_name = "content-type"
		a_gref = None
		a_href = None
		a_title = None
		a_value = None
		childSequence = []
		mayBeEmpty = True


	class MAX(_VOTElement):
		a_inclusive = None
		a_value = None
		childSequence = []
		mayBeEmpty = True


	class MIN(_VOTElement):
		a_inclusive = None
		a_value = None
		childSequence = []
		mayBeEmpty = True


	class OPTION(_VOTElement):
		a_name = None
		a_value = None
		childSequence = ["OPTION"]
		mayBeEmpty = True


	class PARAM(_TypedElement):
		a_value = None
		childSequence = ["DESCRIPTION", "VALUES", "LINK"]


	class PARAMref(_RefElement): pass


	class RESOURCE(_VOTElement):
		a_ID = None
		a_name = None
		a_type = None
		a_utype = None
		childSequence = ["DESCRIPTION", "DEFINITIONS", "COOSYS", "INFO", "GROUP", 
			"PARAM", "LINK", "TABLE", "RESOURCE"]


	class STREAM(_VOTElement):
		a_actuate = None
		a_encoding = None
		a_expires = None
		a_href = None
		a_rights = None
		a_type = None
		childSequence = [None]


	class TABLE(_DescribedElement):
		"""A TABLE element.

		If you want to access fields by name (getFIELDForName), make sure
		name and ids are unique.
		"""
		a_nrows = None
		childSequence = ["DESCRIPTION", "INFO", "GROUP", "FIELD", "PARAM", "LINK",
			"DATA"]

		_fieldIndex = None

		@utils.memoized
		def getFields(self):
			return list(self.iterChildrenOfType(VOTable.FIELD))

		def _getFieldIndex(self):
			if self._fieldIndex is None:
				index = {}
				for child in self.getFields():
					if child.a_name:
						index[child.a_name] = child
					if child.a_ID:
						index[child.a_ID] = child
				self._fieldIndex = index
			return self._fieldIndex

		def getFIELDForName(self, name):
			"""returns the FIELD having a name or id of name.

			A KeyError is raised when the field does not exist; if names are
			not unique, the last column with the name specified is returned.
			"""
			return self._getFieldIndex()["name"]


	class TABLEDATA(_ContentElement):
		childSequence = ["TR"]
		encoding = "utf-8"

		def write(self, file):
			file.write("<TABLEDATA>")
			enc = self.encoding
			for row in self.iterSerialized():
				file.write(row.encode(enc))
			file.write("</TABLEDATA>")
		

	class TD(_VOTElement):
		a_encoding = None
		childSequence = [None]
		mayBeEmpty = True


	class TR(_VOTElement):
		a_ID = None
		childSequence = ["TD"]


	class VALUES(_VOTElement):
		a_ID = None
		a_null = None
		a_ref = None
		a_type = None


	class VOTABLE(_VOTElement):
		a_ID = None
		a_version = "1.2"
		a_xmlns = VOTableNamespace


	class VOTABLE11(_VOTElement):
# An incredibly nasty hack that kinda works due to the fact that
# all elements here are local -- make this your top-level element
# and only use what's legal in VOTable 1.1, and you get a VOTable1.1
# conforming document
		name = "VOTABLE"
		a_ID = None
		a_version = "1.1"
		a_xmlns = "http://www.ivoa.net/xml/VOTable/v1.1"


def voTag(tagName):
	"""returns the VOTable QName for tagName.

	You only need this if you want to search in ElementTrees.
	"""
	return ElementTree.QName(VOTableNamespace, tagName)
