"""
Tests for our low-level VOTable interface.
"""

import re
import struct
from cStringIO import StringIO

from gavo import votable
from gavo.votable import common
from gavo.votable import V
from gavo.votable.iterparse import iterparse

from gavo.helpers import testhelpers


class IterParseTest(testhelpers.VerboseTest):
	"""tests for our custom iterparser.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		xml, parsed = sample
		self.assertEqual(list(iterparse(StringIO(xml))), parsed)
	
	samples = [
		("<doc/>", [("start", "doc", {}), ("end", "doc")]),
		('<doc href="x"/>', [("start", "doc", {"href": "x"}), ("end", "doc")]),
		('<doc>fl\xc3\xb6ge</doc>', 
			[("start", "doc", {}), ("data", u"fl\xf6ge"), ("end", "doc")]),
		('<doc obj="fl\xc3\xb6ge"/>', 
			[("start", "doc", {"obj": u"fl\xf6ge"}), ("end", "doc")]),
		('<doc><abc>'+"unu"*10000+'</abc>\n<bcd>klutz</bcd></doc>', [
			("start", "doc", {}), 
			("start", "abc", {}),
			("data", "unu"*10000),
			("end", "abc"),
			("data", "\n"),
			("start", "bcd", {}),
			("data", "klutz"),
			("end", "bcd"),
			("end", "doc")]),
		('<doc xmlns="http://insane"/>', [
			("start", "doc", {u'xmlns': u'http://insane'}), ("end", "doc"),])
	]


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


class ErrorParseTest(testhelpers.VerboseTest):
	"""tests for more-or-less benign behaviour on input errors.
	"""
	def testExpatReporting(self):
		try:
			list(votable.parseString("<VOTABLE>"))
		except Exception, ex:
			pass
		self.assertEqual(ex.__class__.__name__, "VOTableParseError")
		self.assertEqual(str(ex), "no element found: line 1, column 9")

	def testInternalReporting(self):
		table = votable.parseString("<VOTABLE><RESOURCE><TABLE>\n"
			'<FIELD name="x" datatype="boolean"/>\n'
			'<DATA><TABLEDATA>\n'
			'<TR><TDA>True</TDA></TR>\n'
			'</TABLEDATA></DATA>\n'
			"</TABLE></RESOURCE></VOTABLE>\n").next()
		try:
			list(table)
		except Exception, ex:
			pass
		self.assertEqual(ex.__class__.__name__, "VOTableParseError")
		self.assertEqual(str(ex), "Unexpected element TDA near line 7, column 0")


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
		self.assertEqual(res.text, "abc")

	def testUnicode(self):
		# xml defaults to utf-8
		res = self._getInfoItem('<INFO name="t" value="0">\xc3\xa4rn</INFO>')
		self.assertEqual(res.text, u"\xe4rn")


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


class TabledataReadTest(testhelpers.VerboseTest):
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
		), (
			'<FIELD name="x" datatype="float"><VALUES null="-999."/></FIELD>'
			'<FIELD name="y" datatype="float"/>',
			[['1', '0.5e10'], ['-999.', '']],
			[[1.0, 5e09],     [None, None]]
		), (
			'<FIELD name="x" datatype="floatComplex"><VALUES null="-999. 0"/></FIELD>'
			'<FIELD name="y" datatype="floatComplex"/>',
			[['1 1', '0.5e10 -2e5'], ['-999. 0', '20']],
			[[(1+1j), 5e09-2e5j],    [None, 20+0j]]
		), (
			'<FIELD name="x" datatype="boolean" arraysize="*"/>',
			[['true false ? T'],        [' T'], ['']],
			[[(True, False, None, True)], [(True,)], [()]]
		), (
			'<FIELD name="y" datatype="unsignedByte" arraysize="*">'
			' <VALUES null="16"/></FIELD>',
			[['10 0x10\t 16 \n 0x16']],
			[[(10, 16, None, 22)]]
		), (
			'<FIELD name="x" datatype="char" arraysize="4"/>',
			[[''], ['auto'], ['&apos;xx&quot;'], [u'\xe4'], ['&#xe4;']],
			[[None], ['auto'], ["'xx\""],          [u'\xe4'], [u'\xe4']],
		), (
			'<FIELD name="x" datatype="short" arraysize="*"><VALUES null="0"/></FIELD>',
			[['1 2 3 0 1']], 
			[[(1,2,3,None,1)]]
		), (
			'<FIELD name="y" datatype="floatComplex" arraysize="*"/>',
			[['1 1 0.5e10 -2e5']],
			[[((1+1j), 5e09-2e5j)]]
		), (
			'<FIELD datatype="short" arraysize="2x3"/>',
			[['0 1 2 3 4 5']],
			[[(0,1,2,3,4,5)]],
		)
	]


class FloatTDEncodingTest(testhelpers.VerboseTest):
	"""tests for proper handling of special float values.
	"""
	def _decode(self, fielddefs, literals):
		table = votable.parseString((
			'<VOTABLE><RESOURCE><TABLE>'+
			fielddefs+
			'<DATA><TABLEDATA>'+
			'\n'.join('<TR>%s</TR>'%''.join('<TD>%s</TD>'%l
				for l in row) for row in literals)+
			'</TABLEDATA></DATA>'
			'</TABLE></RESOURCE></VOTABLE>').encode("utf-8")).next()
		return list(table)

	def testNAN(self):
		vals = self._decode(
			'<FIELD name="y" datatype="float"/>',
			[['NaN']])[0]
		self.failUnless(vals[0]!=vals[0])
	
	def testInfinities(self):
		vals = self._decode(
			'<FIELD name="y" datatype="float"/>',
			[['+Inf'], ['-Inf']])
		self.failUnless(vals[0][0]==2*vals[0][0])
		self.failUnless(vals[1][0]==2*vals[1][0])

	def testWeirdArray(self):
		vals = self._decode(
			'<FIELD name="y" datatype="float" arraysize="3"/>',
			[['NaN +Inf -Inf']])[0]
		self.assertEqual(repr(vals), '[(nan, inf, -inf)]')


class TabledataWriteTest(testhelpers.VerboseTest):
	"""tests for serializing TABLEDATA VOTables.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		fielddefs, input, expected = sample
		vot = V.VOTABLE[V.RESOURCE[votable.DelayedTable(
			V.TABLE[fielddefs], input, V.TABLEDATA)]]
		mat = re.search("<TABLEDATA>(.*)</TABLEDATA>", votable.asString(vot))
		content = mat and mat.group(1)
		self.assertEqual(content, expected)

	samples = [(
			[V.FIELD(datatype="float")],
			[[1],[None],[float("NaN")]],
			"<TR><TD>1</TD></TR><TR><TD>NaN</TD></TR><TR><TD>NaN</TD></TR>"
		), (
			[V.FIELD(datatype="double")],
			[[1.52587890625e-05], [float("+Inf")]],
			'<TR><TD>1.52587890625e-05</TD></TR><TR><TD>inf</TD></TR>'
		), (
			[V.FIELD(datatype="boolean")],
			[[True], [False], [None]],
			'<TR><TD>1</TD></TR><TR><TD>0</TD></TR><TR><TD>?</TD></TR>'
		), ([
				V.FIELD(datatype="bit"),
				V.FIELD(datatype="unsignedByte"),
				V.FIELD(datatype="short"),
				V.FIELD(datatype="int"),
				V.FIELD(datatype="long")],
			[[0,1,2,3,4]],
			'<TR><TD>0</TD><TD>1</TD><TD>2</TD><TD>3</TD><TD>4</TD></TR>'
		), (
			[V.FIELD(datatype="unicodeChar")],
			[u'\xe4'],
			'<TR><TD>\xc3\xa4</TD></TR>'
		), (  # 5
			[V.FIELD(datatype="char")],
			[u'\xe4'],
			'<TR><TD>\xc3\xa4</TD></TR>'
		), (
			[V.FIELD(datatype="floatComplex")],
			[[0.5+0.25j]],
			'<TR><TD>0.5 0.25</TD></TR>'
		), ([
				V.FIELD(datatype="unsignedByte")[V.VALUES(null="23")],
				V.FIELD(datatype="unicodeChar")[V.VALUES(null="\x00")],
				V.FIELD(datatype="float")[V.VALUES(null="-9999")]],
			[[1, "a", 1.5], [None, None, None]],
			'<TR><TD>1</TD><TD>a</TD><TD>1.5</TD></TR>'
			'<TR><TD>23</TD><TD>\x00</TD><TD>NaN</TD></TR>'
		), (
			[V.FIELD(datatype="unsignedByte", arraysize="2")[V.VALUES(null="0xff")]],
			[[[]], [[2]], [None], [[2, 3, 4]]],
		'<TR><TD>0xff 0xff</TD></TR><TR><TD>2 0xff</TD></TR>'
		'<TR><TD>0xff 0xff</TD></TR><TR><TD>2 3</TD></TR>'
		), (
			[V.FIELD(datatype="bit", arraysize="*")],
			[[430049293488]],
			'<TR><TD>110010000100000111011110111010010110000</TD></TR>'
		), (  # 10
			[V.FIELD(datatype="doubleComplex", arraysize="2")[V.VALUES(null="0 0")]],
			[[[2+2j, None, 4+4j]]],
			'<TR><TD>2.0 2.0 NaN NaN</TD></TR>'
		), (
			[V.FIELD(datatype="double", arraysize="*")[V.VALUES(null="23")]],
			[[None], [[None]]],
			"<TR><TD></TD></TR><TR><TD>NaN</TD></TR>"
		)
	]


