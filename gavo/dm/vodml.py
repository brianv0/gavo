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

	These are constructed with ElementTrees of the VO-DML defining the model.
	"""
	def __init__(self, dmlTree):
		self.dmlTree = dmlTree
		try:
			self._getModelMeta()
		except:
			raise base.ui.logOldExc(base.ReportableError("Bad data model XML",
				hint="Your log should say a bit more of why DaCHS did not"
				" like the VO-DML specification it was just asked to read."))
	
	def _getModelMeta(self):
		self.prefix = self.dmlTree.find("name").text
		self.title = self.dmlTree.find("title").text
		self.version = self.dmlTree.find("version").text


@utils.memoized
def getModelForPrefix(prefix):
	"""returns an elementtree for the VODML prefix.
	"""
	inF = openModelFile(prefix)
	try:
		return Model(ElementTree.parse(inF))
	finally:
		inF.close()
