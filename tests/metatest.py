"""
Tests for RD metadata management.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import copy
import sys
import traceback
from xml import sax

from nevow import tags as T, flat

from gavo.helpers import testhelpers

from gavo import api
from gavo import base
from gavo.base import meta
from gavo.base import metavalidation
from gavo.registry import builders
from gavo.utils import stanxml
from gavo.web import common as webcommon


class KeyTest(testhelpers.VerboseTest):
	"""tests for parsing of meta keys.
	"""
	def testPrimary(self):
		"""tests for correct recognition of primaries in meta keys.
		"""
		for key, result in [
				("publisher", "publisher"),
				("_related", "_related"),
				("coverage.spatial", "coverage"),]:
			self.assertEqual(meta.getPrimary(key), result)

	def testBadPrimary(self):
		"""tests for correct rejection of bad meta keys.
		"""
		for shouldFail in ["", "abc+7", ".foo", "???"]:
			self.assertRaisesVerbose(base.MetaSyntaxError, meta.getPrimary, 
				(shouldFail,), "%s returned primary meta but shouldn't have"%shouldFail)

	def testParse(self):
		"""tests for correct parsing of meta keys.
		"""
		for key, result in [
				("coverage.spatial.ra", ["coverage", "spatial", "ra"]),
				("publisher", ["publisher"]),
				("_related", ["_related"]),
				("coverage.spatial", ["coverage", "spatial"]),]:
			self.assertEqualForArgs(meta.parseKey, result, key)

	def testBadKey(self):
		for shouldFail in ["", "abc+7", ".foo", "???", "coverage.x/7", "foo..bar"]:
			self.assertRaisesVerbose(base.MetaSyntaxError, meta.parseKey, 
				(shouldFail,), "%s returned primary meta but shouldn't have"%shouldFail)


class CompoundTest(testhelpers.VerboseTest):
	"""tests for buildup of hierarchical meta items.
	"""
	def testFromText(self):
		"""tests for correct buildup of MetaItems from text keys.
		"""
		m = base.MetaMixin()
		m.addMeta("creator.name", meta.MetaValue("F. Bar"))
		m.addMeta("creator.address", meta.MetaValue("21 Foo Street, Bar 02147"))
		self.assertEqual(len(m.getMeta("creator").children), 1)
		self.assertEqual(m.getMeta("creator.name").children[0].content, "F. Bar")
		self.assertEqual(m.getMeta("creator.address").children[0].content, 
			"21 Foo Street, Bar 02147")
		self.assert_(m.getMeta("creator").getMeta("name") is
			m.getMeta("creator.name"))

	def testWithContact(self):
		m = base.MetaMixin()
		m.addMeta("curation.publisher", "The GAVO DC team")
		m.addMeta("curation.publisherID", "ivo://org.gavo.dc")
		m.addMeta("curation.contact", "gavo@ari.uni-heidelberg.de")
		m.addMeta("curation.contact.name", "GAVO Data Center Team")
		m.addMeta("curation.contact.address", 
			"Moenchhofstrasse 12-14, D-69120 Heidelberg")
		m.addMeta("curation.contact.email", "gavo@ari.uni-heidelberg.de")
		m.addMeta("curation.contact.telephone", "++49 6221 54 1837")
		self.assertEqual(str(m.getMeta("curation.contact.name")), 
			"GAVO Data Center Team")
		self.assertEqual(str(m.getMeta("curation.contact")), 
			"gavo@ari.uni-heidelberg.de")
		self.assertEqual(str(m.getMeta("curation").getMeta("contact.telephone")),
			"++49 6221 54 1837")

	def testFromItems(self):
		"""tests for correct buildup of MetaItems from meta items.
		"""
		mv = meta.MetaValue()
		mv.addMeta("name", meta.MetaValue("Foo B."))
		mv.addMeta("address", meta.MetaValue("homeless"))
		m = base.MetaMixin()
		m.addMeta("creator", mv)
		self.assertEqual(len(m.getMeta("creator").children), 1)
		self.assertEqual(m.getMeta("creator.name").children[0].content, "Foo B.")
		self.assertEqual(m.getMeta("creator.address").children[0].content, 
			"homeless")
		self.assert_(m.getMeta("creator").getMeta("name") is
			m.getMeta("creator.name"))

	def testDoubleChildren(self):
		m = base.MetaMixin()
		m.addMeta("testQuery.pos.ra", "340")
		m.addMeta("testQuery.pos.dec", "3")
		m.addMeta("testQuery.size.ra", "0.5")
		m.addMeta("testQuery.size.dec", "1")
		self.assertEqual(str(m.getMeta("testQuery.pos.ra")), "340")
		self.assertEqual(str(m.getMeta("testQuery.pos.dec")), "3")
		self.assertEqual(str(m.getMeta("testQuery.size.dec")), "1")
		self.assertEqual(str(m.getMeta("testQuery.size.ra")), "0.5")

	def testFromXMLSequence(self):
		m = parseMetaXML("""
			<meta name="creator">
				<meta name="name">Maturi, M.</meta>
				<meta name="logo"
					>http://dc.g-vo.org/carsarcs/q/s/static/arcs-logo_letters.png</meta>
			</meta>
			""")
		self.assertEqual(base.getMetaText(m, "creator.name"), "Maturi, M.")
		self.assertEqual(base.getMetaText(m, "creator.logo"), 
			"http://dc.g-vo.org/carsarcs/q/s/static/arcs-logo_letters.png")


class SequenceTest(testhelpers.VerboseTest):
	"""tests for correct buildup of sequence-like meta items.
	"""
# You're not supposed to access meta info like here -- see below for
# how to retrieve meta values.  This is to show buildup.
	def testFlatTextSequence(self):
		"""tests for buildup of sequence metas using text keys.
		"""
		m = base.MetaMixin()
		m.addMeta("subject", "boredom")
		m.addMeta("subject", "drudge")
		m.addMeta("subject", "pain")
		self.assertEqual(len(m.getMeta("subject").children), 3)
		self.assertEqual(m.getMeta("subject").children[0].content, "boredom")
		self.assertEqual(m.getMeta("subject").children[2].content, "pain")
	
	def testCompoundTextSequence(self):
		"""tests for correct buildup of sequences of compound meta items.
		"""
		m = base.MetaMixin()
		m.addMeta("coverage.spatial.ra", "10-20")
		m.addMeta("coverage.spatial.dec", "10-20")
		m.addMeta("coverage.spatial", None)
		m.addMeta("coverage.spatial.ra", "-10-20")
		m.addMeta("coverage.spatial.dec", "-10-20")
		self.assertEqual(len(m.getMeta("coverage").children), 1)
		self.assertEqual(len(m.getMeta("coverage.spatial").children), 2)
		self.assertEqual(m.getMeta("coverage.spatial").children[1].
			getMeta("ra").children[0].content, "-10-20")
		self.assertRaises(base.MetaCardError, m.getMeta, "coverage.spatial.ra")
		self.assertRaises(base.MetaCardError, m.getMeta, "coverage.spatial.dec")

	def testCompoundObjectSequence(self):
		"""tests for correct buildup of meta information through object embedding
		"""
		m = base.MetaMixin()
		alc = meta.MetaValue("50%")
		org = meta.MetaValue("grape")
		stuff = meta.MetaValue("fusel")
		stuff.addMeta("alc", alc)
		stuff.addMeta("org", org)
		m.addMeta("stuff", stuff)
		alc = meta.MetaValue("70%")
		org = meta.MetaValue("rye")
		stuff = meta.MetaValue("fusel")
		stuff.addMeta("alc", alc)
		stuff.addMeta("org", org)
		m.addMeta("stuff", stuff)
		self.assertEqual(len(m.getMeta("stuff").children), 2)
		self.assertEqual(m.getMeta("stuff").children[0].
			getMeta("alc").getContent(), "50%")
		self.assertEqual(m.getMeta("stuff").children[1].
			getMeta("alc").getContent(), "70%")
		# cannot be decided because stuff.alc has multiple values
		self.assertRaises(base.MetaCardError, m.getMeta,
			"stuff.alc")


class IterMetaTest(testhelpers.VerboseTest):
	def testMixedMetas(self):
		m = base.MetaMixin()
		meta.parseMetaStream(m, "foo.bar: a\nfoo:\nfoo.bar:b\nfoo.bar:c")
		self.assertEqual(list(v.getContent() for v in m.iterMeta("foo.bar")),
			["a", "b", "c"])

	def testPropagation(self):
		res = "; ".join(m.getContent("text") for m in
			testhelpers.getTestRD().getById("basicprod").iterMeta(
				"creator.name", propagate=True))
		self.assertEqual(res, "John C. Testwriter")
	
	def testPropagationToDefault(self):
		res = "; ".join(m.getContent("text") for m in
			testhelpers.getTestRD("pubtest").getById("moribund"
				).iterMeta("creator.name", propagate=True))
		self.assertEqual(res, "Could be same as contact.name")

	def testAllMeta(self):
		cont = meta.MetaMixin()
		meta.parseMetaStream(cont, "single: a\none.two: b\none.two:\n"
			"one.two.three:c\none.two.three:d\none.two:e\n")
		res = [(key, value.getContent("text"))
			for key, value in cont.getAllMetaPairs()]
		self.assertEqual(res,  [('single', 'a'), ('one.two', 'b'), 
			('one.two.three', 'c'), ('one.two.three', 'd'), ('one.two', 'e')])


class SetAndDelTest(testhelpers.VerboseTest):
	"""tests for working deletion and setting of meta items.
	"""
	def testSilentDeletion(self):
		m = base.MetaMixin()
		self.assertRuns(m.delMeta, "x")

	def testDeletionSimple(self):
		m = base.MetaMixin()
		m.addMeta("x", "abc")
		self.assertEqual(str(m.getMeta("x")), "abc")
		m.delMeta("x")
		self.assertEqual(m.getMeta("x"), None)

	def testDeletionTree(self):
		m = base.MetaMixin()
		m.addMeta("x.y.z", "abc")
		self.assertEqual(str(m.getMeta("x.y.z")), "abc")
		m.delMeta("x.y.z")
		self.assertEqual(m.getMeta("x.y.z"), None)
		# make sure we cleaned up
		self.assertEqual(m.getMeta("x.y"), None)
		self.assertEqual(m.getMeta("x"), None)

	def testSiblingsAreKept(self):
		m = base.MetaMixin()
		m.addMeta("x.y.z", "abc")
		m.addMeta("x.y.y", "cba")
		m.delMeta("x.y.z")
		self.assertEqual(m.getMeta("x.y.z"), None)
		self.assertEqual(str(m.getMeta("x.y.y")), "cba")
	
	def testAncestorsAreKept(self):
		m = base.MetaMixin()
		m.addMeta("x.y.z", "abc")
		m.addMeta("x", "present")
		m.delMeta("x.y.z")
		self.assertEqual(str(m.getMeta("x")), "present")
	
	def testItemsAreDeleted(self):
		m = base.MetaMixin()
		m.addMeta("x.y.z", "abc")
		m.addMeta("x.y.z", "bdc")
		m.delMeta("x.y.z")
		self.assertEqual(m.getMeta("x.y.z"), None)
	
	def testSetMeta(self):
		m = base.MetaMixin()
		m.addMeta("x.y.z", "abc")
		m.addMeta("x.y.z", "bcd")
		m.setMeta("x.y.z", "new")
		self.assertEqual(str(m.getMeta("x.y.z")), "new")


class CopiesTest(testhelpers.VerboseTest):
	"""tests for deep copying of meta containers.
	"""
	class Copyable(base.MetaMixin):
		def __init__(self, name):
			base.MetaMixin.__init__(self)
			self.name = name

		def copy(self):
			newOb = copy.copy(self)
			newOb.deepCopyMeta()
			return newOb

	def testSimpleCopy(self):
		m = self.Copyable("yikes")
		m.addMeta("subject", "boredom")
		m.addMeta("subject", "drudge")
		m.addMeta("subject", "pain")
		self.assertEqual(len(m.getMeta("subject").children), 3)
		m2 = m.copy()
		self.assertEqual(len(m2.getMeta("subject").children), 3)
		m2.addMeta("subject", "ache")
		self.assertEqual(len(m2.getMeta("subject").children), 1)
		m2.addMeta("subject", "drudge")
		self.assertEqual(len(m2.getMeta("subject").children), 2)
		self.assertEqual(len(m.getMeta("subject").children), 3)

	def testMessyCopy(self):
		m = self.Copyable("mess")
		m.addMeta("foo", "base")
		m.addMeta("foo.bar.baz", "x")
		m.addMeta("foo.bar.baz", "y")
		m.addMeta("foo.bar.quux", "arm")
		m.addMeta("foo.fii", "z")
		tb = meta.TextBuilder()
		m2 = m.copy()
		self.assertEqual(m.buildRepr("foo", tb), m2.buildRepr("foo", tb))
		m2.addMeta("foo.fii", "wo")
		self.assertEqual(str(m2.getMeta("foo.fii")), "wo")
		self.assertEqual(str(m.getMeta("foo.fii")), "z")


class ContentTest(testhelpers.VerboseTest):
# Under normal circumstances, you don't want to access meta content
# like this either; this is much better than fiddling with children
# and content, though
	def testLiteral(self):
		m = base.MetaMixin()
		m.addMeta("brasel", meta.MetaValue("quox \n  ab   c", format="literal"))
		self.assertEqual(m.getMeta("brasel").getContent(), "quox \n  ab   c")
		self.assertEqual(m.getMeta("brasel").getContent("html"),
			'<span class="literalmeta">quox \n  ab   c</span>')
	
	def testPlain(self):
		m = base.MetaMixin()
		m.addMeta("brasel", meta.MetaValue("ab\ncd   foo"))
		self.assertEqual(m.getMeta("brasel").getContent(), "ab cd foo")
		self.assertEqual(m.getMeta("brasel").getContent("html"), 
			'<span class="plainmeta">ab cd foo</span>')
		m.addMeta("long", meta.MetaValue("ab\ncd   foo\n\nnk\n * ork"))
		self.assertEqual(m.getMeta("long").getContent(), 
			'ab cd foo\n\nnk * ork')
		self.assertEqual(m.getMeta("long").getContent("html"), 
			'<span class="plainmeta">ab cd foo</span>\n'
			'<span class="plainmeta">nk * ork</span>')

	def testRst(self):
		m = base.MetaMixin()
		m.addMeta("brasel", meta.MetaValue(unicode("`foo <http://foo.org>`__"),
			format="rst"))
		self.assertEqual(m.getMeta("brasel").getContent(), 
			'`foo <http://foo.org>`__')
		self.assertEqual(m.getMeta("brasel").getContent("html"), 
			'<p><a class="reference external" href="http://foo.org">foo</a></p>\n')

	def testRstExtension(self):
		m = base.MetaMixin()
		m.addMeta("brasel", meta.MetaValue(
			"See also :bibcode:`2011AJ....142....3H` .", format="rst"))
		self.assertTrue(
			'href="http://adsabs.harvard.edu/abs/2011AJ....142....3H"'
			in m.getMeta("brasel").getContent("html"))
			
		
class _MetaCarrier(base.Structure, base.MetaMixin, base.StandardMacroMixin):
	name_ = "m"

	def macro_wicked(self):
		return "\\wicked"


def parseMetaXML(src):
	return base.parseFromString(_MetaCarrier, "<m>"+src+"</m>")


class TestSpecials(testhelpers.VerboseTest):
	"""tests for particular behaviour of special MetaValue subclasses.
	"""
	def testWorkingInfos(self):
		m = base.MetaMixin()
		m.addMeta("info", "foo")
		val = m.getMeta("info").children[0]
		self.assert_(hasattr(val, "infoName"), 
			"info meta doesn't result in InfoItem")
		self.assertEqual(val.infoName, None)
		self.assertEqual(val.infoValue, None)
		self.assertEqual(val.content, "foo")
		m = base.MetaMixin()
		m.addMeta("info", meta.META_CLASSES_FOR_KEYS["info"](
			"info content", infoName="testInfo",
			infoValue="WORKING"))
		self.assertEqual(m.getMeta("info").getContent(), "info content")
		self.assertEqual(m.getMeta("info").children[0].infoName, "testInfo")
		self.assertEqual(m.getMeta("info").children[0].infoValue, "WORKING")
		m.addMeta("test", meta.META_CLASSES_FOR_KEYS["info"](
			"info content", infoName="testInfo",
			infoValue="WORKING"))
		self.assertEqual(m.getMeta("test").getContent(), "info content")
		self.assertEqual(m.getMeta("test").children[0].infoName, "testInfo")
		self.assertEqual(m.getMeta("test").children[0].infoValue, "WORKING")

	def testBadArgs(self):
		m = base.MetaMixin()
		self.assertRaises(meta.MetaError, m.addMeta, "_news", 
			"olds", foo="x")

	def testLinks(self):
		m = base.MetaMixin()
		m.addMeta("_related", "http://anythi.ng")
		m.addMeta("_related.title", "Link 1")
		self.assertEqual(m.getMeta("_related").children[0].getContent("html"),
			'<a href="http://anythi.ng">Link 1</a>')

	def testNews(self):
		m = parseMetaXML("""<meta name="_news" date="2009-03-06" author="MD"
				role="metadataUpdated">
			Added News Meta</meta>""")
		builder = webcommon.HTMLMetaBuilder()
		self.assertEqual(flat.flatten(m.buildRepr("_news", builder)), 
			'<span class="newsitem">2009-03-06 (MD):  Added News Meta</span>')
		builder.clear()
		m.addMeta("_news", "Finally added a facility to sort news")
		m.addMeta("_news.author", "Hopefully someone")
		m.addMeta("_news.date", "2010-03-06")
		self.assertEqual(flat.flatten(m.buildRepr("_news", builder)), 
			'<ul class="metaEnum"><li class="metaItem"><span class="newsitem">'
			'2009-03-06 (MD):  Added News Meta</span></li><li class="metaItem">'
			'<span class="newsitem">2010-03-06 (Hopefully someone): Finally ad'
			'ded a facility to sort news</span></li></ul>')

	def testExample(self):
		m = parseMetaXML("""<meta name="_example" title="test example">
			``seriously technical``</meta>""")
		exMeta = list(m.iterMeta("_example"))[0]
		self.assertEqual(base.getMetaText(exMeta, "title"), 
			"test example")
		self.assertTrue('<tt class="docutils literal">seriously technical</tt>'
			in exMeta.getContent("html"))
	
	def testExampleWithoutTitleFails(self):
		self.assertRaisesWithMsg(base.MetaError,
			"_example meta must always have a title",
			parseMetaXML,
			("""<meta name="_example">``seriously technical``</meta>""",))

	def testNameSplit(self):
		m = parseMetaXML("""
			<meta name="creator.name">Name-Grabowski, Xavier</meta>
			<meta name="creator">Last, J.; Goodman, B.
			</meta><meta name="creator"/>
			<meta name="creator.name">Miller, G.</meta>
			""")
		c = m.getMeta("creator")
		self.assertEqual(len(c), 4)
		self.assertEqual(c[2].getMeta("name").getContent("text"), "Goodman, B.")

	def testNameSplitStream(self):
		m = parseMetaXML("""
			<meta>
				creator.name: Name-Grabowski, Xavier
				creator: Last, J.; Goodman, B.
				creator:
				creator.name: Miller, G.
			</meta>""")
		c = m.getMeta("creator")
		self.assertEqual(len(c), 4)
		self.assertEqual(c[2].getMeta("name").getContent("text"), "Goodman, B.")


def getRadioMeta():
	m = base.MetaMixin()
	m.addMeta("radio", "on")
	m.addMeta("radio.freq", "90.9")
	m.addMeta("radio.unit", "MHz")
	m.addMeta("sense", "less")
	m.addMeta("radio", "off")
	m.addMeta("radio.freq", "9022")
	m.addMeta("radio.unit", "kHz")
	return m

class TextBuilderTest(testhelpers.VerboseTest):
	"""tests for recovery of meta information via TextBuilder.
	"""
	def test(self):
		m = getRadioMeta()
		t = meta.TextBuilder()
		m.traverse(t)
		foundPairs = set(t.metaItems)
		for expected in [('radio', 'off'), ('radio.freq', '90.9'), 
				('radio.unit', 'MHz'), ('radio', 'off'), ('radio.freq', '9022'), 
				('radio.unit', 'kHz'), ('sense', 'less')]:
			self.assert_(expected in foundPairs, "%s missing from expected"
				" meta pairs"%repr(expected))
		self.assertEqual(m.buildRepr("sense", meta.TextBuilder()),
			[('sense', 'less')])


class ModelBasedBuilderTest(testhelpers.VerboseTest):
	"""tests for recovery of meta information through factories interface.
	"""
	def testSynthetic(self):
		def id(arg, **ignored): return arg
		m = getRadioMeta()
		t = meta.ModelBasedBuilder([
			("radio", meta.stanFactory(T.li, class_="radio"), [
				": ",
				("freq", None, ()),
				" ",
				("unit", id, ()),]),
			("sense", meta.stanFactory(T.p), [("nonexisting", None, ())])])
		res = flat.flatten(T.div[t.build(m)])
		self.assertEqual(res, '<div><li class="radio">on: 90.9 MHz</li>'
			'<li class="radio">off: 9022 kHz</li><p>less</p></div>')

	def testWithAttrs(self):
		m = getRadioMeta()
		t = meta.ModelBasedBuilder([
			("radio", meta.stanFactory(T.img), (), {
					"src": "freq", "alt": "unit"}),])
		res = flat.flatten(T.div[t.build(m)])
		self.assertEqual(res, '<div><img src="90.9" alt="MHz">on</img>'
			'<img src="9022" alt="kHz">off</img></div>')

	def testContentBuilder(self):
		m = base.MetaMixin()
		m.addMeta("subject", "whatever")
		m.addMeta("subject", "and something else")
		m.addMeta("description", "useless test case")
		m.addMeta("contentLevel", "0")
		res = "".join(e.render() for e in builders._vrResourceBuilder.build(m))
		self.failUnless("Level>0</contentL" in res)
		self.failUnless("tLevel></content>" in res)
		self.failUnless("ct>whatever</subject><subject>and so" in res)
		self.failUnless("ct><description>u" in res)

	def testInstancesRejected(self):
		class Foo(stanxml.Element): pass
		self.assertRaisesWithMsg(base.ReportableError,
			"Do not use instanciated stanxml element in stanFactories."
			"  Instead, return them from a zero-argument function.",
			meta.stanFactory,
			(Foo(),))


class HtmlBuilderTest(testhelpers.VerboseTest):
	"""tests for the HTML builder for meta values.
	"""
	def testSimpleChild(self):
		builder = webcommon.HTMLMetaBuilder()
		m = base.MetaMixin()
		m.addMeta("boo", "rotzel")
		self.assertEqual(flat.flatten(m.buildRepr("boo", builder)),
			'<span class="plainmeta">rotzel</span>')
		builder.clear()
		m.addMeta("boo.loitz", "woo")
		self.assertEqual(flat.flatten(m.buildRepr("boo.loitz", builder)),
			'<span class="plainmeta">woo</span>')
	
	def testSequenceChild(self):
		builder = webcommon.HTMLMetaBuilder()
		m = base.MetaMixin()
		m.addMeta("boo", "child1")
		m.addMeta("boo", "child2")
		m.buildRepr("boo", builder)
		self.assertEqual(flat.flatten(builder.getResult()),
			'<ul class="metaEnum"><li class="metaItem"><span class="plainmeta">'
			'child1</span></li><li class="metaItem"><span class="plainmeta">'
			'child2</span></li></ul>')
	
	def testCompoundSequenceChild(self):
		builder = webcommon.HTMLMetaBuilder()
		m = base.MetaMixin()
		m.addMeta("boo.k", "boo 1, 1")
		m.addMeta("boo.l", "boo 1, 2")
		self.assertEqual(flat.flatten(m.buildRepr("boo", builder)),
			'<ul class="metaEnum"><li class="metaItem">'
			'<span class="plainmeta">boo 1, 1</span></li>'
			'<li class="metaItem">'
			'<span class="plainmeta">boo 1, 2</span></li></ul>')
		builder.clear()
		m.addMeta("boo.k", "boo 2, 1")
		m.addMeta("boo.l", "boo 2, 2")
		self.assertEqual(flat.flatten(m.buildRepr("boo", builder)),
			'<ul class="metaEnum"><li class="metaItem"><ul class="metaEnum">'
			'<li class="metaItem"><span class="plainmeta">boo 1, 1</span></li>'
			'<li class="metaItem"><span class="plainmeta">boo 2, 1</span></li>'
			'</ul></li><li class="metaItem"><ul class="metaEnum">'
			'<li class="metaItem"><span class="plainmeta">boo 1, 2</span></li>'
			'<li class="metaItem"><span class="plainmeta">boo 2, 2</span></li>'
			'</ul></li></ul>')


class XMLTest(testhelpers.VerboseTest):
	"""tests for parsing meta things out of XML resource descriptions.
	"""
	def testSimple(self):
		mc = parseMetaXML('<meta name="test">abc</meta>')
		self.assertEqual(str(mc.getMeta("test")), "abc")

	def testSequence(self):
		mc = parseMetaXML('<meta name="test">abc1</meta>\n'
			'<meta name="test">abc2</meta>')
		t = meta.TextBuilder()
		self.assertEqual(mc.buildRepr("test", t),
			[('test', u'abc1'), ('test', u'abc2')])

	def testCompound(self):
		mc = parseMetaXML('<meta name="radio">off'
			'<meta name="freq">90.9</meta><meta name="unit">MHz</meta></meta>')
		self.assertEqual(str(mc.getMeta("radio")), "off")
		self.assertEqual(str(mc.getMeta("radio.freq")), "90.9")
		self.assertEqual(str(mc.getMeta("radio.unit")), "MHz")

	def testLink(self):
		"""tests for working recognition of link-typed metas.
		"""
		mc = parseMetaXML('<meta name="_related" title="a link">'
			'http://foo.bar</meta>')
		self.assertEqual(mc.getMeta("_related").getContent("html"),
			'<a href="http://foo.bar">a link</a>')
	
	def testRst(self):
		mc = parseMetaXML('<meta name="bla" format="rst">A\n'
			'  text that is somewhat indented\n'
			'\n'
			'  and has a paragraph.</meta>')
		self.assertEqual(mc.getMeta("bla").getContent("html"), "<p>A\ntext th"
			"at is somewhat indented</p>\n<p>and has a paragraph.</p>\n")

	def testDeIndentation(self):
		mc = parseMetaXML('\t\t<meta name="bla" format="rst">\n'
			'\t\t\tIndented\n'
			'\t\t\t\tmess\n'
			'\t\t</meta>')
		self.assertEqual(mc.getMeta("bla").children[0].content,
			'\nIndented\n\tmess')
	
	def testCustomMetaIndentation(self):
		mc = parseMetaXML('\t\t<meta name="note" tag="6">\n'
			'\t\t\tA zero for the number of used images indicates that all images\n'
			'\t\t\thave some "problem" (such as overexposure).\n'
			'\t\t</meta>')
		self.assertEqual(mc.getMeta("note").children[0].content,
			'\nA zero for the number of used images indicates that all images\n'
			'have some "problem" (such as overexposure).')

	def testAllEmpty(self):
		mc = parseMetaXML("<meta/>")
		# assertion: just parses
	
	def testWellFormedStream(self):
		mc = parseMetaXML("<meta> meta_one: value 1 \n meta_two : value2\n</meta>")
		self.assertEqual(meta.getMetaText(mc, "meta_one"), "value 1")
		self.assertEqual(meta.getMetaText(mc, "meta_two"), "value2")

	def testNestedStream(self):
		mc = parseMetaXML("<meta>creator.name:A. Author\ncreator:\ncreator"
			".name:B.Author</meta>")
		t = meta.TextBuilder()
		self.assertEqual(mc.buildRepr("creator", t),
			[(u'creator.name', u'A. Author'), (u'creator.name', u'B.Author')])
	
	def testWithContinuation(self):
		mc = parseMetaXML("""<meta>longMeta: this Meta \\
			started on one line and ha\\
			d a word broken in the middle.
			shortMeta: This one is short.</meta>""")
		self.assertEqual(meta.getMetaText(mc, "longMeta"), 
			"this Meta started on one line and had a word broken in the middle.")
		self.assertEqual(meta.getMetaText(mc, "shortMeta"), 
			"This one is short.")
	
	def testMalformed(self):
		self.assertRaisesWithMsg(meta.MetaSyntaxError,
			"u'just junk' is no valid line for a meta stream",
			parseMetaXML,
			("<meta>just junk</meta>",))

	def testInlineClearing(self):
		mc = parseMetaXML("<meta>creator.name:A. Author\n!creator.name:B. Berta\n"
			"</meta>")
		t = meta.TextBuilder()
		self.assertEqual(mc.buildRepr("creator", t),
			[(u'creator.name', u'B. Berta')])

	def testLFStripped(self):
		mc = parseMetaXML("<meta>!contact.email: invalid@whereever.else\n</meta>")
		self.assertEqual(base.getMetaText(mc, "contact.email"), 
			'invalid@whereever.else')

	def testDeepNesting(self):
		mc = parseMetaXML("""<meta name="stuff">
			<meta name="level1">on level 1
				<meta name="level2" format="rst">This is RST</meta>
				<meta name="level2" format="literal">This is literal</meta>
			</meta>
			<meta name="level1">once more on level 1
				<meta name="level2">in the second thing</meta>
			</meta>
			<meta name="level1.level2">again in thing 2</meta>
			<meta name="level1">
				<meta name="level2">and a third thing</meta>
			</meta>
		</meta>""")
		thing1, thing2, thing3 = mc.getMeta("stuff.level1")
		self.assertEqual(thing1.getMeta("level2")[0].format, "rst")
		self.assertEqual(thing1.getMeta("level2")[1].format, "literal")
		self.assertEqual(thing2.getMeta("level2")[1].getContent("text"), 
			"again in thing 2")
		self.assertEqual(thing2.getContent("text"), "once more on level 1")
		self.assertEqual(thing3.getContent("text"), "")
		self.assertEqual(thing3.getMeta("level2").getContent("text"), 
			"and a third thing")

class MacroExpansionText(testhelpers.VerboseTest):
	def testUnexpanded(self):
		self.assertEqual(
			parseMetaXML(r'<meta name="test">\test</meta>'
				).getMeta("test").getContent(),
			"\\test")

	def testWithPackage(self):
		mc = parseMetaXML(r'<meta name="test">\test</meta>')
		self.assertEqual(mc.getMeta("test").getContent(macroPackage=mc),
			"test macro expansion")
	
	def testGetMetaTextExpands(self):
		self.assertEqual(
			base.getMetaText(parseMetaXML(r'<meta name="test">\test</meta>'),
				"test"),
			"test macro expansion")
	
	def testGetMetaTextDoesntNeedExpander(self):
		class _NECarrier(base.Structure, base.MetaMixin):
			name_ = "m"
		mc = base.parseFromString(_NECarrier, 
			r'<m><meta name="test">\test</meta></m>')
		self.assertEqual(base.getMetaText(mc, "test"),
			"\\test")

	def testExternalMetaWorks(self):
		self.assertEqual(
			base.getMetaText(parseMetaXML(r'<meta name="test">\rdIdDotted</meta>'),
				"test", macroPackage=testhelpers.getTestRD()),
			"data.test")

	def testModelBuilderExpands(self):
		t = meta.ModelBasedBuilder([
			("a", meta.stanFactory(T.img), (), {
					"src": "b"}),])
		mc = parseMetaXML('<meta>a:\\test\na.b:\\RSTservicelink{svc}</meta>')
		res = flat.flatten(T.div[t.build(mc)])
		self.assertEqual(res,
			'<div><img src="`svc &lt;/svc&gt;`_">test macro expansion</img></div>')

	def testNoDoubleExpansion(self):
		t = meta.ModelBasedBuilder([
			("a", meta.stanFactory(T.img), (),)])
		mc = parseMetaXML('<meta>a:\\wicked</meta>')
		res = flat.flatten(t.build(mc))
		self.assertEqual(res, '<img>\\wicked</img>')


class ModelValidationTest(testhelpers.VerboseTest):
	def setUp(self):
		self.model = metavalidation.parseModel(self.modelDesc)

	def assertFailures(self, carrier, failures):
		try:
			self.model.validate(carrier)
		except base.MetaValidationError, ex:
			pass
		except Exception, ex:
			traceback.print_exc()
			raise AssertionError("Expected MetaValidationError, saw %s"%
				ex.__class__.__name__)
		else:
			raise AssertionError("MetaValidationError not raised")
		self.assertEqual(set(ex.failures), set(failures))

	def assertValidates(self, carrier):
		self.assertRuns(self.model.validate, (carrier,))


class ExistsValidationTest(ModelValidationTest):
	modelDesc = "publisher.name"

	def testOnEmpty(self):
		m = _MetaCarrier(None)
		self.assertFailures(m, ['Meta key publisher.name missing'])

	def testOnCarrier(self):
		m = _MetaCarrier(None)
		m.setMeta("publisher.name", "bar")
		self.assertValidates(m)

	def testOnParent(self):
		p = _MetaCarrier(None)
		p.setMeta("publisher.name", "bar")
		m = _MetaCarrier(None)
		m.setMetaParent(p)
		self.assertValidates(m)


class Exists2ValidationTest(ExistsValidationTest):
	modelDesc = "publisher.name()"


class ExistsOnSelfValidationTest(ModelValidationTest):
	modelDesc = "shortName(!)"

	def testOnEmpty(self):
		m = _MetaCarrier(None)
		self.assertFailures(m, ['Meta key shortName missing'])

	def testOnCarrier(self):
		m = _MetaCarrier(None)
		m.setMeta("shortName", "bar")
		self.assertValidates(m)

	def testNonAtomic(self):
		m = _MetaCarrier(None)
		m.setMeta("shortName", "bar")
		m.addMeta("shortName", "foo")
		self.assertFailures(m, ['Meta key shortName is not atomic'])

	def testOnParent(self):
		p = _MetaCarrier(None)
		p.setMeta("shortName", "bar")
		m = _MetaCarrier(None)
		m.setMetaParent(p)
		self.assertFailures(m, ['Meta key shortName missing'])


class ExistsAtomicValidationTest(ModelValidationTest):
	modelDesc = "shortName(1)"

	def testOnEmpty(self):
		m = _MetaCarrier(None)
		self.assertFailures(m, ['Meta key shortName missing'])

	def testOnCarrier(self):
		m = _MetaCarrier(None)
		m.setMeta("shortName", "bar")
		self.assertValidates(m)

	def testNonAtomic(self):
		m = _MetaCarrier(None)
		m.setMeta("shortName", "bar")
		m.addMeta("shortName", "foo")
		self.assertFailures(m, ['Meta key shortName is not atomic'])

	def testOnParent(self):
		p = _MetaCarrier(None)
		p.setMeta("shortName", "bar")
		m = _MetaCarrier(None)
		m.setMetaParent(p)
		self.assertValidates(m)


class StructureValidationTest(testhelpers.VerboseTest):
	def setUp(self):
		class Foo(_MetaCarrier):
			metaModel = "shortName(!),publisher"
		self.TS = Foo

	def testSynthFail(self):
		s = base.makeStruct(self.TS)
		self.assertRaises(base.MetaValidationError, base.validateStructure,
			s)

	def testSynthOk(self):
		s = base.makeStruct(self.TS)
		s.setMeta("shortName", "o")
		s.addMeta("publisher", "United Leeches, Inc.")
		s.addMeta("publisher", "Greedy University Press")
		self.assertRuns(base.validateStructure, (s,))


class DefaultMetaTest(testhelpers.VerboseTest):
	def testDecoded(self):
		# the meta checked here is set up in testhelpers
		mc = parseMetaXML("<meta/>")
		self.assertEqual(base.getMetaText(mc, "organization.description"
				).encode("iso-8859-1"),
			"Mein w\xfcster Club")


if __name__=="__main__":
	testhelpers.main(IterMetaTest)
