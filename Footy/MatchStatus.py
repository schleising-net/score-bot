postponed = 'POSTPONED'
scheduled = 'SCHEDULED'
awarded = 'AWARDED'
suspended = 'SUSPENDED'
inPlay = 'IN_PLAY'
canceled = 'CANCELED'
paused = 'PAUSED'
finished = 'FINISHED'

matchToBePlayedList = [scheduled, suspended, paused, inPlay]
matchInProgressList = [inPlay, paused]
matchToBeCheckedList = matchToBePlayedList.append(finished)
