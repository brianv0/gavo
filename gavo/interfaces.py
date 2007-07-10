"""
Definitions of sets of fields a table has to have to be useful for a certain
purpose.

Examples:

positions -- clients will want alphaFloat, deltaFloat and some helper fields
products -- clients will want a key to find the image, ownership, embargo,
  plus the products need to be in an accompanying table.

Interfaces may need additional actions for ingestion.  Right now,
we solve this by providing changeRd methods.  These expect an
importparser.RdParser as argument and heavily murk around in it.
This isn't nice, but they have to have access to many aspects of
the XML parsing process.  I guess we'll want a different design at
some point.  Let's see what happens if we have more interfaces.

In general, a somewhat more declarative approach would be nice...
"""

from gavo import utils
from gavo.datadef import DataField
from gavo.parsing import resource


class Interface:
	"""is the abstract superclass for all interfaces.

	It is constructed with a list of dictionaries that define the fields
	expected as (keyword) arguments to a DataField constructor.
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
	
	def changeRd(self, rdParser, fieldDefs=None):
		"""adds the interface's data field to the currently active recordDef
		in the importparser.RdParser instance rdParser.

		For most interfaces, this won't be enough, so you'll probably want
		to override it.

		If you pass the fieldDefs argument, the DataFields in there will
		be added instead of the the DataFields defining the interface.  This
		is convenient when you need to set defaults on fields depending
		on the table the fields end up in.
		"""
		recordDef = rdParser.curRecordDef
		for f in fieldDefs or self.fields:
			recordDef.addto_items(f)


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
				"source": "alphaFloat"},
			{"dest": "deltaFloat", "unit": "deg", "dbtype": "double precision", 
				"ucd": "pos.eq.dec", "literalForm": "do not touch", 
				"source": "deltaFloat"},
			{"dest": "c_x", "dbtype": "real", "literalForm": "do not touch", 
				"source": "c_x"},
			{"dest": "c_y", "dbtype": "real", "literalForm": "do not touch", 
				"source": "c_y"},
			{"dest": "c_z", "dbtype": "real", "literalForm": "do not touch", 
				"source": "c_z"},
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

	def changeRd(self, rdParser):
		Positions.changeRd(self, rdParser)
		schema = rdParser.rd.get_schema()
		tableName = "%s.%s"%(schema, rdParser.curRecordDef.get_table())
		rdParser.rd.addto_scripts(("postCreation", "q3cindex",
			"\n".join([
				r"CREATE INDEX %(indexName)s ON %(tableName)s "
				"(q3c_ang2ipix(alphaFloat, deltaFloat))",
				"CLUSTER %(indexName)s ON %(tableName)s",
				"ANALYZE %(tableName)s"])%{
					"indexName": tableName.replace(".", "_"),
					"tableName": tableName}))


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
	
	The producttable itself is defined in gavo.inputsDir/products, and
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

	def __init__(self):
		Interface.__init__(self, [
			{"dest": "datapath", "source": "prodtblKey", "dbtype": "text",
				"ucd": "meta.ref;obs.image;meta.fits",
				"references": "products", "tablehead": "Product", "optional": "False"},
			{"dest": "owner", "source": "prodtblOwner", "dbtype": "text",
				"tablehead": "Product owner"},
			{"dest": "embargo", "source": "prodtblEmbargo", "dbtype": "date",
				"tablehead": "Embargo ends"},
			{"dest": "fsize", "source": "prodtblFsize", "dbtype": "int",
				"tablehead": "File size"},
		])

	def _insertProductTable(self, rdParser):
		"""sets up exporting the products to the product table by
		prepending a shared record definition to the current recordDef.
		"""
		qualifiedTableName ="%s.%s"%(rdParser.rd.get_schema(), 
			rdParser.curRecordDef.get_table())
		productTable = resource.RecordDef()
		productTable.set_shared(True)
		productTable.set_table("products")
		productTable.set_owningCondition(("sourceTable", qualifiedTableName))
			
		for fieldDict in [
				{"dest": "key", "primary": "True", "source": "prodtblKey",
					"dbtype": "text"},
				{"dest": "owner", "source": "prodtblOwner", "dbtype": "text"},
				{"dest": "embargo", "dbtype": "date", "source": "prodtblEmbargo"},
				{"dest": "accessPath", "source": "prodtblPath", "dbtype": "text"},
				{"dest": "sourceTable", "default": qualifiedTableName,
					"dbtype": "text"}]:
			productTable.addto_items(DataField(**fieldDict))
		rdParser.curSemantics.addto_recordDefs(productTable, infront=True)

	def changeRd(self, rdParser):
		Interface.changeRd(self, rdParser)
		self._insertProductTable(rdParser)


getInterface = utils.buildClassResolver(Interface, globals().values(),
	instances=True)


if __name__=="__main__":
	import sys
	if not utils.makeClassDocs(Interface, globals().values()):
		_test()
