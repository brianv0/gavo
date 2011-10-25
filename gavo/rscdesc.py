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
		childFactory=registry.ResRec,
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

	def __init__(self, srcId, **kwargs):
		# RDs never have parents, so contrary to all other structures they
		# are constructed with with a srcId instead of a parent.  You
		# *can* have that None, but such RDs cannot be used to create
		# non-temporary tables, services, etc, since the srcId is used
		# in the construction of identifiers and such.
		self.sourceId = srcId
		base.Structure.__init__(self, None, **kwargs)
		# The rd attribute is a weakref on self.  Always.  So, this is the class
		# that in roots common.RDAttributes
		self.rd = weakref.proxy(self)
		# real dateUpdated is set by getRD, this is just for RDs created
		# on the fly.
		self.dateUpdated = datetime.datetime.utcnow()
		# if an RD is parsed from a disk file, this gets set to its path
		# by getRD below
		self.srcPath = None
		# this is for modified-since and friends.
		self.loadedAt = time.time()
		# keep track of RDs depending on us for the registry code
		# (only read this)
		self.rdDependencies = set()

	def __iter__(self):
		return iter(self.dds)

	def __repr__(self):
		return "<resource descriptor for %s>"%self.sourceId

	def isDirty(self):
		"""returns true if the RD on disk has a timestamp newer than
		loadedAt.
		"""
		try:
			if self.srcPath is not None:
				return os.path.getmtime(self.srcPath)>self.loadedAt
		except os.error:
			# this could mean the file went away (in which case we should
			# be dirty), but mostly it's something from pkg_resources which
			# isn't supposed to change.  So, most of the time returning false
			# should be all right...
			return False
		return False

	def importModule(self, ctx):
		# this is a callback for the require attribute
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

	def openRes(self, relPath, mode="r"):
		"""returns a file object for relPath within self's resdir.
		"""
		return open(os.path.join(self.resdir, relPath), mode)

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

	def _computeIdmap(self):
		res = {}
		for child in self.iterChildren():
			if hasattr(child, "id"):
				res[child.id] = child
		return res

	def addDependency(self, rd, prereq):
		"""declares that rd needs the RD prereq to properly work.

		This is used in the generation of resource records to ensure that, e.g.
		registred data have added their served-bys to the service resources.
		"""
		if rd.sourceId!=prereq.sourceId:
			self.rdDependencies.add((rd.sourceId, prereq.sourceId))

	def copy(self, parent):
		base.ui.notifyWarning("Copying an RD -- this may not be a good idea")
		new = base.Structure.copy(self, parent)
		new.idmap = new._computeIdmap()
		new.sourceId = self.sourceId
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


def canonicalizeRDId(srcId):
	"""returns a standard rd id for srcId.

	srcId may be a file system path, or it may be an "id".  The canonical
	basically is "inputs-relative path without .rd extension".  Everything
	that's not within inputs or doesn't end with .rd is handed through.
	// is expanded to __system__/.  The path to built-in RDs,
	/resources/inputs, is treated analoguous to inputsDir.

	TODO: We should probably reject everything that's neither below inputs
	nor below resources.
	"""
	if srcId.startswith("//"):
		srcId = "__system__"+srcId[1:]

	for inputsDir in (base.getConfig("inputsDir"), "/resources/inputs"):
		if srcId.startswith(inputsDir):
			srcId = srcId[len(inputsDir):].lstrip("/")
	
	if srcId.endswith(".rd"):
		srcId = srcId[:-3]

	return srcId


def _getFilenamesForId(srcId):
	"""helps getRDInputStream by iterating over possible files for srcId.
	"""
	if srcId.startswith("/"):
		yield srcId+".rd"
		yield srcId
	else:
		inputsDir = base.getConfig("inputsDir")
		yield os.path.join(inputsDir, srcId)+".rd"
		yield os.path.join(inputsDir, srcId)
		yield "/resources/inputs/%s.rd"%srcId
		yield "/resources/inputs/%s"%srcId


def getRDInputStream(srcId):
	"""returns a read-open stream for the XML source of the resource
	descriptor with srcId.

	srcId is already normalized; that means that absolute paths must
	point to a file (sans possibly .rd), relative paths are relative
	to inputsDir or pkg_resources(/resources/inputs).

	This function prefers files with .rd to those without, and
	inputsDir to pkg_resources (the latter allowing the user to
	override built-in system RDs).
	"""
	for fName in _getFilenamesForId(srcId):
		if os.path.isfile(fName):
			return fName, open(fName)
		if (pkg_resources.resource_exists('gavo', fName)
				and not pkg_resources.resource_isdir('gavo', fName)):
			return fName, pkg_resources.resource_stream('gavo', fName)
	raise base.RDNotFound(srcId)


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
# parsed.  The keys are the sourceIds, the values are pairs of
# RLock and the RD object.
_currentlyParsing = {}

def getRD(srcId, forImport=False, doQueries=True, dumpTracebacks=False,
		restricted=False):
	"""returns a ResourceDescriptor for srcId.

	srcId is something like an input-relative path; you'll generally
	omit the extension (unless it's not the standard .rd).

	getRD furnishes the resulting RD with an idmap attribute containing
	the mapping from id to object collected by the parse context.
	"""
	rd = RD(canonicalizeRDId(srcId))
	srcPath, inputFile = getRDInputStream(rd.sourceId)
	context = RDParseContext(forImport, doQueries, dumpTracebacks, restricted)
	rd.srcPath = context.srcPath = os.path.abspath(srcPath)
	context.forRD = rd.sourceId
	rd.idmap = context.idmap

	# concurrency handling (threads suck -- I shouldn't have gone down that
	# way...)
	if rd.sourceId in _currentlyParsing:
		lock, rd = _currentlyParsing[rd.sourceId]
		# lock is an RLock, which means the following will block for
		# all threads but the currently parsing one.  This lets us
		# have recursive definitions in RDs (while still not allowing
		# forward references).
		lock.acquire()
		return rd
	else:
		lock = threading.RLock()
		_currentlyParsing[rd.sourceId] = lock, rd
		lock.acquire()

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


def _makeRDCache():
	"""installs the cache for RDs.

	The main trick here is to handle "aliasing", i.e. making sure that
	you get identical objects regardless of whether you request
	__system__/adql.rd, __system__/adql, or //adql.
	"""
	rdCache = {}

	def getRDCached(srcId, **kwargs):
		if kwargs:
			return getRD(srcId, **kwargs)
		srcId = canonicalizeRDId(srcId)

		if srcId in rdCache and rdCache[srcId].isDirty():
			base.caches.clearForName(srcId)

		if srcId not in rdCache:
			rd = getRD(srcId)
			rdCache[srcId] = rd
		return rdCache[srcId]
	
	base.caches.registerCache("getRD", rdCache, getRDCached)

_makeRDCache()


def openRD(relPath):
	"""returns a (cached) RD for relPath.

	relPath is first interpreted as a file system path, then as an RD id.
	the first match wins.
	"""
	try:
		return base.caches.getRD(os.path.join(os.getcwd(), relPath), forImport=True)
	except base.RDNotFound:
		return base.caches.getRD(relPath, forImport=True)


