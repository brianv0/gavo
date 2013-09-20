"""
The datalink core and its numerous helper classes.

More on this in "Datalink Cores" in the reference documentation.
"""

from gavo import base
from gavo import rscdef
from gavo import svcs
from gavo import utils
from gavo import votable
from gavo.protocols import products
from gavo.formats import votablewrite
from gavo.votable import V, modelgroups


MS = base.makeStruct


class FormatNow(base.ExecutiveAction):
	"""can be raised by data functions to abort all further processing
	and format the current descriptor.data.
	"""


class DeliverNow(base.ExecutiveAction):
	"""can be raised by data functions to abort all further processing
	and return the current descriptor.data to the client.
	"""


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

	If you need to derive custom descriptor classes, you can see the base
	class under the name ProductDescriptor.
	"""
	name_ = "descriptorGenerator"
	requiredType = "descriptorGenerator"
	formalArgs = "pubdid, args"

	additionalNamesForProcs = {
		"ProductDescriptor": ProductDescriptor,
	}


class LinkDef(object):
	"""A definition of a datalink related document.

	These are constructed at least with:

	  - the destination URL (as a string)
	  - the destination contentType (a mime type as a string)
	  - the relationType (another string).
	
	For relationType, there's a semi-controlled vocabulary, items from
	which you should be using if at all matching.
	"""
	def __init__(self, url, contentType, relationType):
		self.url, self.contentType = url, contentType
		self.relationType = relationType

	def asRow(self):
		"""returns self in the format expected by _runGenerateMetadata below.
		"""
		return (self.url, self.contentType, self.relationType)


class MetaMaker(rscdef.ProcApp):
	"""A procedure application that generates metadata for datalink services.

	The code must be generators (i.e., use yield statements) producing either
	svcs.InputKeys or protocols.datalink.LinkDef instances.

	metaMaker see the data descriptor of the input data under the name
	descriptor.

	The data attribute of the descriptor is always None for metaUpdaters, so
	you cannot use anything given there.

	Within MetaMakers' code, you can access InputKey, Values, Option, and
	LinkDef without qualification, and there's the MS function to build
	structures.  Hence, a metaMaker returning an InputKey could look like this::

		<metaMaker>
			<code>
				yield MS(InputKey, name="format", type="text",
					description="Output format desired",
					values=MS(Values,
						options=[MS(Option, content_=descriptor.mime),
							MS(Option, content_="text/plain")]))
			</code>
		</metaMaker>

	(of course, you should give more metadata -- ucds, better description,
	etc) in production).
	"""
	name_ = "metaMaker"
	requiredType = "metaMaker"
	formalArgs = "descriptor"

	additionalNamesForProcs = {
		"MS": base.makeStruct,
		"InputKey": svcs.InputKey,
		"Values": rscdef.Values,
		"Option": rscdef.Option,
		"LinkDef": LinkDef,
	}


class DataFunction(rscdef.ProcApp):
	"""A procedure application that generates or modifies data in a processed
	data service.

	All these operate on the data attribute of the product descriptor.
	The first data function plays a special role: It *must* set the data
	attribute (or raise some appropriate exception), or a server error will 
	be returned to the client.

	What is returned depends on the service, but typcially it's going to
	be a table or products.*Product instance.

	Data functions can shortcut if it's evident that further data functions
	can only mess up (i.e., if the do something bad with the data attribute);
	you should not shortcut if you just *think* it makes no sense to
	further process your output.

	To shortcut, raise either of FormatNow (falls though to the formatter,
	which is usually less useful) or DeliverNow (directly returns the
	data attribute; this can be used to return arbitrary chunks of data).

	The following names are available to the code:
	  - descriptor -- whatever the DescriptorGenerator returned
	  - args -- all the arguments that came in from the web.
	"""
	name_ = "dataFunction"
	requiredType = "dataFunction"
	formalArgs = "descriptor, args"

	additionalNamesForProcs = {
		"FormatNow": FormatNow,
		"DeliverNow": DeliverNow,
	}


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


class DatalinkCoreBase(svcs.Core, base.ExpansionDelegator):
	"""Basic functionality for datalink cores.  

	This is pulled out of the datalink core proper as it is used without
	the complicated service interface sometimes, e.g., by SSAP.
	"""

	_descriptorGenerator = base.StructAttribute("descriptorGenerator",
		default=base.NotGiven, 
		childFactory=DescriptorGenerator,
		description="Code that takes a PUBDID and turns it into a"
			" product descriptor instance.  If not given,"
			" //datalink#fromStandardPubDID will be used.",
		copyable=True)

	_metaMakers = base.StructListAttribute("metaMakers",
		childFactory=MetaMaker,
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

	# The following is a hack complemented in inputdef.makeAutoInputDD.
	# We probably want some other way to do this (if we want to do it
	# at all)
	rejectExtras = True

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

		self._completeElementNext(DatalinkCoreBase, ctx)

	def adaptForDescriptor(self, descriptor):
		"""returns a version of self that has its metadata pulled from whatever
		is in descriptor.
		"""
		linkDefs, inputKeys = [], self.inputKeys[:]
	
		for metaMaker in self.metaMakers:
			for item in metaMaker.compile(self)(descriptor):
				if isinstance(item, LinkDef):
					linkDefs.append(item)
				else:
					inputKeys.append(item)
	
		res = self.change(inputTable=MS(svcs.InputTable, params=inputKeys))
		res.nocache = True
		res.datalinkLinks = linkDefs
		res.descriptor = descriptor
		
		return res

	def getDatalinkDescriptionResource(self, ctx, service):
		"""returns a VOTable RESOURCE element with the metadata
		description for a service using this core.

		You must pass in a VOTable context object ctx (for the management
		of ids).  If this is the entire content of the VOTable, use
		votablewrite.VOTableContext() there.
		"""
		paramsByName, stcSpecs = {}, set()
		for param in self.inputTable.params:
			paramsByName[param.name] = param
			if param.stc:
				stcSpecs.add(param.stc)

		def getIdFor(colRef):
			colRef.toParam = True
			return ctx.makeIdFor(paramsByName[colRef.dest])

		return V.RESOURCE(name="datalinkDescriptor")[

				[modelgroups.marshal_STC(ast, getIdFor)
					for ast in stcSpecs],

				V.GROUP(utype="datalink:service")[
					V.PARAM(name="serviceAccessURL", utype="datalink:accessURL",
						datatype="char", arraysize="*", 
						value=service.getURL("dlget"))[
							V.DESCRIPTION["Access URL for this service"]],
					[votablewrite._addID(ik,
							votablewrite.makeFieldFromColumn(V.PARAM, ik), ctx)
						for ik in self.inputTable.params]],
				votable.DelayedTable(
					V.TABLE(name="relatedData") [
						V.FIELD(name="url", datatype="char", arraysize="*"),
						V.FIELD(name="contentType", datatype="char", arraysize="*"),
						V.FIELD(name="relationType", datatype="char", arraysize="*")],
					[l.asRow() for l in self.datalinkLinks],
					V.TABLEDATA)]


class DatalinkCore(DatalinkCoreBase):
	"""A core for processing datalink and processed data requests.

	You almost certainly do not want to override the input table of this 
	core.

	See `Datalink Cores`_ for more information.

	In contrast to "normal" cores, one of these is made (and destroyed)
	for each datalink request coming in.  This is because the interface
	of a datalink service depends on the request (i.e., pubdid).
	"""
	name_ = "datalinkCore"

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
			if not isinstance(args, dict):
				# again, we're not being called in a context with a pubdid
				raise ValueError("No pubdid")
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
		return self.adaptForDescriptor(descriptor)

	def run(self, service, inputTable, queryMeta):
		args = inputTable.getParamDict()
		argsGiven = set(key for (key, value) in args.iteritems()
			if value is not None)
		
		if argsGiven==set(["PUBDID"]):
			return self._runGenerateMetadata(args, service)
		else:
			return self._runDataProcessing(args)
	
	def _runDataProcessing(self, args):
		"""does run's work if we're handling a data processing request.
		"""
		if not self.dataFunctions:
			raise base.DataError("This datalink service cannot process data")

		self.dataFunctions[0].compile(self)(self.descriptor, args)

		if self.descriptor.data is None:
			raise base.ReportableError("Internal Error: a first data function did"
				" not create data.")

		for func in self.dataFunctions[1:]:
			try:
				func.compile(self)(self.descriptor, args)
			except FormatNow:
				break
			except DeliverNow:
				return self.descriptor.data

		return self.dataFormatter.compile(self)(self.descriptor, args)

	def _runGenerateMetadata(self, args, service):
		"""does run's work if we're handling a metadata request.

		This will always return a rendered VOTable.
		"""

		ctx = votablewrite.VOTableContext(tablecoding="td")
		vot = V.VOTABLE[
				self.getDatalinkDescriptionResource(ctx, service)]
		return ("application/x-votable+xml", vot.render())
