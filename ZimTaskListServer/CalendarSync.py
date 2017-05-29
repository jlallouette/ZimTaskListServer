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
from TaskToDB import *
import caldav
from caldav.elements import dav, cdav
from datetime import *

class CalendarTaskManager:

	defEvent = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:_CREATEDSTRING_
LAST-MODIFIED:_LASTMODIFSTRING_
DTSTAMP:_DTSTAMPSTRING_
UID:_UIDSTRING_
SUMMARY:_SUMMARYSTRING_
TRANSP:OPAQUE
DESCRIPTION:_DESCRIPTIONSTRING_
STATUS:CONFIRMED
CLASS:PRIVATE
DTSTART;VALUE=DATE:_STARTSTRING_
DTEND;VALUE=DATE:_ENDSTRING_
END:VEVENT
PRODID:-//Inf-IT//CalDavZAP 0.12.1//EN
END:VCALENDAR"""

	UIDPrefix = 'CalSyncId-'

	def __init__(self, user):
		self.user = user
		self.url = user.calURL
		self.client = caldav.DAVClient(self.url, username = user.calUsrName, password = user.GetCalPwd())
		self.principal = self.client.principal()
		self.calendars = self.principal.calendars()
		self.calendar = self.calendars[0]

	def CreateEvent(self, task, duedate):
		sumLen = 30;
		event = self.defEvent
		today = datetime.today().strftime('%Y%m%dT%H%M%SZ')
		dueDateStr = duedate.strftime('%Y%m%d')
		event = event.replace('_CREATEDSTRING_', today)
		event = event.replace('_LASTMODIFSTRING_', today)
		event = event.replace('_DTSTAMPSTRING_', today)
		event = event.replace('_UIDSTRING_', self.UIDPrefix + str(task.id) + '-' + dueDateStr)
		event = event.replace('_SUMMARYSTRING_', task.content[0:sumLen] + '...')
		event = event.replace('_DESCRIPTIONSTRING_', task.content)
		event = event.replace('_STARTSTRING_', dueDateStr)
		event = event.replace('_ENDSTRING_', dueDateStr)
		self.calendar.add_event(event)

	def AddTask(self, task):
		datequery = DueDate.select().join(TaskDates).where(TaskDates.from_task == task.id)
		if datequery.count() > 0:
			for duedate in datequery:
				if duedate.date < date.today():
					self.CreateEvent(task, date.today())
				else:
					self.CreateEvent(task, duedate.date)
		for subtsk in task.children:
			if subtsk.state == 0:
				self.AddTask(subtsk)

	def UpdateCalendar(self):
		# Add unfinished tasks
		for task in Task.select().join(NotePage).join(NoteBook).where((Task.state == 0) & (NoteBook.user == self.user)):
			self.AddTask(task)

		# TODO Add some filtering here

		# Remove tasks that have been finished with duedate >= today
		for event in self.calendar.events():
			p = re.compile('.*?^UID:' + self.UIDPrefix + '([0-9]+)-([0-9]+)$\n.*', re.MULTILINE)
			for m in p.findall(event.data):
				p2 = re.compile('.*?^DESCRIPTION:' + '(.*?)$\n.*', re.MULTILINE)
				eventDescr = p2.search(event.data).group(1)
				tskquery = Task.select().where(Task.id == int(m[0]))
				if tskquery.count() > 0:
					task = Task.get(Task.id == int(m[0]))
					if (task.state == 0 and date(int(m[1][0:4]), int(m[1][4:6]), int(m[1][6:8])) < date.today()):
						event.delete()
				else:
					event.delete()
				break

