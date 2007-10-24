"""
Code for checking against our user db.

We don't use nevow.guard here since we know we're queried via http, but we
can't be sure that the other end knows html, and we don't want to fuzz around
with sessions.  twisted.cred is a different issue but probably only complicates
matters unnecessarily.
"""

try:
    from twisted.web import http
except ImportError:
    from twisted.protocols import http

from gavo import config
from gavo import resourcecache
from gavo import sqlsupport

from gavo import Error

def checkCredentials(user, password, reqGroup):
	"""returns true if user and password match the db entry and the user
	is in the reqGroup.
	"""
	conn = resourcecache.getDbConnection()
	dbPw = conn.runQuery("select password from users.users where"
		" username=%(user)s", {
			"user": user})[0][0]
	if dbPw!=password:
		return False
	hasGroup = conn.runQuery("select groupname from users.groups where"
		" username=%(user)s and groupname=%(group)s", {
			"user": user,
			"group": reqGroup,
		})
	return not not hasGroup


def doAuthenticate(ctx, reqGroup, fun):
	"""returns the value of run() if the logged in user is in reqGroup,
	requests authentication otherwise.
	"""
	request = inevow.IRequest(ctx)
	if not checkCredentials(
			request.getUser(), request.getPassword(), reqGroup):
		request.setHeader('WWW-Authenticate', 'Basic realm="Whatever"')
		request.setResponseCode(http.UNAUTHORIZED)
		return "Authorization required"
	return fun()


# command line interface to manage users and groups
# XXX TODO: This would be a nice playground for single-row manipulators
# in DataDef.

import sys
import traceback

class ArgError(Error):
	pass


def _addUser(querier, user, password, remarks=""):
	try:
		querier.query("INSERT INTO users.users (username, password, remarks)"
			" VALUES (%(user)s, %(password)s, %(remarks)s)", locals())
	except sqlsupport.IntegrityError:
		raise ArgError("User %s already exists.  Use 'change' command to edit."%
			user)
	querier.query("INSERT INTO users.groups (username, groupname)"
		" VALUES (%(user)s, %(user)s)", locals())

def _changeUser(querier, user, password, remarks=None):
		if remarks==None:
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
		raise ArgError("User %s doesn't exist."%user)



_actions = {
	"add": (_addUser, "<user> <password> [<remark>] --"
		" adds a user with password"),
	"change": (_changeUser, "<user> <password> [<remark>] --"
		" changes user's data"),
	"addgroup": (_addGroup, "<user> <group> -- adds user to group"),
}

def _usage():
	sys.stderr.write("Usage: %s <action> <args>\n"%sys.argv[0])
	sys.stderr.write("where action may be:\n")
	for action, (fun, usage) in _actions.items():
		sys.stderr.write("%s %s\n"%(action, usage))
	sys.exit(1)


def _parseCmdLine():
	try:
		action = sys.argv[1]
		args = sys.argv[2:]
	except IndexError:
		_usage()
	return action, args


def main():
	config.setDbProfile("feed")
	querier = sqlsupport.SimpleQuerier()
	action, args = _parseCmdLine()
	try:
		_actions[action][0](querier, *args)
		querier.commit()
	except TypeError:
		traceback.print_exc()
		_usage()
	except ArgError, msg:
		sys.stderr.write(str(msg))
		sys.stderr.write("\nRun without arguments for usage.\n")
		sys.exit(1)


if __name__=="__main__":
	main()
	
