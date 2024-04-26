from rlsdk_python import RLSDK, EventTypes, GameEvent, PRI, Ball, Car
from rlsdk_python.events import EventPlayerTick
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
from rlnexto_python.map import MiniMap
from  threading import Thread
import signal

class NextoBot:
    def __init__(self):
        just_fix_windows_console()
        print(Fore.LIGHTMAGENTA_EX + "RLMarlbot (Nexto) v1.3.1" + Style.RESET_ALL)

        self.config = {
            "bot_toggle_key": "F1"
        }

        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                self.config["bot_toggle_key"] = config.get("bot_toggle_key", "F1")

        except Exception as e:
            
            print(Fore.RED + "No config.json found, writing default config" + Style.RESET_ALL)
            with open("config.json", "w") as f:
                json.dump(self.config, f, indent=4)
                print(Fore.LIGHTGREEN_EX + "Default config written to config.json" + Style.RESET_ALL)
            pass

        print(Fore.LIGHTYELLOW_EX + "You can change the settings in config.json" + Style.RESET_ALL)
        print(Fore.CYAN + "For keys binding, you can find values here: https://nerivec.github.io/old-ue4-wiki/pages/list-of-keygamepad-input-names.html" + Style.RESET_ALL)
        print(Fore.LIGHTYELLOW_EX + "Please, give me a star on GitHub: https://github.com/MarlBurroW/RLMarlbot, this work takes a lot of time and effort" + Style.RESET_ALL)

        self.bot_to_use = None
        
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
            self.sdk = RLSDK(hook_player_tick=True)
        except Exception as e:
            print(Fore.RED + "Failed to start SDK: ", e, Style.RESET_ALL)
            exit()
        
        
        
        self.minimap = MiniMap(sdk=self.sdk)
        
        # start a new thread for the minimap main loop
        
        self.minimap_thread = Thread(target=self.minimap.main)
        self.minimap_thread.daemon = True
        self.minimap_thread.start()

   
        print(Fore.LIGHTBLUE_EX + "Starting memory writer..." + Style.RESET_ALL)

        self.mw = memory_writer.MemoryWriter()
        self.mw.open_process("RocketLeague.exe")
        self.write_running = False

        print(Fore.LIGHTGREEN_EX + "Memory writer started" + Style.RESET_ALL)
        
        print(Fore.LIGHTGREEN_EX + "SDK started" + Style.RESET_ALL)

        # functions = self.sdk.scan_functions(10)
        # for function in functions:
        #     print(function.get_full_name())
        
        self.frame_num = 0

        self.bot = None
        self.field_info = None

        self.last_input = None
        self.input_address = None
       
        self.sdk.event.subscribe(EventTypes.ON_PLAYER_TICK, self.on_tick)
        self.sdk.event.subscribe(EventTypes.ON_KEY_PRESSED, self.on_key_pressed)
        self.sdk.event.subscribe(EventTypes.ON_GAME_EVENT_DESTROYED, self.on_game_event_destroyed)

        self.virtual_seconds_elapsed = time.time()

        print(Fore.LIGHTYELLOW_EX + "Press " + self.config["bot_toggle_key"]  + " during a match to toggle Nexto" + Style.RESET_ALL)


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

        if self.bot:
            
            self.frame_num += 1
            game_event = self.sdk.current_game_event
            if game_event:
                

            
                try:
                    game_tick_packet = self.generate_game_tick_packet(game_event)
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
                
                if self.bot:
                    self.minimap.set_game_tick_packet(game_tick_packet, self.bot.index)
          
 
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
            
            try:
                car: Car = pri.get_car()
            except:
                car = None
            
            
            
            team_info = pri.get_team_info()

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
                
                boost_component = car.get_boost_component()
                try:
                    player_info.boost = int(boost_component.get_amount() * 100)
                except:
                    player_info.boost = 0
            else:
                player_info.is_demolished = False
                    
            player_info.team = team_info.get_index()
   
            # player_info.jumped = car.is_jumped()
            
            

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

    def disable_bot(self):
        self.bot = None
        self.stop_writing()
        self.last_input = None
        self.input_address = None
        self.frame_num = 0
        print(Fore.LIGHTRED_EX + "Bot disabled" + Style.RESET_ALL)
        self.minimap.disable()

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


if __name__ == '__main__':
    bot = NextoBot()
    signal.signal(signal.SIGINT, bot.exit)
    
    try:
        sys.stdin.read()
    except KeyboardInterrupt:
        bot.minimap_thread.join()
        sys.exit(0)
        