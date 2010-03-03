"""
Tests for our low-level VOTable interface.
"""

from gavo import votable
from gavo.votable import V

from gavo.helpers import testhelpers

class TrivialParseTest(testhelpers.VerboseTest):
	"""tests operating on an empty VOTable.
	"""
	def testTrivialParse(self):
		self.assertEqual(list(votable.parseString("<VOTABLE/>")), [])

	def testTrivialWatchlist(self):
		res = list(votable.parseString("<VOTABLE/>",
			watchset=[V.VOTABLE]))
		self.assertEqual(len(res), 1)
		self.failUnless(isinstance(res[0], V.VOTABLE))
	
	def testTrivialWithNamespace(self):
		res = list(votable.parseString(
			'<VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.2"/>',
			watchset=[V.VOTABLE]))
		self.failUnless(isinstance(res[0], V.VOTABLE))

	def testTrivialOldNamespace(self):
		res = list(votable.parseString(
			'<VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.1"/>',
			watchset=[V.VOTABLE]))
		self.failUnless(isinstance(res[0], V.VOTABLE))


class TextParseTest(testhelpers.VerboseTest):
	"""tests for parsing elements with text content.
	"""
	def _getInfoItem(self, infoLiteral):
		return list(votable.parseString(
			'<VOTABLE>%s</VOTABLE>'%infoLiteral,
			watchset=[V.INFO]))[0]

	def testEmptyInfo(self):
		res = self._getInfoItem('<INFO name="t" value="0"/>')
		self.assertEqual(res.a_value, "0")
		self.assertEqual(res.a_name, "t")
	
	def testFullInfo(self):
		res = self._getInfoItem('<INFO name="t" value="0">abc</INFO>')
		self.assertEqual(res.children[0], "abc")

	def testUnicode(self):
		# xml defaults to utf-8
		res = self._getInfoItem('<INFO name="t" value="0">\xc3\xa4rn</INFO>')
		self.assertEqual(res.children[0], u"\xe4rn")


class IdTest(testhelpers.VerboseTest):
	"""tests for collection of id attributes.
	"""
	def testSimpleId(self):
		els = list(votable.parseString(
			'<VOTABLE><INFO ID="xy">abc</INFO></VOTABLE>',
			watchset=[V.INFO, V.VOTABLE]))
		self.failUnless(els[0].idmap is els[1].idmap)
		self.failUnless(els[0].idmap["xy"] is els[0])
	
	def testForwardReference(self):
		iter = votable.parseString(
			'<VOTABLE><INFO ID="xy" ref="z">abc</INFO>'
			'<INFO ID="z" ref="xy">zz</INFO></VOTABLE>',
			watchset=[V.INFO])
		info0 = iter.next()
		self.assertRaises(KeyError, lambda: info0.idmap[info0.a_ref])
		info1 = iter.next()
		self.failUnless(info0.idmap[info0.a_ref] is info1)
		self.failUnless(info1.idmap[info1.a_ref] is info0)
		self.assertRaises(StopIteration, iter.next)


class TabledataDeserTest(testhelpers.VerboseTest):
	"""tests for deserialization of TABLEDATA encoded values.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		fielddefs, literals, expected = sample
		table = votable.parseString((
			'<VOTABLE><RESOURCE><TABLE>'+
			fielddefs+
			'<DATA><TABLEDATA>'+
			'\n'.join('<TR>%s</TR>'%''.join('<TD>%s</TD>'%l
				for l in row) for row in literals)+
			'</TABLEDATA></DATA>'
			'</TABLE></RESOURCE></VOTABLE>').encode("utf-8")).next()
		self.assertEqual(list(table), expected)
	
	samples = [(
			'<FIELD name="x" datatype="boolean"/>',
			[['TRue'], ['T'],  ['False'], ['?']],
			[[True],   [True], [False],   [None]]
		), (
			'<FIELD name="x" datatype="unsignedByte"/>'
			'<FIELD name="y" datatype="unsignedByte"><VALUES null="16"/></FIELD>',
			[['',   ''],   ['0x10', '0x10'], ['10', '16']],
			[[None, None], [16,     16],     [10,    None]]
		), (
			'<FIELD name="x" datatype="char"/>',
			[[''],   ['a'], ['&apos;'], [u'\xe4'], ['&#xe4;']],
			[[None], ['a'], ["'"],      [u'\xe4'], [u'\xe4']],
		), (
			'<FIELD name="x" datatype="short"><VALUES null="0"/></FIELD>'
			'<FIELD name="y" datatype="int"/>'
			'<FIELD name="z" datatype="long"><VALUES null="222399322"/></FIELD>',
			[['0', '0', '0'], ['-3', '-300', '222399322'], ['0xff', '0xcafebabe', '0xcafebabedeadbeef',]],
			[[None, 0,  0],   [-3,    -300,  None],        [255,    -889275714,   -3819410105021120785L]]
		)
	]
	

if __name__=="__main__":
	testhelpers.main(TabledataDeserTest)
