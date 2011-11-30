"""
Code for checking against our user db.

We don't use nevow.guard here since we know we're queried via http, but we
can't be sure that the other end knows html, and we don't want to fuzz around
with sessions.  twisted.cred is a different issue but probably only complicates
matters unnecessarily.
"""

from __future__ import with_statement

from gavo import base
from gavo.base import sqlsupport


# this should only be changed for unit tests
adminProfile = "admin"


class AllSet(set):
	def __repr__(self):
		return "<all encompassing set>"

	def __contains__(*args):
		return True


def getGroupsForUser(username, password):
	"""returns a set of all groups user username belongs to.

	If username and password don't match, you'll get an empty set.
	"""
	def parseResponse(dbTable):
		return set([a[0] for a in dbTable])

	if username is None:
			return set()
	if username=='gavoadmin' and (
			password and password==base.getConfig("web", "adminpasswd")):
		return AllSet()
	query = ("SELECT groupname FROM dc.groups NATURAL JOIN dc.users as u"
		" where username=%(username)s AND u.password=%(password)s")
	pars = {"username": username, "password": password}
	with base.SimpleQuerier(useProfile=adminProfile) as querier:
		return parseResponse(querier.query(query, pars))


def hasCredentials(user, password, reqGroup):
	"""returns true if user and password match the db entry and the user
	is in the reqGroup.
	"""
	if user=="gavoadmin" and base.getConfig("web", "adminpasswd"
			) and password==base.getConfig("web", "adminpasswd"):
		return True

	# ADMINPOOL
	with base.SimpleQuerier(useProfile=adminProfile) as querier:
		dbRes = list(querier.query("select password from dc.users where"
			" username=%(user)s", {"user": user}))
		if not dbRes or not dbRes[0]:
			return False
		dbPw = dbRes[0][0]
		if dbPw!=password:
			return False
		dbRes = list(querier.query("select groupname from dc.groups where"
			" username=%(user)s and groupname=%(group)s", 
			{"user": user, "group": reqGroup,}))
		return not not dbRes
