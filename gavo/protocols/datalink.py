"""
The datalink core and its numerous helper classes.

More on this in "Datalink Cores" in the reference documentation.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import itertools
import inspect
import os
import urllib

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo import utils
from gavo.protocols import products
from gavo.protocols import soda
from gavo.protocols.soda import (FormatNow, DeliverNow, DatalinkFault,
	DEFAULT_SEMANTICS)
from gavo.formats import votablewrite
from gavo.votable import V, modelgroups

from nevow import inevow
from nevow import rend
from nevow import static

from twisted.internet import defer


MS = base.makeStruct


class ProductDescriptor(object):
	"""An encapsulation of information about some "product" (i.e., file).

	This is basically equivalent to a line in the product table; the
	arguments of the constructor are all available as same-named attributes.

	It also has an attribute data defaulting to None.  DataGenerators
	set it, DataFilters potentially change it.

	If you inherit from this method and you have a way to guess the
	size of what the descriptor describes, override the estimateSize()
	method.  The default will return a file size if accessPath points
	to an existing file, None otherwise.
	"""
	data = None

	def __init__(self, pubDID, accref, accessPath, mime, 
			owner=None, embargo=None, sourceTable=None, datalink=None,
			preview=None, preview_mime=None):
		self.pubDID = pubDID
		self.accref, self.accessPath, self.mime = accref, accessPath, mime
		self.owner, self.embargo, self.sourceTable = owner, embargo, sourceTable
		self.preview, self.previewMime = preview, preview_mime

	@classmethod
	def fromAccref(cls, pubDID, accref, accrefPrefix=None):
		"""returns a product descriptor for an access reference.

		If an accrefPrefix is passed in, an AuthenticationFault (for want
		of something better fitting) is returned when the accref doesn't
		start with accrefPrefix.
		"""
		if accrefPrefix and not accref.startswith(accrefPrefix):
			return DatalinkFault.AuthenticationFault(pubDID,
				"This Datalink service not available"
				" with this pubDID", semantics="#this")

		return cls(pubDID, **products.RAccref(accref).productsRow)

	def estimateSize(self):
		if isinstance(self.accessPath, basestring):
			candPath = os.path.join(base.getConfig("inputsDir"), self.accessPath)
			try:
				return os.path.getsize(candPath)
			except:
				# fall through to returning None
				pass
	
	def makeLink(self, url, **kwargs):
		"""returns a LinkDef for this descriptor for url.

		kwargs are passed on to LinkDef and include, in particular,
		semantics, contentType, contentLength, and description.
		"""
		return LinkDef(self.pubDID, url, **kwargs)

	def makeLinkFromFile(self, localPath, description, semantics,
			service=None, contentType=None):
		"""returns a LinkDef for a local file.

		Arguments are as for LinkDef.fromFile, except you don't have
		to pass in service if you're using the datalink service itself
		to access the file; this method will try to find the service by
		itself.
		"""
		if service is None:
			try:
				service = inspect.currentframe().f_back.f_locals["self"].parent
			except (KeyError, AttributeError):
				raise base.StructureError("Cannot infer service for datalink"
					" file link.  Pass an appropriate service manually.")
		return LinkDef.fromFile(localPath, description, semantics,
			service=service, contentType=None)


class FITSProductDescriptor(ProductDescriptor):
	"""A SODA descriptor for FITS files.

	On top of the normal product descriptor, this has an attribute hdr
	containing a copy of the image header, and a method 
	changingAxis (see there). 

	There's also an attribute dataIsPristine that must be set to false
	if changes have been made.  The formatter will spit out the original
	data otherwise, ignoring your changes.

	Finally, there's a slices attribute provided explained in 
	soda#fits_doWCSCutout that can be used by data functions running before
	it to do cutouts.

	The FITSProductDescriptor is constructed like a normal ProductDescriptor.
	"""
	def __init__(self, *args, **kwargs):
		ProductDescriptor.__init__(self, *args, **kwargs)
		with open(os.path.join(base.getConfig("inputsDir"), 
				self.accessPath)) as f:
			self.hdr = utils.readPrimaryHeaderQuick(f,
				maxHeaderBlocks=100)
		self.slices = []
		self.dataIsPristine = True
		self._axesTouched = set()
	
	def changingAxis(self, axisIndex, parName):
		"""must be called before cutting out along axisIndex.

		axIndex is a FITS (1-based) axis index axIndex, parName the name of the 
		parameter that causes the cutout.
		
		This will simply return if nobody has called changingAxis with that index
		before and raise a ValidationError otherwise.  Data functions doing a cutout
		must call this before doing so; if they don't the cutout will probably be
		wrong when two conflicting constraints are given.
		"""
		if axisIndex in self._axesTouched:
			raise base.ValidationError("Attempt to cut out along axis %d that"
				" has been modified before."%axisIndex, parName)
		self._axesTouched.add(axisIndex)


class DLFITSProductDescriptor(FITSProductDescriptor):
	"""A SODA descriptor for FITS files with datalink product paths.

	Use is as descClass in //soda#fits_genDesc when the product table
	has a datalink as the product.
	"""
	def __init__(self, *args, **kwargs):
		kwargs["accessPath"] = os.path.join(
			base.getConfig("inputsDir"),
			kwargs["accref"])
		FITSProductDescriptor.__init__(self, *args, **kwargs)


def getFITSDescriptor(pubDID, accrefPrefix=None, 
		cls=FITSProductDescriptor):
	"""returns a datalink descriptor for a FITS file.

	This is the implementation of fits_genDesc and should probably reused
	when making more specialised descriptors.
	"""
	try:
		accref = rscdef.getAccrefFromStandardPubDID(pubDID)
	except ValueError:
		return DatalinkFault.NotFoundFault(pubDID,
			"Not a pubDID from this site.")

	return cls.fromAccref(pubDID, accref, accrefPrefix)


class _File(static.File):
	"""A nevow static.File with a pre-determined type.
	"""
	def __init__(self, path, mediaType):
		static.File.__init__(self, path)
		self.type = mediaType
		self.encoding = None


class _TemporaryFile(_File):
	"""A nevow resource that spits out a file and then deletes it.

	This is a helper class for DataFunctions and DataFormatters, available
	there as TemporaryFile.
	"""
	def renderHTTP(self, ctx):
		return defer.maybeDeferred(_File.renderHTTP, self, ctx).addBoth(
			self._cleanup)
	
	def _cleanup(self, result):
		self.fp.remove()
		return result


class DescriptorGenerator(rscdef.ProcApp):
	"""A procedure application for making product descriptors for PUBDIDs
	
	A normal product descriptor contains basically what DaCHS' product
	table contains.  You could derive from protocols.datalink.ProductDescriptor,
	though, e.g., in the setup of this proc.

	The following names are available to the code:

	  - pubDID -- the pubDID to be resolved
	  - args -- all the arguments that came in from the web
	    (these should not ususally be necessary for making the descriptor
	    and are completely unparsed at this point)
	  - FITSProductDescriptor -- the base class of FITS product descriptors
	  - DLFITSProductDescriptor -- the same, just for when the product table
	    has a datalink.
	  - ProductDescriptor -- the base class of FITSProductDescriptor
	  - DatalinkFault -- use this when flagging failures
	  - soda -- contents of the soda module for convenience
	
	If you made your pubDID using the ``getStandardPubDID`` rowmaker function,
	and you need no additional logic within the descriptor,
	the default (//soda#fromStandardPubDID) should do.

	If you need to derive custom descriptor classes, you can see the base
	class under the name ProductDescriptor; there's also 
	FITSProductDescriptor and DatalinkFault in each proc's namespace.
	"""
	name_ = "descriptorGenerator"
	requiredType = "descriptorGenerator"
	formalArgs = "pubDID, args"

	additionalNamesForProcs = {
		"FITSProductDescriptor": FITSProductDescriptor,
		"DLFITSProductDescriptor": DLFITSProductDescriptor,
		"ProductDescriptor": ProductDescriptor,
		"getFITSDescriptor": getFITSDescriptor,
		"DatalinkFault": DatalinkFault,
		"soda": soda,
	}


class LinkDef(object):
	"""A definition of a datalink related document.

	These are constructed at least with:

		- the pubDID (as a string)
	  - the access URL (as a string)

	In addition, we accept the remaining column names from 
	//datalink#dlresponse as keyword arguments.

	In particular, do set semantics with a term from 
	http://www.ivoa.net/rdf/datalink/core.  This includes #this, #preview,
	#calibration, #progenitor, #derivation
	"""
	def __init__(self, pubDID, accessURL, 
			serviceType=None, 
			errorMessage=None,
			description=None, 
			semantics=DEFAULT_SEMANTICS,
			contentType=None, 
			contentLength=None):
		ID = pubDID #noflake: used in locals()
		del pubDID
		self.dlRow = locals()

	@classmethod
	def fromFile(cls, localPath, description, semantics, 
			service, contentType=None):
		"""constructs a LinkDef based on a local file.
		
		You must give localPath (which may be resdir-relative), description and
		semantics are mandatory.  ContentType and contentSize will normally be
		determined by DaCHS.

		You must also pass in the service used to retrieve the file.  This
		must allow the static renderer and have a staticData property.  It should
		normally be the datalink service itself, which in a metaMaker
		is accessible as self.parent.parent.  It is, however, legal
		to reference other suitable services (use self.parent.rd.getById or 
		base.resolveCrossId)
		"""
		baseDir = service.rd.resdir
		localPath = os.path.join(baseDir, localPath)
		pubDID = utils.stealVar("descriptor").pubDID
		staticPath = os.path.join(baseDir,
			service.getProperty("staticData"))

		if not os.path.isfile(localPath):
			return DatalinkFault.NotFoundFault(pubDID, "No file"
				" for linked item", semantics=semantics, description=description)
		elif not os.access(localPath, os.R_OK):
			return DatalinkFault.AutorizationFault(pubDID, "Linked"
				" item not readable", semantics=semantics, description=description)
		
		try:
			svcPath = utils.getRelativePath(localPath, staticPath)
		except ValueError:
			return LinkDef(pubDID, errorMessage="FatalFault: Linked item"
				" not accessible through the given service", 
				semantics=semantics, description=description)

		ext = os.path.splitext(localPath)[-1]
		contentType = (contentType 
			or static.File.contentTypes.get(ext, "application/octet-stream"))

		return cls(pubDID, 
			service.getURL("static")+"/"+svcPath,
			description=description, semantics=semantics,
			contentType=contentType, 
			contentLength=os.path.getsize(localPath))

	def asDict(self):
		"""returns the link definition in a form suitable for ingestion
		in //datalink#dlresponse.
		"""
		return {
			"ID": self.dlRow["ID"],
			"access_url": self.dlRow["accessURL"],
			"service_def": self.dlRow["serviceType"],
			"error_message": self.dlRow["errorMessage"],
			"description": self.dlRow["description"],
			"semantics": self.dlRow["semantics"],
			"content_type": self.dlRow["contentType"],
			"content_length": self.dlRow["contentLength"]}


class _ServiceDescriptor(object):
	"""An internal descriptor for one of our services.

	These are serialized into service resources in VOTables.
	Basically, these collect input keys, a pubDID, as well as any other
	data we might need in service definition.
	"""
	def __init__(self, pubDID, inputKeys, rendName):
		self.pubDID, self.inputKeys = pubDID, inputKeys
		self.rendName = rendName
		if self.pubDID:
		# if we're fixed to a specific pubDID, reflect that in the ID
		# field -- this is how clients know which dataset to pull
		# from datalink documents.
			for index, ik in enumerate(self.inputKeys):
				if ik.name=="ID":
					ik = ik.copy(None)
					ik.set(pubDID)
					self.inputKeys[index] = ik

	def asVOT(self, ctx, accessURL, linkIdTo=None):
		"""returns VOTable stanxml for a description of this service.

		This is a RESOURCE as required by Datalink.

		linkIdTo is used to support data access descriptors embedded
		in descovery queries.  It is the id of the column containing
		the identifiers.  SSA can already provide this.  It ends up
		in a LINK child of the ID parameter.
		"""
		paramsByName, stcSpecs = {}, set()
		for param in self.inputKeys:
			paramsByName[param.name] = param
			if param.stc:
				stcSpecs.add(param.stc)

		def getIdFor(colRef):
			colRef.toParam = True
			return ctx.makeIdFor(paramsByName[colRef.dest])

		res = V.RESOURCE(ID=ctx.getOrMakeIdFor(self), type="meta",
			utype="adhoc:service")[
			[modelgroups.marshal_STC(ast, getIdFor)
				for ast in stcSpecs],
			V.PARAM(arraysize="*", datatype="char", 
				name="accessURL", ucd="meta.ref.url",
				value=accessURL)]

		standardId = {
			"dlasync": "ivo://ivoa.net/std/SODA#async-1.0",
			"dlget": "ivo://ivoa.net/std/SODA#sync-1.0"}.get(self.rendName)
		if standardId:
			res[
				V.PARAM(arraysize="*", datatype="char",
					name="standardID", value=standardId)]

		inputParams = V.GROUP(name="inputParams")
		res = res[inputParams]

		for ik in self.inputKeys:
			param = ctx.addID(ik,
				votablewrite.makeFieldFromColumn(ctx, V.PARAM, ik))
			if linkIdTo and ik.name=="ID":
				param = param(ref=linkIdTo)
			inputParams[param]

		return res


class MetaMaker(rscdef.ProcApp):
	"""A procedure application that generates metadata for datalink services.

	The code must be generators (i.e., use yield statements) producing either
	svcs.InputKeys or protocols.datalink.LinkDef instances.

	metaMaker see the data descriptor of the input data under the name
	descriptor.

	The data attribute of the descriptor is always None for metaMakers, so
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

	In addition to the usual names available to ProcApps, meta makers have:
	  - MS -- function to make DaCHS structures
	  - InputKey -- the class to make for input parameters
	  - Values -- the class to make for input parameters' values attributes
	  - Options -- used by Values
	  - LinkDef -- a class to define further links within datalink services.
	  - DatalinkFault -- a container of datalink error generators
	  - soda -- the soda module.
	"""
	name_ = "metaMaker"
	requiredType = "metaMaker"
	formalArgs = "self, descriptor"

	additionalNamesForProcs = {
		"MS": base.makeStruct,
		"InputKey": svcs.InputKey,
		"Values": rscdef.Values,
		"Option": rscdef.Option,
		"LinkDef": LinkDef,
		"DatalinkFault": DatalinkFault,
		"soda": soda,
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
	
	In addition to the usual names available to ProcApps, data functions have:
	  - FormatNow -- exception to raise to go directly to the formatter
	  - DeliverNow -- exception to raise to skip all further formatting
	    and just deliver what's currently in descriptor.data
	  - File(path, type) -- if you just want to return a file on disk, pass 
	  	its path and media type to File and assign the result to 
	  	descriptor.data.  
	  - TemporaryFile(path,type) -- as File, but the disk file is 
	    unlinked after use
	  - makeData -- the rsc.makeData function
	  - soda -- the protocols.soda module
	"""
	name_ = "dataFunction"
	requiredType = "dataFunction"
	formalArgs = "descriptor, args"

	additionalNamesForProcs = {
		"FormatNow": FormatNow,
		"DeliverNow": DeliverNow,
		"File": _File,
		"TemporaryFile": _TemporaryFile, 
		"makeData": rsc.makeData, 
		"soda": soda,
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
	
	In addition to the usual names available to ProcApps, data formatters have:
	  - Page -- base class for resources with renderHTTP methods.
	  - IRequest -- the nevow interface to make Request objects with.
	  - File(path, type) -- if you just want to return a file on disk, pass 
	    its path and media type to File and return the result. 
	  - TemporaryFile(path, type) -- as File, but the disk file is unlinked 
	    after use
	  - soda -- the protocols.soda module
	"""
	name_ = "dataFormatter"
	requiredType = "dataFormatter"
	formalArgs = "descriptor, args"

	additionalNamesForProcs = {
		"Page": rend.Page,
		"IRequest": inevow.IRequest,
		"File": _File,
		"TemporaryFile": _TemporaryFile, 
		"soda": soda,
	}


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
			" //soda#fromStandardPubDID will be used.",
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
				procDef=base.resolveCrossId("//soda#fromStandardPubDID"))

		if self.dataFormatter is base.NotGiven:
			self.dataFormatter = MS(DataFormatter, 
				procDef=base.caches.getRD("//datalink").getById("trivialFormatter"))
		
		self.inputKeys.append(MS(svcs.InputKey, name="ID", type="text", 
			ucd="meta.id;meta.main",
			multiplicity="multiple",
			std=True,
			description="The pubisher DID of the dataset of interest"))

		if self.inputTable is base.NotGiven:
			self.inputTable = MS(svcs.InputTable, params=self.inputKeys)

		# this is a cheat for service.getTableSet to pick up the datalink
		# table.  If we fix this for TAP, we should fix it here, too.
		self.queriedTable = base.caches.getRD("//datalink").getById(
			"dlresponse")

		self._completeElementNext(DatalinkCoreBase, ctx)

	def getMetaForDescriptor(self, descriptor):
		"""returns a pair of linkDefs, inputKeys for a datalink desriptor
		and this core.
		"""
		linkDefs, inputKeys, errors = [], self.inputKeys[:], []
	
		for metaMaker in self.metaMakers:
			try:
				for item in metaMaker.compile(self)(self, descriptor):
					if isinstance(item, LinkDef):
						linkDefs.append(item)
					elif isinstance(item, DatalinkFault):
						errors.append(item)
					else:
						inputKeys.append(item)
			except Exception, ex:
				if base.DEBUG:
					base.ui.notifyError("Error in datalink meta generator %s: %s"%(
						metaMaker, repr(ex)))
					base.ui.notifyError("Failing source: \n%s"%metaMaker.getFuncCode())
				errors.append(DatalinkFault.Fault(descriptor.pubDID,
					"Unexpected failure while creating"
					" datalink: %s"%utils.safe_str(ex)))

		return linkDefs, inputKeys, errors

	def getDatalinksResource(self, ctx, service):
		"""returns a VOTable RESOURCE element with the data links.

		This does not contain the actual service definition elements, but it
		does contain references to them.

		You must pass in a VOTable context object ctx (for the management
		of ids).  If this is the entire content of the VOTable, use
		votablewrite.VOTableContext() there.
		"""
		internalLinks = []

		internalLinks.extend(LinkDef(s.pubDID, service.getURL(s.rendName),
				serviceType=ctx.getOrMakeIdFor(s), semantics="#proc")
			for s in self.datalinkEndpoints)

		for d in self.descriptors:
			# for all descriptors that are products, make a full dataset
			# available through the data access, possibly also adding a preview.
			if not isinstance(d, ProductDescriptor):
				continue
			if hasattr(d, "suppressAutoLinks"):
				continue

			# if the accref is a datalink document, go through dlget itself.
			if d.mime=="application/x-votable+xml;content=datalink":
				internalLinks.append(LinkDef(d.pubDID, 
					service.getURL("dlget")+"?ID=%s"%urllib.quote(d.pubDID),
					description="The full dataset.",
					contentType=products.guessMediaType(d.accref),
					contentLength=d.estimateSize(),
					semantics="#this"))

			else:
				internalLinks.append(LinkDef(d.pubDID, 
					products.makeProductLink(d.accref),
					description="The full dataset.",
					contentType=d.mime,
					contentLength=d.estimateSize(),
					semantics="#this"))

			if getattr(d, "preview", None):
				if d.preview.startswith("http"):
					previewLink = d.preview
				else:
					previewLink = products.makeProductLink(
						products.RAccref(d.accref, 
							inputDict={"preview": True}))
				# TODO: preview mime is None for AUTO previews, and there's
				# not much we can do about it.  Or is there?
				internalLinks.append(LinkDef(d.pubDID,
					previewLink, description="A preview for the dataset.",
					contentType=d.previewMime, semantics="#preview"))

		data = rsc.makeData(
			base.caches.getRD("//datalink").getById("make_response"),
			forceSource=self.datalinkLinks+internalLinks+self.errors)
		data.setMeta("_type", "results")

		return votablewrite.makeResource(
			votablewrite.VOTableContext(tablecoding="td"),
			data)

	
class DatalinkCore(DatalinkCoreBase):
	"""A core for processing datalink and processed data requests.

	The input table of this core is dynamically generated from its
	metaMakers; it makes no sense at all to try and override it.

	See `Datalink and SODA`_ for more information.

	In contrast to "normal" cores, one of these is made (and destroyed)
	for each datalink request coming in.  This is because the interface
	of a datalink service depends on the request's value(s) of ID.

	The datalink core can produce both its own metadata and data generated.
	It is the renderer's job to tell them apart.
	"""
	name_ = "datalinkCore"

	datalinkType = "application/x-votable+xml;content=datalink"

	# the core will be specially and non-cacheably adapted for these
	# renderers (ssap.xml is in here for legacy getData):
	datalinkAdaptingRenderers = frozenset([
		"form", "dlget", "dlmeta", "dlasync", "ssap.xml"])

	def _getPubDIDs(self, args):
		"""returns a list of pubDIDs from args["ID"].

		args is supposed to be a nevow request.args-like dict, where the PubDIDs
		are taken from the ID parameter.  If it's atomic, it'll be expanded into
		a list.  If it's not present, a ValidationError will be raised.
		"""
		pubDIDs = args.get("ID")
		if not pubDIDs:
			pubDIDs = []
		elif not isinstance(pubDIDs, list):
			pubDIDs = [pubDIDs]
		return pubDIDs

	def adaptForDescriptors(self, renderer, descriptors):
		"""returns a core for renderer and a sequence of ProductDescriptors.

		This method is mainly for helping adaptForRenderer.  Do read the
		docstring there.
		"""
		try:
			allowedForSvc = set(utils.stealVar("allowedRendsForStealing"))
		except ValueError:
			allowedForSvc = []


		linkDefs, endpoints, errors = [], [], []
		for descriptor in descriptors:
			if isinstance(descriptor, DatalinkFault):
				errors.append(descriptor)

			else:
				lds, inputKeys, lerrs = self.getMetaForDescriptor(descriptor)
				linkDefs.extend(lds)
				errors.extend(lerrs)
	
				# ssap expects the first renderer here to be dlget, so don't
				# remove it or move it back.
				for rendName in ["dlget", "dlasync"]:
					if rendName in allowedForSvc:
						endpoints.append(
							_ServiceDescriptor(descriptor.pubDID, inputKeys, rendName))

		# dispatch on whether we're making metadata (case 1) or actual
		# data (case 2)
		inputKeys = self.inputKeys[:]
		if renderer.name=="dlmeta":
			inputKeys.append(MS(svcs.InputKey, name="REQUEST", 
				type="text", 
				ucd="meta.code",
				multiplicity="single",
				required=False,
				std=True,
				description="Request type (must be getLinks)",
				values=rscdef.Values.fromOptions(
					["getLinks"])))
			inputKeys.append(MS(svcs.InputKey, name="RESPONSEFORMAT", 
				type="text", 
				ucd="meta.code.mime",
				multiplicity="single",
				required=False,
				std=True,
				description="Format of the request document",
				values=rscdef.Values.fromOptions( [
						self.datalinkType,
						"text/xml",
						"votable",
						"application/x-votable+xml"])))

		else:
			# we're a data generating core;  inputKeys are the core's plus 
			# possibly those of actual processors.  Right now, we assume they're
			# all the same, so we take the last one as representative
			#
			# TODO: this restricts the use of the core to dlget and dlasync
			# (see endpoint creation above).  It's not clear that's what we
			# want, as e.g. form may work fine as well.
			if not descriptors:
				raise base.ValidationError("ID is mandatory with dlget",
					"ID")
			if endpoints:
				inputKeys.extend(endpoints[-1].inputKeys)
			if isinstance(descriptors[-1], DatalinkFault):
				descriptors[-1].raiseException()

		res = self.change(inputTable=MS(svcs.InputTable, 
			params=inputKeys))

		# again dispatch on meta or data, this time as regards what to run.
		if renderer.name=="dlmeta":
			res.run = res.runForMeta
		else:
			res.run = res.runForData

		res.nocache = True
		res.datalinkLinks = linkDefs
		res.datalinkEndpoints = endpoints
		res.descriptors = descriptors
		res.errors = errors
		return res

	def adaptForRenderer(self, renderer):
		"""returns a core for a specific product.
	
		The ugly thing about datalink in DaCHS' architecture is that its
		interface (in terms of, e.g., inputKeys' values children) depends
		on the arguments themselves, specifically the pubDID.

		The workaround is to abuse the renderer-specific getCoreFor,
		ignore the renderer and instead steal an "args" variable from
		somewhere upstack.  Nasty, but for now an acceptable solution.

		It is particularly important to never let service cache the
		cores returned for the dl* renderers; hence to "nocache" magic.

		This tries to generate all datalink-relevant metadata in one go 
		and avoid calling the descriptorGenerator(s) more than once per
		pubDID.  It therefore adds datalinkLinks, datalinkEndpoints,
		and datalinkDescriptors attributes.  These are used later
		in either metadata generation or data processing.

		The latter will in general use only the last pubDID passed in.  
		Therefore, this last pubDID determines the service interface
		for now.  Perhaps we should be joining the inputKeys in some way,
		though, e.g., if we want to allow retrieving multiple datasets
		in a tar file?  Or to re-use the same service for all pubdids?
		"""
		# if we're not speaking real datalink, return right away (this will
		# be cached, so this must never happen for actual data)
		if not renderer.name in self.datalinkAdaptingRenderers:
			return self

		try:
			args = utils.stealVar("args")
			if not isinstance(args, dict):
				# again, we're not being called in a context with a pubdid
				raise ValueError("No pubdid")
		except ValueError:
			# no arguments found: decide later on whether to fault out.
			args = {"ID": []}

		pubDIDs = self._getPubDIDs(args)
		descGen = self.descriptorGenerator.compile(self)
		descriptors = []
		for pubDID in pubDIDs:
			try:
				descriptors.append(descGen(pubDID, args))
			except Exception, ex:
				# non-dlmeta exception should go right through to let people redirect
				# (and also because messages might be better).
				if renderer.name!="dlmeta":
					raise
				else:
					if isinstance(ex, base.NotFoundError):
						descriptors.append(DatalinkFault.NotFoundFault(pubDID,
							utils.safe_str(ex)))
					else:
						if base.DEBUG:
							base.ui.notifyError("Error in datalink descriptor generator: %s"%
								utils.safe_str(ex))
						descriptors.append(DatalinkFault.Fault(pubDID,
							utils.safe_str(ex)))

		return self.adaptForDescriptors(renderer, descriptors)
	
	def _iterAccessResources(self, ctx, service):
		"""iterates over the VOTable RESOURCE elements necessary for
		the datalink rows produced by service.
		"""
		for dlSvc in self.datalinkEndpoints:
			yield dlSvc.asVOT(ctx, service.getURL(dlSvc.rendName))

	def runForMeta(self, service, inputTable, queryMeta):
		"""returns a rendered VOTable containing the datalinks.
		"""
		try:
			ctx = votablewrite.VOTableContext(tablecoding="td")
			vot = V.VOTABLE[
					self.getDatalinksResource(ctx, service), 
					self._iterAccessResources(ctx, service)]

			if "text/html" in queryMeta["accept"]:
				# we believe it's a web browser; let it do stylesheet magic
				destMime = "text/xml"
			else:
				destMime = self.datalinkType

			destMime = str(inputTable.getParam("RESPONSEFORMAT") or destMime)
			if destMime=="votable":
				destMime = self.datalinkType
				
			res = (destMime, "<?xml-stylesheet href='/static/xsl/"
				"datalink-to-html.xsl' type='text/xsl'?>"+vot.render())
			return res
		finally:
			self.finalize()

	def runForData(self, service, inputTable, queryMeta):
		"""returns a data set processed according to inputTable's parameters.
		"""
		try:
			args = inputTable.getParamDict()
			if not self.dataFunctions:
				raise base.DataError("This datalink service cannot process data")

			descriptor = self.descriptors[-1]
			self.dataFunctions[0].compile(self)(descriptor, args)

			if descriptor.data is None:
				raise base.ReportableError("Internal Error: a first data function did"
					" not create data.")

			for func in self.dataFunctions[1:]:
				try:
					func.compile(self)(descriptor, args)
				except FormatNow:
					break
				except DeliverNow:
					return descriptor.data

			res = self.dataFormatter.compile(self)(descriptor, args)
			return res
		finally:
			self.finalize()
	
	def finalize(self):
		"""breaks circular references to make the garbage collector's job
		easier.

		The core will no longer function once this has been called.
		"""
		utils.forgetMemoized(self)
		for proc in itertools.chain(self.metaMakers, self.dataFunctions):
			utils.forgetMemoized(proc)
		utils.forgetMemoized(self.descriptorGenerator)
		if self.dataFormatter:
			utils.forgetMemoized(self.dataFormatter)
		self.breakCircles()
		self.run = None
