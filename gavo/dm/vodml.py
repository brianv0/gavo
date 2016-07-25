"""
Parsing VO-DML files and validating against the rules obtained in this way.

Validation is something we expect to do only fairly rarely, so none of
this code is expected to be efficient.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

from gavo import base
from gavo import utils
from gavo.utils import ElementTree
from gavo.votable import V


KNOWN_MODELS = {
# maps the canonical prefix to the file name within resources/dm and
# (for now) the canonical URI (which isn't available anywhere else so far).
	"NDcube": ("CubeDM-1.0.vo-dml.xml", 
		"http://www.ivoa.net/dm/CubeDM-1.0.vo-dml.xml"),
	"ds": ("DatasetMetadata-1.0.vo-dml.xml",
		"http://www.ivoa.net/dm/DatasetMetadata-1.0.vo-dml.xml"),
	"ivoa": ("IVOA.vo-dml.xml", "http://www.ivoa.net/dm/ivoa.vo-dml.xml"),
	"vo-dml": ("VO-DML.vo-dml.xml", "http://www.ivoa.net/dm/VO-DML.vo-dml.xml"),
	"dachstoy": ("dachstoy.vo-dml.xml","http://docs.g-vo.org/dachstoy"),
}


def openModelFile(prefix):
	"""returns an open file for the VO-DML file corresponding to prefix.

	This will raise a NotFoundError for an unknown prefix.
	"""
	try:
		fName, _ = KNOWN_MODELS[prefix]
	except KeyError:
		raise base.NotFoundError(prefix, "VO-DML file for prefix",
			"data models known to DaCHS", hint="This can happen if there"
			" are new data models around or if data providers have defined"
			" custom data models.  If this error was fatal during VOTable"
			" processing, please report it as an error; bad data model"
			" annotation should not be fatal in DaCHS.")
	return base.openDistFile("dm/"+fName)


class Model(object):
	"""a vo-dml model.

	These are usually constructed using the fromPrefix constructor,
	which uses a built-in mapping from well-known prefix to VO-DML file
	to populate the model.
	"""

	# non-well-known models can be fed in through fromFile; they well
	# be entered here and can then be obtained through fromPrefix
	# as long as the don't clash with KNOWN_MODELS.

	_modelsReadFromFile = {}

	def __init__(self, prefix, dmlTree):
		self.prefix = prefix
		self.title = self.version = None
		self.version = self.url = None
		self.description = None
		self.dmlTree = dmlTree
		self.__idIndex = None
		if self.dmlTree:
			self._getModelMeta()

	@classmethod
	def fromPrefix(cls, prefix):
		"""returns a VO-DML model for a well-known prefix.

		User code should typically use the getModelFromPrefix function.
		"""
		if prefix in cls._modelsReadFromFile:
			return cls._modelsReadFromFile[prefix]

		inF = openModelFile(prefix)
		try:
			res = cls(prefix, ElementTree.parse(inF))
			# as long as we can't get the URL from the XML, patch it in here
			res.url = KNOWN_MODELS[prefix][1]
			return res
		finally:
			inF.close()

	@classmethod
	def fromFile(cls, src, srcURL="http //not.given/invalid"):
		"""returns a VO-DML model from src.

		src can either be a file name (interpreted relative to the root
		of DaCHS' VO-DML repository) or an open file (which will be closed
		as a side effect of this function).

		This is intended for documents using non-standard models with custom
		prefixes (i.e., not known to DaCHS).
		"""
		if hasattr(src, "read"):
			inF = src
		else:
			inF = openModelFile(src)

		try:
			tree = ElementTree.parse(inF)
			prefix = tree.find("name").text
			res = cls(prefix, tree)
			res.url = srcURL

			if prefix not in KNOWN_MODELS:
				cls._modelsReadFromFile[prefix] = res
			return res
		finally:
			inF.close()

	@property
	def idIndex(self):
		"""returns a dictionary mapping vodmlids to elementtree objects.
		"""
		if self.__idIndex is None:
			self.__idIndex = self._createIndex()
		return self.__idIndex
	
	def _createIndex(self):
		"""returns a dictionary mapping vodml-ids to elementtree objects.

		Use the idIndex property rather than this function, as the former will 
		cache the dicts.
		"""
		res = {}
		for element in self.dmlTree.getroot().iter():
			id = element.find("vodml-id")
			if id is not None:
				res[id.text] = element
		return res

	def _getModelMeta(self):
		"""sets some metadata on the model from the parsed VO-DML.

		This will fail silently (i.e., the metadata will remain on its
		default).

		Metadata obtained so far includes: title, version, description,
		"""
		try:
			self.title = self.dmlTree.find("title").text
			self.version = self.dmlTree.find("version").text
			self.description = self.dmlTree.find("description").text
		except AttributeError:
			# probably the VO-DML file is bad; just fall through to
			# non-validatable model.
			pass

	def _resolveNonLocalVODMLId(self, id):
		"""returns an etree Element pointed to by the VO-DML id 

		This is a helper for getByVODMLId and works by sucessively
		trying shorter pieces of id.

		This returns None on a failure rather than raising an exception
		(because it's really a helper for getByVODMLId).
		"""
		parts = id.split(".")
		for splitPoint in range(len(parts)-1, 0, -1):
			newId = ".".join(parts[:splitPoint])
			if newId in self.idIndex:
				# this should be an attribute definition.  Now follow
				# the chain of attribute names to the end
				att = self.idIndex[newId]
				thisType = resolveVODMLId(
					att.find("datatype").find("vodml-ref").text)

				for attName in parts[splitPoint:]:
					att = getAttributeDefinition(thisType, attName)
					thisType = resolveVODMLId(
						att.find("datatype").find("vodml-ref").text)
				return att
		# fall through on failure

	def getByVODMLId(self, vodmlId):
		"""returns the element with vodmlId.

		This raises a NotFoundError for elements that are not present.

		This can be used with or without the prefix.  The prefix is not
		validated, though.
		"""
		if ":" in vodmlId:
			vodmlId = vodmlId.split(":", 1)[1]

		# We may have to follow ids through several documents based on types.
		# First try to directly find the element.
		if vodmlId in self.idIndex:
			return self.idIndex[vodmlId]

		res = self._resolveNonLocalVODMLId(vodmlId)
		if res:
			return res
		else:
			raise base.NotFoundError(vodmlId, "data model element",
				self.prefix+" data model")

	def getAttributeMeta(self, vodmlId):
		"""returns a metadata dictionary for a VO-DML element with vodmlId.

		This includes datatype add description.  If vodmlId points to
		the value of a quantity, the associate unit and ucd attributes
		are returned as well.

		If the vodmlId cannot be found, a NotFoundError is raised.
		"""
		raise NotImplementedError("We've not yet figured out how this is"
			" supposed to work.")


	def getVOT(self, ctx):
		"""returns xmlstan for a VOTable declaration of this DM.
		"""
		return V.GROUP[
			V.VODML[V.TYPE["vo-dml:Model"]],
			V.PARAM(datatype="char", arraysize="*",name="name", value=self.prefix)[
				V.VODML[V.ROLE["name"]]],
			V.PARAM(datatype="char", arraysize="*", name="name", value=self.version)[
				V.VODML[V.ROLE["version"]]],
			V.PARAM(datatype="char", arraysize="*", name="name", value=self.url)[
				V.VODML[V.ROLE["url"]]]]


@utils.memoized
def getModelForPrefix(prefix):
	"""returns a vodml.Model instance for as well-known VODML prefix.

	This caches models for prefixes and thus should usually be used
	from user code.
	"""
	return Model.fromPrefix(prefix)


def getAttributeDefinition(typeDef, attName):
	"""returns the attribute definition for attName in typeDef as an etree.

	This raises a NotFoundError if the attribute is not found.
	"""
	for attribute in typeDef.findall("attribute"):
		if attribute.find("name").text==attName:
			return attribute
	raise base.NotFoundError(attName, "Attribute", 
		"VO-DML type "+typeDef.find("name").text)


def resolveVODMLId(vodmlId):
	"""returns an etree element corresponding to the prefixed vodmlId.

	Of course, this only works if vodmlId has a well-known prefix.
	"""
	prefix, id = vodmlId.split(":", 1)
	return getModelForPrefix(prefix).getByVODMLId(id)
