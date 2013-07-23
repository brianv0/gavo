"""
The datalink core and its numerous helper classes.

More on this in "Datalink Cores" in the reference documentation.
"""

from gavo import base
from gavo import rscdef
from gavo.protocols import products
from gavo.svcs import core


class ProductDescriptor(object):
	"""An encapsulation of information about some "product" (i.e., file).

	This is basically equivalent to a line in the product table.
	"""
	def __init__(self, accref, accessPath, mime, owner=None, embargo=None,
			sourceTable=None):
		self.accref, self.accessPath, self.mime = accref, accessPath, mime
		self.owner, self.embargo, self.sourceTable = owner, embargo, sourceTable
	
	@classmethod
	def fromAccref(cls, accref):
		"""returns a product descriptor for an access reference.
		"""
		return cls(**products.RAccref(accref).productsRow)


class DescriptorGenerator(rscdef.ProcApp):
	"""A procedure application for making product descriptors for PUBDIDs
	
	A normal product descriptor contains basically what DaCHS' product
	table contains.  You could derive from protocols.datalink.ProductDescriptor,
	though, e.g., in the setup of this proc.

	The following names are available to the code:

	  - pubdid -- the pubdid to be resolved
	  - args -- all the additional arguments that came in from the web
	    (these should not ususally be necessary)
	
	If you made your pubdid using the ``getStandardPubDID`` rowmaker function,
	and you need no additional logic within the descriptor,
	the default (//products#fromStandardPubDID) should do.
	"""
	name_ = "descriptorGenerator"
	requiredType = "descriptorGenerator"
	formalArgs = "pubdid, args"


class DatalinkCore(core.Core):
	"""A core for processing datalink and processed data requests.

	See `Datalink Cores`_ for more information.
	"""
	name_ = "datalinkCore"

	_descriptorGenerator = base.StructAttribute("descriptorGenerator",
		default=base.Undefined, 
		childFactory=DescriptorGenerator,
		description="The code that takes a PUBDID and turns it into a"
			" product descriptor instance",
		copyable="True")
