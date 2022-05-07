from datetime import datetime, timedelta, time
from pathlib import Path
import random
from typing import Optional
import warnings
import sys
import logging
from zoneinfo import ZoneInfo

from pytz import timezone
from telegram import Bot, Update
from telegram.ext import Updater, JobQueue, CallbackContext, CommandHandler

from Footy.Footy import Footy
from Footy.Table import Table
from Footy.Match import Match
from Footy.TeamData import teamsToWatch, allTeams, supportedTeamMapping, reverseTeamLookup
from Footy.MatchStates import (
    Drawing,
    TeamLeadByOne, 
    TeamExtendingLead,
    TeamLosingLead,
    TeamDeficitOfOne,
    TeamExtendingDeficit,
    TeamLosingDeficit
)

# Set the chat ID
CHAT_ID = -701653934

class ScoreBot:
    def __init__(self) -> None:
        # Enable logging
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            level=logging.INFO)

        self.logger = logging.getLogger(__name__)

        try:
            # Get the token from the bot_token.txt file, this is exclued from git, so may not exist
            with open(Path('bot_token.txt'), 'r', encoding='utf8') as secretFile:
                token = secretFile.read()
        except:
            # If bot_token.txt is not available, print some help and exit
            print('No bot_token.txt file found, you need to put your token from BotFather in here')
            sys.exit()

        # List of chat IDs to respond to
        self.chatIdList: list[int] = []

        # Set the teams we're interested in
        teams = [team for team in teamsToWatch]

        # Create a Footy object using the list of teams we're interested in
        self.footy = Footy(teams)

        # Create the Updater and pass it your bot's token.
        # Make sure to set use_context=True to use the new context based callbacks
        # Post version 12 this will no longer be necessary
        self.updater = Updater(token, use_context=True)

        # Get the dispatcher to register handlers
        self.dp = self.updater.dispatcher

        # On receipt of a /start command call the start() function and /stop command to call the stop() function
        self.dp.add_handler(CommandHandler('start', self.start))
        self.dp.add_handler(CommandHandler('stop', self.stop))

        # Add chat IDs and list the chat IDs from another chat
        self.dp.add_handler(CommandHandler('add', self.add))
        self.dp.add_handler(CommandHandler('list', self.list))

        # Add a handler to get the table
        self.dp.add_handler(CommandHandler('table', self.GetTable))

        # Add a handler to answer questions
        self.dp.add_handler(CommandHandler('can', self.can))

        # Get the job queue
        self.jq: JobQueue = self.updater.job_queue

        # Add a job which gets todays matches once a day at 1am
        matchUpdateTime = time(1, 0, tzinfo=timezone('UTC'))
        nowTime = datetime.now(tz=ZoneInfo('UTC')).timetz()
        self.jq.run_daily(self.MatchUpdateHandler, matchUpdateTime)

        # Call Get Matches if this is started after the update time
        if nowTime > matchUpdateTime:
            self.GetMatches()

        # Add the error handler to log errors
        self.dp.add_error_handler(self.error)

        # Start the bot polling
        self.updater.start_polling()

        # Run the bot until you press Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT. This should be used most of the time, since
        # start_polling() is non-blocking and will stop the bot gracefully.
        self.updater.idle()

    def start(self, update: Update, context: CallbackContext) -> None:
        # Add the chat ID to the list if it isn't already in there
        if update.message.chat_id not in self.chatIdList:
            self.chatIdList.append(update.message.chat_id)
            print(f'Chat ID {update.message.chat_id} added')

    def stop(self, update: Update, context: CallbackContext) -> None:
        # If the user is me
        if update.message.from_user.first_name == 'Stephen' and update.message.from_user.last_name == 'Schleising':
            # If the chat ID is in the list remove it
            if update.message.chat_id in self.chatIdList:
                self.chatIdList.remove(update.message.chat_id)
                print(f'Chat ID {update.message.chat_id} removed')
        else:
            # Otherwise respond rejecting the request to stop me
            update.message.reply_text('Only my master can stop me !!', quote=False)

    def add(self, update: Update, context: CallbackContext) -> None:
        # If the user is me
        if update.message.from_user.first_name == 'Stephen' and update.message.from_user.last_name == 'Schleising':
            # Get the requested date
            commands: list[str] = update.message.text.split(' ')

            # Get the requested date if it exists in the command (only accessible by me)
            if len(commands) > 1:
                try:
                    chatId = int(commands[1])
                except:
                    print('Need to enter a single integer only')
                    update.message.reply_text('Need to enter a single integer only')
                else:
                    if chatId not in self.chatIdList:
                        self.chatIdList.append(chatId)
                        print(f'Chat ID {chatId} added')
                        update.message.reply_text(f'Chat ID {chatId} added')

    def list(self, update: Update, context: CallbackContext) -> None:
        # If the user is me send back the list of chats the bot is going to send to
        if update.message.from_user.first_name == 'Stephen' and update.message.from_user.last_name == 'Schleising':
            chatIds = '\n'.join(str(chatId) for chatId in self.chatIdList)
            print(f'Chat IDs:\n{chatIds}')
            update.message.reply_text(f'Chat IDs:\n{chatIds}', quote=False)

    def GetTable(self, update: Update, context: CallbackContext) -> None:
        table = Table()
        print(table.condensedTable)
        update.message.reply_markdown_v2(table.condensedTable, quote=False)

    def can(self, update: Update, context: CallbackContext) -> None:
        # Log the request
        print(f'{update.message.from_user.first_name} {update.message.from_user.last_name} in chat {update.message.chat.title} asked {update.message.text}')

        # Get the request
        request = update.message.text.lower().replace('?', '').split()[1:]

        # Get a table object
        table = Table()

        # Test for the first team name being in two parts
        test = ''.join(request[0:2])

        # If the first team name is in two parts join them together and insert that at the start of the
        # list replacing the original two entries
        if test in reverseTeamLookup:
            request.insert(0, ''.join((request.pop(0), request.pop(0))))

        # Match the request
        match request:
            # Can team A still beat team B
            case [teamA, 'beat', *teamB] | [teamA, 'still', 'beat', *teamB]:
                # If team B is in two parts join them togther
                teamB = ''.join(teamB)
                # Ensure both teams are in the lookup table
                if teamA in reverseTeamLookup and teamB in reverseTeamLookup:
                    # Check whether team A can beat team B
                    if table.CanTeamABeatTeamB(reverseTeamLookup[teamA], reverseTeamLookup[teamB]):
                        response = 'Yes'
                    else:
                        response = 'No'
                else:
                    # Standard response
                    response = "Don't ask stupid questions"
            # Can team still win the league
            case [team, 'win', 'the', 'league'] | [team, 'still', 'win', 'the', 'league']:
                # Check the team is in the lookup table
                if team in reverseTeamLookup:
                    # Check whether the team can win the league
                    if table.CanTeamWinTheLeague(reverseTeamLookup[team]):
                        response = 'Yes'
                    else:
                        response = 'No'
                else:
                    # Standard response
                    response = "Don't ask stupid questions"
            case _:
                # Standard response
                response = "Don't ask stupid questions"

        # Log and send the response
        print(response)
        update.message.reply_text(response)

    def MatchUpdateHandler(self, context: CallbackContext) -> None:
        # Call get matches, this allows the function to be called directly
        self.GetMatches()

    def GetMatches(self) -> None:
        # Log that we are updating today's matches
        print('Updating matches')

        # Get today's matches for the teams in the list
        self.todaysMatches = self.footy.GetMatches()

        # If the download was successful, print the matches
        if self.todaysMatches is not None:
            # Iterate over the matches
            for match in self.todaysMatches:
                print(match)

                # Get a random time offset between 0 and 30 seconds to ensure
                # the easy win and empty seats messages don't appear all at once
                timeOffsetSeconds = random.randint(0, 30)

                # Set the context to the supported team name if My Team is not playing, otherwise set it to the opposition
                teamContext=match.teamName

                # If the match is in the future
                if (match.matchDate - timedelta(minutes=5)) > datetime.now(ZoneInfo('UTC')):
                    # Add a job to send a message that this should be an easy game 5 minutes before the game starts
                    self.jq.run_once(self.SendEasyWin, match.matchDate - timedelta(minutes=5, seconds=-timeOffsetSeconds), context=teamContext)

                # Add a job to check the scores once the game starts
                matchContext = match
                runTime = match.matchDate if match.matchDate > datetime.now(ZoneInfo('UTC')) else 0
                self.jq.run_once(self.SendScoreUpdates, runTime, context=matchContext)

                if (match.matchDate + timedelta(minutes=5)) > datetime.now(ZoneInfo('UTC')):
                    # If this is a home game for one of the teams we're interested in, add the empty seats message
                    if match.homeTeam in supportedTeamMapping:
                        # Add a job to send the empty seats message 5 minutes after the game starts
                        self.jq.run_once(self.SendEmptySeats, match.matchDate + timedelta(minutes=5, seconds=timeOffsetSeconds), context=teamContext)
        else:
            print('Download Failed')

    def SendMessage(self, bot: Bot, message: Optional[str]):
        if message is not None:
            for chatId in self.chatIdList:
                bot.send_message(chat_id=chatId, text=message)
            print(message)
        else:
            print('No Status Change')

    def SendScoreUpdates(self, context: CallbackContext) -> None:
        if context.job is not None and isinstance(context.job.context, Match):
            oldMatchData: Match = context.job.context
            newMatchData: Optional[Match] = self.footy.GetMatch(oldMatchData)

            if newMatchData is not None:
                # Get the dict details of the team we're sending a message about
                teamDict = allTeams[newMatchData.teamName]

                message = None

                # Check if this is the start of the match
                if newMatchData.matchChanges.fullTime:
                    if newMatchData.matchChanges.teamWon:
                        message = newMatchData.bantzStrings.teamWon[random.randint(0, len(newMatchData.bantzStrings.teamWon ) - 1)].format(**teamDict)
                    if newMatchData.matchChanges.teamLost:
                        message = newMatchData.bantzStrings.teamLost[random.randint(0, len(newMatchData.bantzStrings.teamLost ) - 1)].format(**teamDict)
                    if newMatchData.matchChanges.teamDrew:
                        message = newMatchData.bantzStrings.teamDrew[random.randint(0, len(newMatchData.bantzStrings.teamDrew ) - 1)].format(**teamDict)
                else:
                    if newMatchData.matchChanges.firstHalfStarted:
                        message = newMatchData.bantzStrings.teamMatchStarted[random.randint(0, len(newMatchData.bantzStrings.teamMatchStarted ) - 1)].format(**teamDict)
                    elif newMatchData.matchChanges.goalScored:
                        # Check for a goal
                        match newMatchData.matchState:
                            case Drawing():
                                message = newMatchData.bantzStrings.drawing[random.randint(0, len(newMatchData.bantzStrings.drawing) - 1)].format(**teamDict)
                            case TeamLeadByOne():
                                message = newMatchData.bantzStrings.teamLeadByOne[random.randint(0, len(newMatchData.bantzStrings.teamLeadByOne) - 1)].format(**teamDict)
                            case TeamExtendingLead():
                                message = newMatchData.bantzStrings.teamExtendingLead[random.randint(0, len(newMatchData.bantzStrings.teamExtendingLead) - 1)].format(**teamDict)
                            case TeamLosingLead():
                                message = newMatchData.bantzStrings.teamLosingLead[random.randint(0, len(newMatchData.bantzStrings.teamLosingLead) - 1)].format(**teamDict)
                            case TeamDeficitOfOne():
                                message = newMatchData.bantzStrings.teamDeficitOfOne[random.randint(0, len(newMatchData.bantzStrings.teamDeficitOfOne) - 1)].format(**teamDict)
                            case TeamExtendingDeficit():
                                message = newMatchData.bantzStrings.teamExtendingDeficit[random.randint(0, len(newMatchData.bantzStrings.teamExtendingDeficit) - 1)].format(**teamDict)
                            case TeamLosingDeficit():
                                message = newMatchData.bantzStrings.teamLosingDeficit[random.randint(0, len(newMatchData.bantzStrings.teamLosingDeficit) - 1)].format(**teamDict)

                    # Add a job to check the scores again in 20 seconds
                    self.jq.run_once(self.SendScoreUpdates, 20, context=newMatchData)

                # If there is a message, add the scoreline
                if message is not None:
                    message = f'{message}'

                self.SendMessage(context.bot, message)
            else:
                # This update failed, try again in 20 seconds using the old match data as the context
                self.jq.run_once(self.SendScoreUpdates, 20, context=oldMatchData)
        else:
            return

    def SendEmptySeats(self, context: CallbackContext) -> None:
        if  context.job is not None and isinstance(context.job.context, str):
            # Get the full team name
            team = context.job.context

            # Get the ground for this tean
            ground = allTeams[team]['ground'] if team in allTeams else None

            if ground is not None:
                # Send the message
                self.SendMessage(context.bot, f'Plenty of empty seats at {ground}')

    def SendEasyWin(self, context: CallbackContext) -> None:
        if  context.job is not None and isinstance(context.job.context, str):
            # Get the full name for this team
            team = context.job.context

            # Get the shorter name for this team
            teamName = allTeams[team]['team'] if team in allTeams else team

            # Send easy win if not supported, tough game if supported
            if team in supportedTeamMapping:
                # Send the message
                self.SendMessage(context.bot, f'Should be an easy win for {teamName}')
            else:
                # Send the message
                self.SendMessage(context.bot, f'{teamName} will probably lose today')

    # Log errors
    def error(self, update, context: CallbackContext) -> None:
        self.logger.warning('Update "%s" caused error "%s"', update, context.error)

# Main function
def main() -> None:
    # Filter out a warning from dateparser
    warnings.filterwarnings('ignore', message='The localize method is no longer necessary')

    # Start the score bot
    ScoreBot()

if __name__ == '__main__':
    # Call the main function
    main()
