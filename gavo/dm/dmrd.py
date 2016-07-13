"""
Writing annotations in RDs.

This module provides the glue between annotations (typically in SIL)
and the rest of the RDs.  It provides the ResAnnotation struct, which
contains the SIL, and the makeAttributeAnnotation function at is a factory
for attribute annotations.
"""

import functools

from gavo import base
from gavo.dm import common
from gavo.dm import sil


class DataModelRoles(base.Structure):
	"""an annotation of a table in terms of data models.

	The content of this element is a Simple Instance Language term.
	"""

# We defer the parsing of the contained element to (hopefully) the
# end of the parsing of the RD to enable forward references with
# too many headaches (stubs don't cut it: we need to know types).
# 
# There's an additional complication in that we may want to 
# access parsed annotations while parsing other annotations
# (e.g., when processing foreign keys).
# To allow the thing to "parse itself" in such situations, we do
# all the crazy magic with the _buildAnnotation function.
	name_ = "dm"

	_sil = base.DataContent(description="SIL (simple instance language)"
		" annotation.", copyable=True)

	def completeElement(self, ctx):
		def _buildAnnotation():
			self._parsedAnnotation = sil.getAnnotation(
				self.content_, getAnnotationMaker(self.parent))
			self.parent.annotations.append(self._parsedAnnotation)
			self._buildAnnotation = lambda: None
		self._buildAnnotation = _buildAnnotation

		ctx.addExitFunc(lambda rd, ctx: self._buildAnnotation())
		self._completeElementNext(DataModelRoles, ctx)

	def parse(self):
		"""returns a parsed version of the embedded annotation.

		Do not call this while the RD is still being built, as dm
		elements may contain forward references, and these might
		not yet be available during the parse.
		"""
		self._buildAnnotation()
		return self._parsedAnnotation

	def getCopy(self, instance, newParent):
		# we'll have to re-parse since we want to reference the new columns
		self.parent.annotations.append(
			sil.getAnnotation(self.content_, 
				functools.partial(makeAttributeAnnotation, newParent)))


def makeAttributeAnnotation(container, attName, attValue):
	"""returns a typed annotation for attValue within container.

	When attValue is a literal, this is largely trivial.  If it's a reference,
	this figures out what it points to and creates an annotation of
	the appropriate type (e.g., ColumnAnnotation, ParamAnnotation, etc).

	container in current DaCHS should be a TableDef or something similar;
	this function expects at least a getByName function and an rd attribute.

	This is usually used as a callback from within sil.getAnnotation and
	expects Atom and Reference instances as used there.
	"""
	if isinstance(attValue, sil.Atom):
		return common.AtomicAnnotation(attName, attValue)
	
	elif isinstance(attValue, sil.Reference):
		# try name-resolving first (resolveId only does id resolving on
		# unadorned strings)
		try:
			res = container.getByName(attValue)
		except base.NotFoundError:
			res = base.resolveId(container.rd, attValue, instance=container)

		if not hasattr(res, "getAnnotation"):
			raise base.StructureError("Element %s cannot be referenced"
				" within a data model."%repr(res))

		return res.getAnnotation(attName, container)

	else:
		assert False


def getAnnotationMaker(container):
	"""wraps makeAttributeAnnotationMaker such that names are resolved
	within container.
	"""
	return functools.partial(makeAttributeAnnotation, container)
