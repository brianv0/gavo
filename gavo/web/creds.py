"""
Code for checking against our user db.

We don't use nevow.guard here since we know we're queried via http, but we
can't be sure that the other end knows html, and we don't want to fuzz around
with sessions.  twisted.cred is a different issue but probably only complicates
matters unnecessarily.
"""

from nevow import inevow
try:
    from twisted.web import http
except ImportError:
    from twisted.protocols import http
from twisted.internet import defer

from gavo import config
from gavo import resourcecache
from gavo import sqlsupport
from gavo.web import adbapiconn

from gavo import Error


# this should only be changed for unit tests
adminProfile = "admin"


class AllSet(set):
	def __repr__(self):
		return "<all encompassing set>"

	def __contains__(*args):
		return True

def getGroupsForUser(username, password, async=True):
	"""returns a deferred firing a set of all groups user username belongs to.

	If username and password don't match, you'll get an empty set.
	"""
	def parseResponse(dbTable):
		return set([a[0] for a in dbTable])

	if username is None:
		if async:
			return defer.succeed(set())
		else:
			return set()
	if username=='gavoadmin' and (
			password and password==config.get("web", "adminpasswd")):
		return AllSet()
	query = ("SELECT groupname FROM users.groups NATURAL JOIN users.users as u"
		" where username=%(username)s AND u.password=%(password)s")
	pars = {"username": username, "password": password}
	if async: 
		return resourcecache.getDbConnection(adminProfile).runQuery(query, pars
			).addCallback(parseResponse)
	else:
		return parseResponse(
			sqlsupport.SimpleQuerier(useProfile=adminProfile
				).runIsolatedQuery(query, pars))


def checkCredentials(user, password, reqGroup):
	"""returns true if user and password match the db entry and the user
	is in the reqGroup.
	"""
	# XXX TODO: Maybe keep a hash for login attempts per connection
	# and shut off after too many attempts?
	def checkMembership(dbRes):
		"""receives the reslt of the query for (user, group) tuples.
		"""
		return not not dbRes

	def queryGroups(dbRes):
		"""receives the result of the query for the user password.
		"""
		if not dbRes or not dbRes[0]:
			return False
		dbPw = dbRes[0][0]
		if dbPw!=password:
			return False
		return conn.runQuery("select groupname from users.groups where"
			" username=%(user)s and groupname=%(group)s", {
				"user": user,
				"group": reqGroup,
			}).addCallbacks(checkMembership, lambda f:f)
	
	conn = resourcecache.getDbConnection(adminProfile)
	dbPw = conn.runQuery("select password from users.users where"
		" username=%(user)s", {
			"user": user}).addCallbacks(queryGroups, lambda f: f)
	return dbPw


def runAuthenticated(ctx, reqGroup, fun, *args):
	"""returns the value of fun(*args) if the logged in user is in reqGroup,
	requests authentication otherwise.
	"""
	request = inevow.IRequest(ctx)
	def authenticateOrRun(isAuthorizedUser):
		if isAuthorizedUser:
			return fun(*args)
		else:
			request.setHeader('WWW-Authenticate', 'Basic realm="Gavo"')
			request.setResponseCode(http.UNAUTHORIZED)
			return "Authorization required"
	if request.getUser()=="gavoadmin" and config.get("web", "adminpasswd"
			) and request.getPassword()==config.get("web", "adminpasswd"):
		return authenticateOrRun(True)
	return checkCredentials(
		request.getUser(), request.getPassword(), reqGroup).addCallback(
			authenticateOrRun).addErrback(
			lambda f: f)

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
		raise ArgError("User %s doesn't exist."%user)


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
	config.setDbProfile("admin")
	querier = sqlsupport.SimpleQuerier()
	opts, args = _parseCmdLine()
	action, args = args[0], args[1:]
	try:
		_actions[action][0](querier, *args)
		querier.commit()
	except TypeError:
		traceback.print_exc()
		print _getUsage()
	except ArgError, msg:
		sys.stderr.write(str(msg))
		sys.stderr.write("\nRun without arguments for usage.\n")
		sys.exit(1)


if __name__=="__main__":
	main()
