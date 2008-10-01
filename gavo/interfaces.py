"""
Definitions of sets of fields a table has to have to be useful for a certain
purpose.

Example:

positions -- clients will want alphaFloat, deltaFloat and some helper fields
products -- clients will want a key to find the image, ownership, embargo,
  plus the products need to be in an accompanying table.

Interfaces may need additional actions for ingestion.  This is done
by returning delayed nodes to the nodebuilder.NodeBuilder parsing the resource
descriptor.

In general, a somewhat more declarative approach would be nice...
"""

import gavo
from gavo import config
from gavo import coords
from gavo import datadef
from gavo import record
from gavo import resourcecache
from gavo import sqlsupport
from gavo import utils
from gavo.datadef import DataField
from gavo.parsing import elgen
from gavo.parsing import resource


class Error(gavo.Error):
	pass


class Interface:
	"""is the abstract superclass for all interfaces.

	It is constructed with a list of dictionaries that define the fields
	expected as (keyword) arguments to a DataField constructor.

	This is used for the "default" action of interfaces: Adding new nodes
	to TableDefs; this is done when importparser calls the getNodes
	method.  However, interfaces will frequently want to amend the
	resource descriptor in other parts.  Therefore, they can register
	delayed children (see NodeBuilder) through their getDelayedNodes
	method.

	In addition, some operations may require modifying the existing structure.
	To accomodate this, there is the mogrifyNode method that gets called
	with the finished node.
	"""
	def __init__(self, fieldDicts):
		self.fields = []
		self.fieldIndex = {}
		for fd in fieldDicts:
			self._addField(fd)

	def _addField(self, newField):
		if isinstance(newField, DataField):
			newField = newField.copy()
		else:
			newField = DataField(**newField)
		newField.immutilize()
		self.fields.append(newField)
		self.fieldIndex[newField.get_dest()] = newField

	def isImplementedIn(self, fieldDefs):
		"""returns True if the required fields are present in fieldDefs.

		FieldDefs should be a list of DataFields, but for the time being we also
		support the tuples of MetaTableHandler (until it is moved to DataFields).

		Currently, we only check that the required names are present.
		"""
		if not fieldDefs:
			return False
		if isinstance(fieldDefs[0], DataField):
			names = set([f.get_dest() for f in fieldDefs])
		else:
			names = set([f[0] for f in fieldDefs])
		for reqField in self.fields:
			if not reqField.get_dest() in names:
				return False
		return True
	
	def getNodes(self, tableNode, fieldDefs=None):
		"""returns the fields defined by this interface as list
		of nodes suitable for a NodeBuilder.

		This default implementation should usually do.

		If you pass the fieldDefs argument evaluating to True,
		the DataFields in there will be added instead of the the
		DataFields defining the interface.  This is convenient
		when you need to set defaults on fields depending on
		the table the fields end up in.
		"""
		return [("Field", f) for f in fieldDefs or self.fields]
	
	def getDelayedNodes(self, tableNode):
		return []
	
	def mogrifyNode(self, tableNode):
		return


class TableBasedInterface(Interface):
	"""is an interface that is based on a table definition within an RD.

	It's highly preferable to build interfaces on RDs, so you should
	use this rather than a plain Interface.
	"""
# The inheritance sucks. Refactor.
	def __init__(self, rdId, tableName):
		self.rd = resourcecache.getRd(rdId)
		self.tableDef = self.rd.getTableDefByName(tableName)
		Interface.__init__(self, [])
		
	def getNodes(self, tableNode):
# XXX TODO: We'd need that stuff to be almost unserialized here.  Figure
# out some elegant way to get this.  Meanwhile, we'll have to hardcode:
		for f in self.tableDef.get_items():
			yield ("Field", f)
		for s in self.tableDef.get_scripts():
			yield ("script", s)


