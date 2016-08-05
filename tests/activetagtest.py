"""
Tests for active tags within RDs (and friends).
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo.helpers import testhelpers

from gavo import base
from gavo import rscdef
from gavo import rscdesc


class BasicTest(testhelpers.VerboseTest):
	def testStreamContent(self):
		ctx = base.ParseContext()
		res = base.parseFromString(rscdef.TableDef, """<table id="bar">
			<STREAM id="foo"><table id="u" onDisk="True"><column name="x"/>
			</table></STREAM></table>""", context=ctx)
		parsedEvents = ctx.idmap["foo"].events_
		self.assertEqual(len(parsedEvents), 7)
		self.assertEqual(parsedEvents[0][1], "table")
		self.assertEqual(parsedEvents[4][:3], 
			("value", "name", "x"))
		self.assertEqual(parsedEvents[-1][:2], ("end", "table"))
		self.assertEqual(str(parsedEvents[3][-1]), 
			'[<table id="bar">\\n\\t\\t\\t<ST...], (2, 48)')

	def testBasicReplay(self):
		res = base.parseFromString(rscdef.DataDescriptor, """<data id="bar">
			<STREAM id="foo"><table id="u" onDisk="True"><column name="x"/>
			</table></STREAM><FEED source="foo"/></data>""")
		self.assertEqual(res.tables[0].id, "u")
		self.assertEqual(res.tables[0].columns[0].name, "x")

	def testPlainError(self):
		self.assertRaisesWithMsg(base.StructureError, 
			'At [<data id="bar">\\n\\t\\t\\t<STR...], (3, 40) (replaying,'
			' real error position [<data id="bar">\\n\\t\\t\\t<STR...], (2, 48)):'
			" table elements have no honk attributes or children.",
			base.parseFromString, (rscdef.DataDescriptor, """<data id="bar">
			<STREAM id="foo"><table id="u" onDisk="True"><honk name="x"/>
			</table></STREAM><FEED source="foo"/></data>"""))

	def testDocTag(self):
		ctx = base.ParseContext()
		res = base.parseFromString(rscdef.DataDescriptor, """<data id="bar">
			<STREAM id="foo"><doc>A null table.</doc>
			<table id="u" onDisk="True"/></STREAM><FEED source="foo"/></data>""",
			context=ctx)
		self.assertEqual(ctx.idmap["foo"].doc, "A null table.")

	def testDocTagAtEnd(self):
		ctx = base.ParseContext()
		res = base.parseFromString(rscdef.DataDescriptor, """<data id="bar">
			<STREAM id="foo">
			<table id="u" onDisk="True"/><doc>A null table.</doc></STREAM></data>""",
			context=ctx)
		self.assertEqual(ctx.idmap["foo"].doc, "A null table.")


class ReplayMacroTest(testhelpers.VerboseTest):
	def testBasic(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
			"""<data><STREAM id="foo"><table id="\\tabname" onDisk="True">
			<column name="x"/></table></STREAM>
			<FEED source="foo" tabname="abc"/></data>""")
		self.assertEqual(res.tables[0].id, "abc")

	def testStandardMacrosAvailable(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
			"""<data><STREAM id="foo"><table id="test">
			<column name="x\upper{\col}"/></table></STREAM>
			<FEED source="foo" col="abc"/></data>""")
		self.assertEqual(res.tables[0].columns[0].name, "xABC")

	def testHandover(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
			"""<data><STREAM id="foo"><table id="\\tabname" onDisk="True">
			<index columns="\\\\test"/>
			<column name="x"/></table></STREAM>
			<FEED source="foo" tabname="abc"/></data>""")
		self.assertEqual(res.tables[0].indexedColumns.pop(), 
			"test macro expansion")

	def testMissingSource(self):
		self.assertRaisesWithMsg(base.StructureError,
			"At [<data><STREAM id=\"foo\"><tab...], (3, 24):"
			" Need exactly one of source and events on FEED elements",
			base.parseFromString, (rscdef.DataDescriptor, 
			"""<data><STREAM id="foo"><table id="\\tabname" onDisk="True">
			<column name="x"/></table></STREAM>
			<FEED tabname="abc"/></data>"""))

	def testMissingAttribute(self):
		try:
			res = base.parseFromString(rscdef.DataDescriptor, 
				"""<data><STREAM id="foo"><table id="\\tabname" onDisk="True">
				<column name="x"/></table></STREAM>
				<FEED source="foo" /></data>""")
		except base.MacroError, ex:
			self.assertEqual(ex.hint, "This probably means that you should"
				" have set a tabname attribute in the FEED tag.  For details"
				" see the documentation of the STREAM with id foo.")
			return
		self.fail("MacroError not raised")

	def testDEFAULTSPlain(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
			"""<data><STREAM id="foo"><DEFAULTS tabname="fro"/>
			<table id="\\tabname" onDisk="True">
			<column name="x"/></table></STREAM>
			<FEED source="foo" /></data>""")
		self.assertEqual(res.tables[0].id, "fro")

	def testDEFAULTSElement(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
			"""<data><STREAM id="foo"><DEFAULTS><tabname>fro</tabname></DEFAULTS>
			<table id="\\tabname" onDisk="True">
			<column name="x"/></table></STREAM>
			<FEED source="foo" /></data>""")
		self.assertEqual(res.tables[0].id, "fro")

	def testDEFAULTSOverridden(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
			"""<data><STREAM id="foo"><DEFAULTS tabname="fro"/>
			<table id="\\tabname" onDisk="True">
			<column name="x"/></table></STREAM>
			<FEED source="foo" tabname="quux"/></data>""")
		self.assertEqual(res.tables[0].id, "quux")

	def testWithUnicodeValue(self):
		input = """<?xml version="1.0" encoding="iso-8859-1"?>
			<table id="gack"><STREAM id="foo">
			<column name="\\na" description="\\de\\+m"/></STREAM>
			<FEED source="foo" na="bla" de="foo \xb5"/></table>"""
		res = base.parseFromString(rscdef.TableDef, input)
		self.assertEqual(res.columns[0].description, u"foo \u00b5m")

	def testWithUnicodeStream(self):
		input = """<?xml version="1.0" encoding="iso-8859-1"?>
			<table id="gack"><STREAM id="foo">
			<column name="\\na" description="\xb5m"/></STREAM>
			<FEED source="foo" na="bla"/></table>"""
		res = base.parseFromString(rscdef.TableDef, input)
		self.assertEqual(res.columns[0].description, u"\u00b5m")


class NestedTest(testhelpers.VerboseTest):
	def testDoubleNest(self):
		res = base.parseFromString(rscdesc.RD, 
			r"""<resource schema="test"><STREAM id="cols">
					<column name="from2"/>
					<index columns="\\curtable"/></STREAM>
				<STREAM id="foo">
					<table id="\tabname" onDisk="True">
					<FEED source="cols"/>
					<column name="from1"/></table></STREAM>
				<FEED source="foo" tabname="abc"/></resource>""")
		td = res.tables[0]
		self.assertEqual(td.id, "abc")
		self.assertEqual(", ".join(c.name for c in td), "from2, from1")
		self.assertEqual(res.tables[0].indexedColumns.pop(), 
			"test.abc")

	def testInnermostExpansion(self):
		res = base.parseFromString(rscdesc.RD, 
			r"""<resource schema="test"><STREAM id="cols">
					<column name="\innercol"/>
					<index columns="\\curtable"/></STREAM>
				<STREAM id="foo">
					<table id="\tabname" onDisk="True">
					<FEED source="cols" innercol="whoppa"/>
					<column name="from1"/></table></STREAM>
				<FEED source="foo" tabname="abc"/></resource>""")
		td = res.tables[0]
		self.assertEqual(td.id, "abc")
		self.assertEqual(", ".join(c.name for c in td), "whoppa, from1")
		self.assertEqual(res.tables[0].indexedColumns.pop(), 
			"test.abc")

	def testLoopReplay(self):
		res = base.parseFromString(rscdesc.RD, 
			r"""<resource schema="test"><STREAM id="cols">
					<LOOP listItems="x y">
					<events><column name="\item"/></events></LOOP></STREAM>
				<table id="foo"><FEED source="cols"/></table></resource>""")
		self.assertEqual([c.name for c in res.tables[0]],
			['x', 'y'])

	def testLoopExpansion(self):
		res = base.parseFromString(rscdesc.RD, 
			r"""<resource schema="test"><NXSTREAM id="cols">
					<LOOP listItems="\stuff">
					<events><column name="\\item"/></events></LOOP></NXSTREAM>
					<table id="foo"><FEED source="cols" stuff="x y"/></table>
				</resource>""")
		self.assertEqual([c.name for c in res.tables[0]],
			['x', 'y'])


class PruneTest(testhelpers.VerboseTest):
	def testWithName(self):
		td = base.parseFromString(rscdef.TableDef, """
			<table>
			<STREAM id="foo">
				<column name="abta"/>
				<column name="gub"/>
			</STREAM>
			<FEED source="foo">
				<PRUNE name="abta"/>
			</FEED>
			</table>""")
		self.assertEqual(" ".join(c.name for c in td), "gub")
	
	def testWithUCD(self):
		td = base.parseFromString(rscdef.TableDef, """
			<table id="foo">
				<FEED>
					<events>
						<column name="abta" ucd="clin.dead"/>
						<column name="gub"/>
					</events>
					<PRUNE ucd="clin.dead"/>
				</FEED>
			</table>""")
		self.assertEqual(" ".join(c.name for c in td), "gub")

	def testIsConjunction(self):
		td = base.parseFromString(rscdef.TableDef, """
			<table id="foo">
				<FEED>
					<events>
						<column name="abta" ucd="clin.dead"/>
						<column name="gub"/>
					</events>
					<PRUNE ucd="clin.dead" name="gub"/>
				</FEED>
			</table>""")
		self.assertEqual(" ".join(c.name for c in td), "abta gub")

	def testMultiprune(self):
		td = base.parseFromString(rscdef.TableDef, """
			<table id="foo">
				<FEED>
					<events>
						<column name="abta" ucd="clin.dead"/>
						<column name="abto"/>
					</events>
					<PRUNE name="ab.*"/>
				</FEED>
				<column name="neuro"/>
			</table>""")
		self.assertEqual(" ".join(c.name for c in td), "neuro")

	def testDeepPrune(self):
		dd = base.parseFromString(rscdef.DataDescriptor, """
			<data>
				<table id="foo">
					<FEED>
						<events>
							<column name="abta" ucd="clin.dead">
								<values><option>a</option><option>b</option></values>
							</column>
							<column name="abto"/>
							<column name="neuro"/>
						</events>
						<PRUNE name="ab.*"/>
					</FEED>
				</table>
			</data>""")
		self.assertEqual(" ".join(c.name for c in dd.tables[0]), "neuro")

	def testRecursivePune(self):
		dd = base.parseFromString(rscdef.DataDescriptor, """
			<data>
				<STREAM id="srcev">
					<column name="a"/>
					<column name="b"/>
				</STREAM>
				<STREAM id="pruned">
					<FEED source="srcev">
						<PRUNE name="a"/>
					</FEED>
				</STREAM>
				<table id="foo">
					<FEED source="pruned"/>
				</table>
			</data>""")
		self.assertEqual(" ".join(c.name for c in dd.tables[0]), "b")

	def testRecursivePuneWithId(self):
		dd = base.parseFromString(rscdef.DataDescriptor, """
			<data>
				<STREAM id="srcev">
					<column name="a"/>
					<column name="b" id="kill"/>
				</STREAM>
				<STREAM id="pruned">
					<FEED source="srcev">
						<PRUNE id="kill"/>
					</FEED>
				</STREAM>
				<table id="foo">
					<FEED source="pruned"/>
				</table>
			</data>""")
		self.assertEqual(" ".join(c.name for c in dd.tables[0]), "a")

	def testRecursivePuneLate(self):
		dd = base.parseFromString(rscdef.DataDescriptor, """
			<data>
				<STREAM id="srcev">
					<column name="a"/>
					<column name="b" id="kill"/>
				</STREAM>
				<STREAM id="pruned">
					<FEED source="srcev"/>
					<column name="c"/>
				</STREAM>
				<table id="foo">
					<FEED source="pruned">
						<PRUNE id="kill"/>
					</FEED>
				</table>
			</data>""")
		self.assertEqual(" ".join(c.name for c in dd.tables[0]), "a c")


class EditTest(testhelpers.VerboseTest):
	def testProd(self):
		res = base.parseFromString(rscdef.TableDef, 
				"""<table><FEED source="//products#tablecols">
					<EDIT ref="column[accref]" utype="ssa:Access.Reference">
						<values default="notfound.fits"/></EDIT></FEED>
					</table>""")
		self.assertEqual(res.columns[0].utype, "ssa:Access.Reference")
		self.assertEqual(res.columns[0].values.default, "notfound.fits")

	def testInBetween(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
				"""<data><STREAM id="foo"><table id="bla" onDisk="True">
				<column name="x"/><column name="y"/></table></STREAM>
				<FEED source="foo"><EDIT ref="column[x]" type="text"/></FEED></data>""")
		td = res.tables[0]
		self.assertEqual(", ".join(c.type for c in td), "text, real")

	def testDoubleEdit(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
				"""<data>
				<STREAM id="inc"><column name="grok"/></STREAM>
				<STREAM id="foo"><table id="bla" onDisk="True">
				<column name="x"/><column name="y"/>
				<FEED source="inc">
					<EDIT ref="column[grok]" type="spoint"/></FEED></table></STREAM>
				<FEED source="foo"><EDIT ref="column[x]" type="text"/></FEED></data>""")
		td = res.tables[0]
		self.assertEqual(", ".join(c.type for c in td), "text, real, spoint")

	def testRecursiveEdit(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
				"""<data>
				<STREAM id="stage0"><column name="grok"/><column name="nok"/></STREAM>
				<STREAM id="stage1"><FEED source="stage0">
					<EDIT ref="column[grok]" type="text"/></FEED></STREAM>
				<STREAM id="stage2"><FEED source="stage1"/></STREAM>
				<table><FEED source="stage2"/></table></data>""")
		td = res.tables[0]
		self.assertEqual(", ".join(c.type for c in td), "text, real")
	
	def testRecursiveDoubleEdit(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
				"""<data>
				<STREAM id="stage0"><column name="grok"/><column name="nok"/></STREAM>
				<STREAM id="stage1"><FEED source="stage0">
					<EDIT ref="column[nok]" type="text"/></FEED></STREAM>
				<STREAM id="stage2"><FEED source="stage1">
					<EDIT ref="column[nok]" type="char"/></FEED></STREAM>
				<STREAM id="stage3"><FEED source="stage2"/></STREAM>
				<table><FEED source="stage3"/></table></data>""")
		td = res.tables[0]
		self.assertEqual(", ".join(c.type for c in td), "real, char")
	
	def testRemoteEdit(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
				"""<data>
				<STREAM id="stage0"><column name="grok"/><column name="nok"/></STREAM>
				<STREAM id="stage1"><FEED source="stage0"/></STREAM>
				<STREAM id="stage2"><FEED source="stage1">
					<EDIT ref="column[grok]" type="text"/></FEED></STREAM>
				<table><FEED source="stage2"/></table></data>""")
		td = res.tables[0]
		self.assertEqual(", ".join(c.type for c in td), "text, real")


class LoopTest(testhelpers.VerboseTest):
	def testBasic(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
			"""<?xml version="1.0" encoding="iso-8859-1"?><data><STREAM id="foo">
			<column name="c_\\name" description="\\count, \\desc" 
				verbLevel="\\count"/>
			</STREAM>
			<table id="gook">
			<LOOP source="foo"><csvItems>
				name,desc,count
				anInt,m\xf6rkel,2
				aString,sth,3
				</csvItems>
				</LOOP></table></data>""")
		cols = list(res.tables[0])
		self.assertEqual(len(cols), 2)
		self.assertEqual(cols[0].name, "c_anInt")
		self.assertEqual(cols[0].description, u"2, m\u00f6rkel")
		self.assertEqual(cols[1].verbLevel, 3)

	def testEmbedded(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
			r"""<data>
			<table id="gook">
			<LOOP><csvItems>
				band,desc
				B,Johnson B
				C,Kernighan C
				d,"cumbersome, outdated band d"
				</csvItems>
				<events>
					<column name="mag\band" tablehead="m_\band"
						description="Magnitude in \desc"/>
					<column name="e_mag\band" tablehead="Err. m_\band"
						description="Error in \desc magnitude."/>
				</events>
				</LOOP></table></data>""")
		cols = list(res.tables[0])
		self.assertEqual(len(cols), 6)
		self.assertEqual(cols[-1].description, 
			"Error in cumbersome, outdated band d magnitude.")

	def testNoTwoRowSources(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At [<data>\\n\\t\\t\\t<table id="go...], (5, 4):'
			" Must give exactly one data source in LOOP",
			base.parseFromString, (rscdef.DataDescriptor,
			r"""<data>
			<table id="gook">
			<LOOP listItems="a b"><csvItems>band,desc</csvItems>
				<events><column name="mag\band"/></events>
				</LOOP></table></data>"""))
	
	def testListItems(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
			r"""<data>
			<table id="gook">
			<LOOP listItems="a b c">
				<events>
					<column name="orig_\item"/>
				</events>
				</LOOP></table></data>""")
		cols = list(res.tables[0])
		self.assertEqual(len(cols), 3)
		self.assertEqual(cols[-1].name, "orig_c")

	def testCodeItems(self):
		ctx = base.ParseContext()
		base.parseFromString(rscdef.DataDescriptor,
			r"""<data>
				<table id="nok"><column name="a"/><column name="b"/></table>
				<table id="cop"><LOOP><codeItems>
					for item in context.getById("nok"):
						yield {"copName": item.name+"_copy"}</codeItems>
					<events>
						<column name="\copName"/>
					</events></LOOP></table></data>""", context=ctx)
		cols = list(ctx.getById("cop"))
		self.assertEqual(",".join(c.name for c in cols), "a_copy,b_copy")

	def testAdditionalMacros(self):
		table = base.parseFromString(rscdesc.RD,
			r"""<resource schema="data">
			<table id="o">
				<column name="a"/><column name="b"/>
			</table>
			<table id="c">
				<LOOP listItems="a b" tabname="o">
					<events>
						<column original="\tabname.\item"/>
					</events>
				</LOOP>
			</table></resource>""").tables[1]
		self.assertEqual(table.id, "c")
		self.assertEqual(table.columns[0].name, "a")
		self.assertEqual(table.columns[1].name, "b")

	def testPassivate(self):
		table = base.parseFromString(rscdesc.RD,
			r"""<resource schema="data">
			<STREAM id="col1">
				<column name="foo"/>
			</STREAM>
			<STREAM id="col2">
				<column name="bar"/>
			</STREAM>
			<STREAM id="cols">
				<LOOP listItems="1 2">
					<events passivate="True">
						<FEED source="col\item"/>
					</events>
				</LOOP>
			</STREAM>

			<table id="o">
				<FEED source="cols"/>
			</table>
			</resource>""").tables[0]
		self.assertEqual(table.columns[0].name, "foo")
		self.assertEqual(table.columns[1].name, "bar")

	def testGeneratedSTREAMs(self):
		rd = base.parseFromString(rscdesc.RD,
			r"""<resource schema="data">
				<LOOP listItems="1 2">
					<events passivate="True">
						<STREAM id="\item\+stream">
							<table id="tab\item"><column name="colin\item"/></table>
						</STREAM>
					</events>
				</LOOP>
				<FEED source="1stream"/>
				<FEED source="2stream"/>
			</resource>""")
		self.assertEqual(rd.getById("tab1").columns[0].name, "colin1")
		self.assertEqual(rd.getById("tab2").columns[0].name, "colin2")
			

class RDBasedTest(testhelpers.VerboseTest):
	def setUp(self):
		self.rd = testhelpers.getTestRD("activetest")
	
	def testCSVMacrosExpandedInTable(self):
		cols = list(self.rd.getById("mags"))
		self.assertEqual(len(cols), 6)
		self.assertEqual(cols[0].name, "jmag")
		self.assertEqual(cols[-1].description, "Error in magnitude in the K band")


class MixinTest(testhelpers.VerboseTest):
	baseRDLit = r"""<resource schema="test">
		<mixinDef id="bla">
			<mixinPar key="xy">xy</mixinPar>
			<mixinPar key="nd"/>
			<events>
				<param name="\xy" type="text">\nd</param>
			</events>
		</mixinDef>
		%s
	</resource>"""

	def testWorkingMacro(self):
		res = base.parseFromString(rscdesc.RD,
			self.baseRDLit%'<table><mixin nd="uu">bla</mixin></table>')
		self.assertEqual(res.tables[0].params[0].name, "xy")
		self.assertEqual(res.tables[0].params[0].value, "uu")

	def testWorkingMacroElement(self):
		res = base.parseFromString(rscdesc.RD,
			self.baseRDLit%'<table><mixin><nd>"uu"</nd>bla</mixin></table>')
		self.assertEqual(res.tables[0].params[0].name, "xy")
		self.assertEqual(res.tables[0].params[0].value, '"uu"')

	def testOverridingMacro(self):
		res = base.parseFromString(rscdesc.RD,
			self.baseRDLit%'<table><mixin xy="zq" nd="uu">bla</mixin></table>')
		self.assertEqual(res.tables[0].params[0].name, "zq")
		self.assertEqual(res.tables[0].params[0].value, "uu")

	def testNotFilledMacro(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At [<resource schema="test">\\n\\...], (9, 27):'
			" Mixin parameter nd mandatory",
			base.parseFromString,
			(rscdesc.RD,
			self.baseRDLit%'<table><mixin xy="zq">bla</mixin></table>'))

	def testBadFillingRaises(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At [<resource schema="test">\\n\\...], (9, 20):'
			" nd elements cannot have a children in mixins.",
			base.parseFromString,
			(rscdesc.RD,
			self.baseRDLit%'<table><mixin><nd><a>uu</a></nd>bla</mixin></table>'))
	
	def testUnknownMacroRaises(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At [<resource schema="test">\\n\\...], (9, 35):'
			' The attribute(s) a is/are not allowed on this mixin',
			base.parseFromString,
			(rscdesc.RD,
			self.baseRDLit%'<table><mixin nd="u"><a>uu</a>bla</mixin></table>'))

	def testBadMacroNamesRejected(self):
		self.assertRaises(base.StructureError, 
			base.parseFromString, rscdesc.RD,
			r"""<resource schema="test"><mixinDef id="bla">
				<mixinPar key="a">__NULL__</mixinPar></mixinDef></resource>""")

	def testNULLDefault(self):
			res = base.parseFromString(rscdesc.RD,
			r"""<resource schema="test"><mixinDef id="bla">
				<mixinPar key="aa">__NULL__</mixinPar><events>
				<param name="u">\aa</param></events></mixinDef>
				<table mixin="bla"/></resource>""")
			self.assertEqual(res.tables[0].params[0].value, None)

	def testEmptyDefault(self):
			res = base.parseFromString(rscdesc.RD,
			r"""<resource schema="test"><mixinDef id="bla">
				<mixinPar key="aa">__EMPTY__</mixinPar><events>
				<param name="u" unit=""/></events></mixinDef>
				<table mixin="bla"/></resource>""")
			self.assertEqual(res.tables[0].params[0].unit, "")

	def testNestedFeeds(self):
		res = base.parseFromString(rscdesc.RD,
			r"""<resource schema="test">
			<STREAM id="field">
				<param name="u">\uVal</param>
			</STREAM>
			<mixinDef id="bla">
				<mixinPar key="uVal"/>
				<events>
					<LFEED source="field"/>
				</events>
			</mixinDef>
			<table><mixin uVal="5">bla</mixin></table>
			</resource>""")
		self.assertEqual(res.tables[0].params[0].value, 5.)

	def testReplayedRD(self):
		res = base.parseFromString(rscdesc.RD,
			r"""<resource schema="data">
				<STREAM id="_part">
					<events>
						<column name="urks"/>
					</events>
				</STREAM>
				<mixinDef id="bla">
					<LFEED source="_part"/>
				</mixinDef>
				<table mixin="bla"/></resource>""")
		self.assertEqual(res.tables[0].columns[0].name, "urks")

	def testMixinParsInActiveTags(self):
		res = base.parseFromString(rscdesc.RD,
			r"""<resource schema="data">
				<table id="src">
					<column name="a"/><column name="b"/>
				</table>
				<mixinDef id="bla">
					<mixinPar name="srctable"/>
					<events>
						<LOOP listItems="a b">
							<events>
								<column original="\\srctable.\item"/>
							</events>
						</LOOP>
					</events>
				</mixinDef>
				<table id="dest"><mixin srctable="src">bla</mixin></table>
				</resource>""")
		self.assertEqual(res.tables[1].id, "dest")
		self.assertEqual(res.tables[1].columns[0].name, "a")
		self.assertEqual(res.tables[1].columns[1].name, "b")

	def testMaterialOverrideable(self):
		res = base.parseFromString(rscdesc.RD,
			"""<resource schema="data">
				<table id="bla" mixin="//siap#pgs" onDisk="True" temporary="True">
					<column name="dateObs" description="Don't believe this."/>
				</table></resource>""")
		self.assertEqual(
			res.getById("bla").getColumnByName("dateObs").description,
			"Don't believe this.")

	def testLateEvents(self):
		res = base.parseFromString(rscdesc.RD,
			"""<resource schema="data">
				<table id="bla" mixin="//scs#q3cindex" onDisk="True" temporary="True">
					<column name="r" ucd="pos.eq.ra;meta.main"/>
					<column name="d" ucd="pos.eq.dec;meta.main"/>
				</table></resource>""")
		self.assertTrue("q3c_ang2ipix(r, d)" in
			"".join(res.getById("bla").indices[0].iterCode()))


class ReferenceAttributeTest(testhelpers.VerboseTest):
	def testRefattChangeHonored(self):
		rd = base.parseFromString(rscdesc.RD, """
			<resource schema="test">
				<STREAM id="woo"><var key="src">@inp+33</var></STREAM>
				<STREAM id="loo"><var key="gno">4</var></STREAM>
				<table id="t1"><column name="foo" type="integer" required="True"/>
				</table>
				<data id="make_t1"><dictlistGrammar/>
					<make table="t1">
						<rowmaker>
							<FEED source="woo"/>
							<FEED source="loo"/>
							<map key="foo">@src+1-@gno</map></rowmaker></make></data>
			</resource>
			""")
		from gavo import rsc
		d = rsc.makeData(rd.getById("make_t1"), forceSource=[{'inp': 1}])
		self.assertEqual(d.getPrimaryTable().rows, [{'foo': 31}])


if __name__=="__main__":
	testhelpers.main(MixinTest)
