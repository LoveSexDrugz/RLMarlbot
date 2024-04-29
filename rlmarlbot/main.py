from rlsdk_python import RLSDK, EventTypes, GameEvent, PRI, Ball, Car, PROCESS_NAME
from rlsdk_python.events import EventPlayerTick, EventRoundActiveStateChanged
from nexto.bot import Nexto
from seer.bot import Seer
from necto.bot import Necto
from element.bot import Element
from rlbot.utils.structures.game_data_struct import BallInfo, Vector3, Rotator, FieldInfoPacket, BoostPad, GoalInfo, GameTickPacket, Physics, GameInfo, TileInfo, TeamInfo, PlayerInfo, BoostPadState
import sys
import time
from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from prompt_toolkit import prompt
import struct
from threading import  Event
from memory_writer import memory_writer
from colorama import Fore, Back, Style, just_fix_windows_console
import json
from rlmarlbot.map import MiniMap
from  threading import Thread
import signal
from helpers import serialize_to_json, clear_line, move_cursor_up, clear_lines, clear_screen
import argparse
from art import *
import toml

class NextoBot:
    def __init__(self, pid=None, bot=None, autotoggle=False, minimap=True):
        just_fix_windows_console()
        
        tprint("RLMarlbot")
     
        version = self.get_version()
        
        print(Fore.LIGHTMAGENTA_EX + "RLMarlbot v" + version + Style.RESET_ALL)
        print(Fore.LIGHTYELLOW_EX + "Please, give me a star on GitHub: https://github.com/MarlBurroW/RLMarlbot, this work takes a lot of time and effort" + Style.RESET_ALL)

        self.pid = pid
        self.autotoggle = autotoggle
        self.minimap = minimap
        self.config = {
            "bot_toggle_key": "F1",
            "dump_game_tick_packet_key": "F2"
        }

        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                self.config["bot_toggle_key"] = config.get("bot_toggle_key", "F1")
                self.config["dump_game_tick_packet_key"] = config.get("dump_game_tick_packet_key", "F2")
                

        except Exception as e:
            
            print(Fore.RED + "No config.json found, writing default config" + Style.RESET_ALL)
            with open("config.json", "w") as f:
                json.dump(self.config, f, indent=4)
                print(Fore.LIGHTGREEN_EX + "Default config written to config.json" + Style.RESET_ALL)
            pass

        print(Fore.LIGHTYELLOW_EX + "You can change the settings in config.json" + Style.RESET_ALL)
        print(Fore.CYAN + "For keys binding, you can find values here: https://nerivec.github.io/old-ue4-wiki/pages/list-of-keygamepad-input-names.html" + Style.RESET_ALL)
      
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

        self.frame_num = 0
        self.bot = None
        self.field_info = None
        self.last_input = None
        self.input_address = None
        self.last_tick_start_time = None
        self.tick_counter = 0
        self.tick_rate = 0
        self.last_tick_duration = 0
        
       
        self.sdk.event.subscribe(EventTypes.ON_PLAYER_TICK, self.on_tick)
        self.sdk.event.subscribe(EventTypes.ON_KEY_PRESSED, self.on_key_pressed)
        self.sdk.event.subscribe(EventTypes.ON_GAME_EVENT_DESTROYED, self.on_game_event_destroyed)
        self.sdk.event.subscribe(EventTypes.ON_ROUND_ACTIVE_STATE_CHANGED, self.on_round_active_state_changed)

        self.virtual_seconds_elapsed = time.time()
        
        self.last_game_tick_packet = None

        print(Fore.LIGHTYELLOW_EX + "Press " + self.config["bot_toggle_key"]  + " during a match to toggle Nexto" + Style.RESET_ALL)


    
    def on_round_active_state_changed(self, event: EventRoundActiveStateChanged):
        pass
    
    
    def on_game_event_destroyed(self, event: GameEvent):
        print(Fore.LIGHTRED_EX + "Game event destroyed" + Style.RESET_ALL)
        self.reset_virtual_seconds_elapsed()
        
        self.disable_bot()

    def stop_writing(self):
        self.write_running = False

        if self.input_address:
            # Reset the input state to avoid handbrake bug
            default_input_state = SimpleControllerState()
            bytearray_input = self.controller_to_input(default_input_state)
            self.mw.set_memory_data(self.input_address, bytearray_input)
            time.sleep(0.1)
        
        self.mw.stop()
        
        
        print(Fore.LIGHTRED_EX + "Writing stopped" + Style.RESET_ALL)

    def get_virtual_seconds_elapsed(self):
        return time.time() - self.virtual_seconds_elapsed
    
    def reset_virtual_seconds_elapsed(self):
        self.virtual_seconds_elapsed = time.time()
            
            

    def on_message(self, message, data):
        print("Message received: ", message)
        print("Data received: ", data)


    def generate_field_info(self):
        self.field_info = self.get_field_info()



    def on_tick(self, event: EventPlayerTick):
        
        
        
        

        if not self.field_info and self.sdk.current_game_event:
            self.generate_field_info()
            
            
        if not self.bot and self.autotoggle:
            
            game_event = self.sdk.get_game_event()
            if game_event:
                try:
                    round_active = game_event.is_round_active()
                except:
                    pass
                
                if round_active:
                    try:
                        self.enable_bot()
                    except Exception as e:
                        print(Fore.RED + "Failed to enable bot: ", e, Style.RESET_ALL)
                        self.disable_bot()
                    return

        if self.bot:
            
            if not self.last_tick_start_time:
                self.last_tick_start_time = time.perf_counter()
                
            tick_time = time.perf_counter() - self.last_tick_start_time
            
            tick_duration = time.perf_counter()
            
            # if tick time > 1 second
            
            if tick_time > 1:
                self.last_tick_start_time = time.perf_counter()
                self.tick_rate = self.tick_counter
                self.tick_counter = 0
                
            else:
                self.tick_counter += 1
                
            
        
            
            self.frame_num += 1
            game_event = self.sdk.current_game_event
            if game_event:
                

            
                try:
                    game_tick_packet = self.generate_game_tick_packet(game_event)
                    self.last_game_tick_packet = game_tick_packet
                except Exception as e:
                    print(Fore.RED + "Failed to generate game tick packet: ", e, Style.RESET_ALL)
                    self.disable_bot()
                    return
                
                try:
                    simple_controller_state = self.bot.get_output(game_tick_packet)
                except Exception as e:
                    print(Fore.RED + "Failed to get bot output: ", e, Style.RESET_ALL)
                    self.disable_bot()
                    return
                
                bytearray_input = self.controller_to_input(simple_controller_state)

                local_players = game_event.get_local_players()
             
                if len(local_players) > 0:
                    player_controller = local_players[0]
                    input_address = player_controller.address + 0x0990
         
                    if input_address:
                        
                    
                        self.last_input = bytearray_input
                        self.input_address = input_address

                        self.mw.set_memory_data(input_address, bytearray_input)
                   
                        if self.write_running == False:
                            self.write_running = True
                            print(Fore.LIGHTBLUE_EX + "Starting memory write thread..." + Style.RESET_ALL)
                            self.mw.start()
                
                if self.bot and self.minimap:
                    self.minimap.set_game_tick_packet(game_tick_packet, self.bot.index)
                    
                
                self.last_tick_duration = time.perf_counter() - tick_duration    
                
              
                
      
                    
                self.display_monitoring_info(game_tick_packet, simple_controller_state)
          
 
    def controller_to_input(self, controller: SimpleControllerState):
         # convert controller (numpy) to FVehicleInputs bytes representation
        inputs = bytearray(32)

        # Packing the float values
        inputs[0:4] = struct.pack('<f', controller.throttle)
        inputs[4:8] = struct.pack('<f', controller.steer)
        inputs[8:12] = struct.pack('<f', controller.pitch)
        inputs[12:16] = struct.pack('<f', controller.yaw)
        inputs[16:20] = struct.pack('<f', controller.roll)
        
        # DodgeForward = -pitch
        inputs[20:24] = struct.pack('<f', -controller.pitch)
        # DodgeRight = yaw
        inputs[24:28] = struct.pack('<f', controller.yaw)

        # Rest of the inputs are booleans encoded in a single uint32
        flags = 0
        flags |= (controller.handbrake << 0)
        flags |= (controller.jump << 1)
        flags |= (controller.boost << 2)
        flags |= (controller.boost << 3) 
        flags |= (controller.use_item << 4)  

        # Encode the flags into the last 4 bytes (uint32)
        inputs[28:32] = struct.pack('<I', flags)

        return inputs

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
        game_info.is_round_active = game_event.is_round_active()
        game_info.is_unlimited_time = game_event.is_unlimited_time()
        game_info.is_match_ended = game_event.is_match_ended()
        game_info.world_gravity_z = 1.0
        game_info.is_kickoff_pause = True if game_info.is_round_active and game_tick_packet.game_ball and game_tick_packet.game_ball.physics.location.x == 0 and game_tick_packet.game_ball.physics.location.y == 0 else False
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

                player_info.physics.angular_velocity.x = car.get_angular_velocity().get_x()
                player_info.physics.angular_velocity.y = car.get_angular_velocity().get_y()
                player_info.physics.angular_velocity.z = car.get_angular_velocity().get_z()

                player_info.has_wheel_contact = car.is_on_ground()
                player_info.is_super_sonic = car.is_supersonic()
                
                player_info.double_jumped = car.is_double_jumped()
                player_info.jumped = car.is_jumped()
                
                boost_component = car.get_boost_component()
                try:
                    player_info.boost = int(boost_component.get_amount() * 100)
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


 
    def enable_bot(self):
        game_event = self.sdk.get_game_event()
        self.frame_num = 0

        if game_event:
            game_event = self.sdk.get_game_event()

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
                    print("Player car index: ", pri_index)
                    break
            else:
                raise Exception("Player car not found")
            
            try:
                team_index = player_pri.get_team_info().get_index()
            except:
                raise Exception("Failed to get team index")
            
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
                
            clear_screen()

    def disable_bot(self):
        self.bot = None
        self.stop_writing()
        self.last_input = None
        self.input_address = None
        self.last_game_tick_packet = None
        self.frame_num = 0
        self.minimap.disable()
        self.last_tick_start_time = None
        self.tick_rate = 0
        self.tick_counter = 0
        self.last_tick_duration = 0
        print(Fore.LIGHTRED_EX + "Bot disabled" + Style.RESET_ALL)
        

    def on_key_pressed(self, event):

        #print("Key pressed: ", event.key, event.type)
    
        if event.key == self.config["bot_toggle_key"] :

            if event.type == "pressed":
                if self.bot:
                    self.disable_bot()
                else:
                    try:
                        self.enable_bot()
                    except Exception as e:
                        print(Fore.RED + "Failed to enable bot: ", e, Style.RESET_ALL)
                        self.disable_bot()
                        
        if event.key == self.config["dump_game_tick_packet_key"]:
            if event.type == "pressed":
                if self.last_game_tick_packet:
                    self.dump_packet(self.last_game_tick_packet)
  

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

        for i, goal in  enumerate(goals):
            
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
    
    
    def exit(self, signum, frame):
        self.minimap.running = False
        self.minimap_thread.join()
        sys.exit(0)
        
        
        
    def dump_packet(self, game_tick_packet):
        json_packet = serialize_to_json(game_tick_packet)
        frame_num = game_tick_packet.game_info.frame_num
        with open("game_tick_packet_" + str(frame_num) + ".json", "w") as f:
            f.write(json_packet)
        print(Fore.LIGHTGREEN_EX + "Game tick packet dumped to game_tick_packet_" + str(frame_num) + ".json" + Style.RESET_ALL)
        
        
    def display_monitoring_info(self, game_tick_packet, controller):
        
    
        clear_lines(30)
      
        
        print(Fore.LIGHTYELLOW_EX + "Bot Monitoring Info" + Style.RESET_ALL)
        print(Fore.LIGHTCYAN_EX + "Tick rate: " + Fore.LIGHTGREEN_EX + str(self.tick_rate) + " ticks/s" + Style.RESET_ALL)
        # Tick computation time
        print(Fore.LIGHTCYAN_EX + "Tick processing time: " + Fore.LIGHTGREEN_EX + str(round(self.last_tick_duration * 1000, 2)) + " ms" + Style.RESET_ALL)
        # Frane number
        print(Fore.LIGHTCYAN_EX + "Frame number: " + Fore.LIGHTGREEN_EX + str(game_tick_packet.game_info.frame_num) + Style.RESET_ALL)
        
        
        print(Fore.LIGHTMAGENTA_EX + "Boost pads" + Style.RESET_ALL)
        # Display boost pads (o = small boost, O = big boost, green = active, red = inactive)
        boost_pads = self.sdk.field.boostpads
        boost_pads_str = ""
        for i in range(game_tick_packet.num_boost):
            if boost_pads[i].is_active:
                if boost_pads[i].is_big:
                    boost_pads_str += Fore.GREEN + "O" + Style.RESET_ALL
                else:
                    boost_pads_str += Fore.GREEN + "o" + Style.RESET_ALL
            else:
                if boost_pads[i].is_big:
                    boost_pads_str += Fore.RED + "X" + Style.RESET_ALL
                else:
                    boost_pads_str += Fore.RED + "x" + Style.RESET_ALL
        
        
        print(boost_pads_str)
        
        
        print(Fore.LIGHTMAGENTA_EX + "Players" + Style.RESET_ALL)
        players = game_tick_packet.game_cars
        
        for i in range(game_tick_packet.num_cars):
            # 0 = blue, 1 = red
            color = Fore.BLUE if players[i].team == 0 else Fore.LIGHTYELLOW_EX

            
            player_state = ""
            player_state +=  Style.BRIGHT + Fore.LIGHTWHITE_EX + Back.GREEN + "JUMPED" + Style.RESET_ALL if players[i].jumped else Back.BLACK + "JUMPED" + Style.RESET_ALL
            player_state += " - "
            player_state +=  Style.BRIGHT + Fore.LIGHTWHITE_EX + Back.GREEN + "DOUBLE JUMPED" + Style.RESET_ALL if players[i].double_jumped else Back.BLACK + "DOUBLE JUMPED" + Style.RESET_ALL
            player_state += " - "
            player_state +=  Style.BRIGHT + Fore.LIGHTWHITE_EX + Back.GREEN + "SUPERSONIC" + Style.RESET_ALL if players[i].is_super_sonic else Back.BLACK +  "SUPERSONIC" + Style.RESET_ALL
            player_state += " - "
            player_state +=  Style.BRIGHT + Fore.LIGHTWHITE_EX + Back.GREEN + "WHEELS ON GROUND" + Style.RESET_ALL if players[i].has_wheel_contact else Back.BLACK +  "WHEELS ON GROUND" + Style.RESET_ALL
            player_state += " - "
            player_state +=  Style.BRIGHT + Fore.LIGHTWHITE_EX + Back.GREEN + "DEMOLISHED" + Style.RESET_ALL if players[i].is_demolished else Back.BLACK +  "DEMOLISHED" + Style.RESET_ALL
            
            
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
            
            print(color + player_name + Back.RESET + Fore.RESET + " " + player_state + Style.RESET_ALL)
        

        
    def get_version(self):
        pyproject = toml.load("pyproject.toml")
        return pyproject['tool']['poetry']['version']
            

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RLMarlbot')
    parser.add_argument('-p', '--pid', type=int, help='Rocket League process ID')
    parser.add_argument('-b', '--bot', type=str, help='Bot to use (nexto, necto, seer, element)')
    parser.add_argument('-a', '--autotoggle', action='store_true', help='Automatically toggle the bot on active round')
    # Disable minimap
    parser.add_argument('--no-minimap', action='store_true', help='Disable minimap')
    
    
    args = parser.parse_args()

    bot = NextoBot(pid=args.pid, bot=args.bot, autotoggle=args.autotoggle, minimap=not args.no_minimap)
    
    signal.signal(signal.SIGINT, bot.exit)
    
    try:
        sys.stdin.read()
    except KeyboardInterrupt:
        bot.minimap_thread.join()
        sys.exit(0)
        