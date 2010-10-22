"""
Tests for active tags within RDs (and friends).
"""

from gavo import base
from gavo import rscdef
from gavo.helpers import testhelpers


class BasicTest(testhelpers.VerboseTest):
	def testStreamContent(self):
		ctx = base.ParseContext()
		res = base.parseFromString(rscdef.TableDef, """<table id="bar">
			<STREAM id="foo"><table id="u" onDisk="True"><column name="x"/>
			</table></STREAM></table>""", context=ctx)
		parsedEvents = ctx.idmap["foo"].events
		self.assertEqual(len(parsedEvents), 7)
		self.assertEqual(parsedEvents[0][1], "table")
		self.assertEqual(parsedEvents[4][:3], 
			("value", "name", "x"))
		self.assertEqual(parsedEvents[-1][:2], ("end", "table"))
		self.assertEqual(str(parsedEvents[3][-1]), "(2, 48)")

	def testBasicReplay(self):
		res = base.parseFromString(rscdef.DataDescriptor, """<data id="bar">
			<STREAM id="foo"><table id="u" onDisk="True"><column name="x"/>
			</table></STREAM><FEED source="foo"/></data>""")
		self.assertEqual(res.tables[0].id, "u")
		self.assertEqual(res.tables[0].columns[0].name, "x")

	def testPlainError(self):
		self.assertRaisesWithMsg(base.StructureError, 
			"At (3, 40) (replaying, real error position (2, 48)):"
			" TableDef objects cannot have honk children",
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
			"At (3, 24): Need exactly one of source and events on FEED elements",
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


class LoopTest(testhelpers.VerboseTest):
	def testBasic(self):
		res = base.parseFromString(rscdef.DataDescriptor, 
			"""<data><STREAM id="foo">
			<column name="c_\\name" type="\\type"/></STREAM>
			<table id="gook">
			<LOOP source="foo"><csvItems>
				name,type
				anInt,integer
				aString,text
				</csvItems>
				</LOOP></table></data>""")
		cols = list(res.tables[0])
		self.assertEqual(len(cols), 2)
		self.assertEqual(cols[0].name, "c_anInt")
		self.assertEqual(cols[1].type, "text")

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
			"At (5, 4): Must give exactly one data source in LOOP",
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


class RDBasedTest(testhelpers.VerboseTest):
	def setUp(self):
		self.rd = testhelpers.getTestRD("activetest")
	
	def testCSVMacrosExpandedInTable(self):
		cols = list(self.rd.getById("mags"))
		self.assertEqual(len(cols), 6)
		self.assertEqual(cols[0].name, "jmag")
		self.assertEqual(cols[-1].description, "Error in magnitude in the K band")


if __name__=="__main__":
	testhelpers.main(RDBasedTest)
