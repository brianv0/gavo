"""
Test for the web credentials codes.

You shouldn't run this on your production server.  Really.
"""

import unittest

from gavo import config
from gavo import sqlsupport
from gavo.parsing import importparser
from gavo.web import creds


creds.adminProfile = "test"

class TestGroupsMembership(unittest.TestCase):
	def setUp(self):
		config.setDbProfile("test")
		self.querier = sqlsupport.SimpleQuerier()
		creds._addUser(self.querier, "X_test", "megapass")
		creds._addUser(self.querier, "Y_test", "megapass", "second test user")
		creds._addGroup(self.querier, "X_test", "X_testgroup")
		self.querier.commit()

	def testGroupsForUser(self):
		"""tests for correctness of getGroupsForUser.
		"""
		self.assertEqual(creds.getGroupsForUser("X_test", "wrongpass", async=False),
			set(), "Wrong password should yield empty set but doesn't")
		self.assertEqual(creds.getGroupsForUser("X_test", "megapass", async=False),
			set(["X_test", "X_testgroup"]))
		self.assertEqual(creds.getGroupsForUser("Y_test", "megapass", async=False),
			set(["Y_test"]))

	def tearDown(self):
		creds._delUser(self.querier, "X_test")
		creds._delUser(self.querier, "Y_test")
		self.querier.finish()


if __name__=="__main__":
	unittest.main()
