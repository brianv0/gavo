"""
A wrapper script suitable for starting the server.
"""

import datetime
import os
import pkg_resources
import signal
import sys

from nevow import appserver
from nevow import inevow
from nevow import rend
from twisted.internet import reactor
from twisted.python import log

from gavo import base
from gavo import utils
from gavo.base import config
from gavo.base import cron
from gavo.user.common import exposedFunction, makeParser
from gavo.web import root



def setupServer(rootPage):
	config.setMeta("upSince", utils.formatISODT(datetime.datetime.utcnow()))
	base.ui.notifyWebServerUp()
	cron.registerScheduleFunction(reactor.callLater)


def serverAction(act):
# XXX TODO: Fix this
	pass
	'''
	PATH=/bin:/usr/bin:/sbin:/usr/sbin:/usr/local/bin
	LOGFILE=/data/gavo/logs/web.log
	PIDFILE=/data/gavo/state/twistd.pid
	APP=/home/msdemlei/checkout/gavo/standalone.tac

	TWISTD_OPTS="--no_save --logfile $LOGFILE --pidfile $PIDFILE --rundir /tmp"

	test -f /lib/lsb/init-functions || exit 1
	. /lib/lsb/init-functions

	case "${1}" in
	("start")
			log_begin_msg "Starting VO Server"
			echo "$TWISTD_BIN $TWISTD_OPTS $APP"
			$TWISTD_BIN $TWISTD_OPTS --python $APP
			log_end_msg $?
			exit $?
			;;
	("stop")
			log_begin_msg "Stopping VO Server..."
			kill -INT `cat $PIDFILE`
			log_end_msg $?
			exit $?
			;;
	("restart" | "force-reload")
			"${0}" stop &&
			"${0}" start
			exit $?
			;;
	(*)
			log_success_msg "Usage: $0 {start|stop|restart|force-reload}" >&2
			exit 3
			;;
	esac
	'''


@exposedFunction(help="start the server and put it in the background.")
def start(args):
	print "starting server"


@exposedFunction(help="stop a running server.")
def stop(args):
	print "stopping server"


class ExitPage(rend.Page):
	def renderHTTP(self, ctx):
		req = inevow.IRequest(ctx)
		req.setHeader("content-type", "text/plain")
		reactor.stop()
		return "exiting."


@exposedFunction(help="run a server and remain in the foreground, dumping"
	" all kinds of stuff to the terminal")
def debug(args):
	log.startLogging(sys.stderr)
	root.root.child_exit = ExitPage()
	reactor.listenTCP(int(base.getConfig("web", "serverPort")), root.site)
	setupServer(root)
	reactor.run()


def main():
	args = makeParser(globals()).parse_args()
	args.subAction(args)


if __name__=="__main__":
	main()
