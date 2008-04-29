"""
Some tests for votable production.
"""

import cStringIO
import os
import unittest

try:
    import cElementTree as ElementTree
except:
    from elementtree import ElementTree

from gavo import datadef
from gavo import nullui
from gavo import table
from gavo import votable
from gavo.parsing import resource
from gavo.parsing import columngrammar
from gavo.parsing import importparser


testData="""some silly test data
-33  -3400abc
23829328.9xxy
     22      
          nas 
"""

class VotableTest(unittest.TestCase):
	def _makeRd(self):
		"""returns a test resource descriptor.
		"""
		dataFields = [
			datadef.DataField(dest="anInt", source="1-5", dbtype="integer",
				description="This is a first data field"),
			datadef.DataField(dest="aFloat", source="6-10",
				description="This ain't &alpha; for sure."),
			datadef.DataField(dest="bla", source="11-13", dbtype="text"),
		]
		rd = resource.ResourceDescriptor()
		rd.set_resdir(os.path.abspath("data"))
		grammar = columngrammar.ColumnGrammar()
		grammar.set_topIgnoredLines(1)
		dataDesc = datadef.DataTransformer(rd, initvals={
			"id": "sillyTest",
			"Grammar": grammar,
			"Semantics": resource.Semantics(
				initvals={
					"recordDefs": [
						resource.RecordDef(initvals={
							"table": None,
							"items": dataFields,
						})
					]
				 })
		})
		dataDesc.addMeta("_infolink", "http://vo.org/x?a=b&c=d")

		rd.addto_dataSrcs(dataDesc)

		rd.addMeta("description", "Some test data for VOTables.")
		rd.addMeta("_legal", "Hands off this fascinating data")
		rd.get_systems().defineSystem("J2000.0", "1998", "eq_FK5")
		rd.get_systems().defineSystem("J2000.0", system="ICRS")
		return rd

	def setUp(self):
		rd = self._makeRd()
		dataSet = resource.InternalDataSet(rd.get_dataSrcs()[0], 
			table.Table, cStringIO.StringIO(testData))
		votMaker = votable.VOTableMaker(tablecoding="td")
		output = cStringIO.StringIO()
		votMaker.writeVOT(votMaker.makeVOT(dataSet), output)
		self.rawVOTable = output.getvalue()
		self.tree = ElementTree.fromstring(self.rawVOTable)

	def _testshowdoc(self):
		open("bla.xml", "w").write(self.rawVOTable)
		f = os.popen("xmlstarlet fo", "w")
		f.write(self.rawVOTable)
		f.close()
	
	def testValidates(self):
		"""test for validity of the generated VOTable.
		"""
		pipe = os.popen(
			"xmlstarlet val --err --xsd ../resources/xml/VOTable-1.1.xsd -"
				" > validationres.txt", "w")
		pipe.write(self.rawVOTable)
		res = pipe.close()
		f = open("validationres.txt")
		valprot = f.read()
		f.close()
		os.unlink("validationres.txt")
		self.assertEqual(valprot.strip(), "- - valid", 
			"Generated VOTable doesn't match schema:\n%s"%valprot)

	def testNullvalues(self):
		"""tests for correct serialization of Null values.
		"""
		tbldata = self.tree.find(".//%s"%votable.voTag("TABLEDATA"))
		self.assertEqual(tbldata[3][1].text, None, "NaN isn't rendered as"
			" NULL")
		fields = self.tree.findall(".//%s"%votable.voTag("FIELD"))
		f0Null = fields[0].find(votable.voTag("VALUES")).get("null")
		self.assertEqual(tbldata[2][0].text, f0Null)

	def testRanges(self):
		"""tests for ranges given in VALUES.
		"""
		fields = self.tree.findall(".//%s"%votable.voTag("FIELD"))
		f0 = fields[0].find(votable.voTag("VALUES"))
		self.assertEqual(f0.find(votable.voTag("MIN")).get("value"), "-33",
			"integer minimum bad")
		self.assertEqual(f0.find(votable.voTag("MAX")).get("value"), "23829",
			"integer maximum bad")
		f1 = fields[1].find(votable.voTag("VALUES"))
		self.assertEqual(f1.find(votable.voTag("MIN")).get("value"), "-3400.0",
			"float minimum bad")
		self.assertEqual(f1.find(votable.voTag("MAX")).get("value"), "328.9",
			"float maximum bad")
		self.assertEqual(fields[2].find(votable.voTag("VALUES")), None,
			"VALUES element given for string data")
		

if __name__=="__main__":
	unittest.main()
