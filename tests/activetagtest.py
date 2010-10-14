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


if __name__=="__main__":
	testhelpers.main(BasicTest)
