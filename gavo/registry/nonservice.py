"""
Resources that are not services.
"""

from gavo import base
from gavo import rscdef
from gavo import svcs
from gavo import utils
from gavo.registry import common


class NonServiceResource(
		base.Structure,
		base.StandardMacroMixin,
		base.ComputedMetaMixin):
	"""A base class for resources that are not services.
	"""
	def _meta_identifier(self):
		# Special case the authority
		if base.getMetaText(self, "resType")=="authority":
			localPart = ""
		else:
			localPart = "/%s/%s"%(self.rd.sourceId, self.id)
		return "ivo://%s%s"%(base.getConfig("ivoa", "authority"), localPart)
			

class ResRec(rscdef.IVOMetaMixin, NonServiceResource):
	"""A resource for pure registration purposes.

	A Resource does nothing; it is for registration of Authorities,
	Organizations, Instruments, or whatever.  Thus, they consist
	of metadata only (resources that do something are services; they
	carry their own metadata and care for their registration themselves.).

	All resources must either have an id (which is used in the construction of
	their IVORN), or you must give an identifier meta item.
	
	You must further set the following meta items:

	   - resType specifying the kind of resource record.  This element
	     is intended to be used to build registry, organization, authority, 
	     and deleted resources.  For other types of records, use either
	     service or table elements.
	   - title
	   - subject(s)
	   - description
	   - referenceURL
	   - creationDate
	
	Additional meta keys (e.g., accessURL for a registry) may be required 
	depending on resType.  See the registry session in the operator's guide.
	"""
	name_ = "resRec"
	_rd = rscdef.RDAttribute()


class _FakeRD(object):
	def __init__(self, id):
		self.sourceId = id


class DeletedResource(common.DateUpdatedMixin, NonServiceResource):
	"""a remainder of a deleted resource.  These are always built from information
	in the database, since that is the only place they are remembered.
	"""
	resType = "deleted"

	_resTuple = base.RawAttribute("resTuple")

	def _meta_status(self):
		return "deleted"

	def _meta_recTimestamp(self):
		return utils.formatISODT(self.resTuple["recTimestamp"])

	def completeElement(self, ctx):
		self._completeElementNext(DeletedResource, ctx)
		self.rd = _FakeRD(self.resTuple["sourceRD"])
		self.id = self.resTuple["resId"]
		self.dateUpdated = self.resTuple["recTimestamp"]
