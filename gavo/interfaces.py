"""
Definitions of sets of fields a table has to have to be useful for a certain
purpose.

Example:

positions -- clients will want alphaFloat, deltaFloat and some helper fields
products -- clients will want a key to find the image, ownership, embargo,
  plus the products need to be in an accompanying table.

Interfaces may need additional actions for ingestion.  This is done
by returning delayed nodes to the utils.NodeBuilder parsing the resource
descriptor.

In general, a somewhat more declarative approach would be nice...
"""

import gavo
from gavo import config
from gavo import coords
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
	to RecordDefs; this is done when importparser calls the getNodes
	method.  However, interfaces will frequently want to amend the
	resource descriptor in other parts.  Therefore, they can register
	delayed children (see NodeBuilder) through their getDelayedNodes
	method.
	"""
	def __init__(self, fieldDicts):
		self.fields = []
		self.fieldIndex = {}
		for fd in fieldDicts:
			self._addField(fd)

	def _addField(self, fieldDict):
		newField = DataField(**fieldDict)
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
	
	def getNodes(self, recordNode, fieldDefs=None):
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
	
	def getDelayedNodes(self, recordNode):
		return []


class Positions(Interface):
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
	@staticmethod
	def getName():
		return "positions"

	def __init__(self):
		Interface.__init__(self, [ 
			{"dest": "alphaFloat", "unit": "deg", "dbtype": "double precision", 
				"ucd": "pos.eq.ra", "literalForm": "do not touch", 
				"source": "alphaFloat", "verbLevel": 1},
			{"dest": "deltaFloat", "unit": "deg", "dbtype": "double precision", 
				"ucd": "pos.eq.dec", "literalForm": "do not touch", 
				"source": "deltaFloat", "verbLevel": 1},
			{"dest": "c_x", "dbtype": "real", "literalForm": "do not touch", 
				"source": "c_x", "verbLevel": 30},
			{"dest": "c_y", "dbtype": "real", "literalForm": "do not touch", 
				"source": "c_y", "verbLevel": 30},
			{"dest": "c_z", "dbtype": "real", "literalForm": "do not touch", 
				"source": "c_z", "verbLevel": 30},
			])


class Q3CPositions(Positions):
	"""is an interface for positions indexed using q3c.
	
	This works exactly like the positions interface, except that behind
	the scenes some magic code generates a q3c index on alphaFloat and
	deltaFloat.  This will fail if you don't have the q3c extension to
	postgres.
	"""
	@staticmethod
	def getName():
		return "q3cpositions"

	def getDelayedNodes(self, recordNode):
		tableName = recordNode.get_table()
		yield "Data", ("script", ("postCreation", "q3cindex",
			"\n".join([
				"BEGIN",
				"-DROP INDEX @@@SCHEMA()@@@.%(indexName)s",
				"COMMIT",
				"CREATE INDEX %(indexName)s ON @@@SCHEMA()@@@.%(tableName)s "
				"(q3c_ang2ipix(alphaFloat, deltaFloat))",
				"CLUSTER %(indexName)s ON @@@SCHEMA()@@@.%(tableName)s",
				"ANALYZE @@@SCHEMA()@@@.%(tableName)s"])%{
					"indexName": "q3c_"+tableName,
					"tableName": tableName,
					}))

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


class Q3CIndex(Interface):
	"""is an interface indexing the main positions of a table using Q3C

	The difference to Q3CPositions is that no cartesian coordinates are
	introduced into the table and the positions are taken from the
	fields with the ucds pos.eq.ra;meta.main and pos.eq.dec;meta.main;
	we will raise an error if there are not exactly one of these each
	in the pertaining record.
	"""
	def __init__(self):
		Interface.__init__(self, [])

	@staticmethod
	def getName():
		return "q3cindex"

	def getDelayedNodes(self, recordNode):
		tableName = recordNode.get_table()
		raFields = recordNode.getFieldsByUcd("pos.eq.ra;meta.main")
		deFields = recordNode.getFieldsByUcd("pos.eq.dec;meta.main")
		if len(raFields)!=1 or len(deFields)!=1:
			raise Error("Table must have exactly one field with ucds"
				" pos.eq.ra;meta.main and pos.eq.dec;meta.main each for the"
				" q3cindex interface")
		raName, deName = raFields[0].get_dest(), deFields[0].get_dest()
		yield "Data", ("script", ("postCreation", "q3cindex",
			"\n".join([
				"BEGIN",
				"-DROP INDEX @@@SCHEMA()@@@.%(indexName)s",
				"COMMIT",
				"CREATE INDEX %(indexName)s ON @@@SCHEMA()@@@.%(tableName)s "
				"(q3c_ang2ipix(%(raName)s, %(deName)s))",
				"CLUSTER %(indexName)s ON @@@SCHEMA()@@@.%(tableName)s",
				"ANALYZE @@@SCHEMA()@@@.%(tableName)s"])%{
					"indexName": "q3c_"+tableName.replace(".", "_"),
					"tableName": recordNode.get_table(),
					"raName": raName,
					"deName": deName,
					}))


class Products(Interface):
	"""is an interface for handling products.
	
	The interface requires the fields datapath, owner, embargo, and
	fsize.

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
	@staticmethod
	def getName():
		return "products"

	requiredFields = set(["datapath", "owner", "embargo", "fsize"])
	def __init__(self):
		Interface.__init__(self, [
			{"dest": "datapath", "source": "prodtblKey", "dbtype": "text",
				"ucd": "meta.ref;obs.image;meta.fits", "displayHint": "type=product",
				"tablehead": "Product", "optional": "False", "verbLevel": 5},
# XXX TODO: it would be smart to have "references": "products", here,
# but that causes the remove of the items to take forever.  See if
# we can figure out a way to avoid that penalty.
			{"dest": "owner", "source": "prodtblOwner", "dbtype": "text",
				"tablehead": "Product owner", "displayHint": "type=suppress",
				"verbLevel": 25},
			{"dest": "embargo", "source": "prodtblEmbargo", "dbtype": "date",
				"tablehead": "Embargo ends", 
				"unit": "Y-M-D", "verbLevel": 25},
			{"dest": "fsize", "source": "prodtblFsize", "dbtype": "int",
				"tablehead": "File size", "unit": "byte",
				"verbLevel": 15},
		])

	def getDelayedNodes(self, recordNode):
		"""sets up exporting the products to the product table by
		prepending a shared record definition to the current recordDef.
		"""
		sourceTable = "@schemaq,%s"%recordNode.get_table()
		productTable = resource.RecordDef()
		productTable.set_shared(True)
		productTable.set_table("products")
		productTable.set_owningCondition(("sourceTable", sourceTable))
			
		for fieldDict in [
				{"dest": "key", "primary": "True", "source": "prodtblKey",
					"dbtype": "text"},
				{"dest": "owner", "source": "prodtblOwner", "dbtype": "text"},
				{"dest": "embargo", "dbtype": "date", "source": "prodtblEmbargo"},
				{"dest": "accessPath", "source": "prodtblPath", "dbtype": "text"},
				{"dest": "sourceTable", "default": sourceTable, "dbtype": "text"}]:
			productTable.addto_items(DataField(**fieldDict))
		yield "Semantics", ("Record", productTable), True


