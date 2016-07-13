"""
Management and representation of VO-DML models

In DaCHS, models are managed by their prefixes; there's a global registry
of those here (KNOWN_PREFIXES).

Unless validation is requested, models are just stubs, noting model name,
url, and version (and, of course, the canonical prefix).

When just processing VOTables or similar, it's fine to have models
not in the global registry; just construct model as usual.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

from gavo import base
from gavo.votable import V


class Model(object):
	"""A VO-DML model.
	"""
	def __init__(self, prefix, name, url, version):
		self.prefix, self.name, self.url, self.version =\
			prefix, name, url, version

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


KNOWN_PREFIXES = dict((m.prefix, m) for m in [
	# DaCHS test model
	Model("dachstoy", "DaCHS test data model", 
		"http://docs.g-vo.org/dachstoy/0.1", "0.1"),
	Model("vo-dml", "VO-DML metamodel",
		"http://www.ivoa.net/dm/vo-dml.xml", "1.0"),      # TODO: What's the URL?
])

def getKnownModel(prefix):
	if prefix not in KNOWN_PREFIXES:
		raise base.StructureError("Unknown data model prefix: %s"%prefix)
	return KNOWN_PREFIXES[prefix]
