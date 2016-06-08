"""
Writing annotations in RDs.

This essentially defines a language that allows the translation
of DM annotations to a json-inspired syntax including references
to atomic or compound objects in the same resource.
"""

from gavo import base


class ResAnnotation(base.Structure):
	"""an annotation of this table in terms of data models.

	The content of this element is a Simple Instance Language term.
	"""
	name_ = "dm"


