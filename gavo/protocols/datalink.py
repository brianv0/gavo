"""
The datalink core and its numerous helper classes.

More on this in "Datalink Cores" in the reference documentation.
"""

from gavo import base
from gavo import rscdef
from gavo import svcs
from gavo.protocols import products


MS = base.makeStruct


class ProductDescriptor(object):
	"""An encapsulation of information about some "product" (i.e., file).

	This is basically equivalent to a line in the product table; the
	arguments of the constructor are all available as same-named attributes.

	It also has an attribute data defaulting to None.  DataGenerators
	set it, DataFilters potentially change it.
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
	  - args -- all the arguments that came in from the web
	    (these should not ususally be necessary)
	
	If you made your pubdid using the ``getStandardPubDID`` rowmaker function,
	and you need no additional logic within the descriptor,
	the default (//products#fromStandardPubDID) should do.
	"""
	name_ = "descriptorGenerator"
	requiredType = "descriptorGenerator"
	formalArgs = "pubdid, args"


class DataGenerator(rscdef.ProcApp):
	"""A procedure application that generates the basic data for a processed
	data service.

	This will pull the initial information from a database or a FITS file.
	What is returned depends on the service, but typcially it's going to
	be a table or products.*Product instance.

	The following names are available to the code:
	  - descriptor -- whatever the DescriptorGenerator returned
	  - args -- all the arguments that came in from the web.
	"""
	name_ = "dataGenerator"
	requiredType = "descriptorGenerator"
	formalArgs = "descriptor, args"


class DatalinkCore(svcs.Core):
	"""A core for processing datalink and processed data requests.

	You almost certainly do not want to override the input table of this 
	service.

	See `Datalink Cores`_ for more information.
	"""
	name_ = "datalinkCore"

	_descriptorGenerator = base.StructAttribute("descriptorGenerator",
		default=base.NotGiven, 
		childFactory=DescriptorGenerator,
		description="Code that takes a PUBDID and turns it into a"
			" product descriptor instance.  If not given,"
			" //products#fromStandardPubDID will be used.",
		copyable=True)

	_dataGenerator = base.StructAttribute("dataGenerator",
		default=base.NotGiven,
		childFactory=DataGenerator,
		description="Code that takes a data descriptor and turns it into"
			" some sort of data processable by data filters and formatable"
			" by the formatter.  If not given, this core doesn't process"
			" data but just spits out links.",
		copyable=True)

	def _makeInputTable(self):
		inputKeys = rscdef.ColumnList()
		inputKeys.append(
			MS(svcs.InputKey, name="PUBDID", type="text", 
				multiplicity="forced-single",
				description="The pubisher DID of the dataset of interest"))

		return MS(svcs.InputTable, params=inputKeys)

	def completeElement(self, ctx):
		if self.descriptorGenerator is base.NotGiven:
			self.descriptorGenerator = MS(DescriptorGenerator, 
				procDef=base.caches.getRD("//products").getById("fromStandardPubDID"))

		if self.inputTable is base.NotGiven:
			self.inputTable = self._makeInputTable()

		self._completeElementNext(DatalinkCore, ctx)


	def run(self, service, inputTable, queryMeta):
		args = inputTable.getParamDict()
		pubDID = args["PUBDID"]
		descriptor = self.descriptorGenerator.compile(self)(pubDID, args)

		if False: # TODO: decide when to spit out the metadata document
			pass
		else:
			return self._runDataProcessing(descriptor, args)
	
	def _runDataProcessing(self, descriptor, args):
		if self.dataGenerator is base.NotGiven:
			raise base.DataError("This datalink service cannot process data")

		self.dataGenerator.compile()(descriptor, args)

		if descriptor.data is None:
			raise base.ReportableError("Internal Error: a data generator did"
				" not yield data.")

		return descriptor.data
		

