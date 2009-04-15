#!/bin/sh
dbName=gavo
backupScript=restoreUsers

echo 'psql -c "COPY users.users FROM STDIN" ' $dbName ' <<EOF' > $backupScript
psql -c "COPY users.users TO STDOUT" $dbName >> $backupScript
echo EOF >> $backupScript
echo 'psql -c "COPY users.groups FROM STDIN" ' $dbName ' <<EOF' >> $backupScript
psql -c "COPY users.groups TO STDOUT" $dbName >> $backupScript
echo EOF >> $backupScript
