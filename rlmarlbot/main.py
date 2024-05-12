import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
from rlsdk_python import RLSDK, EventTypes, GameEvent, PRI, Ball, Car, PROCESS_NAME
from rlsdk_python.events import EventPlayerTick, EventRoundActiveStateChanged
from nexto.bot import Nexto
from seer.bot import Seer
from necto.bot import Necto
from element.bot import Element
from immortal.bot import Immortal
from rlbot.utils.structures.game_data_struct import (
    BallInfo,
    Vector3,
    FieldInfoPacket,
    BoostPad,
    GoalInfo,
    GameTickPacket,
    GameInfo,
    TeamInfo,
    PlayerInfo,
    BoostPadState,
)
import sys
import time
from rlbot.agents.base_agent import SimpleControllerState
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
import warnings
warnings.simplefilter('default') 
import traceback

VERSION = "1.6.1-dev1"


class RLMarlbot:

    def __init__(
        self,
        pid=None,
        bot=None,
        minimap=True,
        monitoring=False,
        debug_keys=None,
        built_in_kickoff=False,
        clock=False,
        debug=False,
        nexto_beta=1.0,
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
        self.debug_keys = debug_keys
        self.built_in_kickoff = built_in_kickoff
        self.clock = clock
        self.debug = debug
        self.nexto_beta = nexto_beta

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
            print("5. Immortal (Air dribble bot)")

            answer = prompt("Your choice (1/2/3/4/5): ")

            if answer == "1":
                self.bot_to_use = "nexto"
            elif answer == "2":
                self.bot_to_use = "necto"
            elif answer == "3":
                self.bot_to_use = "seer"
            elif answer == "4":
                self.bot_to_use = "element"
            elif answer == "5":
                self.bot_to_use = "immortal"
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

        print(Fore.LIGHTBLUE_EX + "Instanciating memory writer..." + Style.RESET_ALL)

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
        
        self.last_input = None
        self.input_address = None
        self.last_tick_start_time = None
        self.tick_counter = 0
        self.tick_rate = 0
        self.last_tick_duration = 0
        self.tick_durations = []
        self.average_duration = 0
        
        
        # Cache some data to avoid calling the SDK too often
        
        self.field_info = None
        self.game_event = None
        self.local_player = None
        self.local_pri = None
        self.local_player_controller = None
        self.local_car = None
        self.local_car_index = None
        self.local_team = None
        self.local_team_index = None
        self.local_player_name = None
        self.ball = None
        self.cars = None

        # KICKOPFF MEMBERS

        self.kickoff_seq = None
        self.kickoff_prev_time = 0
        self.kickoff_game_state = GameState = None
        self.kickoff_action = None
        self.kickoff_start_frame_num = 0

        
        # CLOCK
        self.clock_thread = None
        

        self.round_active = False
        
        if not self.clock:
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
        
        
        if self.clock:
            self.start_clock()
            print(Fore.LIGHTYELLOW_EX + "Python based clock started" + Style.RESET_ALL)

        print(
            Fore.LIGHTYELLOW_EX
            + "Press "
            + self.config["bot_toggle_key"]
            + " during a match to toggle the bot"
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
        if self.debug:
            print(Fore.LIGHTRED_EX + "Game event destroyed" + Style.RESET_ALL)
        self.stop_writing()
        self.reset_info()
        self.reset_virtual_seconds_elapsed()
        self.clear_cache()

    def on_tick(self, event: EventPlayerTick):



        # If the bot is not enabled, we don't do anything
        
        
        if not self.bot_enabled:

            # writing should not be running at this step, but we stop it just in case
            self.stop_writing()
            self.reset_info()
            self.clear_cache()
            return
        

    
        # Increment the frame number
        self.frame_num += 1
        
        self.debug_info(f"New tick Frame number: {self.frame_num}")

        # Init mtick onitoring information, only if monitoring is enabled ofc
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
                
        try:       
                    
            if not self.game_event:
                self.debug_info("No game event found, trying to get one")
                self.game_event = self.sdk.get_game_event()
                self.round_active = self.game_event.is_round_active()
                
            # If the field info is not generated, we try to generate it
            
            if not self.field_info and self.game_event:
                self.debug_info("No field info found, trying to generate it")
                self.generate_field_info()

            # Get the main PRI to know on which player the bot is running
            
            if not self.local_player_controller:
                self.debug_info("No local player controller found, trying to get one")
            
                local_player_controllers = self.game_event.get_local_players()

                if len(local_player_controllers) == 0:
                    raise Exception("No local players found")

                if len(local_player_controllers) > 1:
                    raise Exception("Multiple local players not supported")
                
                self.local_player_controller = local_player_controllers[0]

            
            if not self.local_pri:
                self.debug_info("No local PRI found, trying to get one")
                self.local_pri = self.local_player_controller.get_pri()


            if not self.local_car:
                self.debug_info("No local car found, trying to get one")
                self.local_car = self.local_pri.get_car()
                
            if not self.local_player_name:
                self.debug_info("No local player name found, trying to get one")
                self.local_player_name = self.local_pri.get_player_name()
                
                
            if not self.cars:
                self.debug_info("No cars found, trying to get some")
                self.cars = self.game_event.get_cars()
                
            if self.local_car_index is None:
                self.debug_info("No local car index found, trying to get one")
                for i, car in enumerate(self.cars):
                    if car.address == self.local_car.address:
                        self.local_car_index = i
                        break
                else:
                    raise Exception("Player car not found")
                
                
            if not self.local_team:
                self.debug_info("No local team found, trying to get one")
                self.local_team = self.local_pri.get_team_info()
                
            if self.local_team_index is None:
                self.debug_info("No local team index found, trying to get one")
                self.local_team_index = self.local_team.get_index()
                
                            
            if not self.ball:
                self.debug_info("No ball found, trying to get one")
                balls = self.game_event.get_balls()
                if len(balls) == 0:
                    raise Exception("No ball found")
                
                self.ball = balls[0]


            # If the bot is not instantiated, we try to instantiate it
            if not self.bot:
                self.debug_info("No bot found, trying to instantiate one")
                self.bot = self.instantiate_bot(
                    self.bot_to_use,
                    self.field_info, 
                    self.local_player_name, 
                    self.local_team_index, 
                    self.local_car_index
                )
        
            
            # update team index and car index in the current instanciated bot (in case of team change or car change)
            self.bot.team = self.local_team_index
            self.bot.index = self.local_car_index

            # Generate the game tick packet            

            self.debug_info("Generating game tick packet")
            
            game_tick_packet = self.generate_game_tick_packet(
                self.game_event, 
                self.ball, 
                self.cars, 
                self.frame_num, 
                self.get_virtual_seconds_elapsed(), 
                self.sdk.field.boostpads,
                self.round_active
            )
            
            
            
            
            try:
                # Check if this is the end of the match
                if game_tick_packet.game_info.is_match_ended:
                    self.debug_info("Match ended, stopping tick")
                    raise Exception("Match ended")
           

                controller_state = self.generate_bot_input(self.bot, game_tick_packet, self.last_game_tick_packet)
                
                self.debug_info("Bot input generated")
                
                
                self.last_game_tick_packet = game_tick_packet
                
                # Convert the controller state to a bytearray
                bytearray_input = self.controller_to_input(controller_state)
                

                # Construct the input address by adding an offset
                input_address = self.local_player_controller.address + 0x0990

                # Write the input to memory

                self.last_input = bytearray_input
                self.input_address = input_address

                # Send new input to the memory writer
                self.mw.set_memory_data(input_address, bytearray_input)
                
                self.debug_info("Inputs sent to memory writer")

                # at this stage, we can start the memory writer thread if it's not running
                if self.write_running == False:
                    self.start_writing()
                    
                    
            except Exception as e:
                self.debug_exception(e)
                self.clear_cache()
                self.stop_writing()
                raise Exception("Error while writing inputs to memory")
                
            
            
            
                
           # Next lines are for monitoring purposes only and does not affect the bot

            if self.minimap:
                self.minimap.set_game_tick_packet(game_tick_packet, self.local_car_index)

            if self.monitoring:

                self.last_tick_duration = time.perf_counter() - tick_duration
                
                self.tick_durations.append(self.last_tick_duration)
                
                if len(self.tick_durations) > 120:
                    self.tick_durations.pop(0)
                    
                self.average_duration = sum(self.tick_durations) / len(self.tick_durations)
                
                
                # show info each 10 frames
                if self.frame_num % 10 == 0:
                    self.display_monitoring_info(
                        game_tick_packet, controller_state if controller_state else SimpleControllerState()
                    )
    
                
        except Exception as e:
            self.clear_cache()
            self.debug_exception(e)
            




    def on_key_pressed(self, event):

        if self.debug_keys:
            print(
                Fore.LIGHTYELLOW_EX + "Key pressed: ",
                Fore.LIGHTGREEN_EX + event.key,
                Fore.LIGHTYELLOW_EX + "Type: ",
                Fore.LIGHTGREEN_EX + event.type,
                Style.RESET_ALL,
            )

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
        self.debug_info("Memory writer thread started")


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
        
        self.debug_info("Memory writer thread stopped")

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

    def generate_game_tick_packet(self, game_event: GameEvent, ball: Ball, cars: list[Car], frame_num: int, seconds_elapsed: float, boostpads: list[BoostPad], is_round_active: bool) -> GameTickPacket:

        game_tick_packet = GameTickPacket()

        game_info = GameInfo()
        
        # BALL INFO

        ball_info = BallInfo()
        
        ball_location = ball.get_location()
        ball_info.physics.location.x = ball_location.get_x()
        ball_info.physics.location.y = ball_location.get_y()
        ball_info.physics.location.z = ball_location.get_z()
        
        ball_velocity = ball.get_velocity()
        ball_info.physics.velocity.x = ball_velocity.get_x()
        ball_info.physics.velocity.y = ball_velocity.get_y()
        ball_info.physics.velocity.z = ball_velocity.get_z()
        
        
        ball_rotation = ball.get_rotation()
        ball_info.physics.rotation.pitch = ball_rotation.get_pitch()
        ball_info.physics.rotation.yaw = ball_rotation.get_yaw()
        ball_info.physics.rotation.roll = ball_rotation.get_roll()
        
        ball_angular_velocity = ball.get_angular_velocity()
        ball_info.physics.angular_velocity.x = ball_angular_velocity.get_x()
        ball_info.physics.angular_velocity.y = ball_angular_velocity.get_y()
        ball_info.physics.angular_velocity.z = ball_angular_velocity.get_z()

        game_tick_packet.game_ball = ball_info
        
        # GAME INFO

        game_info.seconds_elapsed = seconds_elapsed
        game_info.game_time_remaining = game_event.get_time_remaining()
        game_info.game_speed = 1.0
        game_info.is_overtime = game_event.is_overtime()
        # can't use game_event.is_round_active() because of latency
        game_info.is_round_active = is_round_active
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
        game_info.frame_num = frame_num

        game_tick_packet.game_info = game_info

        player_info_array_type = PlayerInfo * 64

        player_info_array = player_info_array_type()

        player_count = 0

        for i, car in enumerate(cars):
            player_info = PlayerInfo()

            # If player has missing required data, skip to next iteration
            try:
                pri = car.get_pri()
                team_info = pri.get_team_info()
                player_info.team = team_info.get_index()
            except Exception as e:
                self.debug_exception(e)
                raise Exception("Player has missing required data")
            
            
            car_location = car.get_location()
            player_info.physics.location.x = car_location.get_x()
            player_info.physics.location.y = car_location.get_y()
            player_info.physics.location.z = car_location.get_z()

            # if player name is null, show location
            
            car_velocity = car.get_velocity()
            player_info.physics.velocity.x = car_velocity.get_x()
            player_info.physics.velocity.y = car_velocity.get_y()
            player_info.physics.velocity.z = car_velocity.get_z()
            

            car_rotation = car.get_rotation()
            player_info.physics.rotation.pitch = car_rotation.get_pitch()
            player_info.physics.rotation.yaw = car_rotation.get_yaw()
            player_info.physics.rotation.roll = car_rotation.get_roll()
            
            car_angular_velocity = car.get_angular_velocity()
            player_info.physics.angular_velocity.x = car_angular_velocity.get_x()
            player_info.physics.angular_velocity.y = car_angular_velocity.get_y()
            player_info.physics.angular_velocity.z = car_angular_velocity.get_z()

            player_info.has_wheel_contact = car.is_on_ground()
            player_info.is_super_sonic = car.is_supersonic()

            player_info.double_jumped = car.is_double_jumped()
            player_info.jumped = car.is_jumped()

            boost_component = car.get_boost_component()
            
            try:
                player_info.boost = int(round(boost_component.get_amount() * 100))
            except Exception as e:
                self.debug_exception(e)
                player_info.boost = 0

            player_info.name = pri.get_player_name()

            player_info_array[player_count] = player_info
            player_count += 1

        game_tick_packet.num_cars = player_count

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

        print(Fore.LIGHTGREEN_EX + "Bot enabled" + Style.RESET_ALL)

    def disable_bot(self):
        self.reset_inputs()
        self.stop_writing()
        self.reset_info()
        

        if self.minimap:
            self.minimap.disable()
        self.bot_enabled = False
        print(Fore.LIGHTRED_EX + "Bot disabled" + Style.RESET_ALL)

    ##########################
    ######## METHODS #########
    ##########################
    
    
    def clear_cache(self):
        self.field_info = None
        self.game_event = None
        self.local_player = None
        self.local_pri = None
        self.local_player_controller = None
        self.local_car = None
        self.local_car_index = None
        self.local_team = None
        self.local_team_index = None
        self.local_player_name = None
        self.ball = None
        self.cars = None
        self.last_game_tick_packet = None
    
    
    

    def reset_info(self):
        self.clear_cache()
        self.bot = None
        self.last_input = None
        self.input_address = None
        self.last_game_tick_packet = None
        self.frame_num = 0
        self.last_tick_start_time = None
        self.tick_rate = 0
        self.tick_counter = 0
        self.last_tick_duration = 0
        self.tick_durations = []
        self.average_duration = 0

    def instantiate_bot(
        self,
        bot_to_use,
        field_info: FieldInfoPacket,
        player_name,
        team_index,
        car_index,
    ):

 
        if bot_to_use == "nexto":
            bot = Nexto(player_name, team_index, car_index, beta=self.nexto_beta)
            bot.initialize_agent(field_info)
            print(Fore.LIGHTGREEN_EX + "Nexto agent created" + Style.RESET_ALL)
            return bot
        elif bot_to_use == "necto":
            bot = Necto(player_name, team_index, car_index)
            bot.initialize_agent(field_info)
            print(Fore.LIGHTGREEN_EX + "Necto agent created" + Style.RESET_ALL)
            return bot
        elif bot_to_use == "seer":
            bot = Seer(player_name, team_index, car_index)
            bot.initialize_agent()
            print(Fore.LIGHTGREEN_EX + "Seer agent created" + Style.RESET_ALL)
            return bot
        if bot_to_use == "element":
            bot = Element(player_name, team_index, car_index)
            bot.initialize_agent(field_info)
            print(Fore.LIGHTGREEN_EX + "Element agent created" + Style.RESET_ALL)
            return bot
        if bot_to_use == "immortal":
            bot = Immortal(player_name, team_index, car_index)
            bot.initialize_agent(field_info)
            print(Fore.LIGHTGREEN_EX + "Immortal agent created" + Style.RESET_ALL)
            return bot


            
    def start_clock(self):
        
        self.clock_thread = Thread(target=self.clock_loop)
        self.clock_thread.daemon = True
        self.clock_thread.start()
        
    def stop_clock(self):
        self.clock_thread.join()
        
        
    def clock_loop(self):
        target_interval = 1 / 120  # intervalle cible en secondes
        next_time = time.time() + target_interval

        while True:
            self.on_tick(None)
            now = time.time()
            sleep_time = next_time - now  # Calcul du temps jusqu'au prochain tick prévu

            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                # Si on_tick a pris plus de temps que prévu, ajuste le prochain tick
                # pour ne pas dormir mais aussi pour recalculer le moment du prochain tick
                next_time = now
            
            next_time += target_interval  # Prévoit le prochain tick
            
     
     
     
    def generate_bot_input(self, bot, game_tick_packet, last_game_tick_packet) -> SimpleControllerState:       
            
        # compare with the previous game_tick_packet to create some needed data
        starting_kickoff = False
        
        if last_game_tick_packet:
            if (
                not game_tick_packet.game_info.is_kickoff_pause
                and last_game_tick_packet.game_info.is_kickoff_pause
            ):
                starting_kickoff = True
                # starting_kickoff is True the first frame of kickoff

        # if starting_kickoff is True, we reset the kickoff sequence to be sure to start a new one
        if starting_kickoff:
            self.reset_kickoff()

        # Prepare the controller state
        simple_controller_state = None



        # Built-in kickoff handling

        if (
            self.built_in_kickoff
            and game_tick_packet.game_info.is_kickoff_pause
        ):

            simple_controller_state = self.do_kickoff(game_tick_packet)

        # Retrieve the controller state from the bot if game_tick_packet is available
        if not simple_controller_state and game_tick_packet:
            simple_controller_state = bot.get_output(game_tick_packet)
     
        return  simple_controller_state or SimpleControllerState()
     

            
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
    
    def debug_info(self, message):
        if self.debug:
            print(Fore.LIGHTYELLOW_EX + '[DEBUG] ' + message + Style.RESET_ALL)
    
    
    def debug_exception(self, e):
        if not self.debug:
            return
        # Display the exception message, file and line number
        print(Fore.RED + "Exception: ", e, Style.RESET_ALL)
        print(Fore.RED + "File: ", e.__traceback__.tb_frame.f_code.co_filename, Style.RESET_ALL)
        print(Fore.RED + "Line: ", e.__traceback__.tb_lineno, Style.RESET_ALL)
        
        # show 3 last lines of the traceback
        
        traceback.print_tb(e.__traceback__)
    

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
        
        print(
            Fore.LIGHTCYAN_EX
            + "Average (last 120 ticks): "
            + Fore.LIGHTGREEN_EX
            + str(round(self.average_duration * 1000, 2))
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
            
            
            
        # print(create_centered_title("BALL STATE", Fore.WHITE))
        
        # print(
        #     Fore.BLUE
        #     + "Location: "
        #     + " X: "
        #     + Fore.GREEN
        #     + str(game_tick_packet.game_ball.physics.location.x)
        #     + " Y: "
        #     + str(game_tick_packet.game_ball.physics.location.y)
        #     + " Z: "
        #     + str(game_tick_packet.game_ball.physics.location.z)
        #     + Style.RESET_ALL
        # )
        
        # print(
        #     Fore.BLUE
        #     + "Velocity: "
        #     + " X: "
        #     + Fore.GREEN
        #     + str(game_tick_packet.game_ball.physics.velocity.x)
        #     + " Y: "
        #     + str(game_tick_packet.game_ball.physics.velocity.y)
        #     + " Z: "
        #     + str(game_tick_packet.game_ball.physics.velocity.z)
        #     + Style.RESET_ALL
        # )
        
        # print(
        #     Fore.BLUE
        #     + "Rotation: "
        #     + " Pitch: "
        #     + Fore.GREEN
        #     + str(game_tick_packet.game_ball.physics.rotation.pitch)
        #     + " Yaw: "
        #     + str(game_tick_packet.game_ball.physics.rotation.yaw)
        #     + " Roll: "
        #     + str(game_tick_packet.game_ball.physics.rotation.roll)
        #     + Style.RESET_ALL
        # )
        
        # print(
        #     Fore.BLUE
        #     + "Angular Velocity: "
        #     + " X: "
        #     + Fore.GREEN
        #     + str(game_tick_packet.game_ball.physics.angular_velocity.x)
        #     + " Y: "
        #     + str(game_tick_packet.game_ball.physics.angular_velocity.y)
        #     + " Z: "
        #     + str(game_tick_packet.game_ball.physics.angular_velocity.z)
        #     + Style.RESET_ALL
        # )
        

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
    parser.add_argument(
        "--kickoff",
        action="store_true",
        help="Override all bots kickoff with a default one that is pretty good. 1 to enable, 0 to disable",
    )

    # Disable minimap
    parser.add_argument("--minimap", action="store_true", help="Enable minimap")
    parser.add_argument("--monitoring", action="store_true", help="Enable monitoring")
    parser.add_argument(
        "--debug-keys",
        action="store_true",
        help="Print all keys pressed in game in the console (Gamepad and Keyboard)",
    )
    parser.add_argument("--clock", action="store_true", help="Sync ticks with an internal clock at 120Hz, can help in case of unstable FPS ingame")
    parser.add_argument("--debug", action="store_true", help="Show debug information in the console")
    
    parser.add_argument("--nexto-beta", type=float, help="Beta value for Nexto (float between -1 and 1)")

    args = parser.parse_args()
    
    bot_args = {
        "pid": args.pid,
        "bot": args.bot,
        "minimap": args.minimap,
        "monitoring": args.monitoring,
        "debug_keys": args.debug_keys,
        "built_in_kickoff": args.kickoff,
        "clock": args.clock,
        "debug": args.debug,
    }

    if args.nexto_beta is not None:
        bot_args["nexto_beta"] = args.nexto_beta

    bot = RLMarlbot(**bot_args)


    signal.signal(signal.SIGINT, bot.exit)

    try:
        sys.stdin.read()
    except KeyboardInterrupt:
        bot.minimap_thread.join()
        sys.exit(0)
