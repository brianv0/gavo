"""
Tests for the various utils.*tricks modules.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import glob
import os

from gavo.helpers import testhelpers

from gavo import base
from gavo import utils


class RemoteURLTest(testhelpers.VerboseTest):
	"""tests for urlopenRemote rejecting unwanted URLs.
	"""
	def testNoFile(self):
		self.assertRaises(IOError,
			utils.urlopenRemote, "file:///etc/passwd")
	
	def testHTTPConnect(self):
		# this assumes nothing actually listens on 57388
		self.assertRaisesWithMsg(IOError,
			"Could not open URL http://localhost:57388: Connection refused",
			utils.urlopenRemote, ("http://localhost:57388",))

	def testMalformedURL(self):
		self.assertRaisesWithMsg(IOError, 
			'Could not open URL /etc/passwd: unknown url type: /etc/passwd',
			utils.urlopenRemote, ("/etc/passwd",))


class MatrixTest(testhelpers.VerboseTest):
	def testVecMul(self):
		mat = utils.Matrix3([1, 0, 1], [-1, 1, 0], [0, -1, -1])
		self.assertEqual(mat.vecMul((3, 8, -1)), (2, 5, -7))
	
	def testMatMul(self):
		mat1 = utils.Matrix3([1, 0, 1], [-1, 1, 0], [0, -1, -1])
		mat2 = utils.Matrix3(*mat1.getColumns())
		self.assertEqual(mat1.matMul(mat2), utils.Matrix3(
			(2, -1, -1), (-1, 2, -1), (-1, -1, 2)))


class SafeReplacedTest(testhelpers.VerboseTest):
	testName = os.path.join(base.getConfig("tempDir"), "someFile")

	def tearDown(self):
		try:
			os.unlink(self.testName)
		except os.error:
			pass

	def testDelayedOverwrite(self):
		with open(self.testName, "w") as f:
			f.write("\n".join(["line%03d"%i for i in range(50)]))
		with utils.safeReplaced(self.testName) as destF:
			for ln in open(self.testName):
				destF.write("proc"+ln)
		with open(self.testName) as f:
			self.assertEqual(f.read().split("\n")[48], "procline048")

	def testNoCrapOnError(self):
		with open(self.testName, "w") as f:
			f.write("\n".join(["line%03d"%i for i in range(50)]))
		try:
			with utils.safeReplaced(self.testName) as destF:
				for ln in open(self.testName):
					destF.write("proc"+ln)
				raise ValueError()
		except ValueError:
			# it's expected, I'm raising it myself
			pass

		with open(self.testName) as f:
			self.assertEqual(f.read().split("\n")[48], "line048")
		self.failIf(
			glob.glob(os.path.join(base.getConfig("tempDir"), "*.temp")),
			"There's still a *.temp file left in tempDir; this could be"
			" because of earlier failed tests.  Just remove all the stuff"
			" in %s"%(base.getConfig("tempDir")))


if __name__=="__main__":
	testhelpers.main(SafeReplacedTest)
