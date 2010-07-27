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

class _NS(object): 
	def __init__(self, **kwargs):
		for k,v in kwargs.iteritems():
			setattr(self, k, v)


class TestGroupsMembership(unittest.TestCase):
	def setUp(self):
		self.querier = base.SimpleQuerier()
		admin.adduser(self.querier, 
			_NS(user="X_test", password="megapass", remarks=""))
		admin.adduser(self.querier, 
			_NS(user="Y_test", password="megapass", remarks="second test user"))
		admin.addtogroup(self.querier, _NS(user="X_test", group="Y_test"))
		self.querier.commit()

	def testGroupsForUser(self):
		"""tests for correctness of getGroupsForUser.
		"""
		self.assertEqual(creds.getGroupsForUser("X_test", "wrongpass"),
			set(), "Wrong password should yield empty set but doesn't")
		self.assertEqual(creds.getGroupsForUser("X_test", "megapass"),
			set(["X_test", "Y_test"]))
		self.assertEqual(creds.getGroupsForUser("Y_test", "megapass"),
			set(["Y_test"]))

	def tearDown(self):
		admin.deluser(self.querier, _NS(user="X_test"))
		admin.deluser(self.querier, _NS(user="Y_test"))
		self.querier.finish()


if __name__=="__main__":
	unittest.main()
