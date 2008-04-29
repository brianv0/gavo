import sys
import unittest
from xml import sax

from nevow import tags as T, flat

import gavo
from gavo import meta
from gavo.parsing import importparser
from gavo.web import common as webcommon

import testhelpers

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
		for shouldFail in ["", "abc7", ".foo", "???"]:
			self.assertRaisesVerbose(gavo.MetaSyntaxError, meta.getPrimary, 
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
		for shouldFail in ["", "abc7", ".foo", "???", "coverage.x7", "foo..bar"]:
			self.assertRaisesVerbose(gavo.MetaSyntaxError, meta.parseKey, 
				(shouldFail,), "%s returned primary meta but shouldn't have"%shouldFail)


class CompoundTest(testhelpers.VerboseTest):
	"""tests for buildup of hierarchical meta items.
	"""
	def testFromText(self):
		"""tests for correct buildup of MetaItems from text keys.
		"""
		m = meta.MetaMixin()
		m.addMeta("creator.name", meta.makeMetaValue("F. Bar"))
		m.addMeta("creator.address", meta.makeMetaValue("21 Foo Street, Bar 02147"))
		self.assertEqual(len(m.getMeta("creator").children), 1)
		self.assertEqual(m.getMeta("creator.name").children[0].content, "F. Bar")
		self.assertEqual(m.getMeta("creator.address").children[0].content, 
			"21 Foo Street, Bar 02147")
		self.assert_(m.getMeta("creator").getMeta("name") is
			m.getMeta("creator.name"))
	
	def testFromItems(self):
		"""tests for correct buildup of MetaItems from meta items.
		"""
		mv = meta.makeMetaValue()
		mv.addMeta("name", meta.makeMetaValue("Foo B."))
		mv.addMeta("address", meta.makeMetaValue("homeless"))
		m = meta.MetaMixin()
		m.addMeta("creator", mv)
		self.assertEqual(len(m.getMeta("creator").children), 1)
		self.assertEqual(m.getMeta("creator.name").children[0].content, "Foo B.")
		self.assertEqual(m.getMeta("creator.address").children[0].content, 
			"homeless")
		self.assert_(m.getMeta("creator").getMeta("name") is
			m.getMeta("creator.name"))


class SequenceTest(testhelpers.VerboseTest):
	"""tests for correct buildup of sequence-like meta items.
	"""
# You're not supposed to access meta info like here -- see below for
# how to retrieve meta values.  This is to show buildup.
	def testFlatTextSequence(self):
		"""tests for buildup of sequence metas using text keys.
		"""
		m = meta.MetaMixin()
		m.addMeta("subject", "boredom")
		m.addMeta("subject", "drudge")
		m.addMeta("subject", "pain")
		self.assertEqual(len(m.getMeta("subject").children), 3)
		self.assertEqual(m.getMeta("subject").children[0].content, "boredom")
		self.assertEqual(m.getMeta("subject").children[2].content, "pain")
	
	def testCompoundTextSequence(self):
		"""tests for correct buildup of sequences of compound meta items.
		"""
		m = meta.MetaMixin()
		m.addMeta("coverage.spatial.ra", "10-20")
		m.addMeta("coverage.spatial.dec", "10-20")
		m.addMeta("coverage.spatial", None)
		m.addMeta("coverage.spatial.ra", "-10-20")
		m.addMeta("coverage.spatial.dec", "-10-20")
		self.assertEqual(len(m.getMeta("coverage").children), 1)
		self.assertEqual(len(m.getMeta("coverage.spatial").children), 2)
		self.assertEqual(m.getMeta("coverage.spatial").children[1].
			getMeta("ra").children[0].content, "-10-20")
		self.assertRaises(gavo.MetaCardError, m.getMeta, "coverage.spatial.ra")
		self.assertRaises(gavo.MetaCardError, m.getMeta, "coverage.spatial.dec")

	def testCompoundObjectSequence(self):
		"""tests for correct buildup of meta information through object embedding
		"""
		m = meta.MetaMixin()
		alc = meta.makeMetaValue("50%")
		org = meta.makeMetaValue("grape")
		stuff = meta.makeMetaValue("fusel")
		stuff.addMeta("alc", alc)
		stuff.addMeta("org", org)
		m.addMeta("stuff", stuff)
		alc = meta.makeMetaValue("70%")
		org = meta.makeMetaValue("rye")
		stuff = meta.makeMetaValue("fusel")
		stuff.addMeta("alc", alc)
		stuff.addMeta("org", org)
		m.addMeta("stuff", stuff)
		self.assertEqual(len(m.getMeta("stuff").children), 2)
		self.assertEqual(m.getMeta("stuff").children[0].
			getMeta("alc").getContent(), "50%")
		self.assertEqual(m.getMeta("stuff").children[1].
			getMeta("alc").getContent(), "70%")
		# cannot be decided because stuff.alc has multiple values
		self.assertRaises(gavo.MetaCardError, m.getMeta,
			"stuff.alc")


class TestContent(testhelpers.VerboseTest):
	"""tests for plain content access.
	"""
# Under normal circumstances, you don't want to access meta content
# like this either; this is much better than fiddling with children
# and content, though
	def testLiteral(self):
		m = meta.MetaMixin()
		m.addMeta("brasel", meta.makeMetaValue("quox \n  ab   c", format="literal"))
		self.assertEqual(m.getMeta("brasel").getContent(), "quox \n  ab   c")
		self.assertEqual(m.getMeta("brasel").getContent("html"),
			'<span class="literalmeta">quox \n  ab   c</span>')
	
	def testPlain(self):
		m = meta.MetaMixin()
		m.addMeta("brasel", meta.makeMetaValue("ab\ncd   foo"))
		self.assertEqual(m.getMeta("brasel").getContent(), "ab cd foo")
		self.assertEqual(m.getMeta("brasel").getContent("html"), 
			'<span class="plainmeta">ab cd foo</span>')
		m.addMeta("long", meta.makeMetaValue("ab\ncd   foo\n\nnk\n * ork"))
		self.assertEqual(m.getMeta("long").getContent(), 
			'ab cd foo\n\nnk * ork')
		self.assertEqual(m.getMeta("long").getContent("html"), 
			'<span class="plainmeta">ab cd foo</span>\n'
			'<span class="plainmeta">nk * ork</span>')

	def testRst(self):
		m = meta.MetaMixin()
		m.addMeta("brasel", meta.makeMetaValue(unicode("`foo <http://foo.org>`__"),
			format="rst"))
		self.assertEqual(m.getMeta("brasel").getContent(), 
			'`foo <http://foo.org>`__')
		self.assertEqual(m.getMeta("brasel").getContent("html"), 
			'<p><a class="reference" href="http://foo.org">foo</a></p>\n')


class TestSpecials(testhelpers.VerboseTest):
	"""tests for particular behaviour of special MetaValue subclasses.
	"""
	def testWorkingInfos(self):
		m = meta.MetaMixin()
		m.addMeta("info", "foo")
		val = m.getMeta("info").children[0]
		self.assert_(hasattr(val, "infoName"), 
			"info meta doesn't result in InfoItem")
		self.assertEqual(val.infoName, None)
		self.assertEqual(val.infoValue, None)
		self.assertEqual(val.content, "foo")
		m = meta.MetaMixin()
		m.addMeta("info", meta.makeMetaValue("info content", infoName="testInfo",
			infoValue="WORKING", name="info"))
		self.assertEqual(m.getMeta("info").getContent(), "info content")
		self.assertEqual(m.getMeta("info").children[0].infoName, "testInfo")
		self.assertEqual(m.getMeta("info").children[0].infoValue, "WORKING")
		m.addMeta("test", meta.makeMetaValue("info content", infoName="testInfo",
			infoValue="WORKING", type="info"))
		self.assertEqual(m.getMeta("test").getContent(), "info content")
		self.assertEqual(m.getMeta("test").children[0].infoName, "testInfo")
		self.assertEqual(m.getMeta("test").children[0].infoValue, "WORKING")
	
	def testBadInfos(self):
		m = meta.MetaMixin()
		m.addMeta("info", meta.makeMetaValue("no info", name="info",
			type=None))
		self.assert_(not hasattr(m.getMeta("info").children[0], "infoName"),
			"Names override types, which they shouldn't")
	
	def testLinks(self):
		m = meta.MetaMixin()
		m.addMeta("_related", "http://anythi.ng")
		m.addMeta("_related.title", "Link 1")
		self.assertEqual(m.getMeta("_related").children[0].getContent("html"),
			'<a href="http://anythi.ng">Link 1</a>')
		m.addMeta("weirdLink", meta.makeMetaValue("http://some.oth.er",
			title="Link 2", type="link"))
		self.assertEqual(m.getMeta("weirdLink").children[0].getContent("html"),
			'<a href="http://some.oth.er">Link 2</a>')


def getRadioMeta():
	m = meta.MetaMixin()
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
	def test(self):
		def id(arg): return arg
		m = getRadioMeta()
		t = meta.ModelBasedBuilder([
			("radio", meta.stanFactory(T.li, class_="radio"), [
				": ",
				("freq", id, ()),
				" ",
				("unit", id, ()),]),
			("sense", meta.stanFactory(T.p), [("nonexisting", None, ())])])
		res = flat.flatten(T.div[t.build(m)])
		self.assertEqual(res, '<div><li class="radio">on: 90.9 MHz</li>'
			'<li class="radio">off: 9022 kHz</li><p>less</p></div>')


class HtmlBuilderTest(testhelpers.VerboseTest):
	"""tests for the HTML builder for meta values.
	"""
	def testSimpleChild(self):
		builder = webcommon.HtmlMetaBuilder()
		m = meta.MetaMixin()
		m.addMeta("boo", "rotzel")
		self.assertEqual(flat.flatten(m.buildRepr("boo", builder)),
			'<span class="metaItem"><span class="plainmeta">rotzel</span></span>')
		builder.clear()
		m.addMeta("boo.loitz", "woo")
		self.assertEqual(flat.flatten(m.buildRepr("boo.loitz", builder)),
			'<span class="metaItem"><span class="plainmeta">woo</span></span>')
	
	def testSequenceChild(self):
		builder = webcommon.HtmlMetaBuilder()
		m = meta.MetaMixin()
		m.addMeta("boo", "child1")
		m.addMeta("boo", "child2")
		m.buildRepr("boo", builder)
		self.assertEqual(flat.flatten(builder.getResult()),
			'<ul class="metaEnum"><li class="metaItem"><span class="plainmeta">'
			'child1</span></li><li class="metaItem"><span class="plainmeta">'
			'child2</span></li></ul>')
	
	def testCompoundSequenceChild(self):
		builder = webcommon.HtmlMetaBuilder()
		m = meta.MetaMixin()
		m.addMeta("boo.k", "boo 1, 1")
		m.addMeta("boo.l", "boo 1, 2")
		self.assertEqual(flat.flatten(m.buildRepr("boo", builder)),
			'<ul class="metaEnum"><li class="metaItem"><span class="metaItem">'
			'<span class="plainmeta">boo 1, 1</span></span></li>'
			'<li class="metaItem"><span class="metaItem">'
			'<span class="plainmeta">boo 1, 2</span></span></li></ul>')
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



class RdTest(testhelpers.VerboseTest):
	"""tests for parsing meta things out of XML resource descriptions.
	"""
	def _getRd(self, rdContent):
		hdlr = importparser.RdParser("dynamic")
		sax.parseString('<ResourceDescriptor srcdir="/">'+rdContent+
			"</ResourceDescriptor>", hdlr)
		return hdlr.getResult()

	def testSimple(self):
		self.assertEqual(str(self._getRd('<meta name="test">abc</meta>'
			).getMeta("test")), "abc")

	def testSequence(self):
		rd = self._getRd('<meta name="test">abc1</meta>\n'
			'<meta name="test">abc2</meta>')
		t = meta.TextBuilder()
		self.assertEqual(rd.buildRepr("test", t),
			[('test', u'abc1'), ('test', u'abc2')])

	def testCompound(self):
		rd = self._getRd('<meta name="radio">off'
			'<meta name="freq">90.9</meta><meta name="unit">MHz</meta></meta>')
		self.assertEqual(str(rd.getMeta("radio")), "off")
		self.assertEqual(str(rd.getMeta("radio.freq")), "90.9")
		self.assertEqual(str(rd.getMeta("radio.unit")), "MHz")

	def testLink(self):
		"""tests for working recognition of link-typed metas.
		"""
		rd = self._getRd('<meta name="_related" title="a link">'
			'http://foo.bar</meta>')
		self.assertEqual(rd.getMeta("_related").getContent("html"),
			'<a href="http://foo.bar">a link</a>')

	def testBadMeta(self):
		"""tests for correct rejection of malformed meta items.
		"""
		self.assertRaisesVerbose(gavo.Error, self._getRd,
			('<meta name="foo"><meta name="bar">bar</meta>bad</meta>',),
			"importparser accepts badly mixed meta content")

def singleTest():
	suite = unittest.makeSuite(RdTest, "test")
	runner = unittest.TextTestRunner()
	runner.run(suite)


if __name__=="__main__":
#	unittest.main()
	singleTest()
