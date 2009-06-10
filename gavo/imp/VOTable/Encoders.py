# Author: Francesco Pierfederici <fpierfed@eso.org>.
# Licensed under the Academic Free License version 2.0 (see LICENSE.txt). 
"""
VOTable::Encoders
"""

import struct
import itertools
import traceback
import sys

try:
	from xml.etree import ElementTree
except ImportError:
	try:
			import cElementTree as ElementTree
	except ImportError:
			from elementtree import ElementTree



def _xmlencode(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;")


class GenericEncoder(object):
    def encode(self, fields, data):
        """
        Encode
        
        Given an array of data and a list of Field instances, encode the data
        according to the information in each Field object are return a 
        properly constructed ElementTree.Element instance.
        
        This implementation simply throws an exception. Subclasses have to
        override this menthod.
        """
        raise(NotImplementedError('Please, write your own decoder subclassing this class.'))
        return


class TableDataEncoder(GenericEncoder):
    """is an encoder for XML TABLEDATA data.

    Warning: cElementTree's write performance sucks (at least as of version
    1.0.5).  This makes this thing spectacularly slow.
    """
    naN = float("NaN")

    def encode(self, fields, data):
        """
        TABLEDATA encoder.
        """
        repr = ElementTree.Element('TABLEDATA')
        if(data == None or not len(data)):
            return(repr)

        if(len(fields) == len(data[0])):
            for row in data:
                tr = ElementTree.Element('TR')
                for el in row:
                    td = ElementTree.Element('TD')
                    # Create a text representation of each element.
                    if hasattr(el, "getshape"): # numarray instance, I don't
                        # want to import numarray here
                        td.text = " ".join(map(str, el))
                    elif(el == None or el!=el): # 2nd catches NaN
                        td.text = ''
                    elif(isinstance(el, list) or isinstance(el, tuple)):
                        td.text = self._arrayRepr(el)
                    else:
                        td.text = _xmlencode(el)
                    tr.append(td)
                repr.append(tr)
        elif(len(fields) == 1):
            tr = ElementTree.Element('TR')
            td = ElementTree.Element('TD')
            text = str(data.tolist())
            text = text.replace('[', '')
            text = text.replace(']', '')
            text = text.replace(',', '')
            text = text.replace('\n', '')
            text = text.strip()
            td.text = _xmlencode(text)
            tr.append(td)
            repr.append(tr)
        return(repr)
    
    def _arrayRepr(self, v):
        """
        Given an array v (either a list, tuple or numarray.array), return its
        string representation suitable for inclusion in a TD element.
        """
        repr = ''
        for el in v:
            if(isinstance(el, list) or isinstance(el, tuple)):
                repr += ' %s' % (self._arrayRepr(el))
            else:
                repr += ' %s' % (str(el))
        return(repr)


class StreamEncoder(GenericEncoder):
    typedefs = {
        "boolean": ("c", 1),
        #"bit"
        "unsignedByte": ("B", 1),
        "short": ("h", 2),
        "int": ("i", 4),
        "long": ("q", 8),
        "char": ("c", 1),
        #"unicodeChar": 
        "float": ("f", 4),
        "double": ("d", 8),
        #"floatComplex"
        #"doubleComplex"
    }

    def _makeArrayEncoder(self, type, length):
        typeCode, width = self.typedefs[type]
        if type=="char":
            padding = " "
        else:
            padding = [None]
        if length=="*":
            def encoder(data):
                if data is None:
                    data = ""
                l = len(data)
                if isinstance(data, unicode):
                    data = data.encode("utf-8")
                return struct.pack("!i%d%s"%(l, typeCode), l,
                    *data)
        else:
            if not length:
                length = 1
            else:
                length = int(length)
            formatString = "!%d%s"%(length, typeCode)
            def encoder(data):
                if isinstance(data, unicode):
                    data = data.encode("utf-8")
                if len(data)!=length:
                    data = data[:length]+padding*(length-len(data))
                try:
                    return struct.pack(formatString, *data)
                except struct.error:
                    raise ValueError("Cannot pack %s into field with"
                        " length %s"%(repr(data), length))
        return encoder

    naN = float("NaN")
    encNanDouble = '\x7f\xf8\x00\x00\x00\x00\x00\x00'
    encNanFloat = '\x7f\xc0\x00\x00'
    def _encodeFloat(self, val):
        """returns Nullvalue-correct floats.

        This hurts because it slows us down big time, but !f doesn't work
        with NaN in python 2.4.
        """
        try:
            return struct.pack("!f", val)
        except SystemError:
            return self.encNanFloat

    def _encodeDouble(self, val):
        """returns Nullvalue-correct doubles.
        """
        try:
            return struct.pack("!d", val)
        except SystemError:
            return self.encNanDouble
    
    _length1Indicators = set(["1", 1, None, ''])

    def _makeEncoderForField(self, type, length):
        typeCode = self.typedefs[type][0]
        if length in self._length1Indicators:
            # Gruesome workaround for struct bug; side effect: python<2.5
            # can't pack NULL floats in arrays (who cares?)
            if sys.hexversion<=0x20404f0:
                if type=="float":
                    return self._encodeFloat, None
                if type=="double":
                    return self._encodeDouble, None
            return None, typeCode
        else:
           return self._makeArrayEncoder(type, length), None
    
    def _makeEncodingFunc(self, fields):
        """returns a python callable to encode data described by fields.
        """
        encs = []
        for field in fields:
            encs.append(self._makeEncoderForField(
                field.datatype, field.arraysize))
        curCodes = []
        pythonCode = []
        funcDict = {"struct": struct}
        for curInd, (encFun, typeCode) in enumerate(encs):
            if typeCode is None:
                # function inserts bytes
                if curCodes:
                    pythonCode.append("struct.pack('!%s', *row[%d:%d])"%
                        ("".join(curCodes), curInd-len(curCodes), curInd))
                curCodes = []
                pythonCode.append("fun%d(row[%d])"%(curInd, curInd))
                funcDict["fun%d"%curInd] = encFun
            else:
                # struct inserts bytes
                curCodes.append(typeCode)
        if curCodes:
            pythonCode.append("struct.pack('!%s', *row[%d:%d])"%
                ("".join(curCodes), curInd+1-len(curCodes), curInd+1))
        src = "lambda row: ''.join([%s])"%",".join(pythonCode)
        return src, eval(src, funcDict)


    def encode(self, fields, data):
        """returns data as base64 encoded STREAM element.

        Fields must not be empty.  You have to make sure that whatever
        makes your TABLE elements won't try to make empty ones.
        """
        encSrc, encFunc = self._makeEncodingFunc(fields)
        try:
            encodedData = "".join([encFunc(row) for row in data])
        except (struct.error, SystemError), msg:
            traceback.print_exc()
            raise ValueError("Error while encoding row %s to VOTable:"
                " %s; encoding with %s"%(row, msg, encSrc))
        el = ElementTree.Element("STREAM", encoding="base64")
        el.text = encodedData.encode("base64")
        return el


class BinaryEncoder(GenericEncoder):
    def encode(self, fields, data):
        streamEl = StreamEncoder().encode(fields, data)
        binEl = ElementTree.Element("BINARY")
        binEl.append(streamEl)
        return binEl

# vi:et:sta:ts=4:sw=4
