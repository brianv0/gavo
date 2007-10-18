# Author: Francesco Pierfederici <fpierfed@eso.org>.
# Licensed under the Academic Free License version 2.0 (see LICENSE.txt). 
"""
VOTable::Writer
"""
import urllib
import warnings
import copy

try:
    import cElementTree as ElementTree
except:
    from elementtree import ElementTree

import DataModel
import Encoders


namespace = "http://www.ivoa.net/xml/VOTable/v1.1"

class Writer(object):
    """is a facade to writing VOTables.

    Basically, you construct it with the XML encoding you desire (the
    default utf-8 should work fine for most documents).  Then, for each
    VOTable you want to write, you call the write method with the votable
    and a filename or an open, writable stream.
    """
    preamble = '<?xml version="1.0" encoding="%(encoding)s"?>'
    rootAttrs = {
        "xmlns": namespace,
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": namespace,
    }

    def __init__(self, encoding="utf-8"):
        self._encoding = encoding
    
    def write(self, votable, destination):
        tree = ElementTree.ElementTree(votable.xml())
        for key, val in self.rootAttrs.iteritems():
            tree.getroot().set(key, val)
        if isinstance(destination, basestring):
            destination = open(destination, "w")
        destination.write(self.preamble%{
            "encoding": self._encoding,
        })
        tree.write(destination,
            encoding=self._encoding)



# vim:et:sw=4:sta:
