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
import time
from UpdateDB import *

import threading

def updateLoop(thrLock):
	with getAtomicLock(thrLock):
		updatePeriod = App.get().localUpdatePeriod
	while True:
		if dbType == 'MySQL':
			db.get_conn().ping(True)
		with getAtomicLock(thrLock):
			logins = [usr.login for usr in User.select()]
		for lgn in logins:
			runUpdate(lgn, thrLock)
		time.sleep(updatePeriod)
		with getAtomicLock(thrLock):
			updatePeriod = App.get().localUpdatePeriod

def updatePreGens(thrLock):
	while True:
		time.sleep(0.5)
		if dbType == 'MySQL':
			db.get_conn().ping(True)
		with db.atomic(thrLock):
			tsklst = list(Task.select().where(Task.updatePregenNeeded or (not Task.lastUpdate or Task.lastUpdate < date.today())).order_by(Task.state).limit(1))
			if len(tsklst) > 0:
				task = tsklst[0]
				task.generatePreGen()

		with db.atomic(thrLock):
			tglst = list(TaskGroup.select().where(TaskGroup.updatePregenNeeded).order_by(TaskGroup.state).limit(1))
			if len(tglst) > 0:
				tg = tglst[0]
				tg.generatePreGen()

