"""
DC administration interface.
"""

import sys

from gavo import base
from gavo.user.common import Arg, exposedFunction, makeParser
from gavo.protocols import uws


class ArgError(base.Error):
	pass


@exposedFunction([
	Arg("user", help="the user name"),
	Arg("password", help="a password for the user"),
	Arg("remarks", help="optional remarks", 
		default="", nargs='?')],
	help="add a user/password pair and a matching group to the DC server")
def adduser(querier, args):
	try:
		querier.query("INSERT INTO users.users (username, password, remarks)"
			" VALUES (%(user)s, %(password)s, %(remarks)s)", args.__dict__)
	except base.IntegrityError:
		raise base.ui.logOldExc(ArgError("User %s already exists."
			"  Use 'changeuser' command to edit."%args.user))
	querier.query("INSERT INTO users.groups (username, groupname)"
		" VALUES (%(user)s, %(user)s)", args.__dict__)


@exposedFunction([
	Arg("user", help="the user name to remove")],
	help="remove a user from the DC server")
def deluser(querier, args):
	c = querier.query("DELETE FROM users.users WHERE username=%(user)s",
		args.__dict__)
	rowsAffected = c.rowcount
	c = querier.query("DELETE FROM users.groups WHERE username=%(user)s",
		args.__dict__)
	rowsAffected += c.rowcount
	if not rowsAffected:
		sys.stderr.write("Warning: No rows deleted while deleting user %s\n"%
			args.user)


@exposedFunction([
	Arg("user", help="the user name"),
	Arg("password", help="a password for the user"),
	Arg("remarks", help="optional remarks", 
		default="", nargs='?')],
	help="change remarks and/or password for a DC user")
def changeuser(querier, args):
		if args.remarks is None:
			c = querier.query("UPDATE users.users SET password=%(password)s"
			" WHERE username=%(user)s", args.__dict__)
		else:
			c = querier.query("UPDATE users.users SET password=%(password)s,"
			" remarks=%(remarks)s WHERE username=%(user)s", args.__dict__)
		if not c.rowcount:
			sys.stderr.write("Warning: No rows changed for user %s\n"%args.user)


@exposedFunction([
	Arg("user", help="a user name"),
	Arg("group", help="the group to add the user to")],
	help="add a user to a group")
def addtogroup(querier, args):
	try:
		querier.query("INSERT INTO users.groups (username, groupname)"
			" VALUES (%(user)s, %(group)s)", args.__dict__)
	except sqlsupport.IntegrityError:
		raise base.ui.logOldExc(ArgError("User %s doesn't exist."%args.user))


@exposedFunction([
	Arg("user", help="a user name"),
	Arg("group", help="the group to remove the user from")],
	help="remove a user from a group")
def delfromgroup(querier, args):
	c = querier.query("DELETE FROM users.groups WHERE groupname=%(group)s"
		" and username=%(user)s", args.__dict__)
	if not c.rowcount:
		sys.stderr.write("Warning: No rows deleted while deleting user"
			" %s from group %s\n"%(args.user, args.group))


@exposedFunction(help="list users known to the DC")
def listusers(querier, args):
	data = querier.query("SELECT username, groupname, remarks"
		" FROM users.users NATURAL JOIN users.groups ORDER BY username").fetchall()
	curUser = None
	for user, group, remark in data:
		if user!=curUser:
			print "\n%s (%s) --"%(user, remark),
			curUser = user
		print group,
	print


@exposedFunction([
	Arg("-f", help="also remove all jobs in ERROR and QUEUED states (only use"
		" if you are sure what you are doing).", action="store_true",
		dest="includeFailed"),
	Arg("--nuke-completed", help="also remove COMPLETEd jobs (this is"
		" particularly unfriendly.  Dont' use this", action="store_true",
		dest="includeCompleted"),],
	help="remove expired UWS jobs")
def cleanuws(querier, args):
	uws.cleanupJobsTable(includeFailed=args.includeFailed,
		includeCompleted=args.includeCompleted)


def main():
	base.setDBProfile("admin")
	querier = base.SimpleQuerier()
	args = makeParser(globals()).parse_args()
	args.subAction(querier, args)
	querier.commit()

