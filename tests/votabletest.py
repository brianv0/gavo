"""
Some tests for votable production.
"""

from cStringIO import StringIO
import os
import pkg_resources
import unittest

try:
    import cElementTree as ElementTree
except:
    from elementtree import ElementTree


from gavo import base
from gavo import rsc
from gavo import rscdesc
from gavo.formats import votable

testData="""some silly test data
-33  -3400abc
23829328.9xxy
     22      
          nas 
"""

class VotableTest(unittest.TestCase):
	def _makeRD(self):
		"""returns a test resource descriptor.
		"""
		return base.parseFromString(rscdesc.RD, """
			<resource resdir="%s" schema="test">
				<meta name="description">Some test data for VOTables.</meta>
				<meta name="_legal">Hands off this fascinating data</meta>
				<cooSys id="sys1" equ="J2000.0" epoch="1998" system="eq_FK5"/>
				<cooSys id="sys2" equ="J2000.0" system="ICRS"/>
				<table id="foo">
					<column name="anInt" type="integer"
						description="This is a first data field"/>
					<column name="aFloat"
						description="This ain't &amp;alpha; for sure."/>
					<column name="bla" type="text"/>
				</table>
				<data id="bar">
					<meta name="_infolink">http://vo.org/x?a=b&amp;c=d</meta>
					<columnGrammar topIgnoredLines="1">
						<col key="anInt">1-5</col>
						<col key="aFloat">6-10</col>
						<col key="bla">11-13</col>
					</columnGrammar>
					<rowmaker id="_foo" idmaps="*"/>
					<make table="foo" rowmaker="_foo"/>
				</data>
			</resource>"""%os.path.abspath("data"))

	def setUp(self):
		rd = self._makeRD()
		dataSet = rsc.makeData(rd.getById("bar"), forceSource=StringIO(testData))
		votMaker = votable.VOTableMaker(tablecoding="td")
		output = StringIO()
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
			"xmlstarlet val --err --xsd %s -"
				" > validationres.txt"%pkg_resources.resource_filename('gavo',
					"resources/xml/VOTable-1.1.xsd"), "w")
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
