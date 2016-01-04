"""
Definition of data.

Data descriptors describe what to do with data. They contain 
a grammar, information on where to obtain source data from, and "makes",
a specification of the tables to be generated and how they are made
from the grammar output.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import fnmatch
import glob
import os

from gavo import base
from gavo import utils
from gavo.rscdef import builtingrammars
from gavo.rscdef import column
from gavo.rscdef import common
from gavo.rscdef import rmkdef
from gavo.rscdef import scripting
from gavo.rscdef import tabledef


class IgnoreSpec(base.Structure):
	"""A specification of sources to ignore.

	Sources mentioned here are compared against the inputsDir-relative path
	of sources generated by sources (cf. `Element sources`_).  If there is
	a match, the corresponding source will not be processed.

	You can get ignored files from various sources.  If you give more
	than one source, the set of ignored files is the union of the the 
	individual sets.
	"""
	name_ = "ignoreSources"

	_fromdb = base.UnicodeAttribute("fromdb", default=None,
		description="A DB query to obtain a set of sources to ignore; the"
			" select clause must select exactly one column containing the"
			" source key.")
	_fromfile = common.ResdirRelativeAttribute("fromfile", default=None,
		description="A name of a file containing blacklisted source"
			" paths, one per line.  Empty lines and lines beginning with a hash"
			" are ignored.")
	_patterns = base.ListOfAtomsAttribute("patterns", description=
		"Shell patterns to ignore.  Slashes are treated like any other"
		" character, i.e., patterns do not know about paths.",
		itemAttD=base.UnicodeAttribute("pattern", description="Shell pattern"
			" for source file(s), relative to resource directory."),
		copyable=True)
	_rd = common.RDAttribute()

	def prepare(self, connection):
		"""sets attributes to speed up isIgnored()
		"""
		self.inputsDir = base.getConfig("inputsDir")
		self.ignoredSet = set()

		if self.fromdb and connection is not None:
			try:
				with base.savepointOn(connection):
					self.ignoredSet |= set(r[0] 
						for r in connection.query(self.fromdb))
			except base.DBError: # table probably doesn't exist yet.
				base.ui.notifyError("ignore fromdb failed (probably no table yet)")

		if self.fromfile:
			for ln in open(self.fromfile):
				ln = ln.strip()
				if ln and not ln.startswith("#"):
					self.ignoredSet.add(ln)

	def isIgnored(self, path):
		"""returns true if path, made inputsdir-relative, should be ignored.
		"""
		try:
			path = utils.getRelativePath(path, self.inputsDir, liberalChars=True)
		except ValueError: # not in inputs, use full path.
			pass
		if path in self.ignoredSet:
			return True
		for pat in self.patterns:
			if fnmatch.fnmatch(path, pat):
				return True
		return False


class SourceSpec(base.Structure):
	"""A Specification of a data descriptor's inputs.
	"""
	name_ = "sources"

	_patterns = base.ListOfAtomsAttribute("patterns", description=
		"Paths to the source files.  You can use shell patterns here.",
		itemAttD=base.UnicodeAttribute("pattern", description="Shell pattern"
			" for source file(s), relative to resource directory."),
		copyable=True)
	_items = base.ListOfAtomsAttribute("items", description=
		"String literals to pass to grammars.  In contrast to patterns,"
		" they are not interpreted as file names but passed to the"
		" grammar verbatim.  Normal grammars do not like this. It is"
		" mainly intended for use with custom or null grammars.",
		itemAttD=base.UnicodeAttribute("item", 
			description="Grammar-specific string"), copyable=True)
	_recurse = base.BooleanAttribute("recurse", default=False,
		description="Search for pattern(s) recursively in their directory"
			" part(s)?", copyable=True)
	_ignore = base.StructAttribute("ignoredSources", childFactory=
		IgnoreSpec, description="Specification of sources that should not"
			" be processed although they match patterns.  Typically used"
			" in update-type data descriptors.", copyable=True)
	_file = base.DataContent(description="A single"
		" file name (this is for convenience)", copyable="True")
	_original = base.OriginalAttribute()

	def __iter__(self):
		return self.iterSources()

	def completeElement(self, ctx):
		if self.ignoredSources is base.Undefined:
			self.ignoredSources = base.makeStruct(IgnoreSpec)
		self._completeElementNext(SourceSpec, ctx)

	def _expandDirParts(self, dirParts, ignoreDotDirs=True):
		"""expands a list of directories into a list of them and all their
		descendants.

		It follows symbolic links but doesn't do any bookkeeping, so bad
		things will happen if the directory graph contains cycles.
		"""
		res = []
		for root in dirParts:
			for root, dirs, files in os.walk(root):
				if ignoreDotDirs:
					if os.path.basename(root).startswith("."):
						continue
					dirs = [dir for dir in dirs if not dir.startswith(".")]
				dirs = (os.path.join(root, dir) for dir in dirs)
				res.extend(dir for dir in dirs if os.path.isdir(dir))
				for child in files:
					destName = os.path.join(root, child)
					if os.path.islink(destName) and not os.path.isfile(destName):
						res.extend(self._expandDirParts(destName))
		return res

	def iterSources(self, connection=None):
		self.ignoredSources.prepare(connection)
		for item in self.items:
			if not self.ignoredSources.isIgnored(item):
				yield item

		baseDir = ""
		if self.parent.rd:
			baseDir = self.parent.rd.resdir

		for pattern in self.patterns:
			dirPart, baseName = os.path.split(pattern)
			if self.parent.rd:
				dirParts = [os.path.join(baseDir, dirPart)]
			else:
				dirParts = [dirPart]
			if self.recurse:
				dirParts = dirParts+self._expandDirParts(dirParts)
			for dir in dirParts:
				for name in glob.glob(os.path.join(dir, baseName)):
					fullName = os.path.abspath(name)
					if not self.ignoredSources.isIgnored(fullName):
						yield fullName
		if self.content_:
			yield os.path.abspath(os.path.join(baseDir, self.content_))
	
	def __nonzero__(self):
		return (not not self.patterns) or (not not self.items
			) or (not not self.content_)


class Make(base.Structure, scripting.ScriptingMixin):
	"""A build recipe for tables belonging to a data descriptor.

	All makes belonging to a DD will be processed in the order in which they
	appear in the file.
	"""
	name_ = "make"

	_table = base.ReferenceAttribute("table", 
		description="Reference to the table to be embedded",
		default=base.Undefined, 
		copyable=True,
		forceType=tabledef.TableDef)

	_rowmaker = base.ReferenceAttribute("rowmaker", 
		default=base.NotGiven,
		forceType=rmkdef.RowmakerDef,
		description="The rowmaker (i.e., mapping rules from grammar keys to"
		" table columns) for the table being made.", 
		copyable=True)

	_parmaker = base.ReferenceAttribute("parmaker", 
		default=base.NotGiven,
		forceType=rmkdef.ParmakerDef,
		description="The parmaker (i.e., mapping rules from grammar parameters"
		" to table parameters) for the table being made.  You will usually"
		" not give a parmaker.",
		copyable=True)

	_role = base.UnicodeAttribute("role", 
		default=None,
		description="The role of the embedded table within the data set",
		copyable=True)
	
	_rowSource = base.EnumeratedUnicodeAttribute("rowSource",
		default="rows",
		validValues=["rows", "parameters"],
		description="Source for the raw rows processed by this rowmaker.",
		copyable=True,
		strip=True)

	def __repr__(self):
		return "Make(table=%r, rowmaker=%r)"%(
			self.table and self.table.id, self.rowmaker and self.rowmaker.id)

	def onParentComplete(self):
		if self.rowmaker is base.NotGiven:
			self.rowmaker = rmkdef.RowmakerDef.makeIdentityFromTable(self.table)

	def getExpander(self):
		"""used by the scripts of expanding their source.

		We always return the expander of the table being made.
		"""
		return self.table.getExpander()
	
	def create(self, connection, parseOptions, tableFactory, **kwargs):
		"""returns a new empty instance of the table this is making.
		"""
		newTable = tableFactory(self.table,
			parseOptions=parseOptions, connection=connection, role=self.role,
			create=True, **kwargs)
		if (self.table.onDisk
				and not parseOptions.updateMode 
				and not getattr(self.parent, "updating", False)):
			newTable._runScripts = self.getRunner()
		return newTable
	
	def runParmakerFor(self, grammarParameters, destTable):
		"""feeds grammarParameter to destTable.
		"""
		if self.parmaker is base.NotGiven:
			return
		parmakerFunc = self.parmaker.compileForTableDef(destTable.tableDef)
		destTable.setParams(parmakerFunc(grammarParameters, destTable),
			raiseOnBadKeys=False)


class DataDescriptor(base.Structure, base.ComputedMetaMixin, 
		common.IVOMetaMixin):
	"""A description of how to process data from a given set of sources.

	Data descriptors bring together a grammar, a source specification and
	"makes", each giving a table and a rowmaker to feed the table from the
	grammar output.

	They are the "executable" parts of a resource descriptor.  Their ids
	are used as arguments to gavoimp for partial imports.
	"""
	name_ = "data"
	resType = "data"

	_rowmakers = base.StructListAttribute("rowmakers",
		childFactory=rmkdef.RowmakerDef, 
		description="Embedded build rules (usually rowmakers are defined toplevel)",
		copyable=True,
		before="makes")

	_registration = base.StructAttribute("registration",
		default=None,
		childFactory=common.Registration,
		copyable=False,
		description="A registration (to the VO registry) of this data collection.")

	_tables = base.StructListAttribute("tables",
		childFactory=tabledef.TableDef, 
		description="Embedded table definitions (usually, tables are defined"
			" toplevel)", 
		copyable=True,
		before="makes")

	_grammar = base.MultiStructAttribute("grammar", 
		default=None,
		childFactory=builtingrammars.getGrammar,
		childNames=builtingrammars.GRAMMAR_REGISTRY.keys(),
		description="Grammar used to parse this data set.", 
		copyable=True,
		before="makes")
	
	_sources = base.StructAttribute("sources", 
		default=None, 
		childFactory=SourceSpec,
		description="Specification of sources that should be fed to the grammar.",
		copyable=True,
		before="grammar")

	_dependents = base.ListOfAtomsAttribute("dependents",
		itemAttD=base.UnicodeAttribute("recreateAfter"),
		description="A data ID to recreate when this resource is"
			" remade; use # syntax to reference in other RDs.")

	_auto = base.BooleanAttribute("auto", 
		default=True, 
		description="Import this data set if not explicitly"
			" mentioned on the command line?")

	_updating = base.BooleanAttribute("updating", 
		default=False,
		description="Keep existing tables on import?  You usually want this"
			" False unless you have some kind of sources management,"
			" e.g., via a sources ignore specification.", 
		copyable=True)

	_makes = base.StructListAttribute("makes", 
		childFactory=Make,
		copyable=True, 
		description="Specification of a target table and the rowmaker"
			" to feed them.")
	
	_params = common.ColumnListAttribute("params",
		childFactory=column.Param, 
		description='Param ("global columns") for this data (mostly for'
		 ' VOTable serialization).', 
		copyable=True)

	_properties = base.PropertyAttribute()

	_rd = common.RDAttribute()

	_original = base.OriginalAttribute()

	metaModel = ("title(1), creationDate(1), description(1),"
		"subject, referenceURL(1)")

	def __repr__(self):
		return "<data descriptor with id %s>"%self.id

	def validate(self):
		self._validateNext(DataDescriptor)
		if self.registration and self.id is None:
			raise base.StructureError("Published data needs an assigned id.")

	def onElementComplete(self):
		self._onElementCompleteNext(DataDescriptor)
		for t in self.tables:
			t.setMetaParent(self)
		if self.registration:
			self.registration.register()

	# since we want to be able to create DDs dynamically , they must find their
	# meta parent themselves.  We do this while the DD is being adopted;
	# the rules here are: if the parent is a meta mixin itself, it's the
	# meta parent, if it has an rd attribute, use that, else give up.
	# TODO: For DDs on cores, it would be *desirable* to come up
	# with some magic that makes the current service their meta parent.

	def _getParent(self):
		return self.__parent
	
	def _setParent(self, value):
		self.__parent = value
		if isinstance(value, base.MetaMixin):
			self.setMetaParent(value)
		elif hasattr(value, "rd"):
			self.setMetaParent(value.rd)
	
	parent = property(_getParent, _setParent)

	def iterSources(self, connection=None):
		if self.sources:
			return self.sources.iterSources(connection)
		else:
			return iter([])

	def __iter__(self):
		for m in self.makes:
			yield m.table

	def iterTableDefs(self):
		"""iterates over the definitions of all the tables built by this DD.
		"""
		for m in self.makes:
			yield m.table

	def getTableDefById(self, id):
		for td in self.iterTableDefs():
			if td.id==id:
				return td
		raise base.StructureError("No table name %s will be built"%id)

	def getTableDefWithRole(self, role):
		for m in self.makes:
			if m.role==role:
				return m.table
		raise base.StructureError("No table def with role '%s'"%role)

	def getPrimary(self):
		"""returns the "primary" table definition in the data descriptor.

		"primary" means the only table in a one-table dd, the table with the
		role "primary" if there are more.  If no matching table is found, a
		StructureError is raised.
		"""
		if len(self.makes)==1:
			return self.makes[0].table
		else:
			try:
				return self.getTableDefWithRole("primary")
			except base.StructureError: # raise more telling message
				pass
		raise base.StructureError("Ambiguous request for primary table")

	def copyShallowly(self):
		"""returns a shallow copy of self.

		Sources are not copied.
		"""
		return DataDescriptor(self.parent, rowmakers=self.rowmakers[:],
			tables=self.tables[:], grammar=self.grammar, makes=self.makes[:])
	
	def getURL(self, rendName, absolute=True):
		# there's no sensible URL for DDs; thus, let people browse
		# the RD info.  At least they should find links to any tables
		# included here there.
		basePath = "%sbrowse/%s"%(
			base.getConfig("web", "nevowRoot"),
			self.rd.sourceId)
		if absolute:
			return base.getConfig("web", "serverURL")+basePath
		return basePath