class Positions(TableBasedInterface):
	"""is an interface for positions.
	
	It consists of the fields alphaFloat, deltaFloat (float angles
	in degrees, J2000.0) and c_x, c_y, c_z (intersection of the radius
	vector to alphaFloat, deltaFloat with the unit sphere).

	You will usually use it in conjunction with the handleEquatorialPosition
	macro that prepares these fields for you.  So, you might say:

		<Grammar...>
      <Macro name="handleEquatorialPosition"
          alphaFormat="mas" deltaFormat="mas">
        <arg name="alpha" source="18-27"/>
        <arg name="delta" source="29-38"/>
      </Macro>
		<Grammar>
		<Semantics>
			<Record table="data">
				<implements name="positions"/>
			</Record>
		</Semantics>
	"""
	name = "positions"

	def __init__(self):
		TableBasedInterface.__init__(self, "__system__/scs", "positionsFields")


class Q3CPositions(TableBasedInterface):
	"""is an interface for positions indexed using q3c.
	
	This works exactly like the positions interface, except that behind
	the scenes some magic code generates a q3c index on alphaFloat and
	deltaFloat.  This will fail if you don't have the q3c extension to
	postgres.
	"""
	name = "q3cpositions"

	def __init__(self):
		TableBasedInterface.__init__(self, "__system__/scs", "q3cPositionsFields")

	@staticmethod
	def findNClosest(alpha, delta, tableName, n, fields, searchRadius=5):
		"""returns the n objects closest around alpha, delta in table.

		n is the number of items returned, with the closest ones at the
		top, fields is a sequence of desired field names, searchRadius
		is a radius for the initial q3c search and will need to be
		lowered for dense catalogues and possibly raised for sparse ones.

		The last item of each row is the distance of the object from
		the query center in radians (in a flat approximation).
		"""
		# XXX TODO: make this ansynchronous
		q = sqlsupport.SimpleQuerier()
		c_x, c_y, c_z = coords.computeUnitSphereCoords(alpha, delta)
		res = q.query("SELECT %s,"
				" sqrt((%%(c_x)s-c_x)^2+(%%(c_y)s-c_y)^2+(%%(c_z)s-c_z)^2) AS dist"
				" FROM %s WHERE"
				" q3c_radial_query(alphaFloat, deltaFloat, %%(alpha)s, %%(delta)s,"
				" %%(searchRadius)s)"
				" ORDER BY dist LIMIT %%(n)s"%
					(",".join(fields), tableName),
			locals()).fetchall()
		return res


class Q3CIndex(TableBasedInterface):
	"""is an interface indexing the main positions of a table using Q3C

	The difference to Q3CPositions is that no cartesian coordinates are
	introduced into the table and the positions are taken from the
	fields with the ucds pos.eq.ra;meta.main and pos.eq.dec;meta.main;
	we will raise an error if there are not exactly one of these each
	in the pertaining record.
	"""
	name = "q3cindex"

	def __init__(self):
		TableBasedInterface.__init__(self, "__system__/scs", "q3cindexFields")

	def mogrifyNode(self, tableNode):
		# On import, existance and uniquenes of the following are
		# guaranteed since if they are not, macro substitution will crash.
		# If people change the RD without a re-import, they should know what
		# they're doing, and we skip marking of indexed columns silently.
		try:
			raField = tableNode.getFieldsByUcd("pos.eq.ra;meta.main")[0]
			deField = tableNode.getFieldsByUcd("pos.eq.dec;meta.main")[0]
			if not raField.get_index():
				raField.set_index("/")
			if not deField.get_index():
				deField.set_index("/")
		except IndexError:
			pass


