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

KNOWN_MODELS = {
# maps the canonical prefix to the file name within resources/dm
	"NDcube": "CubeDM-1.0.vo-dml.xml",
	"ivoa": "IVOA.vo-dml.xml",
	"dachstoy": "dachstoy.vo-dml.xml",
}


def openModelFile(prefix):
	"""returns an open file for the VO-DML file corresponding to prefix.

	This will raise a NotFoundError for an unknown prefix.
	"""
	try:
		fName = KNOWN_MODELS[prefix]
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
	def __init__(self, prefix, dmlTree):
		self.prefix = prefix
		self.title = self.version = None
		self.dmlTree = dmlTree
		if self.dmlTree:
			self._getModelMeta()

	@classmethod
	def fromPrefix(cls, prefix):
		"""returns a VO-DML model for a well-known prefix.

		User code should typically use the getModelFromPrefix function.
		"""
		inF = openModelFile(prefix)
		try:
			return cls(prefix, ElementTree.parse(inF))
		finally:
			inF.close()

	@classmethod
	def fromFile(cls, srcName):
		"""returns a VO-DML model from a file name.

		This is intended for documents using non-standard models with custom
		prefixes (i.e., not known to DaCHS).
		"""
		inF = openModelFile(srcName)
		try:
			tree = ElementTree.parse(inF)
			prefix = tree.find("name").text
			return cls(prefix, tree)
		finally:
			inF.close()

	def _getModelMeta(self):
		try:
			self.title = self.dmlTree.find("title").text
			self.version = self.dmlTree.find("version").text
		except AttributeError:
			# probably the VO-DML file is bad; just falll through to
			# non-validatable model.
			pass
	

@utils.memoized
def getModelForPrefix(prefix):
	"""returns a vodml.Model instance for as well-known VODML prefix.

	This caches models for prefixes and thus should usually be used
	from user code.
	"""
	return Model.fromPrefix(prefix)
