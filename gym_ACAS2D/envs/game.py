import numpy as np
import random
import pygame
import math

from gym_ACAS2D.envs.aircraft import PlayerAircraft, TrafficAircraft
from gym_ACAS2D.settings import *


def distance(x1, y1, x2, y2):
    # Player and goal positions as np.array
    p1 = np.array((x1, y1))
    p2 = np.array((x2, y2))
    # Euclidean distance between player and goal
    d = np.linalg.norm(p1 - p2, 2)
    return d


def relative_angle(x1, y1, x2, y2):
    # The psi that would lead the player straight to the goal
    dx = x2 - x1
    dy = y2 - y1
    rads = math.atan2(dy, dx) % (2 * math.pi)
    degrees = math.degrees(rads)
    return degrees


def separation_reward(s):
    if 0 <= s <= SAFE_RADIUS:
        return (REWARD_COLLISION + (-REWARD_COLLISION / SAFE_RADIUS) * s) / abs(REWARD_COLLISION)
    elif s > SAFE_RADIUS:
        return 0
    else:
        raise ValueError("Min separation cannot be negative.")


def distance_reward(d):
    if d >= 0:
        d_goal_init = (WIDTH - GOAL_RADIUS) - (2 * AIRCRAFT_SIZE)
        r = REWARD_GOAL - (REWARD_GOAL / d_goal_init) * d
        return max(r, -REWARD_GOAL) / REWARD_GOAL
    else:
        raise ValueError("Distance to goal cannot be negative.")


def step_reward(d, s):
    return distance_reward(d) + separation_reward(s)


