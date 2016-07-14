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
from gavo.dm import vodml
from gavo.formats import votablewrite


def normalizeSIL(sil):
	return re.sub("\s+", " ", sil).strip()


class ModelTest(testhelpers.VerboseTest):
	def testMetadataParsing(self):
		toydm = dm.getModelForPrefix("dachstoy")
		self.assertEqual(toydm.description, 
			"A toy model for DaCHS regression testing")
		self.assertEqual(toydm.title, "DaCHS Toy model")
		self.assertEqual(toydm.version, "1.0a-pl23.44c")
		self.assertEqual(toydm.url, "http://docs.g-vo.org/dachstoy")
	
	def testIdAccess(self):
		toydm = dm.getModelForPrefix("dachstoy")
		res = toydm.getByVODMLId("Ruler.width")
		self.assertEqual(res.find("description").text, "A dimension")

	def testPrefixIgnored(self):
		toydm = dm.getModelForPrefix("dachstoy")
		res = toydm.getByVODMLId("dachstoy:Ruler.width")
		self.assertEqual(res.find("description").text, "A dimension")

	def testNoIdAccess(self):
		toydm = dm.getModelForPrefix("dachstoy")
		self.assertRaisesWithMsg(base.NotFoundError,
			"data model element 'Broken.toy' could not be located"
			" in dachstoy data model",
			toydm.getByVODMLId,
			("Broken.toy",))
	
	def testIndexBuilt(self):
		index = dm.getModelForPrefix("dachstoy").idIndex
		self.assertTrue(isinstance(index, dict))
		key, value = index.iteritems().next()
		self.assertTrue(isinstance(key, basestring))
		self.assertTrue(hasattr(value, "attrib"))


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

	def testObjectCollection(self):
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

	def testImmediateCollection(self):
		res = sil.getGrammar().parseString("""
			(:testclass) {
				seq: [a "b c d" @e]}""")
		self.assertEqual(res[0],
			('obj', ':testclass', 
				[('attr', 'seq', 
					('coll', None, ['a', 'b c d', 'e']))]))


class TestSILParser(testhelpers.VerboseTest):
	def testNestedObject(self):
		res = sil.getAnnotation("""
			(testdm:testclass) {
				attr1: (testdm:otherclass) {
						attr2: val
					}
			}""", dmrd.getAnnotationMaker(None))
		self.assertEqual(normalizeSIL(res.asSIL()),
			'(testdm:testclass) { (testdm:otherclass) { attr2: val} }')

	def testObjectCollection(self):
		res = sil.getAnnotation("""
			(testdm:testclass) {
				seq: (testdm:otherclass)[
					{attr1: a}
					{attr1: b}
					{attr1: c}]}""", dmrd.getAnnotationMaker(None))
		self.assertEqual(normalizeSIL(res.asSIL()),
			'(testdm:testclass) { seq: (testdm:otherclass)'
			' [{ attr1: a} { attr1: b} { attr1: c} ] }')

	def testAtomicCollection(self):
		res = sil.getAnnotation("""
			(testdm:testclass) {
				seq: [a "b c" 3.2]}""", dmrd.getAnnotationMaker(None))
		self.assertEqual(normalizeSIL(res.asSIL()),
			'(testdm:testclass) { seq: [a "b c" 3.2] }')


def getByID(tree, id):
	# (for checking VOTables)
	res = tree.xpath("//*[@ID='%s']"%id)
	assert len(res)==1, "Resolving ID %s gave %d matches"%(id, len(res))
	return res[0]


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
					(dachstoy:Ruler) {
						width: @col1
						location: 
							(dachstoy:Location) {
								x: 0.1
								y: @raj2000
								z: @dej2000
							}
						maker: [
							Oma "Opa Rudolf"]
					}
				</dm>
					<column name="col1" ucd="stuff" type="text"/>
					<column name="raj2000"/>
					<column name="dej2000"/>
				</table>""")
		
		t = rsc.TableForDef(td, rows=[
			{"col1": "1.5", "raj2000": 0.3, "dej2000": 3.1}])
		
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
			"http://www.ivoa.net/dm/VO-DML.vo-dml.xml")
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='version']")[0].get("value"),
			"0.x")

	def testTestModelDefined(self):
		dmgroup = self.tree.xpath(
			"//GROUP[VODML/TYPE='vo-dml:Model']"
			"[PARAM[VODML/ROLE='name']/@value='dachstoy']")[0]

		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='url']")[0].get("value"),
			"http://docs.g-vo.org/dachstoy")
		self.assertEqual(
			dmgroup.xpath("PARAM[VODML/ROLE='version']")[0].get("value"),
			"1.0a-pl23.44c")

	def testNoExtraModels(self):
		self.assertEqual(2,
			len(self.tree.xpath("//GROUP[VODML/TYPE='vo-dml:Model']")))

	def testTestclassInstancePresent(self):
		res = self.tree.xpath("RESOURCE/TABLE/GROUP[VODML/TYPE='dachstoy:Ruler']")
		self.assertEqual(len(res), 1)
	
	def testLiteralSerialized(self):
		par = self.tree.xpath(
			"RESOURCE/TABLE/GROUP/GROUP[VODML/TYPE='dachstoy:Location']"
			"/PARAM[VODML/ROLE='dachstoy:Location.x']")[0]
		self.assertEqual(par.get("value"), "0.1")
		self.assertEqual(par.get("datatype"), "unicodeChar")

	def testChildColumnAnnotated(self):
		fr = self.tree.xpath(
			"RESOURCE/TABLE/GROUP[VODML/TYPE='dachstoy:Ruler']"
			"/FIELDref[VODML/ROLE='dachstoy:Ruler.width']")[0]
		col = getByID(self.tree, fr.get("ref"))
		self.assertEqual(col.get("name"), "col1")

	def testNestedColumnAnnotated(self):
		fr = self.tree.xpath(
			"RESOURCE/TABLE/GROUP/GROUP[VODML/TYPE='dachstoy:Location']"
			"/FIELDref[VODML/ROLE='dachstoy:Location.y']")[0]
		col = getByID(self.tree, fr.get("ref"))
		self.assertEqual(col.get("name"), "raj2000")

	def testCollection(self):
		gr = self.tree.xpath(
			"RESOURCE/TABLE/GROUP/GROUP[VODML/ROLE='maker']")
		self.assertEqual(len(gr), 1)
		params = gr[0].xpath("PARAM")
		self.assertEqual(len(params), 2)
		self.assertEqual(params[0].get("value"), "Oma")
		self.assertEqual(params[1].get("value"), "Opa Rudolf")

if __name__=="__main__":
	testhelpers.main(DirectSerTest)
