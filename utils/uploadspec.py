#!/usr/bin/env python

# ** ARI-Location: alnilam:/data/gavo/inputs/rauchspectra/bin/uploadspec.py

"""
This is a little python script that uploads records (i.e., text files) to
the GAVO site.

This is basically just an http file upload.  You must give File=<file upload>
and Mode=i|u in your request, and you *must* use POST of multipart/form-data
content.

The service returns either 400 (for "parameter errors") or 500 (if
something went badly wrong) with a text/plain error message, or
200 and <number> records updated, again as text/plain.

<number> may be 0 on update requests where no record with a matching
primary key is yet in the database.

**Warning**: On this program, you need to give user and password on the
command line which means that they are *visible to all users on the system*.
This isn't as bad as it sounds since the program also uses basic auth over
HTTP which means that username and password are visible to everyone with
access to the network traffic between client and server.
"""

from email.Message import Message
from email.MIMEMultipart import MIMEMultipart
import urlparse
import optparse
import httplib
import sys


defaultURL = ("http://dc.zah.uni-heidelberg.de/"
  "rauchspectra/theospectra/upload/mupload")


def _genForm(fName, mode):
  form = FormData()
  form.addFile("File", fName)
  form.addParam("Mode", mode)
  form.addParam("_charset_", "UTF-8")
  form.addParam("__nevow_form__", "genForm")
  return form


def upload(fName, mode, uploadURL, auth):
  _, host, path, _, query, _ = urlparse.urlparse(uploadURL)
  uri = path+"?"+query
  form = _genForm(fName, mode)
  mime, payload = encodeMultipartFormdata(form)
  conn = httplib.HTTPConnection(host)
  conn.connect()
  conn.request("POST", uri, payload, {
    "Content-Type": mime,
    "Authorization": "Basic %s"%auth.encode("base64"),
    })
  resp = conn.getresponse()
  res = resp.read()
  conn.close()
  return resp.status, res


def encodeMultipartFormdata(msg):
  """returns a safer version of as_string for msg.
  """
  msg.set_boundary("====================bnd%x"%(long(id(msg))))
  BOUNDARY = msg.get_boundary()
  res = []
  for part in msg.get_payload():
    res.append('--' + BOUNDARY)
    for hdr in part.items():
      res.append('%s: %s'%hdr)
    res.append('')
    if isinstance(part.get_payload(), basestring):
      res.append(part.get_payload().replace("\n", "\r\n"))
    else:
      raise NotImplemented("Cannot encode recursive multiparts yet")
  res.append('--' + BOUNDARY + '--')
  res.append('')
  contentType = 'multipart/form-data; boundary=%s' % BOUNDARY
  return contentType, "\r\n".join(res)+"\r\nfoobar"


class FormData(MIMEMultipart):
  """is a container for multipart/form-data encoded messages.

  This is usually used for file uploads.
  """
  def __init__(self):
    MIMEMultipart.__init__(self)
    self.epilogue = ""
  
  def addFile(self, paramName, fileName):
    """attaches the contents of fileName under the http parameter name
    paramName.
    """
    msg = Message()
    msg.set_type("application/octet-stream")
    msg["Content-Disposition"] = "form-data"
    msg.set_param("name", paramName, "Content-Disposition")
    msg.set_param("filename", fileName, "Content-Disposition")
    msg.set_payload(open(fileName).read())
    self.attach(msg)

  def addParam(self, paramName, paramVal):
    """adds a form parameter paramName with the (string) value paramVal
    """
    msg = Message()
    msg["Content-Disposition"] = "form-data"
    msg.set_param("name", paramName, "Content-Disposition")
    msg.set_payload(paramVal)
    self.attach(msg)


def parseCmdLine():
  parser = optparse.OptionParser(usage="%prog [options] filename --"
    " uploads records to the ARI archive")
  parser.add_option("-l", "--login", help="remote user name",
    dest="user", type="string", default="guest")
  parser.add_option("-p", "--password", help="remote password",
    dest="password", type="string", default="guest")
  parser.add_option("-u", "--update", help="Update record (default is"
    " insert)", dest="update", action="store_true")
  parser.add_option("-d", "--upload-dest", help="use URL to post data",
    metavar="URL", action="store", type="string", dest="uploadURI",
    default=defaultURL)
  opts, args = parser.parse_args()
  if len(args)!=1:
    parser.print_help()
    sys.exit(1)
  return opts, args


if __name__=="__main__":
  opts, args = parseCmdLine()
  status, msg = upload(args[0], 
    {True: "u", False: "i", None: "i"}[opts.update], 
    opts.uploadURI,
    "%s:%s"%(opts.user, opts.password))
  if status==200:
    print msg
  else:
    print "*** Error (%s):"%status, msg

# vi:et:sw=2:ts=2:sta:
