"""
Test for the web credentials codes.

You shouldn't run this on your production server.  Really.
"""

import unittest

from gavo import base
from gavo import rscdesc
from gavo.protocols import creds
from gavo.user import admin


creds.adminProfile = "test"

class TestGroupsMembership(unittest.TestCase):
	def setUp(self):
		base.setDBProfile("test")
		self.querier = base.SimpleQuerier()
		admin._addUser(self.querier, "X_test", "megapass")
		admin._addUser(self.querier, "Y_test", "megapass", "second test user")
		admin._addGroup(self.querier, "X_test", "X_testgroup")
		self.querier.commit()

	def testGroupsForUser(self):
		"""tests for correctness of getGroupsForUser.
		"""
		self.assertEqual(creds.getGroupsForUser("X_test", "wrongpass"),
			set(), "Wrong password should yield empty set but doesn't")
		self.assertEqual(creds.getGroupsForUser("X_test", "megapass"),
			set(["X_test", "X_testgroup"]))
		self.assertEqual(creds.getGroupsForUser("Y_test", "megapass"),
			set(["Y_test"]))

	def tearDown(self):
		admin._delUser(self.querier, "X_test")
		admin._delUser(self.querier, "Y_test")
		self.querier.finish()


if __name__=="__main__":
	unittest.main()
