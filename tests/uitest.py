"""
Tests for event propagation and user interaction.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import contextlib
import os
import re
import subprocess
import sys
import traceback

from gavo.helpers import testhelpers

from gavo import base
from gavo import api
from gavo import rsc
from gavo import rscdesc
from gavo import utils
from gavo.base import events
from gavo.helpers import testtricks
from gavo.user import cli

import tresc


class MiscCLITest(testhelpers.VerboseTest):
	resources = [("conn", tresc.dbConnection)]

	def testUnhandledException(self):
		self.assertOutput(cli.main, argList=["raise"], 
			expectedStderr=lambda msg: "Unhandled exception" in msg,
			expectedRetcode=1)

	def testTopLevelHelp(self):
		self.assertOutput(cli.main, argList=["--help"], 
			expectedStdout=lambda msg: "<func> is a unique" in msg)

	def testNonUniqueMatch(self):
		self.assertOutput(cli.main, argList=["a"], 
			expectedRetcode=1,
			expectedStderr=
				lambda msg: msg.startswith("Multiple matches for function a"))

	def testNoMatch(self):
		self.assertOutput(cli.main, argList=["xyloph"], 
			expectedRetcode=1,
			expectedStderr=
				lambda msg: msg.startswith("No match for function xyloph"))

	def testSubCmdHelp(self):
		self.assertOutput(cli.main, argList=["publish", "--help"], 
			expectedStdout=lambda msg: "gavo publish [options] {<rd-name>}" in msg)

	def testAProg(self):
		self.assertOutput(cli.main, argList=["stc", "utypes", "Position ICRS"],
			expectedStdout=lambda msg: 
				"AstroCoordSystem.SpaceFrame.CoordRefFrame" in msg)

	def testCleanTAP(self):
		self.conn.commit()
		self.assertOutput(cli.main, argList=["admin", "cleantap"],
			expectedRetcode=0)

	def testExecute(self):
		self.assertOutput(cli.main, argList=["admin", "exec", 
			"data/regtest#silly"],
			expectedStdout="Spawning thread for cron job Do silly things\nSilly\n")

	def testCleanTAPPending(self):
		self.conn.commit()
		self.assertOutput(cli.main, argList=["admin", "cleantap", "-p"],
			expectedRetcode=0, expectedStderr="")

	def testShowDD(self):
		self.assertOutput(cli.main, argList=["show", "dds", "//tap"],
			expectedStdout="importTablesFromRD\n"
				"importDMsFromRD\nimportColumnsFromRD\nimportGroupsFromRD\n"
				"importFkeysFromRD\ncreateSchema*\ncreateJobTable*\n")

	def testShowDDBad(self):
		self.assertOutput(cli.main, argList=["show", "dds", "//nonex"],
			expectedRetcode=1,
			expectedStderr=lambda msg: 
				"resource descriptor '__system__/nonex' could not be located")

	def testVersion(self):
		self.assertOutput(cli.main, argList=["--version"],
			expectedRetcode=0,
			expectedStdout=lambda msg: re.match(
				r"Software \(\d+\.\d+(\.\d+)?\)"
				r" Schema \(\d+/-?\d+\)" "\n", msg))


class ImportTest(testhelpers.VerboseTest):
	resources = [("conn", tresc.dbConnection)]

	def testLifecycle(self):
		self.conn.commit()
		with base.AdhocQuerier() as querier:
			self.assertOutput(cli.main, 
				argList=["--suppress-log",
					"imp", "-c", "data/test", "productimport"],
				stdoutStrings=["Rows affected: 2"],
				expectedRetcode=101)

			self.failUnless(querier.tableExists("test.prodtest"))
			self.failIf(querier.tableExists("test.typesTable"))

			self.assertOutput(cli.main,
				argList=["--disable-spew", "--suppress-log", "publish", "data/test"])

			self.failUnless(list(querier.query("SELECT * FROM dc.subjects"
				" WHERE subject=%(s)s", {'s': "Problems, somebody else's"})))

			# drop it all, make sure all traces are gone
			self.assertOutput(cli.main,
				argList=["--disable-spew", "--suppress-log",
					"drop", "data/test"], expectedStdout="", expectedStderr="")
			self.failIf(list(querier.query("SELECT * FROM dc.subjects"
				" WHERE subject=%(s)s", {'s': "Problems, somebody else's"})))
			self.failIf(querier.tableExists("test.prodtest"))

	def testImportDeniedForOffInputs(self):
		destName = os.path.expanduser("~/foobar.rd")
		with testhelpers.testFile(destName, '<resource schema="junk"/>'):
			self.assertOutput(cli.main, 
				argList=["imp", destName],
				expectedRetcode=1, expectedStderr=lambda tx:
				re.match(r"\*\*\* Error: .*/foobar.rd: Only RDs below inputsDir"
				"\n.*/inputs. are allowed.\n", tx) is not None)

	def testMetaImportAndPurge(self):
		self.assertOutput(cli.main, argList=["purge", "test.adql"])
		# make sure the test schema before running the test exists
		self.conn.commit()
		self.assertOutput(cli.main, 
			argList=["imp", "data/test", "productimport-skip"])
		try:
			with base.AdhocQuerier(base.getWritableAdminConn) as querier:
				querier.query("CREATE TABLE test.adql (erratic INTEGER)")
				querier.query("INSERT INTO test.adql VALUES (1)")

			with base.AdhocQuerier() as querier:
				self.assertOutput(cli.main, argList=
					["imp", "-m", "data/test", "ADQLTest"],
					expectedStdout="Updating meta for ADQLTest\n")
				self.assertEqual(list(querier.query(
					"select * from dc.tablemeta where tablename='test.adql'")),
					[(u'test.adql', u'data/test', None, None, True)])
				
				# make sure gavo imp didn't touch the table
				self.assertEqual(list(querier.query("SELECT * FROM test.adql")),
					[(1,)])
		finally:
			self.assertOutput(cli.main, argList=["purge", "test.adql"])

	def testNonExistingDataImpError(self):
		with testtricks.testFile(
				os.path.join(base.getConfig("inputsDir"), "empty.rd"),
				"""<resource schema="test"><table id="foo"/></resource>"""):
			self.assertOutput(cli.main, argList=["--hints", "imp", "empty", "foo"],
				expectedRetcode=1, expectedStderr="*** Error: The DD 'foo'"
					" you are trying to import is not defined within\nthe RD"
					" 'empty'.\nHint: Data elements available in empty include (None)\n")

	def testNoAutoDataImpError(self):
		with testtricks.testFile(
				os.path.join(base.getConfig("inputsDir"), "empty.rd"),
				"""<resource schema="test"><table id="foo"/>
				<data auto="False" id="x"><make table="foo"/></data>
				<data auto="False" id="y"><make table="foo"/></data>
				</resource>"""):
			self.assertOutput(cli.main, argList=["--hints", "imp", "empty"],
				expectedRetcode=1, expectedStderr='*** Error: Neither automatic'
					' not manual data selected from RD empty\nHint: All data'
					' elements have auto=False.  You have to explicitely name\none'
					' or more data to import (names available: x, y)\n')


class _SysRDResource(tresc.FileResource):
	path = "inputs/sysrd.rd"
	content = """<resource schema="test">
			<table onDisk="True" id="fromclitest" system="True">
				<column name="x" type="integer"><values nullLiteral="0"/></column>
			</table>
			<data id="y"><make table="fromclitest"/></data>
		</resource>"""


class SystemImportTest(testhelpers.VerboseTest):
	resources = [("conn", tresc.dbConnection),
		("sysrdFile", _SysRDResource())]

	def _fillTable(self):
		rd = api.getRD("sysrd")
		t = rsc.TableForDef(rd.getById("fromclitest"), connection=self.conn)
		t.addRow({'x': 2})
		self.conn.commit()

	def testNoSystemImportDefault(self):
		self.assertOutput(cli.main, argList=["imp", "--system", "sysrd"],
			expectedRetcode=0, expectedStderr="")
		# Write a 2 into the table that must survive the next imp
		self._fillTable()

		self.assertOutput(cli.main, argList=["imp", "sysrd"],
			expectedRetcode=0, expectedStderr="")
		with base.AdhocQuerier() as q:
			self.assertEqual(list(q.query("select * from test.fromclitest")),
				[(2,)])
			
	def testSystemImport(self):
		self.assertOutput(cli.main, argList=["imp", "--system", "sysrd"],
			expectedRetcode=0, expectedStderr="")
		# Write a 2 into the table that must survive the next imp
		self._fillTable()

		self.assertOutput(cli.main, argList=["imp", "--system", "sysrd"],
			expectedRetcode=0, expectedStderr="")
		with base.AdhocQuerier() as q:
			self.assertEqual(list(q.query("select * from test.fromclitest")),
				[])

	def testSystemDropDrops(self):
		self.assertOutput(cli.main, argList=["drop", "--system", "sysrd"],
			expectedRetcode=0, expectedStderr="", expectedStdout="")
		with base.AdhocQuerier() as q:
			self.failIf(q.tableExists("test.fromclitest"))


class _FITSGeneratedRD(testhelpers.TestResource):
	def make(self, ignored):
		p = testhelpers.ForkingSubprocess(
			["test harness", "--debug", "mkrd", "-r", 
				str(os.path.join(base.getConfig("inputsDir"), "data")),
				"test_data/ex.fits"],
			executable=cli.main, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		out, err = p.communicate(input=input)
		retcode = p.wait()
		if err or retcode:
			sys.stderr.write("panic: generating RD failed, bailing out.\n%s\n"%
				err)
			sys.exit(0)
		return out


class MkRDTest(testhelpers.VerboseTest):
	resources = [("fitsrd", _FITSGeneratedRD())]

	def testFITSRDLooksOk(self):
		for frag in [
				'<column name="color" type="text"',
				'description="Effective exposure time [seconds]"',
				'<map key="exptime">EXPTIME</map>']:
			self.failUnless(frag in self.fitsrd, "%s missing"%frag)
	
	def testRunImp(self):
		with testhelpers.testFile(os.path.join(base.getConfig("inputsDir"),
				"gen.rd"), self.fitsrd):
			self.assertOutput(cli.main, ["imp", "gen"], expectedStderr="",
				expectedStdout=lambda s: "Rows affected: 1", expectedRetcode=0)
			self.assertOutput(cli.main, ["drop", "gen"])

	def testFITSRDMetaFirst(self):
		self.failUnless(self.fitsrd.split("\n")[1].strip().startswith("<meta"))


class _MyRDResource(tresc.FileResource):
	path = "inputs/myrd.rd"
	content = """<resource schema="test">
			<table onDisk="True" id="autotable">
				<column name="x" type="integer" required="True"/></table>
			<table onDisk="True" id="noautotable">
				<column name="x" type="integer" required="True"/></table>
			<data id="y"><make table="autotable"/></data>
			<data id="z" auto="False"><make table="noautotable"/></data>
		</resource>"""


class DropTest(testhelpers.VerboseTest):
	resources = [("myrdFile", _MyRDResource())]

	def testAutoDropping(self):
		self.assertOutput(cli.main, argList=["imp", "myrd", "y", "z"],
			expectedRetcode=0, expectedStderr="")
		self.assertOutput(cli.main, argList=["drop", "myrd"],
			expectedRetcode=0, expectedStderr="")
		with base.AdhocQuerier() as q:
			self.failIf(q.tableExists("test.autotable"))
			self.failUnless(q.tableExists("test.noautotable"))

	def testAllDropping(self):
		self.assertOutput(cli.main, argList=["imp", "myrd", "y", "z"],
			expectedRetcode=0, expectedStderr="")
		self.assertOutput(cli.main, argList=["drop", "myrd", "--all"],
			expectedRetcode=0, expectedStderr="")
		with base.AdhocQuerier() as q:
			self.failIf(q.tableExists("test.autotable"))
			self.failIf(q.tableExists("test.noautotable"))

	def testNamedDropping(self):
		self.assertOutput(cli.main, argList=["imp", "myrd", "y", "z"],
			expectedRetcode=0, expectedStderr="")
		self.assertOutput(cli.main, argList=["drop", "myrd", "z"],
			expectedRetcode=0, expectedStderr="")
		with base.AdhocQuerier() as q:
			self.failUnless(q.tableExists("test.autotable"))
			self.failIf(q.tableExists("test.noautotable"))


class ValidationTest(testhelpers.VerboseTest):
	def testValidUserconfig(self):
		base.caches.clearForName(rscdesc.USERCONFIG_RD_PATH)
		with testtricks.testFile(rscdesc.USERCONFIG_RD_PATH+".rd",
				"""<resource schema="test"><STREAM id="foo"><column name="abc"/>
				</STREAM></resource>"""):
			self.assertOutput(cli.main, argList=["val", "%"],
				expectedRetcode=0, expectedStderr='',
				expectedStdout='% -- OK\n')

	def testInvalidUserconfig(self):
		base.caches.clearForName(rscdesc.USERCONFIG_RD_PATH)
		with testtricks.testFile(rscdesc.USERCONFIG_RD_PATH+".rd",
				"""<resource schema="test"><STREAM id="foo"><column name="abc">
				</STREAM></resource>"""):
			self.assertOutput(cli.main, argList=["val", "%"],
				expectedRetcode=0, expectedStderr='',
				expectedStdout='% -- [ERROR] %: Malformed RD input, message follows\n'
					"  *** Error: mismatched tag: line 2, column 6\n  \nFail\n")


class CLIReferenceTest(testhelpers.VerboseTest):
	def testNonExRD(self):
		self.assertRaisesWithMsg(base.RDNotFound,
			"Resource descriptor 'i/do/not/exist' could not be located"
			" in file system",
			api.getReferencedElement,
			("i/do/not/exist",))
	
	def testNoRDReference(self):
		with testhelpers.testFile(os.path.join(base.getConfig("inputsDir"),
				"nordref.rd"),
				"""<resource schema="__test"><table original="i/do/not#exist"/>
				</resource>""") as src:
			self.assertRaisesWithMsg(base.RDNotFound,
				"Resource descriptor u'i/do/not' could not be located in file system",
				api.getReferencedElement,
				("nordref",))

	def testNoElDirectReference(self):
		self.assertRaisesWithMsg(base.NotFoundError,
			"Element with id 'justrandomjunk' could not be located in RD data/test",
			api.getReferencedElement,
			("data/test#justrandomjunk",))

	def testNoElIndirectReference(self):
		with testhelpers.testFile(os.path.join(base.getConfig("inputsDir"),
				"badref.rd"),
				"""<resource schema="__test">
					<table original="data/test#justrandomjunk"/>
				</resource>""") as src:
			self.assertRaisesWithMsg(base.NotFoundError,
				"Element with id u'justrandomjunk' could not be located"
				" in RD data/test",
				api.getReferencedElement,
				("badref",))

	def testNoElIndirectReferenceInDir(self):
		baseDir = os.path.join(base.getConfig("inputsDir"), "test")
		with testhelpers.testFile(os.path.join(baseDir, "locbad.rd"),
				"""<resource schema="__test">
					<table original="data/test#justrandomjunk"/>
				</resource>""") as src:
			with utils.in_dir(baseDir):
				self.assertRaisesWithMsg(base.NotFoundError,
					"Element with id u'justrandomjunk' could not be located"
					" in RD data/test",
					api.getReferencedElement,
					("locbad",))
	
if __name__=="__main__":
	testhelpers.main(DropTest)
