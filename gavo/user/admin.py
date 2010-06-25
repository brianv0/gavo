"""
DC administration interface.
"""

import sys

from gavo import base
from gavo.protocols import uws


class ArgError(base.Error):
	pass


def _addUser(querier, user, password, remarks=""):
	try:
		querier.query("INSERT INTO users.users (username, password, remarks)"
			" VALUES (%(user)s, %(password)s, %(remarks)s)", locals())
	except sqlsupport.IntegrityError:
		raise base.ui.logOldExc(ArgError("User %s already exists."
			"  Use 'changeuser' command to edit."%user))
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


def _cleanUWS(querier):
	uws.cleanupJobsTable()


_actions = {
	"adduser": (_addUser, "<user> <password> [<remark>] --"
		" adds a user with password"),
	"changeuser": (_changeUser, "<user> <password> [<remark>] --"
		" changes user's data"),
	"deluser": (_delUser, "<user> --"
		" deletes a user"),
	"addgroup": (_addGroup, "<user> <group> -- adds user to group"),
	"delgroup": (_delGroup, "<group> -- deletes a group"),
	"listusers": (_listUsers, "-- lists known users with groups"),
	"cleanuws": (_cleanUWS, "-- removes expired UWS jobs"),
}


def _getUsage():
	return ("Usage: %s <action> <args>\n"
		"where action may be:\n"+
		"\n".join(["  %s %s"%(action, usage)
				for action, (fun, usage) in _actions.items()]))%sys.argv[0]


def _parseCmdLine():
	from optparse import OptionParser
	parser = OptionParser(usage=_getUsage())
	opts, args = parser.parse_args()
	if len(args)<1:
		parser.print_help()
		sys.exit(1)
	return opts, args


def main():
	base.setDBProfile("admin")
	querier = base.SimpleQuerier()
	opts, args = _parseCmdLine()
	action, args = args[0], args[1:]
	try:
		_actions[action][0](querier, *args)
		querier.commit()
	except TypeError:
		import traceback
		traceback.print_exc()
		print _getUsage()
	except ArgError, msg:
		sys.stderr.write(str(msg))
		sys.stderr.write("\nRun without arguments for usage.\n")
		sys.exit(1)