class BinaryWriteTest(testhelpers.VerboseTest):
	"""tests for serializing BINARY VOTables.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		fielddefs, input, expected = sample
		vot = V.VOTABLE[V.RESOURCE[votable.DelayedTable(
			V.TABLE[fielddefs], input, V.BINARY)]]
		mat = re.search('(?s)<STREAM encoding="base64">(.*)</STREAM>', 
			votable.asString(vot))
		content = mat and mat.group(1)
		self.assertEqual(content.decode("base64"), expected)

	samples = [(
			[V.FIELD(datatype="float")],
			[[1],[None],[common.NaN]],
			struct.pack("!fff", 1, common.NaN, common.NaN)
		), (
			[V.FIELD(datatype="double")],
			[[1],[None],[common.NaN]],
			struct.pack("!ddd", 1, common.NaN, common.NaN)
		), (
			[V.FIELD(datatype="boolean")],
			[[True],[False],[None]],
			"10?"
		), (
			[V.FIELD(datatype="bit")],
			[[1],[0]],
			"\x01\x00"
		), (
			[V.FIELD(datatype="unsignedByte")],
			[[20]],
			"\x14"
		), (  # 5
			[V.FIELD(datatype="unsignedByte")[V.VALUES(null="23")]],
			[[20], [None]],
			"\x14\x17"
		), (
			[V.FIELD(datatype="short")],
			[[20]],
			"\x00\x14"
		), (
			[V.FIELD(datatype="int")],
			[[-20]],
			"\xff\xff\xff\xec"
		), (
			[V.FIELD(datatype="long")],
			[[-20]],
			"\xff\xff\xff\xff\xff\xff\xff\xec"
		), (
			[V.FIELD(datatype="char")[V.VALUES(null="x")]],
			[['a'], [None]],
			"ax"
		), (  # 10
			[V.FIELD(datatype="unicodeChar")[V.VALUES(null=u"\udead")]],
			[['a'], ['\xe4'.decode("iso-8859-1")], [None]],
			"\x00a\x00\xe4\xde\xad"
		), (
			[V.FIELD(datatype="floatComplex")],
			[[6+7j], [None]],
			struct.pack("!ff", 6, 7)+struct.pack("!ff", common.NaN, common.NaN)
		), (
			[V.FIELD(datatype="bit", arraysize="17")],
			[[1],[2**25-1]],
			"\x00\x00\x01\xff\xff\xff"
		), (
			[V.FIELD(datatype="bit", arraysize="*")],
			[[1],[2**25-1]],
			"\x00\x00\x00\x08\x01"
			"\x00\x00\x00\x20\x01\xff\xff\xff"
		), (
			[V.FIELD(datatype="unsignedByte", arraysize="*")],
			[[[]], [[1]], [[0, 1, 2]]],
			"\x00\x00\x00\x00"
			"\x00\x00\x00\x01\x01"
			"\x00\x00\x00\x03\x00\x01\x02"
		), (
			[V.FIELD(datatype="unsignedByte", arraysize="2")[V.VALUES(null="255")]],
			[[[]], [[1]], [[0, 1, 2]]],
			"\xff\xff"
			"\x01\xff"
			"\x00\x01"
		), (
			[V.FIELD(datatype="short", arraysize="2*")],
			[[[]], [[1]], [[0, 1, 2]]],
			"\x00\x00\x00\x00"
			"\x00\x00\x00\x01\x00\x01"
			"\x00\x00\x00\x03\x00\x00\x00\x01\x00\x02"
		), (
			[V.FIELD(datatype="char", arraysize="2")],
			[["abc"], ["a"]],
			"aba "
		), (
			[V.FIELD(datatype="char", arraysize="*")],
			[["abc"], ["a"]],
			"\0\0\0\x03abc\0\0\0\x01a"
		), (
			[V.FIELD(datatype="unicodeChar", arraysize="2")],
			[[u"\u00e4bc"], [u"\u00e4"]],
			'\x00\xe4\x00b\x00\xe4\x00 '
		), (
			[V.FIELD(datatype="short", arraysize="3x2")],
			[[[1,2,3,4,5,6]]],
			'\x00\x01\x00\x02\x00\x03\x00\x04\x00\x05\x00\x06'
		)
	]


class BinaryReadTest(testhelpers.VerboseTest):
	"""tests for deserializing BINARY VOTables.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		fielddefs, stuff, expected = sample
		table = votable.parseString((
			'<VOTABLE><RESOURCE><TABLE>'+
			fielddefs+
			'<DATA><BINARY><STREAM encoding="base64">'+
			stuff.encode("base64")+
			'</STREAM></BINARY></DATA>'
			'</TABLE></RESOURCE></VOTABLE>').encode("utf-8")).next()
		self.assertEqual(list(table), expected)

	samples = [(
			'<FIELD datatype="boolean"/>',
			"10?",
			[[True],[False],[None]],
		), (
			'<FIELD datatype="bit"/>',
			"\x01\x00\xff",
			[[1],[0],[1]],
		), (
			'<FIELD datatype="bit" arraysize="9"/>',
			"\x01\x00\xff\xff",
			[[256],[511]],
		), (
			'<FIELD datatype="bit" arraysize="*"/>',
			"\x00\x00\x00\x03\xff\x00\x00\x00\x45"
				"\xff\x00\x00\x00\x00\x00\x00\x00\x01",
			[[7],[0x1f0000000000000001]],
		), (
			'<FIELD datatype="char"><VALUES null="a"/></FIELD>',
			"x\x00a",
			[['x'],['\x00'], [None]],
		), (
			'<FIELD datatype="unicodeChar"><VALUES null="&#xbabe;"/></FIELD>',
			"\x00a\x23\x42\xba\xbe",
			[['a'],[u'\u2342'], [None]],
		), (
			'<FIELD datatype="unsignedByte"><VALUES null="12"/></FIELD>'
				'<FIELD datatype="short"><VALUES null="12"/></FIELD>'
				'<FIELD datatype="int"><VALUES null="12"/></FIELD>'
				'<FIELD datatype="long"><VALUES null="12"/></FIELD>',
			"\x0c\x00\x0c\x00\x00\x00\x0c\x00\x00\x00\x00\x00\x00\x00\x0c"
			"\x0d\x0d\x0d\x00\x0d\x0d\x0c\x00\xdd\x00\x00\x00\x00\x00\x0c", [
				[None, None, None, None],
				[13, 3341, 855308, 62205969853054988L]]
		), (
			'<FIELD datatype="float"/>',
			"\x7f\xc0\x00\x00:\x80\x00\x00",
			[[None], [0.0009765625]]
		), (
			'<FIELD datatype="double"/>',
			"\x7f\xf8\x00\x00\x00\x00\x00\x00?P\x00\x01\x00\x00\x00\x00",
			[[None], [0.00097656343132257462]]
		), (
			'<FIELD datatype="doubleComplex"/>',
			"\x7f\xf8\x00\x00\x00\x00\x00\x00?P\x00\x01\x00\x00\x00\x00"
			'@\x04\x00\x00\x00\x00\x00\x00?\xe0\x00\x00\x00\x00\x00\x00',
			[[None], [2.5+0.5j]]
		), (
			'<FIELD datatype="char" arraysize="4"><VALUES null="0000"/></FIELD>',
			"abcd0000",
			[["abcd"], [None]]
		), (
			'<FIELD datatype="char" arraysize="*"/>',
			"\x00\x00\x00\x00\x00\x00\x00\x03abc",
			[[""], ["abc"]]
		), (
			'<FIELD datatype="unicodeChar" arraysize="*"/>',
			"\x00\x00\x00\x03\x00a\x23\x42bc",
			[[u"a\u2342\u6263"]]
		), (
			'<FIELD datatype="unicodeChar" arraysize="2"/>',
			"\x00a\x23\x42",
			[[u"a\u2342"]]
		), (
			'<FIELD datatype="unsignedByte" arraysize="2"/>',
			'\x00\x01',
			[[(0, 1)]],
		), (  # 15
			'<FIELD datatype="short" arraysize="*"><VALUES null="16"/></FIELD>',
			'\x00\x00\x00\x03\x00\x01\x00\x10\x00\x02',
			[[(1, None, 2)]],
		), (
			'<FIELD datatype="int" arraysize="2"/>',
			'\x00\x00\x00\x03\x00\x01\x00\x10',
			[[(3, 0x10010)]],
		), (
			'<FIELD datatype="float" arraysize="2"/>',
			'\x7f\xc0\x00\x00:\x80\x00\x00',
			[[(None, 0.0009765625)]],
		), (
			'<FIELD datatype="double" arraysize="*"/>',
			'\x00\x00\x00\x02\x7f\xf8\x00\x00\x00\x00\x00\x00'
				'?P\x00\x01\x00\x00\x00\x00',
			[[(None, 0.00097656343132257462)]]
		), (
			'<FIELD datatype="float" arraysize="2"><VALUES null="2"/></FIELD>',
			'\x7f\xc0\x00\x00:\x80\x00\x00',
			[[(None, 0.0009765625)]],
		), (
			'<FIELD datatype="floatComplex" arraysize="2"/>',
			'\x7f\xc0\x00\x00:\x80\x00\x00'
				'A\x80\x00\x00A\x0c\x00\x00',
			[[(None, 16+8.75j)]],
		), (
			'<FIELD datatype="short" arraysize="2x3"/>',
			'\x00\x00\x00\x01\x00\x02\x00\x03\x00\x04\x00\x05',
			[[(0,1,2,3,4,5)]],
		)]


class NDArrayTest(testhelpers.VerboseTest):
	"""tests for the (non-existing) support for multi-D arrays.
	"""
	def _assertRavels(self, arrayspec, data, expected):
		res = votable.unravelArray(arrayspec, data)
		self.assertEqual(res, expected)

	def testUnravelNull(self):
		self._assertRavels("*", range(10), range(10))
	
	def testUnravelPlain(self):
		self._assertRavels("3x2", range(6), [[0,1,2],[3,4,5]])

	def testUnravelSkewed(self):
		self._assertRavels("3x2", range(5), [[0,1,2],[3,4]])

	def testUnravelOverlong(self):
		self._assertRavels("3x2", range(9), [[0,1,2],[3,4,5],[6,7,8]])

	def testUnravelAccpetsStar(self):
		self._assertRavels("3x2*", range(9), [[0,1,2],[3,4,5],[6,7,8]])

	def testUnravel3d(self):
		self._assertRavels("3x2x2", range(12), 
			[[[0,1,2],[3,4,5]], [[6,7,8],[9,10,11]]])


if __name__=="__main__":
	testhelpers.main(BinaryReadTest)
