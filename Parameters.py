# ----------------------------------------------------------------------------
# ZimTaskListServer: Management and centralization of tasks in Zim notebooks.
# Copyright (c) 2016-2017 Jules Lallouette
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# ----------------------------------------------------------------------------
import os
from ConfigParser import SafeConfigParser

dirPath = os.path.dirname(os.path.abspath(__file__))

parser = SafeConfigParser()
parser.read(dirPath + '/TaskList.conf')

TaskRootPath = parser.get('TaskListApp', 'TaskRootPath').rstrip('/')+'/'
allowUserCreation = parser.getboolean('TaskListApp', 'allowUserCreation')
NoLogin = parser.getboolean('TaskListApp', 'NoLogin')
localUpdatePeriod = parser.get('TaskListApp', 'localUpdatePeriod')
defaultCSS = parser.get('TaskListApp', 'defaultCSS')
dbType = parser.get('TaskListApp', 'dbType')

sqlitedbFile = parser.get('SQLiteConf', 'sqlitedbFile')

dbName = parser.get('MySQLConf', 'dbName')
dbusr = parser.get('MySQLConf', 'dbusr')
dbpwd = parser.get('MySQLConf', 'dbpwd')

flaskLogPath = parser.get('FlaskConf', 'flaskLogPath')

mailSenderAddress = parser.get('MailReminders', 'mailSenderAddress')
mailSendMailPath  = parser.get('MailReminders', 'mailSendMailPath')
