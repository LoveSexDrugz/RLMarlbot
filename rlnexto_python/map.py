



import pygame
import sys

import time
from collections import deque
from rlbot.utils.structures.game_data_struct import GameTickPacket, PlayerInfo
from rlsdk_python import RLSDK

class MiniMap:
    def __init__(self, sdk: RLSDK=None):

        self.time = time.time()
        self.frame_num = 0
        self.running = False
        self.padding = 500
        self.goal_height = 880
        self.max_world_x = 4210.0 + self.padding  # Ajuster max_world_x pour inclure le padding
        self.max_world_y = 6140.0 + self.padding  # Ajuster max_world_y pour inclure le padding
        self.world_width = 8420.0 + 2 * self.padding  # Ajouter le padding des deux côtés en largeur
        self.world_height = 12280.0 + 2 * self.padding  # Ajouter le padding des deux côtés en hauteur
     
        self.initial_screen_width = 820
        self.initial_screen_height = 1024
        self.screen_width = self.initial_screen_width
        self.screen_height = self.initial_screen_height
        self.scale_factor = 1.0
        self.aspect_ratio = self.initial_screen_width / self.initial_screen_height
        self.player_name_font = None
        self.fps_font = None

        self.game = None
        self.field_info = None
        self.TRAIL_SIZE = 120
        self.car_trails = {}
        self.ball_trail =  deque(maxlen=self.TRAIL_SIZE)

        self.blue_color = (40, 169, 255)
        self.red_color = (239, 92 ,48)
        
        self.game_tick_packet = None
        self.sdk = sdk
        

    
    def set_game_tick_packet(self, game_tick_packet):
        self.game_tick_packet = game_tick_packet


    def update_scale_factor(self, new_width, new_height):
        # Calculate new size while maintaining the aspect ratio
        new_ratio = new_width / new_height
        if new_ratio > self.aspect_ratio:
            # Too wide
            new_width = int(new_height * self.aspect_ratio)
        else:
            # Too tall
            new_height = int(new_width / self.aspect_ratio)

        self.screen_width = new_width
        self.screen_height = new_height
        self.scale_factor = new_width / self.initial_screen_width
        pygame.display.set_mode((new_width, new_height), pygame.RESIZABLE)

    def world_to_screen(self, x, y):
        # Ajustement du centre en considérant le padding
        center_x = self.max_world_x + self.padding
        center_y = self.max_world_y + self.padding

        # Convertir les coordonnées du monde réel avec le nouveau centre
        location_x = center_x - x
        location_y = center_y - y

        # Calculer les taux de position par rapport à la taille totale du monde ajustée
        location_x_rate = location_x / (self.world_width + 2 * self.padding)
        location_y_rate = location_y / (self.world_height + 2 * self.padding)

        # Appliquer les taux à la taille de l'écran pour obtenir les coordonnées de l'écran
        screen_x = self.screen_width * location_x_rate
        screen_y = self.screen_height * location_y_rate

        return screen_x, screen_y
    def main(self):
        pygame.init()
        screen = pygame.display.set_mode((self.screen_width, self.screen_height), pygame.RESIZABLE)

        
        pygame.display.set_caption("Marlbot MiniMap (Bot vision)")
        background_color = (0, 0, 0)
        clock = pygame.time.Clock()

        self.player_name_font = pygame.font.Font(None, int(20 * self.scale_factor))
        self.fps_font = pygame.font.Font(None, int(15 * self.scale_factor))

        self.running = True
        while self.running:
            try:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.VIDEORESIZE:
                        self.update_scale_factor(event.w, event.h)

                screen.fill(background_color)

                field_surface = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
                field_surface.fill((0, 0, 0, 0)) 

                self.draw_field(field_surface)

                screen.blit(field_surface, (0, 0))

                object_surface = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
                object_surface.fill((0, 0, 0, 0)) 
                
                
                if self.game_tick_packet:
                    try:
                        self.draw_game_elements(object_surface, self.game_tick_packet)
                        screen.blit(object_surface, (0, 0))
                    except Exception as e:
                        print(e)



                # display FPS on the screen to the top right corner
            
                fps = str(int(clock.get_fps()))
                fps_text =  self.fps_font.render(fps + " FPS", True, pygame.Color('white'))
                screen.blit(fps_text, (self.screen_width - 60, 10))

                pygame.display.flip()
                clock.tick(60)
            except (SystemExit, KeyboardInterrupt):
                self.running = False
                break
                
        

       
        pygame.quit()
        sys.exit()

    def draw_field(self, screen):

        # Définition des points du terrain
        # Sommets du polygone: haut gauche, haut droite
        field = [
            (-2944, 5120),
            (-893, 5120),
            (-893, 5120 + 880),
            (893, 5120 + 880),
            (893, 5120),
            (2944, 5120),
            (4096, 3968),
            (4096, -3968),
            (2944, -5120),
            (893, -5120),
            (893, -5120 - 880),
            (-893, -5120 - 880),
            (-893, -5120),
            (-2944, -5120),
            (-4096, -3968),
            (-4096, 3968),
            (-2944, 5120)
        ]

        # # Transformer chaque coordonnée du monde en coordonnée de l'écran
        # field_screen = [self.world_to_screen(x, y) for x, y in field]

        # # Dessiner le polygone sur l'écran
        # pygame.draw.polygon(screen, (255, 255, 255), field_screen, 2)

        # # ligne centrale

        # center_line = [
        #     (-4096, 0),
        #     (4096, 0)
        # ]

        # center_line_screen = [self.world_to_screen(x, y) for x, y in center_line]

        # pygame.draw.lines(screen, (255, 255, 255), False, center_line_screen, 2)


        # cercle central

        pygame.draw.circle(screen, (255, 255, 255), self.world_to_screen(0, 0), int(60 * self.scale_factor), 2)


        top_surface_polygone = [
            (-2944, 5120),
            (-893, 5120),
            (-893, 5120 + 880),
            (893, 5120 + 880),
            (893, 5120),
            (2944, 5120),
            (4096, 3968),
            (4096, -3968),
            (4096, 0),
            (-4096, 0),
            (-4096, 3968),
            (-2944, 5120)
        ]

        top_surface_screen = [self.world_to_screen(x, y) for x, y in top_surface_polygone]

        pygame.draw.polygon(screen, self.red_color + (100,), top_surface_screen)

        bottom_surface_polygone = [
            (-2944, -5120),
            (-893, -5120),
            (-893, -5120 - 880),
            (893, -5120 - 880),
            (893, -5120),
            (2944, -5120),
            (4096, -3968),
            (4096, 3968),
            (4096, 0),
            (-4096, 0),
            (-4096, -3968),
            (-2944, -5120)
        ]

        bottom_surface_screen = [self.world_to_screen(x, y) for x, y in bottom_surface_polygone]

        pygame.draw.polygon(screen, self.blue_color + (100,), bottom_surface_screen)



    def draw_game_elements(self, screen, game_tick_packet: GameTickPacket):

        
       
        cars = game_tick_packet.game_cars
        
        for car_index in range(0, game_tick_packet.num_cars):
            car = cars[car_index]
   
            color = car.team == 0 and self.blue_color or self.red_color
           
            # make radius changing according z (altitude)

            radius = int(15 * self.scale_factor) + int(car.physics.location.z / 100)

        

            if car_index not in self.car_trails:
                self.car_trails[car_index] = deque(maxlen=self.TRAIL_SIZE) 


            x, y = self.world_to_screen(car.physics.location.x, car.physics.location.y)

            self.car_trails[car_index].appendleft((x, y))

             # Dessin de la trainée
            for i, (trail_x, trail_y) in enumerate(self.car_trails[car_index]):
                
                trail_color =  (color[0], color[1], color[2], int(255 * (1 - i / len(self.car_trails[car_index]))))  # Diminue l'opacité

                trail_radius = max(1, radius * (1 - i / len(self.car_trails[car_index])))  # Diminue le rayon
                pygame.draw.circle(screen, trail_color, (trail_x, trail_y), trail_radius)

            pygame.draw.circle(screen, color, (x, y), radius)  # Scale circle radius

            nickname = car.name
            text = self.player_name_font.render(nickname, True, color)
            text_rect = text.get_rect(center=(x, y - int(40 * self.scale_factor)))
            screen.blit(text, text_rect)

            boost_amount = car.boost
            boost_amount = boost_amount / 100  # Normalize to 0-1
            
           
            

            # Create a progress bar for the boost amount just under the nickname

            boost_bar_width = int(50 * self.scale_factor)
            boost_bar_height = int(5 * self.scale_factor)
            boost_bar_x = x - boost_bar_width // 2
            boost_bar_y = y - int(30 * self.scale_factor)

            pygame.draw.rect(screen, (255, 0, 0), (boost_bar_x, boost_bar_y, boost_bar_width, boost_bar_height))
            pygame.draw.rect(screen, (0, 255, 0), (boost_bar_x, boost_bar_y, int(boost_bar_width * boost_amount), boost_bar_height))
            
        
        boostpads = self.sdk.field.boostpads

        for boostpad_index in range(0, game_tick_packet.num_boost):
            pad = boostpads[boostpad_index]
            
 
        
            x, y = self.world_to_screen(pad.location.x,pad.location.y)
            radius = pad.is_big and 10 or 5

            if pad.is_active:
                # circle filled
                pygame.draw.circle(screen, (255, 255, 0), (x, y),  int(radius * self.scale_factor))
            else:
                # circle outline
                pygame.draw.circle(screen, (255, 255, 0), (x, y), int(radius * self.scale_factor), 2)
             
                remaining = pad.get_remaining_time()
                if remaining > 0:
                    text = self.player_name_font.render(str(round(remaining, 1)), True, (255, 255, 255))
                    text_rect = text.get_rect(center=(x, y + int(20 * self.scale_factor)))
                    screen.blit(text, text_rect)
                    
                    

        ball = game_tick_packet.game_ball
         
        radius = int(20 * self.scale_factor) + int(ball.physics.location.z / 100)

        x, y = self.world_to_screen(ball.physics.location.x, ball.physics.location.y)

        # Dessin de la trainée

        self.ball_trail.appendleft((x, y))

        for i, (trail_x, trail_y) in enumerate(self.ball_trail):
            
            trail_color =  (255, 255, 255, int(255 * (1 - i / len(self.ball_trail))) )
            trail_radius = max(1, radius * (1 - i / len(self.ball_trail)))
            pygame.draw.circle(screen, trail_color, (trail_x, trail_y), trail_radius)

        pygame.draw.circle(screen, (255, 255, 255), (x, y),  radius)





