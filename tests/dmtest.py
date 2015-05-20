"""
Tests to do with new-style data modelling and VO-DML serialisation.
"""

from gavo.helpers import testhelpers


from gavo import dm


_toyModel = dm.Model(name="toy", version="0.5", url="http://g-vo.org/toymodel")


class _OnlyParamVOT(testhelpers.TestResource):
	def make(self, deps):
		class Ob(object):
			width = 3
			height = 6.8
			location = "upstairs"
			internal = object()
			annotations = dm.Annotations.fromRoles(_toyModel, "Thing",
				"width", "height", "location")
		
		return testhelpers.getXMLTree(dm.asString(Ob), debug=False)


class SimpleSerTest(testhelpers.VerboseTest):
	resources = [("tree", _OnlyParamVOT())]

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



if __name__=="__main__":
	testhelpers.main(SimpleSerTest)
