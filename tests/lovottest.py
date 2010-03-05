"""
Tests for our low-level VOTable interface.
"""

import re

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
			[[[True, False, None, True]], [[True]], [[]]]
		), (
			'<FIELD name="y" datatype="unsignedByte" arraysize="*">'
			' <VALUES null="16"/></FIELD>',
			[['10 0x10\t 16 \n 0x16']],
			[[[10, 16, None, 22]]]
		), (
			'<FIELD name="x" datatype="char" arraysize="4"/>',
			[[''], ['auto'], ['&apos;xx&quot;'], [u'\xe4'], ['&#xe4;']],
			[[''], ['auto'], ["'xx\""],          [u'\xe4'], [u'\xe4']],
		), (
			'<FIELD name="x" datatype="short" arraysize="*"><VALUES null="0"/></FIELD>',
			[['1 2 3 0 1']], 
			[[[1,2,3,None,1]]]
		), (
			'<FIELD name="y" datatype="floatComplex" arraysize="*"/>',
			[['1 1 0.5e10 -2e5']],
			[[[(1+1j), 5e09-2e5j]]]
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
		self.assertEqual(repr(vals), '[[nan, inf, -inf]]')


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
			"<TR><TD>1</TD></TR><TR><TD></TD></TR><TR><TD></TD></TR>"
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
		), (
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
			'<TR><TD>23</TD><TD>\x00</TD><TD>-9999</TD></TR>'
		), (
			[V.FIELD(datatype="unsignedByte", arraysize="2")[V.VALUES(null="0xff")]],
			[[[]], [[2]], [None], [[2, 3, 4]]],
		'<TR><TD>0xff 0xff</TD></TR><TR><TD>2 0xff</TD></TR>'
		'<TR><TD>0xff 0xff</TD></TR><TR><TD>2 3</TD></TR>'
		), (
			[V.FIELD(datatype="bit", arraysize="*")],
			[[430049293488]],
			'<TR><TD>110010000100000111011110111010010110000</TD></TR>'
		), (
			[V.FIELD(datatype="doubleComplex", arraysize="2")[V.VALUES(null="0 0")]],
			[[[2+2j, None, 4+4j]]],
			'<TR><TD>2.0 2.0 0 0</TD></TR>'
		), (
			[V.FIELD(datatype="double", arraysize="*")[V.VALUES(null="23")]],
			[[None], [[None]]],
			"<TR><TD></TD></TR><TR><TD>23</TD></TR>"
		)
	]


if __name__=="__main__":
	testhelpers.main(TabledataWriteTest)
