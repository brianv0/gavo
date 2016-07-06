"""
Tests to do with new-style data modelling and VO-DML serialisation.
"""

from gavo.helpers import testhelpers

import datetime
import re
import unittest

from gavo import base
from gavo import dm
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo.dm import common
from gavo.dm import dmrd
from gavo.dm import sil
from gavo.formats import votablewrite


def normalizeSIL(sil):
	return re.sub("\s+", " ", sil).strip()


class TestSILGrammar(testhelpers.VerboseTest):
	def testPlainObject(self):
		res = sil.getGrammar().parseString("""
			(:testclass) {
				attr1: plain12-14
				attr2: "this is a ""weird"" literal"
			}""")
		self.assertEqual(res[0],
			('obj', ':testclass', [
				('attr', 'attr1', 'plain12-14'), 
				('attr', 'attr2', 'this is a "weird" literal')]))
	
	def testNestedObject(self):
		res = sil.getGrammar().parseString("""
			(:testclass) {
				attr1: (:otherclass) {
						attr2: val
					}
			}""")
		self.assertEqual(res[0],
			('obj', ':testclass', [
				('attr', 'attr1', 
					('obj', ':otherclass', [ 
						('attr', 'attr2', 'val')]))]))

	def testCollection(self):
		res = sil.getGrammar().parseString("""
			(:testclass) {
				seq: (:otherclass)[
					{attr1: a}
					{attr1: b}
					{attr1: c}]}""")
		self.assertEqual(res[0], 
			('obj', ':testclass', [
				('attr', 'seq', 
					('coll', ':otherclass', [
						('uobj', None, [('attr', 'attr1', 'a')]),
						('uobj', None, [('attr', 'attr1', 'b')]),
						('uobj', None, [('attr', 'attr1', 'c')]),]))]))


class TestSILParser(testhelpers.VerboseTest):
	def testNestedObject(self):
		res = sil.getAnnotation("""
			(testdm:testclass) {
				attr1: (testdm:otherclass) {
						attr2: val
					}
			}""", dmrd.getAnnotationMaker(None))
		self.assertEqual(normalizeSIL(res.asSIL()),
			'(testdm:testclass) { (testdm:otherclass) { attr2: "val"} }')
			
	def testAtomicCollection(self):
		res = sil.getAnnotation("""
			(testdm:testclass) {
				seq: (testdm:otherclass)[
					{attr1: a}
					{attr1: b}
					{attr1: c}]}""", dmrd.getAnnotationMaker(None))
		self.assertEqual(normalizeSIL(res.asSIL()),
			'(testdm:testclass) { seq: (testdm:otherclass)'
			' [ { attr1: "a"} { attr1: "b"}'
			' { attr1: "c"} ] }')
			

def getByID(tree, id):
	# (for checking VOTables)
	res = tree.xpath("//*[@ID='%s']"%id)
	assert len(res)==1, "Resolving ID %s gave %d matches"%(id, len(res))
	return res[0]


#class _SampleQs(dm.DMNode):
#	DM_model = _toyModel
#	DM_typeName = "Bland"

	_a_someQ = dm.Annotation(None, unit="m", ucd="phys.length")


class AnnotationTest(testhelpers.VerboseTest):
	def testAtomicValue(self):
		t = base.parseFromString(rscdef.TableDef,
			"""<table id="foo">
				<dm>
					(testdm:testclass) {
						attr1: test
					}
				</dm></table>""")
		self.assertEqual(t.annotations[0].type, "testdm:testclass")
		self.assertEqual(t.annotations[0].childRoles["attr1"].value,
			"test")
	
	def testColumnReference(self):
		t = base.parseFromString(rscdef.TableDef,
			"""<table id="foo">
				<dm>
					(testdm:testclass) {
						attr1: @col1
					}
				</dm><column name="col1" ucd="stuff"/></table>""")
		col = t.annotations[0].childRoles["attr1"].value
		self.assertEqual(col.ucd, "stuff")
	

