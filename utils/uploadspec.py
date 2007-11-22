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
"""

from email.Message import Message
from email.MIMEMultipart import MIMEMultipart
import optparse
import httplib
import sys


voServer = "vo.ari.uni-heidelberg.de"
archURI = "/nv/rauchspectra/theospectra/data/mupload"


def _genForm(fName, mode):
  form = FormData()
  form.addFile("File", fName)
  form.addParam("Mode", mode)
  form.addParam("_charset_", "UTF-8")
  form.addParam("__nevow_form__", "upload")
  return form

def upload(fName, mode, host, uri):
  form = _genForm(fName, mode)
  conn = httplib.HTTPConnection(host)
  conn.connect()
  conn.request("POST", uri, form.as_string(), 
    {"Content-Type": 'multipart/form-data; boundary="%s"'%form.get_boundary()})
  resp = conn.getresponse()
  res = resp.read()
  conn.close()
  return resp.status, res
  

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
  parser.add_option("-u", "--update", help="Update record (default is"
    " insert)", dest="update", action="store_true")
  opts, args = parser.parse_args()
  if len(args)!=1:
    parser.print_help()
    sys.exit(1)
  return opts, args


if __name__=="__main__":
  opts, args = parseCmdLine()
  status, msg = upload(args[0], 
    {True: "u", False: "i", None: "i"}[opts.update], 
    voServer, archURI)
  if status==200:
    print msg
  else:
    print "*** Error:", msg
