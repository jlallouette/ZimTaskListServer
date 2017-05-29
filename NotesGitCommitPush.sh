#!/bin/bash
GitDir=$1
SpecifName=$2
NeedToRunLock=/tmp/NeedToRun$SpecifName.lock
NeedToRunPath=/tmp/NeedToRun$SpecifName
ActualRunLock=/tmp/ActualRun$SpecifName.lock


# Just signals that a run is needed
while true; do
	if mkdir "$NeedToRunLock"
	then
		touch "$NeedToRunPath"
		break
	else
		sleep 1
	fi
done
rm -rf "$NeedToRunLock"

# Actually run the script
while true; do
	if mkdir "$ActualRunLock"
	then
		# Remove lockdir when the script finishes, or when it receives a signal
		trap 'rm -rf "$ActualRunLock"' 0    # remove directory when script finishes

		RunningNeeded=false
		# First check if running is needed
		while true; do
			if mkdir "$NeedToRunLock"
			then
				if [ -f "$NeedToRunPath" ]
				then
					RunningNeeded=true
					rm -f "$NeedToRunPath"
				fi
				break
			else
				sleep 1
			fi
		done
		rm -rf "$NeedToRunLock"

		if [ "$RunningNeeded" = true ]
		then
			oldUmask=$(umask)
			umask 0002
			cd $GitDir
			git --git-dir $GitDir.git --work-tree $GitDir commit -a -m "AutoCommit from TaskList app"
			git --git-dir $GitDir.git --work-tree $GitDir push
			umask $oldUmask
		fi
		break

	else
		sleep 1
	fi
done

