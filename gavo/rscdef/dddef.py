"""
Definition of data.

Data descriptors describe what to do with data. They contain 
a grammar, information on where to obtain source data from, and "makes",
a specification of the tables to be generated and how they are made
from the grammar output.
"""

import glob
import os

from gavo import base
from gavo.rscdef import common
from gavo.rscdef import rmkdef
from gavo.rscdef import scripting
from gavo.rscdef import tabledef


class IgnoreSpec(base.Structure):
	"""is a specificatioin of sources to ignore.
	"""
	name_ = "ignoreSources"

	_fromdb = base.UnicodeAttribute("fromdb", default=None,
		description="A DB query to obtain a set of sources to ignore; the"
			" select clause must select exactly one column containing the"
			" source key.")

	def prepare(self):
		"""sets attributes to speed up isIgnored()
		"""
		self.inputsDir = base.getConfig("inputsDir")
		self.ignoredSet = set()
		if self.fromdb:
			try:
				self.ignoredSet |= set(r[0] 
					for r in base.SimpleQuerier().runIsolatedQuery(self.fromdb))
			except base.DBError: # table probably doesn't exist yet.
				pass

	def isIgnored(self, path):
		"""returns true if path, made inputsdir-relative, should be ignored.
		"""
		try:
			path = base.getRelativePath(path, self.inputsDir)
		except base.LiteralParseError: # not in inputs, use full path.
			pass
		if path in self.ignoredSet:
			return True
		return False


class SourceSpec(base.Structure):
	"""is a specification of source files.
	"""
	name_ = "sources"

	_patterns = base.ListOfAtomsAttribute("patterns",
		itemAttD=base.UnicodeAttribute("pattern", description="Shell pattern"
			" for source file(s), relative to resource directory."),
		copyable=True)
	_recurse = base.BooleanAttribute("recurse", default=False,
		description="Search for pattern(s) recursively in their directory"
			" part(s)?", copyable=True)
	_ignore = base.StructAttribute("ignoredSources", childFactory=
		IgnoreSpec)

	def completeElement(self):
		if self.ignoredSources is base.Undefined:
			self.ignoredSources = base.makeStruct(IgnoreSpec)
		self._completeElementNext(SourceSpec)

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
					if os.path.islink(os.path.join(root, child)):
						res.expand(self._expandDirParts(os.path.join(root, child)))
		return res

	def iterSources(self):
		self.ignoredSources.prepare()
		for pattern in self.patterns:
			dirPart, baseName = os.path.split(pattern)
			if self.parent.rd:
				dirParts = [os.path.join(self.parent.rd.resdir, dirPart)]
			else:
				dirParts = [dirPart]
			if self.recurse:
				dirParts = dirParts+self._expandDirParts(dirParts)
			for dir in dirParts:
				for name in glob.glob(os.path.join(dir, baseName)):
					fullName = os.path.abspath(name)
					if not self.ignoredSources.isIgnored(fullName):
						yield fullName
	
	def __nonzero__(self):
		return not not self.patterns


class GrammarAttribute(base.StructAttribute):
	"""is an attribute containing some kind of grammar.

	This is a bit funky in that it's polymorphous.  We look up the
	class that's actually going to be created in the parent's class
	registry.

	This really only works on DataDescriptors.
	"""
	def __init__(self, name, description, **kwargs):
		base.AttributeDef.__init__(self, name, 
			default=None, description=description, **kwargs)

	def create(self, structure, name):
		return getGrammar(name)(structure)


class Make(base.Structure):
	"""is a definition for a Table within a Data instance.

	The idea is that you combine a table definition with a rowmaker that
	builds the table and possibly the role of the resulting table.
	"""
# Allow embedding maps, idmaps, defaults for auto-rowmaker?
	name_ = "make"

	_table = base.ReferenceAttribute("table", forceType=tabledef.TableDef,
		description="Reference to the table to be embedded",
		default=base.Undefined, copyable=True)
	_rowmaker = base.ReferenceAttribute("rowmaker", forceType=rmkdef.RowmakerDef,
		description="Rowmaker for this table", default=base.NotGiven,
		copyable=True)
	_role = base.UnicodeAttribute("role", default=None,
		description="The role of the embedded table within the data set",
		copyable=True)

	def onParentCompleted(self):
		if self.rowmaker is base.NotGiven:
			if (self.parent and self.parent.grammar and 
					self.parent.grammar.yieldsTyped):
				self.rowmaker = rmkdef.RowmakerDef.makeTransparentFromTable(self.table)
			else:
				self.rowmaker = rmkdef.RowmakerDef.makeIdentityFromTable(self.table)


class DataDescriptor(base.Structure, base.MetaMixin, scripting.ScriptingMixin):
	name_ = "data"

	_rowmakers = base.StructListAttribute("rowmakers",
		childFactory=rmkdef.RowmakerDef, 
		description="Embedded build rules (usually rowmakers are defined toplevel)",
		copyable=True)
	_tables = base.StructListAttribute("tables",
		childFactory=tabledef.TableDef, 
		description="Embedded table definitions (usually, tables are defined"
			" toplevel)", copyable=True)
	# polymorphous through getDynamicAttribute
	_grammar = GrammarAttribute("grammar", description="Grammar used"
		" to parse this data set", copyable=True)
	_sources = base.StructAttribute("sources", default=None, 
		childFactory=SourceSpec,
		description="Specification of sources that should be fed to the grammar.",
		copyable=True)
	_dependents = base.ListOfAtomsAttribute("dependents",
		itemAttD=base.UnicodeAttribute("recreateAfter"),
		description="List of data IDs to recreate when this resource is"
			" remade")
	_auto = base.BooleanAttribute("auto", default=True, description=
		"Import this data set without explicit mention on the command line?")
	_makes = base.StructListAttribute("makes", childFactory=Make,
		copyable=True)
	_properties = base.PropertyAttribute()
	_rd = common.RDAttribute()
	_original = base.OriginalAttribute()
	_ref = base.RefAttribute()

	validWaypoints = ["preCreation", "postCreation"]


	def onElementComplete(self):
		self._onElementCompleteNext(DataDescriptor)
		for t in self.tables:
			t.setMetaParent(self)

	def getDynamicAttribute(self, name):
		try:
			grammarClass = getGrammar(name)
		except KeyError:  # no such grammar, let Structure raise its error
			return
		self.managedAttrs[name] = self._grammar
		return self._grammar

	def getExpander(self):
		"""returns the current rd.
		"""
		# This is required by the ScriptingMixin
		return self.rd

	def iterSources(self):
		if self.sources:
			return self.sources.iterSources()
		else:
			return iter([])

	def __iter__(self):
		for m in self.makes:
			yield m.table

	def getTableDefById(self, id):
		for m in self.makes:
			if m.table.id==id:
				return m.table
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

		Sources are not copied to protect the innocent.
		"""
		return DataDescriptor(self.parent, rowmakers=self.rowmakers[:],
			tables=self.tables[:], grammar=self.grammar, makes=self.makes[:])


_grammarRegistry = {}

def registerGrammar(grammarClass):
	elName = grammarClass.name_
	_grammarRegistry[elName] = grammarClass


def getGrammar(grammarName):
	return _grammarRegistry[grammarName]
