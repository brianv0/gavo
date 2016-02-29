<?xml version="1.0" encoding="UTF-8"?>

<!-- A stylesheet to turn IVOA datalink documents 
(http://www.ivoa.net/documents/DataLink) into HTML pages.

Assumptions on document content beyond conforming datalink content:

(1) null value of content_length is -1
(2) VOTable namespace is 1.2 (as long as you know what version you're handing
    out, just fix xmlns:vot below)


Copyright 2015 The GAVO Project, Moenchhofstr. 12-14, D-69120 Heidelberg;
This code can be used under the GNU GPL; see 
http://www.gnu.org/licenses/gpl.html to learn about your rights.
-->


<xsl:stylesheet
    xmlns:vot="http://www.ivoa.net/xml/VOTable/v1.2"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
   	xmlns="http://www.w3.org/1999/xhtml"
    version="1.0">
   
    <!-- ############################################## Global behaviour -->

    <xsl:output method="xml" 
      doctype-public="-//W3C//DTD XHTML 1.0 Strict//EN"
      doctype-system="http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd"/>

    <!-- Don't spill the content of unknown elements. -->
    <xsl:template match="text()"/>

    <xsl:key
        name="fields"
        match="vot:RESOURCE[@type='results']/vot:TABLE/vot:FIELD"
        use="count(preceding::vot:FIELD)+1"/>

    <xsl:variable
        name="id_index"
        select="count(vot:VOTABLE/vot:RESOURCE[@type='results']/vot:TABLE/
            vot:FIELD[@name='ID']/preceding::vot:FIELD)+1"/>
    <xsl:variable
        name="access_url_index"
        select="count(vot:VOTABLE/vot:RESOURCE[@type='results']/vot:TABLE/
            vot:FIELD[@name='access_url']/preceding::vot:FIELD)+1"/>
    <xsl:variable
        name="service_def_index"
        select="count(vot:VOTABLE/vot:RESOURCE[@type='results']/vot:TABLE/
            vot:FIELD[@name='service_def']/preceding::vot:FIELD)+1"/>
    <xsl:variable
        name="error_message_index"
        select="count(vot:VOTABLE/vot:RESOURCE[@type='results']/vot:TABLE/
            vot:FIELD[@name='error_message']/preceding::vot:FIELD)+1"/>
    <xsl:variable
        name="description_index"
        select="count(vot:VOTABLE/vot:RESOURCE[@type='results']/vot:TABLE/
            vot:FIELD[@name='description']/preceding::vot:FIELD)+1"/>
    <xsl:variable
        name="semantics_index"
        select="count(vot:VOTABLE/vot:RESOURCE[@type='results']/vot:TABLE/
            vot:FIELD[@name='semantics']/preceding::vot:FIELD)+1"/>
    <xsl:variable
        name="content_type_index"
        select="count(vot:VOTABLE/vot:RESOURCE[@type='results']/vot:TABLE/
            vot:FIELD[@name='content_type']/preceding::vot:FIELD)+1"/>
    <xsl:variable
        name="content_length_index"
        select="count(vot:VOTABLE/vot:RESOURCE[@type='results']/vot:TABLE/
            vot:FIELD[@name='content_length']/preceding::vot:FIELD)+1"/>
            
    <!-- ################################### links table -->
    
    <xsl:template match="vot:RESOURCE[@type='results']">
        <h1>Table links</h1>
        <xsl:call-template name="fetch_preview"/>
        <xsl:apply-templates/>
    </xsl:template>

    <xsl:template match="vot:TABLEDATA">
      <table class="links">
        <tr><th>Where?</th><th>Description</th><th>What?</th></tr>
        <xsl:apply-templates/>
      </table>
    </xsl:template>

    <xsl:template name="normal_row">
        <!-- a datalink table row not requring extra processing
        (e.g., not #access) -->
        <tr>
        <xsl:attribute name="class">
            <xsl:value-of select="substring(vot:TD[$semantics_index], 2)"/>
        </xsl:attribute>
        <td>
            <xsl:apply-templates select="vot:TD[$access_url_index]"
                mode="access_url"/>
            <xsl:apply-templates select="vot:TD[$content_length_index]"
                mode="content_length"/>
            <xsl:apply-templates select="vot:TD[$error_message_index]"
                mode="error_message"/>
        </td>
        <td>
            <xsl:apply-templates select="vot:TD[$description_index]"
                mode="description"/>
        </td>
        <td>
            <xsl:apply-templates select="vot:TD[$semantics_index]"
                mode="semantics"/><br/>
            <xsl:apply-templates select="vot:TD[$id_index]"
                mode="id"/>
        </td>

        </tr>
    </xsl:template>

    <xsl:template match="vot:TR">
        <xsl:choose>
            <xsl:when test="vot:TD[$semantics_index]='#access'">
            <!-- services not formatted so far -->
            </xsl:when>
            <xsl:otherwise>
                <xsl:call-template name="normal_row"/>
            </xsl:otherwise>
        </xsl:choose>
    </xsl:template>

    <xsl:template match="vot:TD" mode="id">
        <span class="ivoid-container">
            <span class="ivoid">
                <xsl:value-of select="."/>
            </span>
        </span>
    </xsl:template>

    <xsl:template match="vot:TD" mode="semantics">
            <span class="semantics"><xsl:value-of select="."/></span>
    </xsl:template>

    <xsl:template match="vot:TD" mode="access_url">
           <a class="datalink">
               <xsl:attribute name="href">
                    <xsl:value-of select="."/>
               </xsl:attribute>Link</a>
    </xsl:template>

    <xsl:template name="format-file-size">
        <xsl:param name="file-size"/>
        <xsl:choose>
            <xsl:when test="$file-size&lt;2000">
                <xsl:value-of select="$file-size"/> Bytes</xsl:when>
            <xsl:when test="$file-size&lt;1500000">
                <xsl:value-of select="round($file-size div 102.4) div 10"
                    /> kiB</xsl:when>
            <xsl:when test="$file-size&lt;1500000000">
                <xsl:value-of select="round($file-size div 10485.76) div 100"
                    /> MiB</xsl:when>
            <xsl:when test="$file-size&lt;20e9">
                <xsl:value-of select="round($file-size div 10737418.24) div 100"
                    /> GiB</xsl:when>
            <xsl:otherwise>
                <xsl:value-of select="$file-size"/> Bytes</xsl:otherwise>
        </xsl:choose>
    </xsl:template>

    <xsl:template match="vot:TD" mode="content_length">
        <xsl:if test=". and number(.)!=-1">
            <span class="size">
                (<xsl:call-template name="format-file-size">
                    <xsl:with-param name="file-size" select="number(.)"/>
                </xsl:call-template>)
            </span>
        </xsl:if>
    </xsl:template>

    <xsl:template match="vot:TD" mode="error_message">
            <span class="errmsg">
                    <xsl:value-of select="."/>
            </span>
    </xsl:template>

    <xsl:template match="vot:TD" mode="description">
            <p class="description">
                    <xsl:value-of select="."/>
            </p>
    </xsl:template>

    <!-- ################################### service interface -->

    <xsl:template match="vot:RESOURCE" utype="adhoc:service">
        <xsl:if test="vot:PARAM[@name='standardID']/@value=
           'ivo://ivoa.net/std/SODA#sync-1.0'">
            <form class="service-interface" method="GET">
                <xsl:attribute name="action">
                    <xsl:value-of select="vot:PARAM[@name='accessURL']/@value"/>
                </xsl:attribute>
                <dl class="inputpars">
                    <xsl:apply-templates select="vot:GROUP[@name='inputParams']"
                        mode="build-inputs"/>
                </dl>
                <input type="submit" value="Retrieve data"/>
            </form>
        </xsl:if>
    </xsl:template>

    <!-- **vot:PARAM -> html:input translation**: we match with various
        templates and control conflicts through priority.  Please
        sort rules by descending priority. 
        
        Priorities >=200 are for protocol-specified cases.
        Priorities ]100, 200[ are for 3-factor semantics 
        Priorities <=100 are for heuristics. -->


    <!-- params with a value always become hidden -->
    <xsl:template match="vot:PARAM[@value!='']" mode="build-inputs"
            priority="200">
        <input type="hidden">
            <xsl:attribute name="name">
                <xsl:value-of select="@name"/>
            </xsl:attribute>
            <xsl:attribute name="value">
                <xsl:value-of select="@value"/>
            </xsl:attribute>
        </input>
    </xsl:template>

    <!-- interval-valued params get an interval-valued placeholder -->

    <xsl:template match="vot:PARAM[@xtype='interval']" mode="build-inputs"
            priority="100">
        <dt><xsl:value-of select="@name"/></dt>
        <dd>
            <input type="text" class="interval-input">
                <xsl:attribute name="name">
                    <xsl:value-of select="@name"/>
                </xsl:attribute>
                <xsl:attribute name="placeholder">
                    <xsl:value-of select="vot:VALUES/vot:MIN/@value"/>
                    <xsl:text> </xsl:text>
                    <xsl:value-of select="vot:VALUES/vot:MAX/@value"/>
                </xsl:attribute>
            </input>
            <p class="range">An interval (space-separated pair of numbers),
                where the limits have to be between
                <span class="min">
                    <xsl:value-of select="vot:VALUES/vot:MIN/@value"/>
                </span>
                and
                <span class="max">
                    <xsl:value-of select="vot:VALUES/vot:MAX/@value"/>
                </span>
            </p>
            <p class="param-description">
                <xsl:value-of select="vot:DESCRIPTION"/>
            </p>
        </dd>
    </xsl:template>

    <!-- ... params with options become a select box.  Yes, this
    collides with the interval priority.  We'll resolve this when
    we see an interval-valued enumerated parameter. -->

    <xsl:template match="vot:PARAM[vot:VALUES/vot:OPTION]" mode="build-inputs"
            priority="100">
        <dt><xsl:value-of select="@name"/></dt>
        <dd>
            <select multiple="multiple">
                <xsl:attribute name="name">
                    <xsl:value-of select="@name"/>
                </xsl:attribute>
                <xsl:apply-templates select="vot:VALUES" mode="build-inputs"/>
            </select>
            <p class="param-description">
                <xsl:value-of select="vot:DESCRIPTION"/>
            </p>
        </dd>
    </xsl:template>

    <xsl:template match="vot:OPTION" mode="build-inputs">
        <option>
            <xsl:attribute name="value">
                <xsl:value-of select="@value"/>
            </xsl:attribute>
            <xsl:choose>
                <xsl:when test="@name">
                    <xsl:value-of select="@name"/>
                </xsl:when>
                <xsl:otherwise>
                    <xsl:value-of select="."/>
                </xsl:otherwise>
            </xsl:choose>
        </option>
    </xsl:template>

    <!-- ...non-interval params having min and max get pre-filled with the
        min -->

    <xsl:template match="vot:PARAM[vot:VALUES/vot:MIN]" mode="build-inputs"
        priority="50">
        <dt><xsl:value-of select="@name"/></dt>
        <dd>
            <input type="text">
                <xsl:attribute name="name">
                    <xsl:value-of select="@name"/>
                </xsl:attribute>
                <xsl:attribute name="placeholder">
                    <xsl:value-of select="vot:VALUES/vot:MIN/@value"/>
                </xsl:attribute>
            </input>
            <p class="range">A value between
                <span class="min">
                    <xsl:value-of select="vot:VALUES/vot:MIN/@value"/>
                </span>
                and
                <span class="max">
                    <xsl:value-of select="vot:VALUES/vot:MAX/@value"/>
                </span>
            </p>
            <p class="param-description">
                <xsl:value-of select="vot:DESCRIPTION"/>
            </p>
        </dd>
    </xsl:template>




    <!-- ################################### utility, top-level -->

    <xsl:template name="fetch_preview">
        <xsl:variable name="preview_url" 
            select="//vot:TR[vot:TD[$semantics_index]='#preview']/vot:TD[$access_url_index]"/>
        <xsl:if test="$preview_url">
            <p><img alt="[PREVIEW]">
                <xsl:attribute name="src">
                    <xsl:value-of select="$preview_url"/>
                </xsl:attribute>
            </img></p>
        </xsl:if>
    </xsl:template>


    <xsl:template match="/">
    	<html>
    	<head>
    	<title>Datalink response</title>
    	<style type="text/css">
    	  table {
    	      border-spacing: 0pt;
    	      border-collapse: collapse;
    	  }

    	  td {
    	      padding: 8pt;
    	      border-left: 2pt solid grey;
    	      border-right: 2pt solid grey;
    	  }

    	  span.ivoid-container {
    	      display:inline-block;
    	      width: 20em;
    	      overflow: hidden;
    	  }

    	  span.ivoid {
    	      padding: 2pt;
    	      white-space: nowrap;
    	      background-color: white;
    	  }

    	  span.ivoid-container:hover {
    	      overflow: visible;
    	  }

    	  p.description {
    	      max-width: 20em;
        }

        tr.science {
            background: #AAFFAA;
        }

        tr.calib {
            background: #FFFFAA;
        }

        tr.unknown{
            color: #777777;
        }

        tr.calibration{
            background: #DDDDDD;
        }

        tr.this{
            font-weight: bold;
            background-color: #FFAAAA;
        }

        tr.preview, tr.preview-image {
            background: #FFDDDD;
        }

        tr.access {
            color: #999999;
        }


    	</style>
    	</head>
    	<body>
    	<xsl:apply-templates/>
    	</body>
    	</html>
    </xsl:template>

</xsl:stylesheet>


<!-- vim:et:sw=4:sta
-->
