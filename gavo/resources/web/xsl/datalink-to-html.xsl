<?xml version="1.0" encoding="UTF-8"?>

<xsl:stylesheet
    xmlns:vot="http://www.ivoa.net/xml/VOTable/v1.2"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
   	xmlns="http://www.w3.org/1999/xhtml"
    version="1.0">
   
   	<xsl:include href="dachs-xsl-config.xsl"/>
    
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

    <xsl:template match="vot:TD" mode="content_length">
            <xsl:if test=".">
                 <span class="size">
                      (<xsl:value-of select="."/> Bytes)
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