class ACAS2DGame:
    def __init__(self, episode=None, manual=False):

        # Initialize PyGame
        pygame.init()
        # Title and icon
        pygame.display.set_caption(CAPTION)
        pygame.display.set_icon(pygame.image.load(LOGO))

        # Create the screen: WIDTH x HEIGHT
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        # Game clock
        self.clock = pygame.time.Clock()
        # Episode
        self.episode = episode
        # Time steps counter
        self.steps = 0
        # Total reward
        self.total_reward = 0

        # Game status flags
        self.manual = manual  # Is the player controlled manually?
        self.running = True  # Is the game running?
        self.quit = False  # Has the game window been closed?

        # Game outcome
        self.outcome = None

        # Load images
        self.playerIMG = pygame.image.load(PLAYER_IMG)
        self.goalIMG = pygame.image.load(GOAL_IMG)
        self.trafficIMG = pygame.image.load(TRAFFIC_IMG)
        # Text font
        self.font = pygame.font.Font(FONT_NAME, FONT_SIZE)

        # Set the goal position at random, in the top part of the airspace.
        self.goal_x = WIDTH - GOAL_RADIUS
        self.goal_y = HEIGHT / 2

        # # Maximum allowed distance from goal
        # self.max_distance = np.sqrt(WIDTH ** 2 + HEIGHT ** 2)

        # Set the player starting position at random, in the bottom part of the airspace
        # Set the player starting psi and v_air
        player_x = COLLISION_RADIUS
        player_y = HEIGHT / 2
        player_speed = AIRSPEED
        player_psi = random.uniform(0, 360)
        self.player = PlayerAircraft(x=player_x, y=player_y, v_air=player_speed, psi=player_psi)
        # Set player's initial heading towards the general direction of the goal.
        self.player.psi = (relative_angle(self.player.x, self.player.y, WIDTH, HEIGHT/2) +
                           random.uniform(-INITIAL_HEADING_LIM, INITIAL_HEADING_LIM)) % 360

        # Initial distance to goal
        self.d_goal_initial = self.distance_to_goal()
        # Max possible distance from goal
        self.d_goal_max = self.distance_to_goal() + (AIRSPEED / FPS) * MAX_STEPS

        # Number of traffic aircraft
        self.num_traffic = random.randint(MIN_TRAFFIC, MAX_TRAFFIC)

        # Set the traffic aircraft positions, headings and speeds at random, in the middle part of the airspace.
        self.traffic = []
        for t in range(self.num_traffic):

            if t == 0:
                # Random position in the mid part of the airspace
                t_x = WIDTH - COLLISION_RADIUS
                t_y = COLLISION_RADIUS
                # Random v_air
                t_speed = random.uniform(AIRSPEED_FACTOR_MIN, AIRSPEED_FACTOR_MAX) * AIRSPEED
                # Random psi: 0..360 degrees
                t_heading = random.uniform(110, 160)
                self.traffic.append(TrafficAircraft(x=t_x, y=t_y, v_air=t_speed, psi=t_heading))
            else:
                # Random position in the mid part of the airspace
                t_x = random.uniform(0, WIDTH - AIRCRAFT_SIZE)
                t_y = random.uniform(0, 3 * HEIGHT / 5)
                # Random v_air
                t_speed = random.uniform(AIRSPEED_FACTOR_MIN, AIRSPEED_FACTOR_MAX) * AIRSPEED
                # Random psi: 0..360 degrees
                t_heading = random.uniform(0, 360)
                self.traffic.append(TrafficAircraft(x=t_x, y=t_y, v_air=t_speed, psi=t_heading))

    def minimum_separation(self):
        if self.num_traffic == 0:
            return float("inf")
        distances = [distance(self.player.x, self.player.y, t.x, t.y) for t in self.traffic]
        return np.min(distances)

    def distance_to_goal(self):
        return distance(self.player.x, self.player.y, self.goal_x, self.goal_y)
    #
    # def heading_to_goal(self):
    #     # The psi that would lead the player straight to the goal
    #     return relative_angle(self.player.x, self.player.y, self.goal_x, self.goal_y)

    def check_timeout(self):
        return self.steps == MAX_STEPS

    # def check_runaway(self):
    #     return self.player.x < 0 or \
    #            self.player.y > HEIGHT or \
    #            (self.player.y < 0 and self.player.x < WIDTH - GOAL_RADIUS) or \
    #            (self.player.x > WIDTH and self.player.y > GOAL_RADIUS)

    def detect_collisions(self):
        for t in self.traffic:
            if distance(self.player.x, self.player.y, t.x, t.y) < 2 * COLLISION_RADIUS:
                return True
        return False

    def check_goal(self):
        return self.distance_to_goal() < GOAL_RADIUS

    def observe(self):

        # Increase number of steps in the game (all steps start with an observation)
        self.steps += 1

        obs = [self.steps / MAX_STEPS,
               self.player.x / WIDTH,
               self.player.y / HEIGHT,
               self.player.psi / 360,
               self.distance_to_goal() / self.d_goal_max,
               relative_angle(self.player.x, self.player.y, self.goal_x, self.goal_y) / 360]

        obs = np.array(obs).astype(np.float64)

        # print("observe() 	>>> obs: {}".format(obs))

        return obs

    def action(self, action):
        # Update player a_lat based on action taken
        # Action is scaled to [-1, 1] ; scale to original [-ACC_LAT_LIMIT, ACC_LAT_LIMIT]
        self.player.a_lat = action[0] * ACC_LAT_LIMIT
        # Update player position based on that v_air and psi
        self.player.update_state()
        # If the game is still running, update the traffic aircraft positions.
        for t in self.traffic:
            if self.running:
                t.update_state()
                # if t.out_of_bounds(WIDTH, HEIGHT):
                #     t.bounce(WIDTH, HEIGHT)

        # print("action() 	>>> Action: {}".format(action))

    def evaluate(self):
        # reward = 0
        # Shaped reward guiding us to the goal
        # Time discount factor
        tdf = 1 - (self.steps / MAX_STEPS)
        reward = step_reward(self.distance_to_goal(), self.minimum_separation()) * tdf
        # # Time discounted distance reward
        # d_goal = self.distance_to_goal()
        # d_init = self.d_goal_initial
        # r_dist = np.tanh((d_init - d_goal) / self.d_goal_max)
        # # x_max = (AIRSPEED / FPS) * MAX_STEPS
        # # r_dist = np.tanh(self.player.x / x_max)
        # reward += r_dist * tdf
        # # Penalise running away
        # if self.check_runaway():
        #     reward += REWARD_RUNAWAY_FACTOR * d_goal
        # # Penalise timeouts.
        # if self.check_timeout():
        #     reward += REWARD_TIMEOUT_FACTOR * d_goal

        # Penalise collisions.
        if self.detect_collisions():
            reward += REWARD_COLLISION
        # Reward reaching the goal
        if self.check_goal():
            reward += REWARD_GOAL
        # Accumulate episode rewards
        self.total_reward += reward

        # print("evaluate() 	>>> Reward: {}".format(reward))

        return reward

    def is_done(self):
        done = False
        # # Check for run away
        # if self.check_runaway():
        #     self.running = False
        #     self.outcome = 4
        #     done = True
        # Check for Timeout
        if self.check_timeout():
            self.running = False
            done = True
            self.outcome = 3
        # Check for collisions
        elif self.detect_collisions():
            self.running = False
            self.outcome = 2
            done = True
        # Check if we have reached the goal
        elif self.check_goal():
            self.running = False
            self.outcome = 1
            done = True
        if done:
            print("is_done() 	>>> Outcome: {} Total Reward: {}".format(OUTCOME_NAMES[self.outcome], self.total_reward))
        return done

    def view(self):
        # Detect events
        for event in pygame.event.get():
            # Quit game
            if event.type == pygame.QUIT:
                self.quit = True

        # Change background colour to sky colour RGB value
        self.screen.fill(SKY_RGB)

        # Place player in the game
        self.screen.blit(self.playerIMG, (self.player.x - (AIRCRAFT_SIZE / 2),
                                          self.player.y - (AIRCRAFT_SIZE / 2)))

        # Place goal in the game
        self.screen.blit(self.goalIMG, (self.goal_x - (AIRCRAFT_SIZE / 2),
                                        self.goal_y - (AIRCRAFT_SIZE / 2)))

        # Place traffic aircraft in the game
        for t in self.traffic:
            self.screen.blit(self.trafficIMG, (t.x - (AIRCRAFT_SIZE / 2),
                                               t.y - (AIRCRAFT_SIZE / 2)))

        # Draw collision radius around aircraft
        pygame.draw.circle(self.screen, GREEN_RGB, (self.player.x, self.player.y),
                           COLLISION_RADIUS, 1)

        # Draw goal radius around goal
        pygame.draw.circle(self.screen, YELLOW_RBG, (self.goal_x, self.goal_y),
                           GOAL_RADIUS, 1)

        # Draw collision radius around traffic aircraft
        for t in self.traffic:
            pygame.draw.circle(self.screen, RED_RGB, (t.x, t.y), COLLISION_RADIUS, 1)

        # Display minimum separation
        min_separation = self.minimum_separation()
        ms = self.font.render("Min. Separation: {}".format(round(min_separation, 1)), True, FONT_RGB)
        self.screen.blit(ms, (20, HEIGHT - 20))

        # Display episode and 'time' (number of game loop iterations)
        st = self.font.render("Steps: {}".format(self.steps), True, FONT_RGB)
        self.screen.blit(st, (WIDTH / 2 - 50, HEIGHT - 20))
        ep = self.font.render("Episode: {}".format(self.episode), True, FONT_RGB)
        self.screen.blit(ep, (WIDTH / 2 - 50, HEIGHT - 40))

        # Display total reward
        r_tot = self.font.render("Total reward: {}".format(round(self.total_reward, 1)), True, FONT_RGB)
        self.screen.blit(r_tot, (WIDTH - 200, HEIGHT - 20))

        # # Detect collisions
        # if self.detect_collisions():
        #     mes = self.font.render("Collision!", True, FONT_RGB)
        #     self.screen.blit(mes, (WIDTH / 2 - 30, HEIGHT / 2))

        # # Check if player reached the goal
        # if self.check_goal():
        #     mes = self.font.render("Goal reached!", True, FONT_RGB)
        #     self.screen.blit(mes, (WIDTH / 2 - 40, HEIGHT / 2))

        # Update the game screen
        pygame.display.update()
