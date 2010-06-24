"""
Code for checking against our user db.

We don't use nevow.guard here since we know we're queried via http, but we
can't be sure that the other end knows html, and we don't want to fuzz around
with sessions.  twisted.cred is a different issue but probably only complicates
matters unnecessarily.
"""

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
	query = ("SELECT groupname FROM users.groups NATURAL JOIN users.users as u"
		" where username=%(username)s AND u.password=%(password)s")
	pars = {"username": username, "password": password}
	return parseResponse(
		base.SimpleQuerier(useProfile=adminProfile
			).runIsolatedQuery(query, pars))


def hasCredentials(user, password, reqGroup):
	"""returns true if user and password match the db entry and the user
	is in the reqGroup.
	"""
	if user=="gavoadmin" and base.getConfig("web", "adminpasswd"
			) and password==base.getConfig("web", "adminpasswd"):
		return True

	conn = base.SimpleQuerier(useProfile=adminProfile)
	dbRes = conn.runIsolatedQuery("select password from users.users where"
		" username=%(user)s", {"user": user})
	if not dbRes or not dbRes[0]:
		return False
	dbPw = dbRes[0][0]
	if dbPw!=password:
		return False
	dbRes = conn.runIsolatedQuery("select groupname from users.groups where"
		" username=%(user)s and groupname=%(group)s", 
		{"user": user, "group": reqGroup,})
	return not not dbRes


# command line interface to manage users and groups
# XXX TODO: This would be a nice playground for single-row manipulators
# in DataDef.

import sys
import traceback

class ArgError(base.Error):
	pass


def _addUser(querier, user, password, remarks=""):
	try:
		querier.query("INSERT INTO users.users (username, password, remarks)"
			" VALUES (%(user)s, %(password)s, %(remarks)s)", locals())
	except sqlsupport.IntegrityError:
		raise base.ui.logOldExc(ArgError("User %s already exists."
			"  Use 'change' command to edit."%user))
	querier.query("INSERT INTO users.groups (username, groupname)"
		" VALUES (%(user)s, %(user)s)", locals())


def _changeUser(querier, user, password, remarks=None):
		if remarks is None:
			c = querier.query("UPDATE users.users SET password=%(password)s"
			" WHERE username=%(user)s", locals())
		else:
			c = querier.query("UPDATE users.users SET password=%(password)s,"
			" remarks=%(remarks)s WHERE username=%(user)s", locals())
		if not c.rowcount:
			sys.stderr.write("Warning: No rows changed for user %s\n"%user)


def _addGroup(querier, user, group):
	try:
		querier.query("INSERT INTO users.groups (username, groupname)"
			" VALUES (%(user)s, %(group)s)", locals())
	except sqlsupport.IntegrityError:
		raise base.ui.logOldExc(ArgError("User %s doesn't exist."%user))


def _listUsers(querier):
	data = querier.query("SELECT username, groupname, remarks"
		" FROM users.users NATURAL JOIN users.groups"
		" GROUP BY username, groupname, remarks").fetchall()
	curUser = None
	for user, group, remark in data:
		if user!=curUser:
			print "\n%s (%s) --"%(user, remark),
			curUser = user
		print group,
	print


def _delUser(querier, user):
	c = querier.query("DELETE FROM users.users WHERE username=%(user)s",
		locals())
	rowsAffected = c.rowcount
	c = querier.query("DELETE FROM users.groups WHERE username=%(user)s",
		locals())
	rowsAffected += c.rowcount
	if not rowsAffected:
		sys.stderr.write("Warning: No rows deleted while deleting user %s\n"%user)


def _delGroup(querier, group):
	c = querier.query("DELETE FROM users.groups WHERE groupname=%(group)s",
		locals())
	if not c.rowcount:
		sys.stderr.write("Warning: No rows deleted while deleting group %s\n"%
			group)


_actions = {
	"add": (_addUser, "<user> <password> [<remark>] --"
		" adds a user with password"),
	"change": (_changeUser, "<user> <password> [<remark>] --"
		" changes user's data"),
	"del": (_delUser, "<user> --"
		" deletes a user"),
	"addgroup": (_addGroup, "<user> <group> -- adds user to group"),
	"delgroup": (_delGroup, "<group> -- deletes a group"),
	"list": (_listUsers, "-- lists known users with groups"),
}

def _getUsage():
	return ("%proc <action> <args>\n"
		"where action may be:\n"+
		"\n".join(["  %s %s"%(action, usage)
				for action, (fun, usage) in _actions.items()]))


def _parseCmdLine():
	from optparse import OptionParser
	parser = OptionParser(usage=_getUsage())
	opts, args = parser.parse_args()
	if len(args)<1:
		parser.print_help()
		sys.exit(1)
	return opts, args


def main():
	from gavo import rscdesc
	from gavo.protocols import basic
	base.setDBProfile("admin")
	querier = base.SimpleQuerier()
	opts, args = _parseCmdLine()
	action, args = args[0], args[1:]
	try:
		_actions[action][0](querier, *args)
		querier.commit()
	except TypeError:
		print _getUsage()
	except ArgError, msg:
		sys.stderr.write(str(msg))
		sys.stderr.write("\nRun without arguments for usage.\n")
		sys.exit(1)


if __name__=="__main__":
	main()
