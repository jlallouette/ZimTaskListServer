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
from Parameters import *
from TaskToDB import *
from email.mime.text import MIMEText
from subprocess import Popen, PIPE, call
from datetime import date, datetime, timedelta
from jinja2 import Environment, FileSystemLoader
import os

CRONTABCMD = 'crontab'

class DummyPageManager:
	def ParseAndHighlight(self, s):
		return Markup(s)
	def GetSubTaskFilter(self):
		return Task.state == 0
	def GetSubTaskOrdering(self):
		return (Task.lineId)
	def PrintMenu(self):
		return ''

class MailCategory:
	def __init__(self, title, tasks):
		self.title = title
		self.tasks = tasks

dummyPgMngr = DummyPageManager()
sendMailFile = 'sendReminderMail.py'

def checkMailSending(user):
	with db.atomic():
		mailCategories = [(mc.split('/')[0], int(mc.split('/')[1])) for mc in user.mailCategories.split(',')]
		categories = []
		nbTasks = 0
		# Create categories
		for ind, mc in enumerate(mailCategories):
			allTasks = []
			query = Task.select().join(TaskDates).join(DueDate).join(NotePage, on=(NotePage.id == Task.parentPage)).join(NoteBook).where((Task.state == 0) & (NoteBook.user == user))
			query = query.where(DueDate.date <= date.today() + timedelta(days = mc[1]))
			if ind > 0:
				query = query.where(DueDate.date > date.today() + timedelta(days = mailCategories[ind-1][1]))
			query = query.order_by(Task.priority.desc())
			for task in query:
				allTasks.append(task)
				task.lastMailReminder = datetime.today()
				task.save()
				nbTasks += 1
			if len(allTasks) > 0:
				categories.append(MailCategory(mc[0], allTasks))

		if len(categories) > 0:
			env = Environment(loader=FileSystemLoader([TaskRootPath + 'templates', TaskRootPath + 'static/css']))
			template = env.get_template('mail.html')
			cssContent = ''
			with open(TaskRootPath + 'static/css/' + user.cssTheme, 'r') as cssFile:
				for l in cssFile:
					cssContent += l
			message = template.render(categories = categories, pageMngr = dummyPgMngr, cssContent=cssContent, colorHighPrio = user.colorHighPrio, colorLowPrio = user.colorLowPrio, maxPrio = user.maxPrio)

			msg = MIMEText(message.encode('utf-8'), 'html', 'utf-8')
			msg["From"] = mailSenderAddress
			msg["To"] = user.mailAddress
			msg["Subject"] = user.mailSubject + ' // ' + str(nbTasks) + ' things to do !'
			p = Popen([mailSendMailPath, "-t", "-oi"], stdin=PIPE)
			p.communicate(msg.as_string())

def UpdateCronTab(user):
	if user.mailEnable:
		mailDays = [int(d) for d in user.mailDays.split(',')]
		mailTimes = [(int(mt.split(':')[1]), int(mt.split(':')[0])) for mt in user.mailTimes.split(',')]
		crntabCmd = TaskRootPath + sendMailFile + ' ' + user.login

		(out, err) = Popen([CRONTABCMD, '-l'], stdout=PIPE, stderr=PIPE).communicate()
		lines = out.decode('utf-8').split('\n')
		fh, tmpPath = mkstemp()
		with open(tmpPath, 'w') as new_file:
			found = False
			for line in lines:
				if crntabCmd not in line and line != '':
					new_file.write(line + '\n')
			timeCmd = ''
			if user.mailEnable:
				for mt in mailTimes:
					timeCmd = str(mt[0]) + ' ' + str(mt[1]) + ' * * '
					for (i, md) in enumerate(mailDays):
						timeCmd += str(md) + (',' if i < len(mailDays) - 1 else ' ')
					new_file.write(timeCmd + 'python ' + crntabCmd + '\n')
		close(fh)
		(out, err) = Popen([CRONTABCMD, tmpPath], stdout=PIPE, stderr=PIPE).communicate()
		print(out + ' // ' + err)
		os.remove(tmpPath)

