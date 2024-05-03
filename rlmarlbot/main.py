from rlsdk_python import RLSDK, EventTypes, GameEvent, PRI, Ball, Car, PROCESS_NAME
from rlsdk_python.events import EventPlayerTick, EventRoundActiveStateChanged
from nexto.bot import Nexto
from seer.bot import Seer
from necto.bot import Necto
from element.bot import Element
from rlbot.utils.structures.game_data_struct import (
    BallInfo,
    Vector3,
    Rotator,
    FieldInfoPacket,
    BoostPad,
    GoalInfo,
    GameTickPacket,
    Physics,
    GameInfo,
    TileInfo,
    TeamInfo,
    PlayerInfo,
    BoostPadState,
)
import sys
import time
from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from prompt_toolkit import prompt
import struct
from threading import Event
from memory_writer import memory_writer
from colorama import Fore, Back, Style, just_fix_windows_console
import json
from rlmarlbot.map import MiniMap
from threading import Thread
import signal
from helpers import (
    serialize_to_json,
    clear_screen,
)
import argparse
from art import *
import math
import os
from rlgym_compat import GameState
import numpy as np
from element.sequences.speedflip import Speedflip

VERSION = "1.5.4"


class RLMarlbot:

    def __init__(
        self, pid=None, bot=None,  minimap=True, monitoring=False
    ):
        just_fix_windows_console()

        tprint("RLMarlbot")

        print(Fore.LIGHTMAGENTA_EX + "RLMarlbot v" + VERSION + Style.RESET_ALL)
        print(Fore.WHITE + "Run with --help for command line options" + Style.RESET_ALL)
        print(
            Fore.LIGHTYELLOW_EX
            + "Please, give me a star on GitHub: https://github.com/MarlBurroW/RLMarlbot, this work takes a lot of time and effort"
            + Style.RESET_ALL
        )

        self.pid = pid
      
        self.minimap = minimap
        self.monitoring = monitoring
        self.config = {"bot_toggle_key": "F1", "dump_game_tick_packet_key": "F2"}

        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                self.config["bot_toggle_key"] = config.get("bot_toggle_key", "F1")
                self.config["dump_game_tick_packet_key"] = config.get(
                    "dump_game_tick_packet_key", "F2"
                )

        except Exception as e:

            print(
                Fore.RED
                + "No config.json found, writing default config"
                + Style.RESET_ALL
            )
            with open("config.json", "w") as f:
                json.dump(self.config, f, indent=4)
                print(
                    Fore.LIGHTGREEN_EX
                    + "Default config written to config.json"
                    + Style.RESET_ALL
                )
            pass

        print(
            Fore.LIGHTYELLOW_EX
            + "You can change the settings in config.json"
            + Style.RESET_ALL
        )
        print(
            Fore.CYAN
            + "For keys binding, you can find values here: https://nerivec.github.io/old-ue4-wiki/pages/list-of-keygamepad-input-names.html"
            + Style.RESET_ALL
        )

        self.bot_to_use = bot or None

        if not self.bot_to_use:

            print(Fore.GREEN + "Select the bot to use:" + Style.RESET_ALL)
            print("1. Nexto")
            print("2. Necto")
            print("3. Seer (old version)")
            print("4. Element")

            answer = prompt("Your choice (1/2/3/4): ")

            if answer == "1":
                self.bot_to_use = "nexto"
            elif answer == "2":
                self.bot_to_use = "necto"
            elif answer == "3":
                self.bot_to_use = "seer"
            elif answer == "4":
                self.bot_to_use = "element"
            else:
                print(Fore.RED + "Invalid bot selected" + Style.RESET_ALL)
                exit()

        self.start()

    def start(self):
        print(Fore.LIGHTBLUE_EX + "Starting SDK..." + Style.RESET_ALL)
        try:
            self.sdk = RLSDK(hook_player_tick=True, pid=self.pid)
        except Exception as e:
            print(Fore.RED + "Failed to start SDK: ", e, Style.RESET_ALL)
            exit()

        if self.minimap:

            self.minimap = MiniMap(sdk=self.sdk)

            # start a new thread for the minimap main loop

            self.minimap_thread = Thread(target=self.minimap.main)
            self.minimap_thread.daemon = True
            self.minimap_thread.start()

        print(Fore.LIGHTBLUE_EX + "Starting memory writer..." + Style.RESET_ALL)

        self.mw = memory_writer.MemoryWriter()

        if self.pid:
            self.mw.open_process_by_id(self.pid)
        else:
            self.mw.open_process(PROCESS_NAME)

        self.write_running = False

        print(Fore.LIGHTGREEN_EX + "Memory writer started" + Style.RESET_ALL)

        print(Fore.LIGHTGREEN_EX + "SDK started" + Style.RESET_ALL)

        self.bot_enabled = False
        self.frame_num = 0
        self.bot = None
        self.field_info = None
        self.last_input = None
        self.input_address = None
        self.last_tick_start_time = None
        self.tick_counter = 0
        self.tick_rate = 0
        self.last_tick_duration = 0

        self.kickoff_seq = None
        self.kickoff_prev_time = 0
        self.kickoff_game_state = GameState = None
        self.kickoff_action = None
        self.kickoff_start_frame_num = 0

        self.round_active = False

        self.sdk.event.subscribe(EventTypes.ON_PLAYER_TICK, self.on_tick)
        self.sdk.event.subscribe(EventTypes.ON_KEY_PRESSED, self.on_key_pressed)
        self.sdk.event.subscribe(
            EventTypes.ON_GAME_EVENT_DESTROYED, self.on_game_event_destroyed
        )
        self.sdk.event.subscribe(
            EventTypes.ON_ROUND_ACTIVE_STATE_CHANGED, self.on_round_active_state_changed
        )

        self.virtual_seconds_elapsed = time.time()

        self.last_game_tick_packet = None

        print(
            Fore.LIGHTYELLOW_EX
            + "Press "
            + self.config["bot_toggle_key"]
            + " during a match to toggle Nexto"
            + Style.RESET_ALL
        )

    def exit(self, signum, frame):
        if self.minimap:
            self.minimap.running = False
            self.minimap_thread.join()
            sys.exit(0)

    ##########################
    ##### EVENT HANDLERS #####
    ##########################

    def on_round_active_state_changed(self, event: EventRoundActiveStateChanged):
        self.round_active = event.is_active
        if not event.is_active:
            self.reset_inputs()

    def on_game_event_destroyed(self, event: GameEvent):
        print(Fore.LIGHTRED_EX + "Game event destroyed" + Style.RESET_ALL)
        self.stop_writing()
        self.reset_virtual_seconds_elapsed()
        self.reset_info()

    def on_tick(self, event: EventPlayerTick):

        # All the instructions in this method are executed at each tick of the game
        # Each frame, we will try to get all required information to be able to reach the end of the method
        # If any data is missing, we silently ignore the error and continue to the next frame to avoid spamming the console with errors
        # The tricky is about the memory writer that evolves in a different thread, so we need to be careful about the memory writer state
        # because if it writes when any data is missing, it will crash the game
        # So we want to stop the memory writer if any data is missing and restart it when all data is available

        # If the bot is not enabled, we don't do anything
        if not self.bot_enabled:
            # writing should not be running at this step, but we stop it just in case
            self.stop_writing()
            return

        # Increment the frame number
        self.frame_num += 1

        # Get the game event from the SDK at each tick
        try:
            game_event = self.sdk.get_game_event()
        except:
            self.stop_writing()
            pass

        # If the field info is not generated, we try to generate it
        if not self.field_info and game_event:
            try:
                self.generate_field_info()
            except:
                self.stop_writing()
                pass

        # We only continue if the game event and the field info are available because we need them to instantiate the bot
        if game_event and self.field_info:

            # If the bot is not instantiated, we try to instantiate it
            if not self.bot:
                try:
                    self.instantiate_bot(game_event, self.field_info)
                except:
                    self.stop_writing()
                    pass

            # If the bot is instantiated, we continue
            if self.bot:

                # Monitoring information, only if monitoring is enabled
                if self.monitoring:

                    if not self.last_tick_start_time:
                        self.last_tick_start_time = time.perf_counter()
                    tick_time = time.perf_counter() - self.last_tick_start_time
                    tick_duration = time.perf_counter()

                    # Calculate some monitoring information
                    if tick_time > 1:
                        self.last_tick_start_time = time.perf_counter()
                        self.tick_rate = self.tick_counter
                        self.tick_counter = 0

                    else:
                        self.tick_counter += 1

                # Generate game tick packet
                game_tick_packet = None
                try:
                    game_tick_packet = self.generate_game_tick_packet(game_event)
                    self.last_game_tick_packet = game_tick_packet
                except Exception as e:
                    self.stop_writing()
                    pass

                # Prepare the controller state
                simple_controller_state = None

                # Built-in kickoff handling (disabled for now)

                # if game_tick_packet.game_info.is_kickoff_pause:

                #     # if first frame of kickoff, sleep
                #     if self.kickoff_start_frame_num == 0:
                #         self.reset_kickoff()

                #     simple_controller_state = self.do_kickoff(game_tick_packet)

                # Retrieve the controller state from the bot if game_tick_packet is available
                if not simple_controller_state and game_tick_packet:
                    try:
                        simple_controller_state = self.bot.get_output(game_tick_packet)
                    except Exception as e:
                        self.stop_writing()
                        pass

                # If no controller state is returned, create a default one
                if not simple_controller_state:
                    simple_controller_state = SimpleControllerState()

                # Convert the controller state to a bytearray
                bytearray_input = self.controller_to_input(simple_controller_state)

                try:
                    # Get the local players controllers to write the input
                    local_players = game_event.get_local_players()
                except:
                    self.stop_writing()
                    local_players = []
                    pass

                # Check if there are local players
                if len(local_players) > 0:

                    # Currently only supports one local player so we take the first one
                    player_controller = local_players[0]

                    # Construct the input address by adding an offset
                    input_address = player_controller.address + 0x0990

                    # Write the input to memory

                    self.last_input = bytearray_input
                    self.input_address = input_address

                    # Send new input to the memory writer
                    self.mw.set_memory_data(input_address, bytearray_input)

                    # at this stage, we can start the memory writer thread if it's not running
                    if self.write_running == False:
                        self.start_writing()
                else:
                    self.stop_writing()

                # Next lines are for monitoring purposes only and does not affect the bot

                if self.minimap:
                    self.minimap.set_game_tick_packet(game_tick_packet, self.bot.index)

                if self.monitoring:

                    self.last_tick_duration = time.perf_counter() - tick_duration
                    # show info each 10 frames
                    if self.frame_num % 10 == 0:
                        self.display_monitoring_info(
                            game_tick_packet, simple_controller_state
                        )

    def on_key_pressed(self, event):

        # print("Key pressed: ", event.key, event.type)

        if event.key == self.config["bot_toggle_key"]:

            if event.type == "pressed":
                if self.bot_enabled:
                    self.disable_bot()
                else:
                    self.enable_bot()

        if event.key == self.config["dump_game_tick_packet_key"]:
            if event.type == "pressed":
                if self.last_game_tick_packet:
                    self.dump_packet(self.last_game_tick_packet)

    def on_message(self, message, data):
        print("Message received: ", message)
        print("Data received: ", data)

    #########################
    ##### MEMORY WRITER #####
    #########################

    def start_writing(self):

        self.mw.start()
        self.write_running = True
        print(Fore.LIGHTBLUE_EX + "Memory writer thread started" + Style.RESET_ALL)

    def stop_writing(self):
        if not self.write_running:
            return

        self.write_running = False

        if self.input_address:
            # Reset the input state to avoid handbrake bug
            self.reset_inputs()
            # wait a little to be sure the input is reset
            time.sleep(0.1)

        self.mw.stop()

        print(Fore.LIGHTRED_EX + "Memory writer thread stopped" + Style.RESET_ALL)

    def reset_inputs(self):
        if self.input_address:
            default_input_state = SimpleControllerState()
            bytearray_input = self.controller_to_input(default_input_state)
            self.mw.set_memory_data(self.input_address, bytearray_input)

    ##############################
    ##### VIRTUAL GAME TIMER #####
    ##############################

    def get_virtual_seconds_elapsed(self):
        return time.time() - self.virtual_seconds_elapsed

    def reset_virtual_seconds_elapsed(self):
        self.virtual_seconds_elapsed = time.time()

    #####################################
    ##### RLBOT INTERFACE EMULATION #####
    #####################################

    def generate_game_tick_packet(self, game_event: GameEvent):

        game_tick_packet = GameTickPacket()

        game_info = GameInfo()

        balls = game_event.get_balls()
        ball = None

        if len(balls) > 0:
            ball = balls[0]
            ball_info = BallInfo()

            ball_info.physics.location.x = ball.get_location().get_x()
            ball_info.physics.location.y = ball.get_location().get_y()
            ball_info.physics.location.z = ball.get_location().get_z()

            ball_info.physics.velocity.x = ball.get_velocity().get_x()
            ball_info.physics.velocity.y = ball.get_velocity().get_y()
            ball_info.physics.velocity.z = ball.get_velocity().get_z()

            ball_info.physics.rotation.pitch = ball.get_rotation().get_pitch()
            ball_info.physics.rotation.yaw = ball.get_rotation().get_yaw()
            ball_info.physics.rotation.roll = ball.get_rotation().get_roll()

            ball_info.physics.angular_velocity.x = ball.get_angular_velocity().get_x()
            ball_info.physics.angular_velocity.y = ball.get_angular_velocity().get_y()
            ball_info.physics.angular_velocity.z = ball.get_angular_velocity().get_z()

            game_tick_packet.game_ball = ball_info

        game_info.seconds_elapsed = self.get_virtual_seconds_elapsed()
        game_info.game_time_remaining = game_event.get_time_remaining()
        game_info.game_speed = 1.0
        game_info.is_overtime = game_event.is_overtime()
        # can't use game_event.is_round_active() because of latency
        game_info.is_round_active = self.round_active
        game_info.is_unlimited_time = game_event.is_unlimited_time()
        game_info.is_match_ended = game_event.is_match_ended()
        game_info.world_gravity_z = 1.0
        game_info.is_kickoff_pause = (
            True
            if game_info.is_round_active
            and game_tick_packet.game_ball
            and game_tick_packet.game_ball.physics.location.x == 0
            and game_tick_packet.game_ball.physics.location.y == 0
            else False
        )
        game_info.frame_num = self.frame_num

        game_tick_packet.game_info = game_info

        pris = game_event.get_pris()

        # filter only non spectator pris

        pris = [pri for pri in pris if not pri.is_spectator()]

        game_tick_packet.num_cars = len(pris)

        player_info_array_type = PlayerInfo * 64

        player_info_array = player_info_array_type()

        for i, pri in enumerate(pris):
            player_info = PlayerInfo()

            # If player has no team, he is probably a spectator, so we skip him
            try:
                team_info = pri.get_team_info()
                player_info.team = team_info.get_index()
            except:
                continue

            try:
                car: Car = pri.get_car()
            except:
                car = None

            if car:

                player_info.physics.location.x = car.get_location().get_x()
                player_info.physics.location.y = car.get_location().get_y()
                player_info.physics.location.z = car.get_location().get_z()

                player_info.physics.velocity.x = car.get_velocity().get_x()
                player_info.physics.velocity.y = car.get_velocity().get_y()
                player_info.physics.velocity.z = car.get_velocity().get_z()

                player_info.physics.rotation.pitch = car.get_rotation().get_pitch()
                player_info.physics.rotation.yaw = car.get_rotation().get_yaw()
                player_info.physics.rotation.roll = car.get_rotation().get_roll()

                player_info.physics.angular_velocity.x = (
                    car.get_angular_velocity().get_x()
                )
                player_info.physics.angular_velocity.y = (
                    car.get_angular_velocity().get_y()
                )
                player_info.physics.angular_velocity.z = (
                    car.get_angular_velocity().get_z()
                )

                player_info.has_wheel_contact = car.is_on_ground()
                player_info.is_super_sonic = car.is_supersonic()

                player_info.double_jumped = car.is_double_jumped()
                player_info.jumped = car.is_jumped()

                boost_component = car.get_boost_component()
                try:
                    # round ceil
                    player_info.boost = int(
                        math.ceil(boost_component.get_amount() * 100)
                    )
                except:
                    player_info.boost = 0
            else:
                # at this point, the car is not found, but the player has a team, so this is probably a demolished car
                player_info.is_demolished = True

            player_info.name = pri.get_player_name()

            player_info_array[i] = player_info

        game_tick_packet.game_cars = player_info_array

        teams = game_event.get_teams()

        game_tick_packet.num_teams = len(teams)

        team_info_array_type = TeamInfo * 2

        team_info_array = team_info_array_type()

        for i, team in enumerate(teams):
            team_info = TeamInfo()
            team_info.score = team.get_score()
            team_info.team_index = team.get_index()
            team_info_array[i] = team_info

        game_tick_packet.teams = team_info_array

        boostpads = self.sdk.field.boostpads

        game_tick_packet.num_boost = len(boostpads)

        boostpad_array_type = BoostPadState * 50

        boostpad_array = boostpad_array_type()

        for i, boostpad in enumerate(boostpads):
            boostpad_state = BoostPadState()
            boostpad_state.is_active = boostpad.is_active

            if not boostpad.is_active:
                boostpad_state.timer = boostpad.get_elapsed_time()
            else:
                boostpad_state.timer = 0
            boostpad_array[i] = boostpad_state

        game_tick_packet.game_boosts = boostpad_array

        return game_tick_packet

    def generate_field_info(self):
        self.field_info = self.get_field_info()

    def get_field_info(self):
        packet = FieldInfoPacket()
        packet.num_boosts = len(self.sdk.field.boostpads)

        # Créer une instance de BoostPad_Array_MAX_BOOSTS
        boostpad_array_type = BoostPad * 50
        boostpad_array = boostpad_array_type()

        # Copier les données dans l'array ctypes
        for i, boostpad in enumerate(self.sdk.field.boostpads):
            boostpad_array[i].location.x = boostpad.location.x
            boostpad_array[i].location.y = boostpad.location.y
            boostpad_array[i].location.z = boostpad.location.z
            boostpad_array[i].is_full_boost = boostpad.is_big

        # Assigner l'array ctypes au champ boost_pads du paquet
        packet.boost_pads = boostpad_array

        game_event = self.sdk.get_game_event()

        goals = game_event.get_goals()
        packet.num_goals = len(goals)

        goal_array_type = GoalInfo * 200
        goal_array = goal_array_type()

        for i, goal in enumerate(goals):

            location = Vector3()
            loc = goal.get_location()
            location.x = loc.get_x()
            location.y = loc.get_y()
            location.z = loc.get_z()

            goal_array[i].location = location

            direction = Vector3()
            dir = goal.get_direction()
            direction.x = dir.get_x()
            direction.y = dir.get_y()
            direction.z = dir.get_z()

            goal_array[i].direction = direction

            goal_array[i].team_num = goal.get_team_num()

            goal_array[i].width = goal.get_width()
            goal_array[i].height = goal.get_height()

        packet.goals = goal_array

        return packet

    ########################
    ##### BOT TOGGLING #####
    ########################

    def enable_bot(self):
        self.frame_num = 0
        self.bot_enabled = True

    def disable_bot(self):

        self.stop_writing()
        self.reset_info()

        if self.minimap:
            self.minimap.disable()
        self.bot_enabled = False
        print(Fore.LIGHTRED_EX + "Bot disabled" + Style.RESET_ALL)

    ##########################
    ######## METHODS #########
    ##########################

    def reset_info(self):
        self.field_info = None
        self.bot = None
        self.last_input = None
        self.input_address = None
        self.last_game_tick_packet = None
        self.frame_num = 0
        self.last_tick_start_time = None
        self.tick_rate = 0
        self.tick_counter = 0
        self.last_tick_duration = 0

    def instantiate_bot(self, game_event: GameEvent, field_info: FieldInfoPacket):

        local_player_controllers = game_event.get_local_players()

        if len(local_player_controllers) == 0:
            raise Exception("No local players found")

        if len(local_player_controllers) > 1:
            raise Exception("Multiple local players not supported")
        player_controller = local_player_controllers[0]

        player_pri = player_controller.get_pri()
        player_name = player_pri.get_player_name()

        if player_pri.is_spectator():
            raise Exception("Player is spectator")

        pris = game_event.get_pris()

        for i, pri in enumerate(pris):
            if pri.address == player_pri.address:
                pri_index = i
                break
        else:
            raise Exception("Player car not found")

        try:
            team_index = player_pri.get_team_info().get_index()
        except:
            raise Exception("Failed to get team index")

        if game_event.is_round_active():
            self.round_active = True

        try:
            if self.bot_to_use == "nexto":
                self.bot = Nexto(player_name, team_index, pri_index)
                self.bot.initialize_agent(self.field_info)
                print(Fore.LIGHTGREEN_EX + "Nexto enabled" + Style.RESET_ALL)
            elif self.bot_to_use == "necto":
                self.bot = Necto(player_name, team_index, pri_index)
                self.bot.initialize_agent(self.field_info)
                print(Fore.LIGHTGREEN_EX + "Necto enabled" + Style.RESET_ALL)
            elif self.bot_to_use == "seer":
                self.bot = Seer(player_name, team_index, pri_index)
                self.bot.initialize_agent()
                print(Fore.LIGHTGREEN_EX + "Seer enabled" + Style.RESET_ALL)
            if self.bot_to_use == "element":
                self.bot = Element(player_name, team_index, pri_index)
                self.bot.initialize_agent(self.field_info)
                print(Fore.LIGHTGREEN_EX + "Element enabled" + Style.RESET_ALL)
        except Exception as e:
            print(Fore.RED + "Failed to instantiate bot: ", e, Style.RESET_ALL)
            self.bot = None

    ##########################
    ##### HELPER METHODS #####
    ##########################

    def controller_to_input(self, controller: SimpleControllerState):
        # convert controller (numpy) to FVehicleInputs bytes representation
        inputs = bytearray(32)

        # Packing the float values
        inputs[0:4] = struct.pack("<f", controller.throttle)
        inputs[4:8] = struct.pack("<f", controller.steer)
        inputs[8:12] = struct.pack("<f", controller.pitch)
        inputs[12:16] = struct.pack("<f", controller.yaw)
        inputs[16:20] = struct.pack("<f", controller.roll)

        # DodgeForward = -pitch
        inputs[20:24] = struct.pack("<f", -controller.pitch)
        # DodgeRight = yaw
        inputs[24:28] = struct.pack("<f", controller.yaw)

        # Rest of the inputs are booleans encoded in a single uint32
        flags = 0
        flags |= controller.handbrake << 0
        flags |= controller.jump << 1
        flags |= controller.boost << 2
        flags |= controller.boost << 3
        flags |= controller.use_item << 4

        # Encode the flags into the last 4 bytes (uint32)
        inputs[28:32] = struct.pack("<I", flags)

        return inputs

    ###################
    ##### ACTIONS #####
    ###################

    def do_kickoff(self, packet) -> SimpleControllerState:

        if not self.kickoff_start_frame_num:
            self.kickoff_start_frame_num = packet.game_info.frame_num

        ticks_elapsed = packet.game_info.frame_num - self.kickoff_start_frame_num

        if not self.kickoff_game_state:
            self.kickoff_game_state = GameState(self.get_field_info())

        self.kickoff_game_state.decode(packet, ticks_elapsed)

        try:
            player = self.kickoff_game_state.players[self.bot.index]

            teammates = [
                p
                for p in self.kickoff_game_state.players
                if p.team_num == self.bot.team
            ]
            closest = min(
                teammates,
                key=lambda p: np.linalg.norm(
                    self.kickoff_game_state.ball.position - p.car_data.position
                ),
            )

            if self.kickoff_seq is None:
                self.kickoff_seq = Speedflip(player)

            if player == closest and self.kickoff_seq.is_valid(
                player, self.kickoff_game_state
            ):

                self.kickoff_action = np.asarray(
                    self.kickoff_seq.get_action(
                        player, self.kickoff_game_state, self.kickoff_action
                    )
                )

                controls = SimpleControllerState()
                controls.throttle = self.kickoff_action[0]
                controls.steer = self.kickoff_action[1]
                controls.pitch = self.kickoff_action[2]
                controls.yaw = (
                    0 if self.kickoff_action[5] > 0 else self.kickoff_action[3]
                )
                controls.roll = self.kickoff_action[4]
                controls.jump = self.kickoff_action[5] > 0
                controls.boost = self.kickoff_action[6] > 0
                controls.handbrake = self.kickoff_action[7] > 0

                return controls
        except Exception as e:
            print(Fore.RED + "Failed to do kickoff: ", e, Style.RESET_ALL)
            return None

    def reset_kickoff(self):
        self.kickoff_seq = None
        self.kickoff_prev_time = 0
        self.kickoff_game_state = None
        self.kickoff_action = None
        self.kickoff_start_frame_num = 0

    ########################
    ##### MONITORING ######
    ########################

    def display_monitoring_info(self, game_tick_packet, controller):

        # clear the console
        print("\033[H\033[J")
        term_width = os.get_terminal_size().columns

        def create_centered_title(title, style, back=Back.LIGHTBLACK_EX):
            return back + Fore.WHITE + title.center(term_width) + Style.RESET_ALL

        print(create_centered_title("BOT LIVE MONITORING", Fore.LIGHTYELLOW_EX))
        print(
            Fore.LIGHTCYAN_EX
            + "Tick rate: "
            + Fore.LIGHTGREEN_EX
            + str(self.tick_rate)
            + " ticks/s"
            + Style.RESET_ALL
        )
        # Tick computation time
        print(
            Fore.LIGHTCYAN_EX
            + "Tick processing time: "
            + Fore.LIGHTGREEN_EX
            + str(round(self.last_tick_duration * 1000, 2))
            + " ms"
            + Style.RESET_ALL
        )
        # Frane number
        print(
            Fore.LIGHTCYAN_EX
            + "Frame number: "
            + Fore.LIGHTGREEN_EX
            + str(game_tick_packet.game_info.frame_num)
            + Style.RESET_ALL
        )
        # elapsed time
        print(
            Fore.LIGHTCYAN_EX
            + "Elapsed time: "
            + Fore.LIGHTGREEN_EX
            + str(round(game_tick_packet.game_info.seconds_elapsed, 2))
            + " s"
            + Style.RESET_ALL
        )
        # Game time remaining
        print(
            Fore.LIGHTCYAN_EX
            + "Game time remaining: "
            + Fore.LIGHTGREEN_EX
            + str(round(game_tick_packet.game_info.game_time_remaining, 2))
            + " s"
            + Style.RESET_ALL
        )
        print(create_centered_title("GAMEINFO STATE", Fore.WHITE))

        # is_round_active
        game_state = ""

        game_state = (
            Style.BRIGHT
            + Fore.LIGHTWHITE_EX
            + Back.GREEN
            + "ROUND ACTIVE"
            + Style.RESET_ALL
            if game_tick_packet.game_info.is_round_active
            else Back.BLACK + "ROUND ACTIVE" + Style.RESET_ALL
        )
        game_state += " - "
        game_state += (
            Style.BRIGHT
            + Fore.LIGHTWHITE_EX
            + Back.GREEN
            + "OVERTIME"
            + Style.RESET_ALL
            if game_tick_packet.game_info.is_overtime
            else Back.BLACK + "OVERTIME" + Style.RESET_ALL
        )
        game_state += " - "
        game_state += (
            Style.BRIGHT
            + Fore.LIGHTWHITE_EX
            + Back.GREEN
            + "MATCH ENDED"
            + Style.RESET_ALL
            if game_tick_packet.game_info.is_match_ended
            else Back.BLACK + "MATCH ENDED" + Style.RESET_ALL
        )
        game_state += " - "
        game_state += (
            Style.BRIGHT
            + Fore.LIGHTWHITE_EX
            + Back.GREEN
            + "KICKOFF PAUSE"
            + Style.RESET_ALL
            if game_tick_packet.game_info.is_kickoff_pause
            else Back.BLACK + "KICKOFF PAUSE" + Style.RESET_ALL
        )

        print(game_state)
        print(create_centered_title("BOOSTPADS STATE", Fore.WHITE))

        # Display boost pads (o = small boost, O = big boost, green = active, red = inactive)
        boost_pads = self.sdk.field.boostpads
        boost_pads_str = ""
        for i in range(game_tick_packet.num_boost):
            if boost_pads[i].is_active:
                if boost_pads[i].is_big:
                    boost_pads_str += Fore.GREEN + " ⬤ " + Style.RESET_ALL
                else:
                    boost_pads_str += Fore.GREEN + " ● " + Style.RESET_ALL
            else:
                if boost_pads[i].is_big:
                    boost_pads_str += Fore.RED + " ◯ " + Style.RESET_ALL
                else:
                    boost_pads_str += Fore.RED + " ○ " + Style.RESET_ALL

        print(boost_pads_str)

        print(create_centered_title("PLAYERS STATE", Fore.WHITE))
        players = game_tick_packet.game_cars

        for i in range(game_tick_packet.num_cars):
            # 0 = blue, 1 = red
            color = Fore.BLUE if players[i].team == 0 else Fore.LIGHTYELLOW_EX

            player_state = ""
            player_state += (
                Style.BRIGHT
                + Fore.LIGHTWHITE_EX
                + Back.GREEN
                + "JUMPED"
                + Style.RESET_ALL
                if players[i].jumped
                else Back.BLACK + "JUMPED" + Style.RESET_ALL
            )
            player_state += " - "
            player_state += (
                Style.BRIGHT
                + Fore.LIGHTWHITE_EX
                + Back.GREEN
                + "DOUBLE JUMPED"
                + Style.RESET_ALL
                if players[i].double_jumped
                else Back.BLACK + "DOUBLE JUMPED" + Style.RESET_ALL
            )
            player_state += " - "
            player_state += (
                Style.BRIGHT
                + Fore.LIGHTWHITE_EX
                + Back.GREEN
                + "SUPERSONIC"
                + Style.RESET_ALL
                if players[i].is_super_sonic
                else Back.BLACK + "SUPERSONIC" + Style.RESET_ALL
            )
            player_state += " - "
            player_state += (
                Style.BRIGHT
                + Fore.LIGHTWHITE_EX
                + Back.GREEN
                + "WHEELS ON GROUND"
                + Style.RESET_ALL
                if players[i].has_wheel_contact
                else Back.BLACK + "WHEELS ON GROUND" + Style.RESET_ALL
            )
            player_state += " - "
            player_state += (
                Style.BRIGHT
                + Fore.LIGHTWHITE_EX
                + Back.GREEN
                + "DEMOLISHED"
                + Style.RESET_ALL
                if players[i].is_demolished
                else Back.BLACK + "DEMOLISHED" + Style.RESET_ALL
            )

            boost = players[i].boost
            # pad the boost with leading space (3 digits)
            boost_str = " " * (3 - len(str(boost))) + str(boost)

            # color the boost based on the amount
            if boost < 33:
                boost_str = Fore.RED + boost_str + Style.RESET_ALL
            elif boost >= 33 and boost < 66:
                boost_str = Fore.LIGHTYELLOW_EX + boost_str + Style.RESET_ALL
            else:
                boost_str = Fore.GREEN + boost_str + Style.RESET_ALL

            player_state += " - Boost: " + boost_str

            # pad the player name with spaces

            player_name = players[i].name + " " * (20 - len(players[i].name))

            print(
                color
                + player_name
                + Back.RESET
                + Fore.RESET
                + " "
                + player_state
                + Style.RESET_ALL
            )

        print(create_centered_title("INPUTS STATE", Fore.WHITE))
        print(
            Fore.BLUE
            + "Throttle: "
            + Fore.GREEN
            + str(controller.throttle)
            + Style.RESET_ALL
        )
        print(
            Fore.BLUE + "Steer: " + Fore.GREEN + str(controller.steer) + Style.RESET_ALL
        )
        print(
            Fore.BLUE + "Pitch: " + Fore.GREEN + str(controller.pitch) + Style.RESET_ALL
        )
        print(Fore.BLUE + "Yaw: " + Fore.GREEN + str(controller.yaw) + Style.RESET_ALL)
        print(
            Fore.BLUE + "Roll: " + Fore.GREEN + str(controller.roll) + Style.RESET_ALL
        )
        print(
            Fore.BLUE + "Jump: " + Fore.GREEN + str(controller.jump) + Style.RESET_ALL
        )
        print(
            Fore.BLUE + "Boost: " + Fore.GREEN + str(controller.boost) + Style.RESET_ALL
        )
        print(
            Fore.BLUE
            + "Handbrake: "
            + Fore.GREEN
            + str(controller.handbrake)
            + Style.RESET_ALL
        )

    def dump_packet(self, game_tick_packet):
        json_packet = serialize_to_json(game_tick_packet)
        frame_num = game_tick_packet.game_info.frame_num
        with open("game_tick_packet_" + str(frame_num) + ".json", "w") as f:
            f.write(json_packet)
        print(
            Fore.LIGHTGREEN_EX
            + "Game tick packet dumped to game_tick_packet_"
            + str(frame_num)
            + ".json"
            + Style.RESET_ALL
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RLMarlbot")
    parser.add_argument("-p", "--pid", type=int, help="Rocket League process ID")
    parser.add_argument(
        "-b", "--bot", type=str, help="Bot to use (nexto, necto, seer, element)"
    )

    # Disable minimap
    parser.add_argument("--minimap", action="store_true", help="Enable minimap")
    parser.add_argument("--monitoring", action="store_true", help="Enable monitoring")

    args = parser.parse_args()

    bot = RLMarlbot(
        pid=args.pid,
        bot=args.bot,
        minimap=args.minimap,
        monitoring=args.monitoring,
    )

    signal.signal(signal.SIGINT, bot.exit)

    try:
        sys.stdin.read()
    except KeyboardInterrupt:
        bot.minimap_thread.join()
        sys.exit(0)