class BboxSiap(Interface):
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
	* the values of the product interface.  Note that bboxSiap doesn't
	  automatically enable products.  Maybe it should, but maybe we'll
	  have more than one products interface...
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
	"""
	# XXX TODO: Seperate the stuff necessary for searching from all the 
	# XXX SIAP cruft.
	@staticmethod
	def getName():
		return "bboxSiap"
	
	def __init__(self):
		Interface.__init__(self, self._getInterfaceFields())
	
	def _getInterfaceFields(self):
		# everything required in the standard must have verbLevel<=20,
		# because by default, you'll get verb=2
		return self.siapFields
		
	siapFields = [
			{"dest": "centerAlpha", "source": "centerAlpha", "ucd": "PO_EQ_RA_MAIN",
				"dbtype": "double precision", "unit": "deg", "tablehead": "alpha",
				"displayHint": "type=time", "verbLevel": 0},
			{"dest": "centerDelta", "source": "centerDelta", "ucd": "PO_EQ_DEC_MAIN",
				"dbtype": "double precision", "unit": "deg", "tablehead": "delta",
				"displayHint": "type=sexagesimal", "verbLevel": 0},
			{"dest": "primaryBbox", "source": "primaryBbox", 
				"dbtype": "box",
				"displayHint": "type=suppress", "literalForm": "do not touch"},
			{"dest": "secondaryBbox", "source": "secondaryBbox", 
				"dbtype": "box",
				"displayHint": "type=suppress", "literalForm": "do not touch"},
			{"dest": "imageTitle", "source": "imageTitle", "ucd": "VOX:Image_Title",
				"dbtype": "text", "tablehead": "Title", "verbLevel": 0},
			{"dest": "instId", "source": "instId", "ucd": "INST_ID",
				"dbtype": "text", "tablehead": "Instrument", "verbLevel":15},
			{"dest": "dateObs", "source": "dateObs", "ucd": "VOX:Image_MJDateObs",
				"dbtype": "timestamp", "unit": "d", "tablehead": "Obs. date",
				"verbLevel": 0},
			{"dest": "nAxes", "source": "NAXIS", "ucd": "VOX:Image_Naxes", 
				"dbtype": "integer", "displayHint": "type=suppress", "verbLevel": 20},
			{"dest": "pixelSize", "source": "pixelSize", "ucd": "VOX:Image_Naxis",
				"dbtype": "integer[]", "verbLevel": 15},
			{"dest": "pixelScale", "source": "pixelSize", "ucd": "VOX:Image_Scale",
				"dbtype": "real[]", "verbLevel": 12},
			{"dest": "imageFormat", "source": "imageFormat", "dbtype": "text",
				"ucd": "VOX:Image_Format", "verbLevel": 20, "default": "image/fits"},
			{"dest": "refFrame", "source": "RADESYS", "dbtype": "text",
				"ucd": "VOX:STC_CoordRefFrame", "verbLevel": 20},
			{"dest": "wcs_equinox", "ucd": "VOX:STC_CoordEquinox",
				"source": "wcs_equinox", "verbLevel": 20},
			{"dest": "wcs_projection", "ucd": "VOX:WCS_CoordProjection",
				"source": "wcs_projection", "dbtype": "text", "verbLevel": 20},
			{"dest": "wcs_refPixel", "ucd": "VOX:WCS_CoordRefPixel",
				"source": "wcs_refPixel", "dbtype": "real[]", "verbLevel": 20},
			{"dest": "wcs_refValues", "ucd": "VOX:WCS_CoordRefValue",
				"source": "wcs_refValues", "dbtype": "double precision[]",
				"verbLevel": 20},
			{"dest": "wcs_cdmatrix", "ucd": "VOX:CDMatrix", "verbLevel": 20,
				"source": "wcs_cdmatrix", "dbtype": "real[]"},
			{"dest": "bandpassId", "ucd": "VOX:Bandpass_ID",
				"source": "bandpassId", "dbtype": "text", "verbLevel": 10},
			{"dest": "bandpassUnit", "ucd": "VOX:BandPass_Unit",
				"source": "bandpassUnit", "dbtype": "text", "verbLevel": 20},
			{"dest": "bandpassRefval", "ucd": "VOX:BandPass_RefValue",
				"source": "bandpassRefval", "verbLevel": 20},
			{"dest": "bandpassHi", "ucd": "VOX:BandPass_HiLimit",
				"source": "bandpassHi", "verbLevel": 20},
			{"dest": "bandpassLo", "ucd": "VOX:BandPass_LoLimit",
				"source": "bandpassLo", "verbLevel": 20},
			{"dest": "pixflags", "ucd": "VOX:Image_PixFlags", "verbLevel": 20,
				"source": "pixflags", "dbtype": "text"},
			{"dest": "accref", "ucd": "VOX:Image_AccessReference",
				"source": "prodtblKey", "dbtype": "text", "verbLevel": 0,
				"displayHint": "type=product", "tablehead": "Product"},
			{"dest": "accsize", "ucd": "VOX:Image_FileSize",
				"tablehead": "File size", "description": "Size of the image in bytes",
				"source": "prodtblFsize", "dbtype": "integer", "verbLevel": 11},
		]


def elgen_siapOutput(**args):
	for field in BboxSiap.siapFields:
		of = field.copy()
		of["source"] = of["dest"]
		yield ("empty", "outputField", of)
elgen.registerElgen("siapOutput", elgen_siapOutput)


getInterface = utils.buildClassResolver(Interface, globals().values(),
	instances=True)


if __name__=="__main__":
	import sys
	if not utils.makeClassDocs(Interface, globals().values()):
		_test()
