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
import fcntl
import os
import time
import hashlib

import threading

class Lock:
	def __init__(self, filename, thrLock = None):
		self.filename = filename
		self.thrLock = thrLock
		if not os.path.isfile(self.filename):
			self.handle = open(filename, 'w')
			os.chmod(self.filename, 438)
		else:
			self.handle = open(filename, 'w')

	def getTimeStamp(self):
		try:
			f = open(self.filename + '.val', 'r')
			line = f.readline()
			lt = float(line)
			f.close()
		except:
			lt = 0.0
		if not os.path.isfile(self.filename + '.val'):
			with open(self.filename + '.val', 'w') as val:
				val.write(format(time.time(), '.16f') + '\n')
			os.chmod(self.filename + '.val', 438)
		else:
			with open(self.filename + '.val', 'w') as val:
				val.write(format(time.time(), '.16f') + '\n')
		return lt

	# Block the call if another instance is running and return true if a further run is necessary
	def RunWaitNeeded(self):
		start = time.time()
		self.acquire()
		return self.getTimeStamp() < start

	def acquire(self):
		if self.thrLock:
			self.thrLock.acquire()
		fcntl.flock(self.handle, fcntl.LOCK_EX)
		
	def release(self):
		fcntl.flock(self.handle, fcntl.LOCK_UN)
		if self.thrLock:
			self.thrLock.release()
		
	def __del__(self):
		self.handle.close()

def getLockOn(identifier, thrLock = None):
	return Lock('/tmp/' + hashlib.md5(identifier).hexdigest() + '.lock', thrLock)