class _DirectVOT(testhelpers.TestResource):
	def make(self, deps):
		td = base.parseFromString(rscdef.TableDef,
			"""<table id="foo">
				<dm>
					(testdm:testclass) {
						attr1: @col1
						attr2: 
							(testdm:otherclass) {
								nook: 0.1
								ra: @raj2000
								dec: @dej2000
							}
						references: (testdm:ref)[
							{ bibcode: "too lazy" }
							{ bibcode: "still too lazy" }]
					}
				</dm>
					<column name="col1" ucd="stuff" type="text"/>
					<column name="raj2000"/>
					<column name="dej2000"/>
				</table>""")
		
		t = rsc.TableForDef(td, rows=[
			{"col1": "id1", "raj2000": 0.3, "dej2000": 3.1}])
		
		return testhelpers.getXMLTree(votablewrite.getAsVOTable(t, 
			ctx=votablewrite.VOTableContext(version=(1,4))), debug=False)


class DirectSerTest(testhelpers.VerboseTest):
	resources = [("tree", _DirectVOT())]

	def testVODMLModelDefined(self):
		dmgroup = self.tree.xpath(
			"//GROUP[VODML/TYPE='vo-dml:Model']"
			"[PARAM[VODML/ROLE='name']/@value='vo-dml']")[0]
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='name']")[0].get("value"),
			"vo-dml")
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='url']")[0].get("value"),
			"http://www.ivoa.net/dm/vo-dml.xml")
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='version']")[0].get("value"),
			"1.0")

	def testTestModelDefined(self):
		dmgroup = self.tree.xpath(
			"//GROUP[VODML/TYPE='vo-dml:Model']"
			"[PARAM[VODML/ROLE='name']/@value='testdm']")[0]

		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='name']")[0].get("value"),
			"testdm")
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='url']")[0].get("value"),
			"http://docs.g-vo.org/testdm/0.1")
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='version']")[0].get("value"),
			"0.1")

	def testNoExtraModels(self):
		self.assertEqual(2,
			len(self.tree.xpath("//GROUP[VODML/TYPE='vo-dml:Model']")))

	def testTestclassInstancePresent(self):
		res = self.tree.xpath("RESOURCE/TABLE/GROUP[VODML/TYPE='testdm:testclass']")
		self.assertEqual(len(res), 1)
	
	def testLiteralSerialized(self):
		par = self.tree.xpath(
			"RESOURCE/TABLE/GROUP/GROUP[VODML/TYPE='testdm:otherclass']"
			"/PARAM[VODML/ROLE='nook']")[0]
		self.assertEqual(par.get("value"), "0.1")
		self.assertEqual(par.get("datatype"), "unicodeChar")

	def testChildColumnAnnotated(self):
		fr = self.tree.xpath(
			"RESOURCE/TABLE/GROUP[VODML/TYPE='testdm:testclass']"
			"/FIELDref[VODML/ROLE='attr1']")[0]
		col = getByID(self.tree, fr.get("ref"))
		self.assertEqual(col.get("name"), "col1")

	def testNestedColumnAnnotated(self):
		fr = self.tree.xpath(
			"RESOURCE/TABLE/GROUP/GROUP[VODML/TYPE='testdm:otherclass']"
			"/FIELDref[VODML/ROLE='ra']")[0]
		col = getByID(self.tree, fr.get("ref"))
		self.assertEqual(col.get("name"), "raj2000")
	
	def testCollection(self):
		gr = self.tree.xpath(
			"RESOURCE/TABLE/GROUP/GROUP[VODML/ROLE='references']")
		self.assertEqual(len(gr), 1)
		refs = gr[0].xpath("GROUP/PARAM[VODML/ROLE='bibcode']")
		self.assertEqual(len(refs), 2)
		self.assertEqual(refs[0].get("value"), "too lazy")



