"""
Tests to do with new-style data modelling and VO-DML serialisation.
"""

from gavo.helpers import testhelpers

import datetime

from gavo import dm
from gavo import rsc
from gavo.dm import common
from gavo.formats import votablewrite


_toyModel = dm.Model(name="toy", version="0.5", 
	url="http://g-vo.org/toymodel")
_toy2Model = dm.Model(name="toy2", version="2.5",
	url="http://g-vo.org/toy2model")


class _SampleQs(dm.DMNode):
	DM_model = _toyModel
	DM_typeName = "Bland"

	_a_someQ = dm.Annotation(None, unit="m", ucd="phys.length")


class AnnotationTest(testhelpers.VerboseTest):
	def testGetValue(self):
		o = _SampleQs(someQ=4)
		self.assertEqual(o.someQ, 4)
	
	def testGetMeta(self):
		o = _SampleQs()
		self.assertEqual(dm.getAnnotations(o)[0]["someQ"].ucd, "phys.length")



class _DirectVOT(testhelpers.TestResource):
	def make(self, deps):
		class Child(object):
			x = 2
			y = 3
			annotations = [common.VODMLMeta.fromRoles(_toyModel, "Pos",
				"x", "y")]

		class Ob(object):
			width = 3
			height = 6.8
			location = "upstairs"
			pos = Child
			internal = object()
			annotations = [common.VODMLMeta.fromRoles(_toyModel, "Thing",
				"width", "height", "location",
				dm.DataTypeAnnotation("pos", "Pos"))]
		
		return testhelpers.getXMLTree(dm.asString(
			votablewrite.VOTableContext(), Ob), debug=False)


class DirectSerTest(testhelpers.VerboseTest):
	resources = [("tree", _DirectVOT())]

	def testVODMLModelFirst(self):
		dmgroup = self.tree.xpath("//GROUP[VODML/TYPE='vo-dml:Model']")[0]
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='vo-dml:Model.name']")[0].get("value"),
			"vo-dml")
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='vo-dml:Model.url']")[0].get("value"),
			"http://this.needs.to/be/fixed")
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='vo-dml:Model.version']")[0].get("value"),
			"1.0")

	def testToyModelDefined(self):
		dmgroup = self.tree.xpath("//GROUP[VODML/TYPE='vo-dml:Model']")[1]
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='vo-dml:Model.name']")[0].get("value"),
			"toy")
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='vo-dml:Model.url']")[0].get("value"),
			"http://g-vo.org/toymodel")
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='vo-dml:Model.version']")[0].get("value"),
			"0.5")

	def testNoExtraModels(self):
		self.assertEqual(2,
			len(self.tree.xpath("//GROUP[VODML/TYPE='vo-dml:Model']")))

	def testToyInstancePresent(self):
		toyGroup = self.tree.xpath("RESOURCE/GROUP")[0]
		self.assertEqual(toyGroup.xpath("VODML/TYPE")[0].text, "toy:Thing")
	
	def testFloatAttrSerialized(self):
		par = self.tree.xpath("//PARAM[VODML/ROLE='toy:Thing.width']")[0]
		self.assertEqual(par.get("value"), "3")

	def testStringAttrSerialized(self):
		par = self.tree.xpath("//PARAM[VODML/ROLE='toy:Thing.location']")[0]
		self.assertEqual(par.get("value"), "upstairs")

	def testIntTypeDeclared(self):
		par = self.tree.xpath("//PARAM[VODML/ROLE='toy:Thing.width']")[0]
		self.assertEqual(par.get("datatype"), "int")
		self.assertEqual(par.get("arraysize"), None)

	def testFloatTypeDeclared(self):
		par = self.tree.xpath("//PARAM[VODML/ROLE='toy:Thing.height']")[0]
		self.assertEqual(par.get("datatype"), "double")
		self.assertEqual(par.get("arraysize"), None)

	def testStringTypeDeclared(self):
		par = self.tree.xpath("//PARAM[VODML/ROLE='toy:Thing.location']")[0]
		self.assertEqual(par.get("datatype"), "char")
		self.assertEqual(par.get("arraysize"), "*")

	def testDataTypeChild(self):
		posGroup = self.tree.xpath("//GROUP/GROUP[VODML/TYPE='toy:Pos']")[0]
		self.assertEqual("3",
			posGroup.xpath("PARAM[VODML/ROLE='toy:Pos.y']")[0].get("value"))

class _TableVOT(testhelpers.TestResource):
	def make(self, deps):
		td = testhelpers.getTestRD().getById("abcd").copy(None)
		td.maker = "Oma"
		td.annotations = [common.VODMLMeta.fromRoles(
				_toyModel, "Toy", dm.ColumnAnnotation("name", "a"),
				dm.ColumnAnnotation("width", "b"), 
				dm.ColumnAnnotation("birthday", "e"),
				dm.Annotation(name="maker", value="Opa")),
			common.VODMLMeta.fromRoles(
				_toy2Model, "Toy2", dm.ColumnAnnotation("properName", "a"))]

		names = [c.name for c in td]
		table = rsc.TableForDef(td, rows=[dict(zip(names, r)) 
			for r in [
				("fred", 12, 13, 15, datetime.datetime(2014, 4, 3, 12, 20)),
				("fran", 11, 14, 13, datetime.datetime(2013, 2, 20, 12, 20))]])

		return (table, 
			testhelpers.getXMLTree(votablewrite.getAsVOTable(table), debug=False))


class TableSerTest(testhelpers.VerboseTest):
	resources = [("tt", _TableVOT())]

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
			self.tt[1].xpath("RESOURCE/TABLE/GROUP/VODML/TYPE")[0].text)
	
	def testParamSerialized(self):
		self.assertEqual("Oma", self.tt[1].xpath(
			"RESOURCE/TABLE/GROUP[1]/PARAM[VODML/ROLE='toy:Toy.maker']")[0].get(
			"value"))
	
	def testFieldrefsSerialized(self):
		self.assertEqual(3, len(self.tt[1].xpath(
			"RESOURCE/TABLE/GROUP[1]/FIELDref[VODML/ROLE]")))

	def testFieldrefRef(self):
		for el in self.tt[1].xpath(
				"RESOURCE/TABLE/GROUP/FIELDref[VODML/ROLE]"):
			self.assertEqual("FIELD",
				self.tt[1].xpath("//*[@ID='%s']"%el.get("ref"))[0].tag)

	# TODO: Tests for making objects from the table.

if __name__=="__main__":
	testhelpers.main(DirectSerTest)
