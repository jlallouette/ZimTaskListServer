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
from CalendarSync import CalendarTaskManager
from Parameters import *
import sys
import os
import hashlib
import datetime

def UpdateCyclicTasks(user):
	def resetTask(tsk):
		tsk.state = 0
		tsk.updatePregenNeeded = True
		tsk.save()
		tsk.updateFile()
		# also reset all subtasks
		for child in tsk.children:
			resetTask(child)

	with db.transaction():
		dates = DueDate.select().join(TaskDates).join(Task).join(NotePage).join(NoteBook).where((NoteBook.user == user) &
			((DueDate.cyclic_y > 0) | (DueDate.cyclic_m > 0) | (DueDate.cyclic_d > 0)) & (DueDate.date <= date.today()) & (Task.state != 0) & (TaskDates.parentDate == False)).order_by(Task.lineId).desc().distinct()
		for dd in dates:
			while 1:
				dd.cycleCounter += 1
				newdate = dd.origDate + timedelta(days = dd.cycleCounter * dd.cyclic_d)
				if dd.cyclic_m > 0:
					tmp = 0
					while 1:
						try:
							newdate = newdate.replace(year = newdate.year + (newdate.month + dd.cycleCounter * dd.cyclic_m - 1) / 12, 
								month = (newdate.month + dd.cycleCounter * dd.cyclic_m - 1) % 12 + 1, day = newdate.day - tmp)
							break
						except:
							tmp += 1
							continue
				if dd.cyclic_y > 0:
					newdate = newdate.replace(year = newdate.year + dd.cyclic_y * dd.cycleCounter)
				dd.date = newdate
				if dd.date < datetime.date.today():
					continue
				else:
					break
			dd.save()
			tasks = Task.select().join(TaskDates).join(NotePage, on=(Task.parentPage == NotePage.id)).join(NoteBook).where((TaskDates.to_date == dd) & (NoteBook.user == user) & (TaskDates.parentDate == False)).distinct()
			for t in tasks:
				if (not t.parent) or (DueDate.select().join(TaskDates).join(Task).where(Task.id == t.parent.id, ((DueDate.cyclic_y > 0) | (DueDate.cyclic_m > 0) | (DueDate.cyclic_d > 0))).count() == 0):
					resetTask(t)
				else:
					t.updatePregenNeeded = True
					t.updateFile()
					t.save()
	with db.transaction():
		for nb in NoteBook.select().where(NoteBook.user == user):
			nb.CommitIfNeeded(doDbCommit = False)
			

def runUpdate(usrName, thrLock = None):
	lock = getLockOn(hashlib.md5(TaskRootPath).hexdigest() + '//' + usrName)
	try:
		print(u'Wait for lock')
		if lock.RunWaitNeeded():
			print(u'Lock ok')
			with getAtomicLock(thrLock):
				user = User.get(User.login == usrName)

			changed = UpdateDB(user, thrLock)
			print(u'UpdateDB end')
			
			with getAtomicLock(thrLock):
				print(u'calendar stuff start')
				if user.calEnable:
					try:
						ctm = CalendarTaskManager(user)
					except:
						ctm = None
				else:
					ctm = None

				print(u'calendar stuff end / cyclic start')
				UpdateCyclicTasks(user)
				print(u'cyclic end')
				if user.calEnable and ctm:
					ctm.UpdateCalendar()
				print(u'Update calendar end')
	finally: 
		lock.release()

if __name__ == "__main__":
	usrName = 'default'
	if len(sys.argv) > 1:
		usrName = sys.argv[1]
	runUpdate(usrName)