class _TableVOT(testhelpers.TestResource):
	def make(self, deps):
		td = testhelpers.getTestRD().getById("abcd").copy(None)
		td.maker = "Oma"

		class Rulers(dm.DMNode):
			DM_model = _toyModel
			DM_typeName = "Rulers"
			_a_caesar = dm.ColumnAnnotation(columnName="c")
			_a_david = dm.ColumnAnnotation(columnName="d")

		td.annotations = [common.VODMLMeta.fromRoles(
				_toyModel, "Toy", dm.ColumnAnnotation("name", "a"),
				dm.ColumnAnnotation("width", "b"), 
				dm.ColumnAnnotation("birthday", "e"),
				dm.Annotation(name="maker", value="Opa"),
				dm.GroupRefAnnotation("rulers", Rulers())),
			common.VODMLMeta.fromRoles(
				_toy2Model, "Toy2", dm.ColumnAnnotation("properName", "a"))]

		names = [c.name for c in td]
		table = rsc.TableForDef(td, rows=[dict(zip(names, r)) 
			for r in [
				("fred", 12, 13, 15, datetime.datetime(2014, 4, 3, 12, 20)),
				("fran", 11, 14, 13, datetime.datetime(2013, 2, 20, 12, 20))]])

		return (table, 
			testhelpers.getXMLTree(votablewrite.getAsVOTable(table), debug=False))


@unittest.skip("Pending Res/VOT redesign")
class TableSerTest(testhelpers.VerboseTest):
#	resources = [("tt", _TableVOT())]

	def testDM1declared(self):
		dm1group = self.tt[1].xpath(
			"GROUP[PARAM/@name='url' and PARAM/@value='http://g-vo.org/toymodel']"
		)[0]
		self.assertEqual("toy",
			dm1group.xpath("PARAM[VODML/ROLE='vo-dml:Model.name']")[0].get("value"))
	
	def testDM2declared(self):
		dm2group = self.tt[1].xpath(
			"GROUP[PARAM[VODML/ROLE='vo-dml:Model.name' and @value='toy2']]")[0]
		self.assertEqual("http://g-vo.org/toy2model",
			dm2group.xpath("PARAM[VODML/ROLE='vo-dml:Model.url']")[0].get("value"))

	def testTypeDeclared(self):
		self.assertEqual("toy:Toy",
			self.tt[1].xpath("RESOURCE/TABLE/GROUP/VODML/TYPE")[1].text)
	
	def testParamSerialized(self):
		self.assertEqual("Oma", self.tt[1].xpath(
			"RESOURCE/TABLE/GROUP[2]/PARAM[VODML/ROLE='toy:Toy.maker']")[0].get(
			"value"))
	
	def testFieldrefsSerialized(self):
		self.assertEqual(3, len(self.tt[1].xpath(
			"RESOURCE/TABLE/GROUP[VODML/TYPE='toy:Toy']/FIELDref[VODML/ROLE]")))

	def testFieldrefRef(self):
		for el in self.tt[1].xpath(
				"RESOURCE/TABLE/GROUP/FIELDref[VODML/ROLE]"):
			self.assertEqual("FIELD",
				getByID(self.tt[1], el.get("ref")).tag)

	def testReffedObject(self):
		reffedGroup = self.tt[1].xpath("//GROUP[VODML/TYPE='toy:Rulers']")[0]
		self.assertEqual(
			reffedGroup.xpath("FIELDref[@ref='c']/VODML/ROLE")[0].text,
			"toy:Rulers.caesar")

	def testInnerReference(self):
		reffing = self.tt[1].xpath("//GROUP[VODML/ROLE='toy:Toy.rulers']")[0]
		self.assertEqual(reffing.xpath("VODML/TYPE")[0].text, "vo-dml:GROUPref")
		self.assertEqual(getByID(self.tt[1], reffing.get("ref")).tag, "GROUP")

	# TODO: Tests for making objects from the table.


