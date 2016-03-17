<?xml version="1.0" encoding="UTF-8"?>

<xsl:stylesheet
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns="http://www.w3.org/1999/xhtml"
    version="1.0">
    
    <!-- A stylesheet to convert a UWS job-summary into HTML.  -->
    
    <xsl:output method="xml" 
      doctype-public="-//W3C//DTD XHTML 1.0 Strict//EN"
      doctype-system="http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd"/>

    <!-- Don't spill the content of unknown elements. -->
    <xsl:template match="text()"/>

    <xsl:template match="uws:parameter">
      <li class="param">
      <label>
        <xsl:attribute name="for"><xsl:value-of select="@id"/></xsl:attribute>
        <xsl:value-of select="@id"/>
      </label>
      <xsl:text> </xsl:text>
      <input type="text">
        <xsl:attribute name="id"><xsl:value-of select="@id"/></xsl:attribute>
        <xsl:attribute name="name"><xsl:value-of select="@id"/></xsl:attribute>
        <xsl:attribute name="value">
          <xsl:value-of select="text()"/>
        </xsl:attribute>
      </input>
      </li>
    </xsl:template>

    <xsl:template match="uws:parameter[@id='query']">
      <li class="param">
      <label for="query">QUERY</label><br/>
        <textarea name="QUERY" style="width:100%" rows="7">
            <xsl:value-of select="//uws:parameter[@id='query']"/>
        </textarea>
      </li>
    </xsl:template>

    <xsl:template match="uws:parameter[@id='format']">
      <li class="param">
      <label for="query">Response format </label>
        <select name="FORMAT">
          <option value="votable/b2">VOTable</option>
          <option value="text/xml">Text VOTable</option>
          <option value="application/fits">FITS binary</option>
          <option value="text/csv">CSV</option>
          <option value="application/json">JSON</option>
        </select>
        <xsl:text> Current: </xsl:text>
        <xsl:value-of select="."/>
      </li>
    </xsl:template>

    <xsl:template match="uws:parameters">
      <form method="POST">
        <xsl:attribute name="action">
          <xsl:value-of select="/*/uws:jobId"/>/parameters</xsl:attribute>
        <ul class="params"><xsl:apply-templates/></ul>
        <input type="submit" value="Set Parameters"/>
      </form>
    </xsl:template>


    <xsl:template name="instrux">
      <xsl:param name="phase"/>
      <xsl:choose>
        <xsl:when test="$phase='PENDING'">
          <p class="instrux">Use the parameter form to configure 
          your query (in particular, type in the ADQL query and choose some
          maxrec suitable for your query), then use the 
          "Execute query" button below 
          to start the job.</p>
        </xsl:when>
        <xsl:when test="$phase='QUEUED'">
          <p class="instrux">Your job is waiting for other jobs to
          complete.  Please be patient and hit reload now and then.
          You can no longer change parameters except the destruction time.</p>
        </xsl:when>
        <xsl:when test="$phase='EXECUTING'">
          <p class="instrux">Your job is executing.
          You can no longer change parameters except the destruction time.</p>
        </xsl:when>
      </xsl:choose>
    </xsl:template>


    <xsl:template match="/">
      <html>
        <head>
          <title>UWS job <xsl:value-of select="/*/uws:jobId"/></title>
          <style type="text/css">
            p.instrux {
              padding-left: 1ex;
              padding-right: 1ex;
              border-left: 3pt solid grey;
              border-right: 3pt solid grey;
              max-width: 30em;
              margin-left: 3em;
              margin-top: 2ex;
              margin-bottom: 2ex;
            }

            form {
              margin-top: 2ex;
              margin-bottom: 2ex;
              background-color: #ccc;
              padding: 1ex;
            }
          </style>
        </head>
        <body>
          <h1>UWS job <xsl:value-of select="/*/uws:jobId"/></h1>
          <xsl:apply-templates/>
        </body>
      </html>
    </xsl:template>

    <xsl:template match="uws:job">
      <xsl:variable name="jobId"><xsl:value-of select="uws:jobId"/></xsl:variable>
      <xsl:variable name="phase"><xsl:value-of select="uws:phase"/></xsl:variable>

      <xsl:call-template name="instrux">
        <xsl:with-param name="phase" select="$phase"/>
      </xsl:call-template>

      <dl>
        <dt><xsl:text>Phase:</xsl:text></dt>
        <dd><xsl:value-of select="uws:phase"/></dd>

        <dt><xsl:text>Start time</xsl:text></dt>
        <dd><xsl:value-of select="uws:startTime"/></dd>

        <dt><xsl:text>End time:</xsl:text></dt>
        <dd><xsl:value-of select="uws:endTime"/></dd>

        <dt><xsl:text>Maximum duration:</xsl:text></dt>
        <dd><xsl:value-of select="uws:executionDuration"/></dd>

        <dt><xsl:text>Destruction time:</xsl:text></dt>
        <dd><xsl:value-of select="uws:destruction"/></dd>

        <dt>Parameters</dt>
        <dd><xsl:apply-templates/></dd>

        <xsl:if test="$phase='COMPLETED'">
          <dt><xsl:text>Query results:</xsl:text></dt>
          <dd><a>
            <xsl:attribute name="href">
              <xsl:value-of select="$jobId"/>/results/result</xsl:attribute>
             Result</a></dd>
        </xsl:if>

        <xsl:if test="$phase='ERROR'">
          <dt><xsl:text>Error message:</xsl:text></dt>
          <dd><xsl:value-of select="uws:errorSummary/uws:message"/></dd>
        </xsl:if>

      </dl>
      <xsl:if test="$phase='PENDING'">
        <p>
          <form method="post">
            <xsl:attribute name="action">
              <xsl:value-of select="$jobId"/>/executionduration</xsl:attribute>
            Set maximum runtime to <input type="text" name="EXECUTIONDURATION"
                size="5">
              <xsl:attribute name="value"><xsl:value-of select="uws:executionDuration"/></xsl:attribute>
            </input> seconds. <input type="submit" value="Go"/></form> </p>

          <form method="post">
            <xsl:attribute name="action">
              <xsl:value-of select="$jobId"/>/phase</xsl:attribute>
              <input type="hidden" name="PHASE" value="RUN"/>
              <input type="submit" value="Execute query"/>
          </form>

          <p>If you edit the query, you must hit
          "Set query". Otherwise, "Execute query" will not pick up 
          your changes.</p>

        </xsl:if>
      <xsl:if test="$phase='EXECUTING' or $phase='QUEUED'">
        <p>Use your browser's reload to update the phase information.</p>
        <form method="post">
          <xsl:attribute name="action">
            <xsl:value-of select="$jobId"/>/phase</xsl:attribute>
              <input type="hidden" name="PHASE" value="ABORT"/>
              <input type="submit" value="Abort query"/>
          </form></xsl:if>
      <p>
        <form method="post">
          <xsl:attribute name="action">
            <xsl:value-of select="$jobId"/></xsl:attribute>
           <input type="hidden" name="ACTION" value="DELETE"/>
           <input type="submit" value="Delete job"/></form></p>
      <p>
        <form method="post">
          <xsl:attribute name="action">
            <xsl:value-of select="$jobId"/>/destruction</xsl:attribute>
          <input type="submit" value="Change destruction time to"/>
          <input type="text" name="DESTRUCTION">
            <xsl:attribute name="value"><xsl:value-of select="uws:destruction"/></xsl:attribute>
            <xsl:attribute name="size">23</xsl:attribute>
          </input> </form> </p>
       <p>
        <a href=".">List of known jobs</a></p>
  </xsl:template>
</xsl:stylesheet>
<!-- vi:et:sw=2:sta 
-->
