"""
Structure definition of resource descriptors.

The stuff they are describing is not a resource in the VO sense (whatever
that is) or in the Dublin Core sense, but simply stuff held together
by common metadata.  If it's got the same creator, the same base title,
the same keywords, etc., it's described by one RD.

In the GAVO DC, a resource descriptor in general sets up a schema in
the database.
"""

import datetime
import grp
import os
import pkg_resources
import time
import threading
import traceback
import warnings
import weakref

from gavo import base
from gavo import registry
from gavo import rscdef
from gavo import svcs
from gavo import utils
from gavo.rscdef import common
from gavo.rscdef import scripting


class ResRec(base.Structure, base.MetaMixin, base.StandardMacroMixin):
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
	
	Additional meta keys may be required depdending on resType.  See the
	tutorial chapter on registry support.
	"""
	name_ = "resRec"
	_rd = rscdef.RDAttribute()


class RD(base.Structure, base.ComputedMetaMixin, scripting.ScriptingMixin,
		base.StandardMacroMixin, common.RolesMixin, registry.DateUpdatedMixin):
	"""A resource descriptor (RD); the root for all elements described here.
	
	RDs collect all information about how to parse a particular source (like a
	collection of FITS images, a catalogue, or whatever), about the database
	tables the data ends up in, and the services used to access them.
	"""
	name_ = "resource"

	_resdir = base.FunctionRelativePathAttribute("resdir", 
		default=None, 
		baseFunction=lambda instance: base.getConfig("inputsDir"),
		description="Base directory for source files and everything else"
			" belonging to the resource.", 
		copyable=True)

	_schema = base.UnicodeAttribute("schema", 
		default=base.Undefined,
		description="Database schema for tables defined here.", 
		copyable=True,
		callbacks=["_inferResdir"])

	_dds = base.StructListAttribute("dds", 
		childFactory=rscdef.DataDescriptor,
		description="Descriptors for the data generated and/or published"
		" within this resource.", 
		copyable=True, 
		before="outputTables")

	_tables = base.StructListAttribute("tables",
		childFactory=rscdef.TableDef, 
		description="A table used or created by this resource", 
		copyable=True, 
		before="dds")

	_outputTables = base.StructListAttribute("outputTables",
		childFactory=svcs.OutputTableDef, 
		description="Canned output tables for later reference.", 
		copyable=True)

	_rowmakers = base.StructListAttribute("rowmakers",
		childFactory=rscdef.RowmakerDef, 
		description="Transformations for going from grammars to tables."
			" If specified in the RD, they must be referenced from make"
			" elements to become active.",
		copyable=True, 
		before="dds")

	_procDefs = base.StructListAttribute("procDefs", 
		childFactory=rscdef.ProcDef,
		description="Procedure definintions (rowgens, rowmaker applys)",
		copyable=True, before="rowmakers")

	_condDescs = base.StructListAttribute("condDescs", 
		childFactory=svcs.CondDesc,
		description="Global condition descriptors for later reference", 
		copyable=True, 
		before="cores")

	_resRecs = base.StructListAttribute("resRecs",
		childFactory=ResRec,
		description="Non-service resources for the IVOA registry.  They will"
			" be published when gavo publish is run on the RD.")

	_services = base.StructListAttribute("services", 
		childFactory=svcs.Service, 
		description="Services exposing data from this resource.", 
		copyable=True)

	_macDefs = base.MacDefAttribute(before="tables", 
		description="User-defined macros available on this RD")

	_mixinDefs = base.StructListAttribute("mixdefs",
		childFactory=rscdef.MixinDef,
		description="Mixin definitions (usually not for users)")

	_require = base.ActionAttribute("require", 
		methodName="importModule",
		description="Import the named gavo module (for when you need something"
		" registred)")

	_cores = base.MultiStructListAttribute("cores", 
		childFactory=svcs.getCore, 
		childNames=svcs.CORE_REGISTRY.keys(),
		description="Cores available in this resource.", copyable=True,
		before="services")

	# These replace themselves with expanded tables
	_viewDefs = base.StructAttribute("simpleView",
		childFactory=rscdef.SimpleView, 
		description="Definitions of views created from natural joins", 
		default=None)

	_properties = base.PropertyAttribute()

	def __init__(self, parent, **kwargs):
	#	parent should in general be None, I guess, but I'll leave the signature
	#	as-is in case I ever need super().__init__ on Structures.
		base.Structure.__init__(self, parent, **kwargs)
		# The rd attribute is a weakref on self.  Always.  So, this is the class
		# that in roots common.RDAttributes
		self.rd = weakref.proxy(self)
		# RDs can be Anonymous.  The sourceId is only important in operations
		# like inserting into the dc_tables#tablemeta table.  These should fail
		# on anonymous RDs (and in this case will because parts of primary
		# keys must not be NULL)
		self.sourceId = None
		# real dateUpdated is set by getRD, this is just for RDs created
		# on the fly.
		self.dateUpdated = datetime.datetime.utcnow()
		# this is for modified-since and friends.
		self.loadedAt = time.time()

	def __iter__(self):
		return iter(self.dds)

	def __repr__(self):
		return "<resource descriptor for %s>"%self.sourceId

	def importModule(self, ctx):
		utils.loadInternalObject(self.require, "__doc__")

	def onElementComplete(self):
		for table in self.tables:
			self.readRoles = self.readRoles|table.readRoles
			table.setMetaParent(self)
		self.serviceIndex = {}
		for svc in self.services:
			self.serviceIndex[svc.id] = svc
			svc.setMetaParent(self)
		for dd in self.dds:
			dd.setMetaParent(self)
		if self.resdir and not os.path.isdir(self.resdir):
			base.ui.notifyWarning("RD %s: resource directory '%s' does not exist"%(
				self.sourceId, self.resdir))
		self._onElementCompleteNext(RD)

	def _inferResdir(self, value):
		if self.resdir is None:
			self._resdir.feedObject(self, value)

	def iterDDs(self):
		return iter(self.dds)

	def getService(self, id):
		return self.serviceIndex.get(id, None)

	def getTableDefById(self, id):
		return self.getById(id, rscdef.TableDef)
	
	def getDataDescById(self, id):
		return self.getById(id, rscdef.DataDescriptor)
	
	def getById(self, id, forceType=None):
		try:
			res = self.idmap[id]
		except KeyError:
			raise base.ui.logOldExc(base.StructureError(
				"No element with id '%s' found in RD %s"%(id, self.sourceId)))
		if forceType:
			if not isinstance(res, forceType):
				raise base.StructureError("Element with id '%s' is not a %s"%(
					id, forceType.__name__))
		return res

	def getTimestampPath(self):
		"""returns a path to a file that's accessed by Resource each time 
		a bit of the described resource is written to the db.
		"""
		return os.path.join(base.getConfig("stateDir"), "updated_"+
			self.sourceId.replace("/", "+"))

	def touchTimestamp(self):
		"""updates the timestamp on the rd's state file.
		"""
		fn = self.getTimestampPath()
		try:
			try: 
				os.unlink(fn)
			except os.error: 
				pass
			f = open(fn, "w")
			f.close()
			os.chmod(fn, 0664)
			try:
				os.chown(fn, -1, grp.getgrnam(base.getConfig("GavoGroup")[2]))
			except (KeyError, os.error):
				pass
		except (os.error, IOError):
			warnings.warn("Could not update timestamp on RD %s"%self.sourceId)

	def computeSourceId(self, sourcePath):
		"""returns the inputsDir-relative path to the rd.

		Any extension is purged, too.  This value can be accessed as the
		sourceId attribute.
		"""
		if sourcePath.startswith(base.getConfig("inputsDir")):
			sourcePath = sourcePath[len(base.getConfig("inputsDir")):].lstrip("/")
		if sourcePath.startswith("/resources/inputs"):
			sourcePath = sourcePath[len("/resources/inputs"):].lstrip("/")
		self.sourceId = os.path.splitext(sourcePath)[0]

	def _computeIdmap(self):
		res = {}
		for child in self.iterChildren():
			if hasattr(child, "id"):
				res[child.id] = child
		return res

	def copy(self, parent):
		new = base.Structure.copy(self, parent)
		new.idmap = new._computeIdmap()
		new.sourceId = "(copy of) "+str(self.sourceId)
		return new


class RDParseContext(base.ParseContext):
	"""is a parse context for RDs.

	It defines a couple of attributes that structures can ask for (however,
	it's good practice not to rely on their presence in case someone wants
	to parse XML snippets with a standard parse context, so use 
	getattr(ctx, "doQueries", True) or somesuch.
	"""
	def __init__(self, forImport=False, doQueries=True, dumpTracebacks=False, 
			restricted=False, forRD=None):
		self.forImport, self.doQueries = forImport, doQueries
		self.dumpTracebacks = dumpTracebacks
		base.ParseContext.__init__(self, restricted, forRD)


def getRDInputStream(srcId):
	"""returns a read-open stream for the XML source of the resource
	descriptor with srcId.
	"""
	userInput = srcId
	if srcId.startswith("//"):
		srcId = "__system__"+srcId[1:]
	srcPath = os.path.join(base.getConfig("inputsDir"), srcId)
	if os.path.isfile(srcPath):
		return srcPath, open(srcPath)
	if not srcId.endswith(".rd"):
		srcId = srcId+".rd"
	srcPath = os.path.join(base.getConfig("inputsDir"), srcId)
	if os.path.isfile(srcPath):
		return srcPath, open(srcPath)
	srcPath = "/resources/inputs/"+srcId
	if pkg_resources.resource_exists('gavo', srcPath):
		return srcPath, pkg_resources.resource_stream('gavo', srcPath)
	raise base.RDNotFound(userInput)


def setRDDateTime(rd, inputFile):
	"""guesses a date the resource was updated.

	This uses either the timestamp on inputFile or the rd's import timestamp,
	whatever is newer.
	"""
# this would look better as a method on RD, and maybe it would be cool
# to just try to infer the inputFile from the ID?
	rdTimestamp = utils.fgetmtime(inputFile)
	try:
		dataTimestamp = os.path.getmtime(rd.getTimestampPath())
	except os.error: # no timestamp yet
		dataTimestamp = rdTimestamp
	rd.timestampUpdated = max(dataTimestamp, rdTimestamp)
	rd.dateUpdated = datetime.datetime.utcfromtimestamp(
		rd.timestampUpdated)


# in _currentlyParsing, getRD keeps track of what RDs are currently being
# parsed.  For those, the unfinished RD is being returned.  This allows
# qualified references within RDs and to some extent even circular
# cross-RD references.
_currentlyParsing = {}

def getRD(srcId, forImport=False, doQueries=True, dumpTracebacks=False,
		restricted=False):
	"""returns a ResourceDescriptor for srcId.

	srcId is something like an input-relative path; you'll generally
	omit the extension (unless it's not the standard .rd).

	getRD furnishes the resulting RD with an idmap attribute containing
	the mapping from id to object collected by the parse context.
	"""
	srcPath, inputFile = getRDInputStream(srcId)
	context = RDParseContext(forImport, doQueries, dumpTracebacks, restricted)
	context.srcPath = srcPath
	rd = RD(None)
	rd.idmap = context.idmap
	rd.computeSourceId(srcPath)
	if rd.sourceId in _currentlyParsing:
		lock, rd = _currentlyParsing[rd.sourceId]
		lock.acquire()
		return rd
	else:
		lock = threading.RLock()
		_currentlyParsing[rd.sourceId] = lock, rd
		lock.acquire()
	context.forRD = rd.sourceId
	try:
		try:
			rd = base.parseFromStream(rd, inputFile, context=context)
		except Exception, ex:
			ex.srcPath = srcPath
			raise
	finally:
		del _currentlyParsing[rd.sourceId]
		lock.release()
	setRDDateTime(rd, inputFile)
	return rd


base.caches.makeCache("getRD", getRD)
