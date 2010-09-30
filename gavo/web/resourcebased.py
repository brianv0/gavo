"""
The form renderer and related code.
"""

# XXX TODO: break this up.

import cStringIO
import imp
import mutex
import new
import os
import sys
import time
import traceback
import urllib
import urlparse


from nevow import context
from nevow import flat
from nevow import inevow
from nevow import loaders
from nevow import rend
from nevow import static
from nevow import tags as T, entities as E
from nevow import url
from nevow import util

from twisted.internet import defer
from twisted.internet import threads

from zope.interface import implements

from gavo import base
from gavo import rsc
from gavo import svcs
from gavo.imp import formal
from gavo.imp.formal import form
from gavo.base import typesystems
from gavo.web import common
from gavo.web import grend
from gavo.web import producttar
from gavo.web import serviceresults
from gavo.web import streaming

from gavo.svcs import Error, UnknownURI, ForbiddenURI