class _ManyTablesVOT(testhelpers.TestResource):
	def make(self, deps):
		rd = base.parseFromString(rscdesc.RD, """
			<resource schema="test">
				<table id="auxaux">
					<column name="mything" type="integer"/>
				</table>
				<table id="aux">
					<foreignKey inTable="auxaux" source="c2" dest="mything"/>
					<column name="c1" type="integer"/>
					<column name="c2" type="integer"/>
				</table>
				<table id="main">
					<foreignKey inTable="aux" source="a,b" dest="c1,c2"/>
					<foreignKey inTable="auxaux" source="c" dest="mything"/>
					<column name="a" type="integer"/>
					<column name="b" type="integer"/>
					<column name="c" type="integer"/>
				</table>
				<data id="import">
					<sources item="2"/>
					<embeddedGrammar isDispatching="True">
						<iterator>
						<code>
						for id in range(int(self.sourceToken)):
							yield "auxaux", {"mything": id}
							for c2 in range(3):
								yield "aux", {"c1": id, "c2": c2}
								for c in range(2):
									yield "main", {"a": id, "b": c2, "c": c}
						</code>
						</iterator>
					</embeddedGrammar>
					<make role="auxaux" table="auxaux"/>
					<make role="aux" table="aux"/>
					<make role="main" table="main"/>
				</data>
			</resource>""")

		# hold ref to data so dependent tables don't go away.
		self.data = rsc.makeData(rd.getById("import"))
		table = self.data.tables["main"]
		table.tableDef.annotations = [common.VODMLMeta.fromRoles(_toyModel, "Toy",
			dm.ColumnAnnotation("foo", "a"), dm.ColumnAnnotation("bar", "b")),
			common.VODMLMeta.fromRoles(
				_toyModel, "Mess", dm.ColumnAnnotation("comp", "c"))]

		return (table, 
			testhelpers.getXMLTree(votablewrite.getAsVOTable(table), debug=False))

	def clean(self, ignored):
		del self.data  


@unittest.skip("Pending Res/VOT redesign")
class ManyTablesTest(testhelpers.VerboseTest):
#	resources = [("tt", _ManyTablesVOT())]

	def testAllTablesSerializedOnce(self):
		self.assertEqual(len(self.tt[1].xpath("RESOURCE/TABLE")), 3)

	def testAuxAuxFK(self):
		refGroup = self.tt[1].xpath("//GROUP[VODML/TYPE='toy:Toy']"
			"/GROUP[VODML/TYPE='vo-dml:ORMReference']")[0]
		self.assertEqual(refGroup.xpath("FIELDref")[0].get("ref"), "a")
		self.assertEqual(refGroup.xpath("FIELDref")[1].get("ref"), "b")
			
		pkGroup = getByID(self.tt[1], refGroup.get("ref"))
		self.assertEqual(pkGroup.xpath("VODML/ROLE")[0].text,
			"vo-dml:ObjectTypeInstance.ID")

	def testAuxFK(self):
		refGroup = self.tt[1].xpath("//GROUP[VODML/TYPE='toy:Mess']"
			"/GROUP[VODML/TYPE='vo-dml:ORMReference']")[0]
		self.assertEqual(refGroup.xpath("FIELDref")[0].get("ref"), "c")

		pkGroup = getByID(self.tt[1], refGroup.get("ref"))
		self.assertEqual(pkGroup.xpath("VODML/ROLE")[0].text,
			"vo-dml:ObjectTypeInstance.ID")

	def testSecondaryRefResolves(self):
		destField = getByID(self.tt[1],
			self.tt[1].xpath("RESOURCE/TABLE[1]/GROUP/FIELDref")[0].get("ref"))
		self.assertEqual(destField.get("name"), "c1")


if __name__=="__main__":
	testhelpers.main(DirectSerTest)