class Products(TableBasedInterface):
	"""is an interface for handling products.
	
	The interface requires the fields accref, owner, embargo, and
	accsize.

	Tables providing products must also enter their data into the product
	table, a system-global table mapping keys to files (which is usually
	trivial, since the product key is the path in most of the cases).
	The main point of the product table is to allow programs to check the
	ownership status (i.e., who owns the thing and when will it become free) 
	of a product without needing more information than the key.  
	
	The producttable itself is defined in inputsDir/products, and
	you'll need to gavoimp the resource descriptor in there once before
	importing anything implementing the products interface.  The interface
	will then take care of inserting your data into that table as well.

	You will usually want to use this in conjunction with the setProdtblValues
	macro that fills some "magic fields" the interface needs.  This might
	look like this:

        <Macro name="setProdtblValues">
          <arg name="prodtblKey" value="@inputRelativePath"/>
          <arg name="prodtblOwner" value="XXXXXX"/>
          <arg name="prodtblEmbargo" value="XXXX-12-31"/>
          <arg name="prodtblPath" value="@inputRelativePath"/>
          <arg name="prodtblFsize" value="@inputSize"/>
        </Macro>

	"""
	name = "products"

	requiredFields = set(["accref", "owner", "embargo", "accsize"])

	def __init__(self):
		TableBasedInterface.__init__(self, "__system__/products/products",
			"productFields")
		self.productTable = self.rd.getTableDefByName("products")

	def getDelayedNodes(self, tableDef):
		"""sets up exporting the products to the product table by
		prepending a shared record definition to the current TableDef.
		"""
		sourceTable = tableDef.getQName()
		products = self.productTable.copy()
		products.set_owningCondition(("sourceTable", tableDef.getQName()))
		products.getFieldByName("sourceTable").set_default(
			tableDef.getQName())
		yield "Semantics", ("Table", products), False


class BboxSiap(Products):
	"""is an interface for simple support of SIAP.

	This currently only handles two-dimensional images.

	The input consists of 
	* (certain) FITS WCS headers 
	* the primaryBbox, secondaryBbox, centerAlpha and centerDelta, nAxes, 
		pixelSize, pixelScale, imageFormat, wcs* fields calculated by the 
		computeBboxSiapFields macro.   
	* ImageTitle (interpolateString should come in handy for these)
	* InstId -- some id for the instrument used
	* DateObs -- a timestamp of the "characteristic" observation time
	* the bandpass* values.  You're on your own with them...
	* the values of the product interface.  
	* mimetype -- the mime type of the product.

	Tables satisfying this interface can be used for bbox-based SIAP querying.

	The interface automatically adds the appropriate macro call to compute
	the bboxes from FITS fields.

	In grammars feeding such tables, you should probably have 

	<Macro name="computeBboxSiapFields"/>

	and something like

	<Macro name="setSiapMeta">
		<arg name="siapTitle" source="imageTitle"/>
		<arg name="siapInstrument" source="TELESCOP"/>
		<arg name="siapObsDate" source="DATE-OBS"/>
		<arg name="siapImageFormat" value="image/fits"/>
		<arg name="siapBandpassId" source="FILTER"/>
	</Macro>

	Tables implementing bboxSiap also implement products.
	"""
	# XXX TODO: Seperate the stuff necessary for searching from all the 
	# XXX SIAP cruft.
	name = "bboxSiap"
	
	def __init__(self):
		TableBasedInterface.__init__(self, "__system__/siap", "bboxsiapfields")
		self.siapFields = self.tableDef.get_items()
		self.productTable = self.rd.getTableDefByName("products")
	
	def _getInterfaceFields(self):
		# everything required in the standard must have verbLevel<=20,
		# because by default, you'll get verb=2
		return self.siapFields
		

def elgen_siapOutput(preview="True"):
	doPreview = record.parseBooleanLiteral(preview)
	for field in getInterface("bboxSiap").siapFields:
		of = datadef.OutputField.fromDataField(field)
		if of.get_dest()=="accref":
			of.set_displayHint("type=product,nopreview=True")
		of.set_source(of.get_dest())
		yield ("addChild", ("outputField", of))
elgen.registerElgen("siapOutput", elgen_siapOutput)


getInterface = utils.buildClassResolver(Interface, globals().values(),
	instances=True)


if __name__=="__main__":
	import sys
	if not utils.makeClassDocs(Interface, globals().values()):
		_test()
