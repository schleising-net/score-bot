from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from pytz import timezone
from dateparser import parse

import Footy.MatchStatus as MatchStatus
from Footy.MatchStates import MatchState
from Footy.TeamData import myTeamMapping, teamsToWatch, allTeams
from Footy import SupportedBantzStrings
from Footy import UnsupportedBantzStrings

@dataclass
class MatchChanges:
    firstHalfStarted: bool = False
    halfTime: bool = False
    secondHalfStarted: bool = False
    fullTime: bool = False

    goalScored: bool = False

    teamWon: bool = False
    teamLost: bool = False
    teamDrew: bool = False

class Match:
    def __init__(self, matchData: dict[str, Any], competition: str, oldMatch: Optional[Match] = None) -> None:
        # Get the match ID
        self.id = matchData['id']

        # Get the home and away team names
        self.homeTeam = matchData['homeTeam']['name']
        self.awayTeam = matchData['awayTeam']['name']
        self.homeTeamShort = allTeams[self.homeTeam]['team'] if self.homeTeam in allTeams else self.homeTeam
        self.awayTeamShort = allTeams[self.awayTeam]['team'] if self.awayTeam in allTeams else self.awayTeam

        # Get the full time score, replacing None with TBD
        self.homeScore = int(matchData['score']['fullTime']['homeTeam']) if matchData['score']['fullTime']['homeTeam'] is not None else 'TBD'
        self.awayScore = int(matchData['score']['fullTime']['awayTeam']) if matchData['score']['fullTime']['awayTeam'] is not None else 'TBD'

        # Get and parse the match date and time, times are all UTC, so make sure the datetime is aware
        matchDate = parse(matchData['utcDate'])
        if matchDate is None:
            self.matchDate = datetime(1900, 1, 1).replace(tzinfo=timezone('UTC'))
        else:
            self.matchDate = matchDate.replace(tzinfo=timezone('UTC'))

        # Set the competition name
        self._competition = competition

        # Set the stage and group
        self._stage = matchData['stage']
        self._group = matchData['group']

        # Get the status of the match
        self.status = matchData['status']

        # Set whether my team is home or away
        if self.homeTeam in teamsToWatch:
            self._teamHome = True
            self._teamAway = False
        elif self.awayTeam in teamsToWatch:
            self._teamHome = False
            self._teamAway = True
        else:
            self._teamHome = False
            self._teamAway = False

        # Get the team name
        self.teamName = self.homeTeam if self._teamHome else self.awayTeam

        # Check whether supported teams are playing each other
        if self._teamHome and self._teamAway:
            self.supportedTeamPlayingSupportedTeam = True
        else:
            self.supportedTeamPlayingSupportedTeam = False

        # Set the team and opposition scores
        if self.homeScore != 'TBD' and self.awayScore != 'TBD':
            self.teamScore = self.homeScore if self._teamHome else self.awayScore
            self.oppositionScore = self.awayScore if self._teamHome else self.homeScore
        else:
            self.teamScore = 0
            self.oppositionScore = 0

        # Get the match changes if the old data is available
        if oldMatch is not None:
            # Set the match state to the old match state
            self.matchState = oldMatch.matchState

            # Get the match changes
            self.matchChanges = self._CheckStatus(oldMatch)

        else:
            # initialise the match changes
            self.matchChanges = MatchChanges()

            # initialise the match state
            self.matchState = MatchState(0, 0).FindState()

        if self.teamName in myTeamMapping:
            self.bantzStrings = SupportedBantzStrings
        else:
            self.bantzStrings = UnsupportedBantzStrings

    def _CheckStatus(self, oldMatch: Match) -> MatchChanges:
        # Check for various state changes in the match
        matchChanges = MatchChanges()

        # Check whether the match has started
        if oldMatch.status == MatchStatus.scheduled and self.status == MatchStatus.inPlay:
            matchChanges.firstHalfStarted = True

        # Check for half time
        elif oldMatch.status == MatchStatus.inPlay and self.status == MatchStatus.paused:
            matchChanges.halfTime = True

        # Check for the start of the second half
        elif oldMatch.status == MatchStatus.paused and self.status == MatchStatus.inPlay:
            matchChanges.secondHalfStarted = True

        # Check for full time
        elif oldMatch.status == MatchStatus.inPlay and self.status == MatchStatus.finished:
            matchChanges.fullTime = True

            # Check for the home team winning
            if self.teamScore > self.oppositionScore:
                matchChanges.teamWon = True
                matchChanges.teamLost = False

            # Check for the away team winning
            elif self.teamScore < self.oppositionScore:
                matchChanges.teamWon = False
                matchChanges.teamLost = True
            else:
                # Game was drawn
                if self._teamHome or self._teamAway:
                    matchChanges.teamDrew = True

        # Check for a goal
        if self.homeScore != oldMatch.homeScore or self.awayScore != oldMatch.awayScore:
            matchChanges.goalScored = True

            # Get the new match state
            self.matchState = self.matchState.GoalScored(self.teamScore, self.oppositionScore)

        # Return the changes
        return matchChanges

    def GetScoreline(self) -> str:
        # Create a string for the scoreline
        return f'{self.homeTeamShort} {self.homeScore} - {self.awayScore} {self.awayTeamShort}'

    # Convert this match into a string for printing
    def __str__(self) -> str:
        # Create a string for the match details
        matchDetails = f'{self.matchDate.astimezone(tz=ZoneInfo("Europe/London")).strftime("%c %Z")} - {self._competition}'

        # Return the two strings separated by a new line
        return f'{matchDetails}\n{self.GetScoreline()}'
