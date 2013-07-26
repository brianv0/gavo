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
	data = None

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
	the default (//datalink#fromStandardPubDID) should do.
	"""
	name_ = "descriptorGenerator"
	requiredType = "descriptorGenerator"
	formalArgs = "pubdid, args"


class DataFunction(rscdef.ProcApp):
	"""A procedure application that generates or modifies data in a processed
	data service.

	All these operate on the data attribute of the product descriptor.
	The first data function plays a special role: It *must* set the data
	attribute (or raise some appropriate exception), or a server error will 
	be returned to the client.

	What is returned depends on the service, but typcially it's going to
	be a table or products.*Product instance.

	The following names are available to the code:
	  - descriptor -- whatever the DescriptorGenerator returned
	  - args -- all the arguments that came in from the web.
	"""
	name_ = "dataFunction"
	requiredType = "dataFunction"
	formalArgs = "descriptor, args"


class DataFormatter(rscdef.ProcApp):
	"""A procedure application that renders data in a processed service.

	These play the role of the renderer, which for datalink is ususally
	trivial.  They are supposed to take descriptor.data and return
	a pair of (mime-type, bytes), which is understood by most renderers.

	When no dataFormatter is given for a core, it will return descriptor.data
	directly.  This can work with the datalink renderer itself if 
	descriptor.data will work as a nevow resource (i.e., has a renderHTTP
	method, as our usual products do).  Consider, though, that renderHTTP
	runs in the main event loop and thus most not block for extended
	periods of time.

	The following names are available to the code:
	  - descriptor -- whatever the DescriptorGenerator returned
	  - args -- all the arguments that came in from the web.
	"""
	name_ = "dataFormatter"
	requiredType = "dataFormatter"
	formalArgs = "descriptor, args"


class DatalinkCore(svcs.Core, base.ExpansionDelegator):
	"""A core for processing datalink and processed data requests.

	You almost certainly do not want to override the input table of this 
	core.

	See `Datalink Cores`_ for more information.
	"""
	name_ = "datalinkCore"

	_descriptorGenerator = base.StructAttribute("descriptorGenerator",
		default=base.NotGiven, 
		childFactory=DescriptorGenerator,
		description="Code that takes a PUBDID and turns it into a"
			" product descriptor instance.  If not given,"
			" //datalink#fromStandardPubDID will be used.",
		copyable=True)

	_dataFunctions = base.StructListAttribute("dataFunctions",
		childFactory=DataFunction,
		description="Code that generates of processes data for this"
			" core.  The first of these plays a special role in that it"
			" must set descriptor.data, the others need not do anything"
			" at all.",
		copyable=True)

	_dataFormatter = base.StructAttribute("dataFormatter",
		default=base.NotGiven,
		childFactory=DataFormatter,
		description="Code that turns descriptor.data into a nevow resource"
			" or a mime, content pair.  If not given, the renderer will be"
			" returned descriptor.data itself (which will probably not usually"
			" work).")

	_inputKeys = rscdef.ColumnListAttribute("inputKeys",
		childFactory=svcs.InputKey,
		description="A parameter to one of the proc apps (data functions,"
		" formatters) active in this datalink core; no specific relation"
		" between input keys and procApps is supposed; all procApps are passed"
		" all argments. Conventionally, you will write the input keys in"
		" front of the proc apps that interpret them.",
		copyable=True)

	def completeElement(self, ctx):
		if self.descriptorGenerator is base.NotGiven:
			self.descriptorGenerator = MS(DescriptorGenerator, 
				procDef=base.caches.getRD("//datalink").getById("fromStandardPubDID"))

		if self.dataFormatter is base.NotGiven:
			self.dataFormatter = MS(DataFormatter, 
				procDef=base.caches.getRD("//datalink").getById("trivialFormatter"))

		self.inputKeys.append(
			MS(svcs.InputKey, name="PUBDID", type="text", 
				multiplicity="forced-single",
				required=True,
				description="The pubisher DID of the dataset of interest"))

		if self.inputTable is base.NotGiven:
			self.inputTable = MS(svcs.InputTable, params=self.inputKeys)

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
		if not self.dataFunctions:
			raise base.DataError("This datalink service cannot process data")

		self.dataFunctions[0].compile(self)(descriptor, args)

		if descriptor.data is None:
			raise base.ReportableError("Internal Error: a first data function did"
				" not create data.")

		for func in self.dataFunctions[1:]:
			func.compile(self)(descriptor, args)

		return self.dataFormatter.compile(self)(descriptor, args)
