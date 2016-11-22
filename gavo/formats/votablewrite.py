"""
Generating VOTables from internal data representations.

This is glue code to the more generic GAVO votable library.  In particular,
it governs the application of base.SerManagers and their column descriptions
(which are what is passed around as colDescs in this module to come up with 
VOTable FIELDs and the corresponding values.

You should access this module through formats.votable.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import contextlib
import functools
import itertools
from cStringIO import StringIO
import warnings

from gavo import base
from gavo import dm
from gavo import rsc
from gavo import utils
from gavo import votable
from gavo.base import meta
from gavo.base import valuemappers
from gavo.formats import common
from gavo.votable import V
from gavo.votable import modelgroups


class Error(base.Error):
	pass


tableEncoders = {
	"td": V.TABLEDATA,
	"binary": V.BINARY,
	"binary2": V.BINARY2,
}


class VOTableContext(utils.IdManagerMixin):
	"""encoding context.

	This class provides management for unique ID attributes, the value mapper
	registry, and possibly additional services for writing VOTables.

	VOTableContexts optionally take

		- a value mapper registry (by default, valuemappers.defaultMFRegistry)
		- the tablecoding (currently, td, binary, or binary2)
		- version=(1,1) to order a 1.1-version VOTable, (1,2) for 1.2.
		  (default is now 1.3.
		- acquireSamples=False to suppress reading some rows to get
		  samples for each column
		- suppressNamespace=False to leave out a namespace declaration
		  (mostly convenient for debugging)
		- overflowElement (see votable.tablewriter.OverflowElement)
	
	There's also an attribute produceVODML that will automatically be
	set for VOTable 1.4; you can set it to true manually, but the
	resulting VOTables will probably be invalid.

	If VO-DML processing is enabled, the context also manages models declared;
	that's the modelsUsed dictionary, mapping prefix -> dm.Model instances
	"""
	def __init__(self, mfRegistry=valuemappers.defaultMFRegistry, 
			tablecoding='binary', version=None, acquireSamples=True,
			suppressNamespace=False, overflowElement=None):
		self.mfRegistry = mfRegistry
		self.tablecoding = tablecoding
		self.version = version or (1,3)
		self.acquireSamples = acquireSamples
		self.suppressNamespace = suppressNamespace
		self.overflowElement = overflowElement
		self._containerStack = []
		self._tableStack = []

		self.produceVODML = self.version[0]>1 or self.version[1]>3
		self.modelsUsed = {}

	def addVODMLPrefix(self, prefix):
		"""arranges the DM with prefix to be included in modelsUsed.
		"""
		if prefix not in self.modelsUsed:
			self.modelsUsed[prefix] = dm.getModelForPrefix(prefix)

	def makeTable(self, table):
		"""returns xmlstan for a table.

		This is exposed as a method of context as the dm subpackage
		needs it, but I don't want to import formats there (yet).

		This may go away as I fix the interdependence of dm, votable, and
		format.
		"""
		return makeTable(self, table)

	def getEnclosingTable(self):
		"""returns the xmlstan element of the table currently built.

		This returns a ValueError if the context isn't aware of a table
		being built.

		(This depends builders using activeContainer)
		"""
		for el in reversed(self._containerStack):
			if el.name_=="TABLE":
				return el
		raise ValueError("Not currently building a table.")

	def getEnclosingResource(self):
		"""returns the xmlstan element of the resource currently built.

		This returns a ValueError if the context isn't aware of a resource
		being built.

		(This depends builders using activeContainer)
		"""
		for el in reversed(self._containerStack):
			if el.name_=="RESOURCE":
				return el
		raise ValueError("Not currently building a table.")

	def getEnclosingContainer(self):
		"""returns the innermost container element the builders have declared.
		"""
		return self._containerStack[-1]

	@property
	def currentTable(self):
		"""the DaCHS table object from which things are currently built.

		If no builder has declared a table being built (using buildingFromTable), 
		it's a value error.
		"""
		if not self._tableStack:
			raise ValueError("No table being processed.")
		return self._tableStack[-1]

	@contextlib.contextmanager
	def activeContainer(self, container):
		"""a context manager to be called by VOTable builders when
		they open a new TABLE or RESOURCE.
		"""
		self._containerStack.append(container)
		try:
			yield
		finally:
			self._containerStack.pop()

	@contextlib.contextmanager
	def buildingFromTable(self, table):
		"""a context manager to control code that works on a DaCHS table.
		"""
		self._tableStack.append(table)
		try:
			yield
		finally:
			self._tableStack.pop()

	def addID(self, rdEl, votEl):
		"""adds an ID attribute to votEl if rdEl has an id managed by self.
		"""
		try:
			votEl.ID = self.getIdFor(rdEl)
		except base.NotFoundError: 
			# the param is not referenced and thus needs no ID
			pass
		return votEl



################# Turning simple metadata into VOTable elements.

def _iterInfoInfos(dataSet):
	"""returns a sequence of V.INFO items from the info meta of dataSet.
	"""
	for infoItem in dataSet.getMeta("info", default=[]):
		name, value, id = infoItem.infoName, infoItem.infoValue, infoItem.infoId
		yield V.INFO(name=name, value=value, ID=id)[infoItem.getContent()]


def _iterWarningInfos(dataSet):
	"""yields INFO items containing warnings from the tables in dataSet.
	"""
	for table in dataSet.tables.values():
		for warning in table.getMeta("_warning", propagate=False, default=[]):
			yield V.INFO(name="warning", value="In table %s: %s"%(
				table.tableDef.id, warning.getContent("text", macroPackage=table)))


def _iterResourceMeta(ctx, dataSet):
	"""adds resource metadata to the Resource parent.
	"""
	yield V.DESCRIPTION[base.getMetaText(dataSet, "description", 
		macroPackage=dataSet.dd.rd, propagate=False)]
	for el in  itertools.chain(
			_iterInfoInfos(dataSet), _iterWarningInfos(dataSet)):
		yield el

	sourcesSeen, citeLinksSeen = set(), set()
	for table in dataSet.tables.values():
		for m in table.iterMeta("source", propagate="True"):
			src = m.getContent("text")
			if src not in sourcesSeen:
				yield V.INFO(name="source", value=src)[
					"This resource contains data associated with the publication"
					" %s."%src]
			sourcesSeen.add(src)

		for m in table.iterMeta("howtociteLink"):
			link = m.getContent("text")
			if link not in citeLinksSeen:
				yield V.INFO(name="howtocite", value=link)[
					"For advice on how to cite the resource(s)"
					" that contributed to this result, see %s"%link]
			citeLinksSeen.add(link)


def _iterToplevelMeta(ctx, dataSet):
	"""yields meta elements for the entire VOTABLE from dataSet's RD.
	"""
	rd = dataSet.dd.rd
	if rd is None:
		return
	yield V.DESCRIPTION[base.getMetaText(rd, "description",
		macroPackage=dataSet.dd.rd)]

	for infoItem in rd.iterMeta("copyright"):
		yield V.INFO(name="legal", value=infoItem.getContent("text",
			macroPackage=dataSet.dd.rd))
	

# link elements may be defined using the votlink meta on RESOURCE, TABLE,
# GROUP, FIELD, or PARAM; within in the DC, GROUPs have no meta structure,
# so we don't run _linkBuilder on them.

def _makeLinkForMeta(args, localattrs=None):
	localattrs.update({"href": args[0]})
	return V.LINK(**localattrs)


_linkBuilder = meta.ModelBasedBuilder([
	('votlink', _makeLinkForMeta, (), {
			"href": "href",
			"content_role": "role",
			"content_type": "contentType",
			"name": "linkname",})])


################# Generating FIELD and PARAM elements.

def _makeValuesForColDesc(colDesc):
	"""returns a VALUES element for a column description.

	This just stringifies whatever is in colDesc's respective columns,
	so for anything fancy pass in byte strings to begin with.
	"""
	valEl = V.VALUES()
	if colDesc.get("min") is None:
		colDesc["min"] = getattr(colDesc.original.values, "min", None)
	if colDesc.get("max") is None:
		colDesc["max"] = getattr(colDesc.original.values, "max", None)

	if colDesc["max"] is utils.Infimum:
		colDesc["max"] = None
	if colDesc["min"] is utils.Supremum:
		colDesc["min"] = None

	if colDesc["min"] is not None:
		valEl[V.MIN(value=str(colDesc["min"]))]
	if colDesc["max"] is not None:
		valEl[V.MAX(value=str(colDesc["max"]))]
	if colDesc["nullvalue"] is not None:
		valEl(null=colDesc["nullvalue"])

	for option in getattr(colDesc.original.values, "options", []):
		valEl[V.OPTION(value=option.content_, name=option.title)]

	return valEl


# keys copied from colDescs to FIELDs in _getFieldFor
_voFieldCopyKeys = ["name", "datatype", "ucd", "utype"]

def defineField(ctx, element, colDesc):
	"""adds attributes and children to element from colDesc.

	element can be a V.FIELD or a V.PARAM *instance* and is changed in place.

	This function returns None to remind people we're changing in place
	here.
	"""
	# bomb if you got an Element rather than an instance -- with an
	# Element, things would appear to work, but changes are lost when
	# this function ends.
	assert not isinstance(element, type)

	if colDesc["arraysize"]!='1':
		element(arraysize=colDesc["arraysize"])
	# (for char, keep arraysize='1' to keep topcat happy)
	if colDesc["datatype"]=='char' and colDesc["arraysize"]=='1':
		element(arraysize='1')

	if colDesc["unit"]:
		element(unit=colDesc["unit"])
	element(ID=colDesc["id"])

	# don't include xtype if writing 1.1
	xtype = colDesc.get("xtype")
	if ctx.version>(1,1):
		element(xtype=xtype)
	
	if isinstance(element, V.PARAM):
		if hasattr(colDesc.original, "getStringValue"):
			try:
				element(value=str(colDesc.original.getStringValue()))
			except:
				# there's too much that can legitimately go wrong here to bother:
				pass

	element(**dict((key, colDesc.get(key)) for key in _voFieldCopyKeys))[
		V.DESCRIPTION[colDesc["description"]],
		_makeValuesForColDesc(colDesc),
		_linkBuilder.build(colDesc.original)
	]


def makeFieldFromColumn(ctx, colType, rscCol):
	"""returns a VOTable colType for a rscdef column-type thing.

	This function lets you make PARAM and FIELD elements (colType) from
	column or param instances.
	"""
	instance = colType()
	defineField(ctx, instance, valuemappers.AnnotatedColumn(rscCol))
	return instance


def _iterFields(ctx, serManager):
	"""iterates over V.FIELDs based on serManger's columns.
	"""
	for colDesc in serManager:
		el = V.FIELD()
		defineField(ctx, el, colDesc)
		yield el


def _makeVOTParam(ctx, param):
	"""returns VOTable stan for param.
	"""
	# note that we're usually accessing the content, i.e., the string
	# serialization we got.  The only exception is when we're seeing
	# nulls or null-equivalents.
	if param.content_ is base.NotGiven or param.value is None:
		content = None
	else:
		content = param.content_

	el = V.PARAM()
	defineField(ctx, el, valuemappers.AnnotatedColumn(param))
	if content is None:
		el.value = ""
	else:
		el.value = content
	return el


def _iterTableParams(ctx, serManager):
	"""iterates over V.PARAMs based on the table's param elements.
	"""
	for param in serManager.table.iterParams():
		votEl = _makeVOTParam(ctx, param)
		if votEl is not None:
			ctx.addID(param, votEl)
			yield votEl


def _iterParams(ctx, dataSet):
	"""iterates over the entries in the parameters table of dataSet.
	"""
# deprecate this.  The parameters table of a data object was a grave
# mistake.
# Let's see who's using it and then remove this in favor of actual
# data parameters (or table parameters)
	try:
		parTable = dataSet.getTableWithRole("parameters")
	except base.DataError:  # no parameter table
		return

	warnings.warn("Parameters table used.  You shouldn't do that any more.")
	values = {}
	if parTable:  # no data for parameters: keep empty values.
		values = parTable.rows[0]

	for item in parTable.tableDef:
		colDesc = valuemappers.AnnotatedColumn(item)
		el = V.PARAM()
		el(value=ctx.mfRegistry.getMapper(colDesc)(values.get(item.name)))
		defineField(ctx, el, colDesc)
		ctx.addID(el, item)
		yield el


####################### Tables and Resources



def _iterSTC(tableDef, serManager):
	"""adds STC groups for the systems to votTable fetching data from 
	tableDef.
	"""
	def getIdFor(colRef):
		try:
			return serManager.getColumnByName(colRef.dest)["id"]
		except KeyError:
			# in ADQL processing, names are lower-cased, and there's not
			# terribly much we can do about it without breaking other things.
			# Hence, let's try and see whether our target is there with 
			# case normalization:
			return serManager.getColumnByName(colRef.dest.lower())["id"]
	for ast in tableDef.getSTCDefs():
		yield modelgroups.marshal_STC(ast, getIdFor)


def _iterNotes(serManager):
	"""yields GROUPs for table notes.

	The idea is that the note is in the group's description, and the FIELDrefs
	give the columns that the note applies to.
	"""
	# add notes as a group with FIELDrefs, but don't fail on them
	for key, note in serManager.notes.iteritems():
		noteId = serManager.getOrMakeIdFor(note)
		noteGroup = V.GROUP(name="note-%s"%key, ID=noteId)[
			V.DESCRIPTION[note.getContent(targetFormat="text")]]
		for col in serManager:
			if col["note"] is note:
				noteGroup[V.FIELDref(ref=col["id"])]
		yield noteGroup


def _makeRef(baseType, ref, container, serManager):
	"""returns a new node of baseType reflecting the group.TypedRef 
	instance ref.

	container is the destination of the reference.  For columns, that's
	the table definition, but for parameters, this must be the table
	itself rather than its definition because it's the table's
	params that are embedded in the VOTable.
	"""
	return baseType(
		ref=serManager.getOrMakeIdFor(ref.resolve(container)),
		utype=ref.utype,
		ucd=ref.ucd)


def _iterGroups(ctx, container, serManager):
	"""yields GROUPs for the RD groups within container, taking params and
	fields from serManager's table.

	container can be a tableDef or a group.
	"""
	for group in container.groups:
		votGroup = V.GROUP(ucd=group.ucd, utype=group.utype, name=group.name)
		votGroup[V.DESCRIPTION[group.description]]

		for ref in group.columnRefs:
			votGroup[_makeRef(V.FIELDref, ref,
				serManager.table.tableDef, serManager)]

		for ref in group.paramRefs:
			votGroup[_makeRef(V.PARAMref, ref,
				serManager.table, serManager)]

		for param in group.params:
			votGroup[_makeVOTParam(ctx, param)]

		for subgroup in _iterGroups(ctx, group, serManager):
			votGroup[subgroup]

		yield votGroup


def makeTable(ctx, table):
	"""returns a Table node for the table.Table instance table.
	"""
	sm = valuemappers.SerManager(table, mfRegistry=ctx.mfRegistry,
		idManager=ctx, acquireSamples=ctx.acquireSamples)

	# this must happen before FIELDs and such are serialised to ensure
	# referenced things have IDs.

	result = V.TABLE()
	with ctx.activeContainer(result):
		result(
				name=table.tableDef.id,
				utype=base.getMetaText(table, "utype", macroPackage=table.tableDef,
				propagate=False))[
			# _iterGroups must run before _iterFields and _iterParams since it
			# may need to add ids to the respective items.  XSD-correct ordering of 
			# the elements is done by xmlstan.
			V.DESCRIPTION[base.getMetaText(table, "description", 
				macroPackage=table.tableDef, propagate=False)],
			_iterGroups(ctx, table.tableDef, sm),
			_iterFields(ctx, sm),
			_iterTableParams(ctx, sm),
			_iterNotes(sm),
			_linkBuilder.build(table.tableDef),
			]

		if ctx.version>(1,1):
			result[_iterSTC(table.tableDef, sm)]

		if ctx.produceVODML:
			for ann in table.tableDef.annotations:
				try:
					result[ann.getVOT(ctx)]
				except Exception, msg:
					# never fail just because stupid DM annotation doesn't work out
					base.ui.notifyError("DM annotation failed: %s"%msg)

		return votable.DelayedTable(result,
			sm.getMappedTuples(),
			tableEncoders[ctx.tablecoding],
			overflowElement=ctx.overflowElement)


def _makeResource(ctx, data):
	"""returns a Resource node for the rsc.Data instance data.
	"""
	res = V.RESOURCE()
	with ctx.activeContainer(res):
		res(type=base.getMetaText(data, "_type"),
				utype=base.getMetaText(data, "utype"))[
			_iterResourceMeta(ctx, data),
			_iterParams(ctx, data), [
				_makeVOTParam(ctx, param) for param in data.iterParams()],
			_linkBuilder.build(data.dd),
			]
		for table in data:
			with ctx.buildingFromTable(table):
				res[makeTable(ctx, table)]
		res[ctx.overflowElement]
	return res

############################# Toplevel/User-exposed code

makeResource = _makeResource


def makeVOTable(data, ctx=None, **kwargs):
	"""returns a votable.V.VOTABLE object representing data.

	data can be an rsc.Data or an rsc.Table.  data can be a data or a table
	instance, tablecoding any key in votable.tableEncoders.

	You may pass a VOTableContext object; if you don't a context
	with all defaults will be used.

	A deprecated alternative is to directly pass VOTableContext constructor
	arguments as additional keyword arguments.  Don't do this, though,
	we'll probably remove the option to do so at some point.
	
	You will usually pass the result to votable.write.  The object returned
	contains DelayedTables, i.e., most of the content will only be realized at
	render time.
	"""
	ctx = ctx or VOTableContext(**kwargs)

	data = rsc.wrapTable(data)
	if ctx.version==(1,1):
		vot = V.VOTABLE11()
	elif ctx.version==(1,2):
		vot = V.VOTABLE12()
	elif ctx.version==(1,3):
		vot = V.VOTABLE()
	elif ctx.version==(1,4):
		vot = V.VOTABLE()     # TODO: When 1.4 XSD comes out, actually implement
	else:
		raise votable.VOTableError("No toplevel element for VOTable version %s"%
			ctx.version)

	vot[_iterToplevelMeta(ctx, data)]
	vot[_makeResource(ctx, data)]

	if ctx.produceVODML:
		if ctx.modelsUsed:
			# if we declare any models, we'll need vo-dml
			ctx.addVODMLPrefix("vo-dml")
		for model in ctx.modelsUsed.values():
			vot[model.getVOT(ctx)]

	if ctx.suppressNamespace:  
		# use this for "simple" table with nice element names
		vot._fixedTagMaterial = ""

	# What follows is a hack around the insanity of stuffing
	# unused namespaces and similar detritus into VOTable's roots.
	rootAttrs = data.getMeta("_votableRootAttributes")
	if rootAttrs:
		rootHacks = [vot._fixedTagMaterial]+[
			item.getContent() for item in rootAttrs]
		vot._fixedTagMaterial = " ".join(s for s in rootHacks if s)

	return vot


def writeAsVOTable(data, outputFile, ctx=None, **kwargs):
	"""a formats.common compliant data writer.

	See makeVOTable for the arguments.
	"""
	ctx = ctx or VOTableContext(**kwargs)
	vot = makeVOTable(data, ctx)
	votable.write(vot, outputFile)


def getAsVOTable(data, ctx=None, **kwargs):
	"""returns a string containing a VOTable representation of data.

	For information on the arguments, refer to makeVOTable.
	"""
	ctx = ctx or VOTableContext(**kwargs)
	dest = StringIO()
	writeAsVOTable(data, dest, ctx)
	return dest.getvalue()


def format(data, outputFile, **ctxargs):
# used for construction of the formats.common interface
	return writeAsVOTable(data, outputFile, VOTableContext(**ctxargs))

common.registerDataWriter("votable", format, 
	base.votableType, "Default VOTable")
common.registerDataWriter("votableb2", functools.partial(
	format, tablecoding="binary2"),
	"application/x-votable+xml;serialization=BINARY2",
	"Binary2 VOTable")
common.registerDataWriter("votabletd", functools.partial(
	format, tablecoding="td"), 
	"application/x-votable+xml;serialization=TABLEDATA", "Tabledata VOTable",
	"text/xml")
common.registerDataWriter("votabletd1.1", functools.partial(
	format, tablecoding="td", version=(1,1)), 
	"application/x-votable+xml;serialization=TABLEDATA;version=1.1", 
	"Tabledata VOTable version 1.1",
	"text/xml")
common.registerDataWriter("votabletd1.2", functools.partial(
	format, tablecoding="td", version=(1,2)), 
	"application/x-votable+xml;serialization=TABLEDATA;version=1.2", 
	"Tabledata VOTable version 1.2",
	"text/xml")
