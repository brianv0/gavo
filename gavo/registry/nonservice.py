"""
Resources that are not services.
"""

from gavo import base
from gavo import rscdef
from gavo import svcs
from gavo.registry import common


class NonServiceResource(
		base.Structure,
		base.ComputedMetaMixin, 
		base.StandardMacroMixin,
		common.DateUpdatedMixin,
		svcs.RegistryMetaMixin):
	"""A base class for resources that are not services.
	"""


class ResRec(NonServiceResource):
	"""A "resource" for registration purposes.

	A Resource does nothing; it is for registration of Authorities,
	Organizations, Instruments, or whatever.  Thus, they consist
	of metadata only (resources that do something are services; they
	carry their own metadata and care for their registration themselves.).

	All resources must have an id (which is used in the construction of
	their ivoa id; alternatively, you can force an id via the identifier
	meta). 
	
	You must further set the following meta items:

	   - resType specifying the kind of resource record
		 - title
		 - subject(s)
		 - description
		 - referenceURL
		 - creationDate
	
	Additional meta keys may be required depending on resType.  See the
	tutorial chapter on registry support.
	"""
	name_ = "resRec"
	_rd = rscdef.RDAttribute()



class _FakeRD(object):
	def __init__(self, id):
		self.sourceId = id


class DeletedResource(NonServiceResource):
	"""a remainder of a deleted resource.  These are always built from information
	in the database, since that is the only place they are remembered.
	"""
	resType = "deleted"

	def __init__(self, ivoId, resTuple):
		self.resTuple = resTuple
		self.rd = _FakeRD(resTuple["sourceRD"])
		self.id = resTuple["resId"]
		NonServiceResource.__init__(self, self.resTuple["dateUpdated"])
		self.setMeta("identifier", ivoId)
		self.setMeta("status", "deleted")
		self.setMeta("recTimestamp", resTuple["recTimestamp"])
		self.dateUpdated = resTuple["recTimestamp"]
