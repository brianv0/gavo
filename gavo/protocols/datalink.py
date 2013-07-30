"""
The datalink core and its numerous helper classes.

More on this in "Datalink Cores" in the reference documentation.
"""

from gavo import base
from gavo import rscdef
from gavo import svcs
from gavo import utils
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
	    (these should not ususally be necessary and are completely unparsed)
	
	If you made your pubdid using the ``getStandardPubDID`` rowmaker function,
	and you need no additional logic within the descriptor,
	the default (//datalink#fromStandardPubDID) should do.
	"""
	name_ = "descriptorGenerator"
	requiredType = "descriptorGenerator"
	formalArgs = "pubdid, args"


class MetaUpdater(rscdef.ProcApp):
	"""A procedure application that generates metadata for datalink services.

	This can either mean updating InputKey's options (e.g., limits, enumerated
	values), in which case the procs return nothing.  Alternatively,
	they can yield zero or more datalink.LinkDef instances, which
	represent related metadata.  See there on how to come up with them.

	metaUpdaters see the descriptor of the input data as descriptor.
	The data attribute of the descriptor is always None for metaUpdaters.
	"""
	name_ = "metaUpdater"
	requiredType = "metaUpdater"
	formalArgs = "descriptor"


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

	In contrast to "normal" cores, one of these is made (and destroyed)
	for each datalink request coming in.  This is because the interface
	of a datalink service depends on the request (i.e., pubdid).
	"""
	name_ = "datalinkCore"

	_descriptorGenerator = base.StructAttribute("descriptorGenerator",
		default=base.NotGiven, 
		childFactory=DescriptorGenerator,
		description="Code that takes a PUBDID and turns it into a"
			" product descriptor instance.  If not given,"
			" //datalink#fromStandardPubDID will be used.",
		copyable=True)

	_metaUpdaters = base.StructListAttribute("metaUpdaters",
		childFactory=MetaUpdater,
		description="Code that takes a data descriptor and either"
			" updates input key options or yields related data.",
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
			" work).",
		copyable=True)

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

	def adaptForRenderer(self, renderer):
		"""returns a core for a specific product.
	
		The ugly thing about datalink in DaCHS' architecture is that its
		interface (in terms of, e.g., inputKeys' values children) depends
		on the arguments themselves, specifically the pubdid.

		The workaround is to abuse the renderer-specific getCoreFor,
		ignore the renderer and instead steal an "args" variable from
		somewhere upstack.  Nasty, but for now an acceptable solution.

		It is particularly important to never let service cache the
		cores returned; hence to "nocache" magic.

		To generate all datalink-relevant metadata in one go and avoid
		calling the descriptorGenerator more than once, the resulting
		table also has "datalinkDescriptor" and "datalinkLinks" attributes.
		"""
		try:
			args = utils.stealVar("args")
		except ValueError:
			# no arguments found: no pubdid-specific interfaces
			return self

		try:
			pubDID = args["PUBDID"]
			if isinstance(pubDID, list):
				pubDID = pubDID[0]
		except (KeyError, IndexError):
			raise base.ValidationError("Value is required but was not provided",
				"PUBDID")
		descriptor = self.descriptorGenerator.compile(self)(pubDID, args)

		linkDefs, inputKeys = [], self.inputKeys[:]
		
		for updater in self.metaUpdaters:
			for item in updater.compile(self)(descriptor):
				if isinstance(item, LinkDef):
					linkDefs.append
		
		res = self.change(inputKeys=inputKeys)
		res.nocache = True
		res.datalinkLinks = linkDefs
		res.descriptor = descriptor
		
		return res

	def run(self, service, inputTable, queryMeta):
		args = inputTable.getParamDict()

		if not self.dataFunctions:
			raise base.DataError("This datalink service cannot process data")

		self.dataFunctions[0].compile(self)(self.descriptor, args)

		if self.descriptor.data is None:
			raise base.ReportableError("Internal Error: a first data function did"
				" not create data.")

		for func in self.dataFunctions[1:]:
			func.compile(self)(self.descriptor, args)

		return self.dataFormatter.compile(self)(self.descriptor, args)
