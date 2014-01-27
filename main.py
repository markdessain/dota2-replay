
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from cStringIO import StringIO

from dota2py import messages
from dota2py.parser import Reader
from dota2py.summary import DemoSummary
from dota2py.proto.demo_pb2 import CDemoFileInfo
from dota2py.parser import DemoParser, GameEvent, PlayerInfo
from dota2py.proto.netmessages_pb2 import CSVCMsg_UserMessage, CNETMsg_Tick
from dota2py.proto.usermessages_pb2 import CUserMsg_SayText2, CUserMsg_TextMsg
from dota2py.proto.dota_usermessages_pb2 import CHAT_MESSAGE_TOWER_KILL, CDOTAUserMsg_ChatEvent


class Parser(DemoParser):
    # HACK: dota2py is giving an error:
    # - IndexError: Unknown user message cmd: 106 
    def parse_user_message(self, message):
        cmd = message.msg_type

        if cmd not in messages.COMBINED_USER_MESSAGE_TYPES:
            pass # If the cmd is unknown just skip over it and ignore
        else:
            reader = Reader(StringIO(message.msg_data))
            message_type = messages.COMBINED_USER_MESSAGE_TYPES[cmd]
            user_message = reader.read_message(message_type, read_size=False)

            self.run_hooks(user_message)

            self.info("|-----> %s" % (message_type, ))
            self.debug(user_message)


class Team(object):
    def __init__(self, name, color):
        self.name = name
        self.color = color
        self.players = []
        self.towerKills = []

    def getPlayerKills(self):
        return sorted(sum([p.kills for p in self.players], []), key=lambda k: k['tick'])

    def getTowerKills(self):
        return sorted(self.towerKills, key=lambda k: k['tick'])


class Player(object):
    def __init__(self, steamId, name, hero, team):
        self.steamId = steamId
        self.name = name
        self.hero = hero
        self.team = team
        self.kills = []
        self.deaths = []

    def killed(self, otherPlayer, tick):
        event = {
            'tick': tick,
            'source': self,
            'target': otherPlayer
        }
        self.kills.append(event)

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name


class Summary(object):

    def __init__(self, demoPath, verbosity=1, frames=None):
        self.parser = Parser(
            demoPath, 
            verbosity=verbosity,
            frames=frames, 
            hooks={
                GameEvent: self.parse_game_event,
                CDemoFileInfo: self.parse_file_info,
                CNETMsg_Tick: self.handle_tick,
                CDOTAUserMsg_ChatEvent: self.chat_event
            }
        )
        self.gameKills = []
        self.towerKills = []
        self.teams = [Team('Radiant', 'r'), Team('Dire', 'b')]
        self.tick = 0

    def getPlayerForHero(self, hero):
        for team in self.teams:
            for player in team.players:
                if player.hero == hero:
                    return player

    def parse(self):
        self.parser.parse()
        self.finish()

    def finish(self):
        for kill in self.gameKills:
            killer = self.getPlayerForHero(kill.get('source'))
            victim = self.getPlayerForHero(kill.get('target'))
            if killer and victim:
                killer.killed(victim, kill.get('tick'))

    def chat_event(self, message):
        if message.type == CHAT_MESSAGE_TOWER_KILL:
            self.teams[message.value - 2].towerKills.append({"tick": self.tick})

    def handle_tick(self, event):
        self.tick = event.tick

    def parse_file_info(self, file_info):
        for index, player in enumerate(file_info.game_info.dota.player_info):
            team = self.teams[0 if index < 5 else 1]
            team.players.append(Player('guid', player.player_name, player.hero_name, team))

    def parse_game_event(self, ge):
        if ge.name == "dota_combatlog" and ge.keys["type"] == 4:

            source = self.parser.combat_log_names.get(ge.keys["sourcename"], "unknown")
            target = self.parser.combat_log_names.get(ge.keys["targetname"], "unknown")
            target_illusion = ge.keys["targetillusion"]
            tick = self.tick

            if target.startswith("npc_dota_hero") and not target_illusion:
                self.gameKills.append({
                    "target": target,
                    "source": source,
                    "tick": tick,
                })

    def plot(self):
        gs = gridspec.GridSpec(2, 1, height_ratios=[10, 1]) 
        ax0 = plt.subplot(gs[0])
        ax0.set_ylabel('Total Player Kills')
        ax1 = plt.subplot(gs[1], sharex=ax0)
        ax1.set_xlabel('Time (Minutes)')
        ax1.set_ylabel('Tower Kills')
        ax1.get_yaxis().set_ticks([])

        for team in self.teams:
            playerKillsCount = range(1, len(team.getPlayerKills())+1)
            playerKillsTime = [k.get('tick') / 1800.0 for k in team.getPlayerKills()]
            ax0.plot(playerKillsTime, playerKillsCount, '%s' % team.color, label="Team %s" % team.name)

            towerKillsLine = [22] * len(team.getTowerKills())
            towerKillsTime = [k.get('tick') / 1800.0 for k in team.getTowerKills()]
            ax1.plot(towerKillsTime, towerKillsLine, '%ss' % team.color)

        ax0.legend(loc='upper center', shadow=True)
        plt.show()


def main():
    import argparse
    p = argparse.ArgumentParser(description="Dota 2 demo parser")
    p.add_argument('demo', help="The .dem file to parse")
    p.add_argument("--verbosity", dest="verbosity", default=3, type=int, help="how verbose [1-5] (optional)")
    p.add_argument("--frames", dest="frames", default=None, type=int, help="maximum number of frames to parse (optional)")
    args = p.parse_args()

    s = Summary(args.demo, verbosity=1, frames=None)
    s.parse()
    s.plot()


if __name__ == "__main__":
    main()

    