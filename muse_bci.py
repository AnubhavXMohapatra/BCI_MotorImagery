#pip install numpy pylsl scipy pygame matplotlib
import numpy as np
from pylsl import StreamInlet, resolve_byprop
from scipy.signal import butter, filtfilt
import pygame
import os
import time
import csv
from math import sin, pi
import matplotlib.pyplot as plt

# MuseBCI Class: Handles EEG data processing and calibration
class MuseBCI:
    def __init__(self):
        self.fs = 256  # Muse sampling frequency
        self.channel_names = ['TP9', 'AF7', 'AF8', 'TP10']
        self.inlet = None
        self.thresholds = {'mu_threshold': 10, 'beta_threshold': 15}
        self.load_calibration()
        self.eeg_data_log = []  # To store EEG data for analysis

    def load_calibration(self):
        try:
            self.thresholds = np.load('muse_calibration.npy', allow_pickle=True).item()
            print(f"Calibration loaded: {self.thresholds}")
        except:
            print("No calibration found. Using default thresholds.")

    def connect_muse(self):
        print("Looking for EEG stream...")
        streams = resolve_byprop('type', 'EEG')
        if not streams:
            raise Exception("No EEG stream found. Ensure Muse is streaming via BlueMuse.")
        for stream in streams:
            if 'Muse' in stream.name():
                self.inlet = StreamInlet(stream)
                print(f"Connected to Muse: {stream.name()}")
                return
        raise Exception("Muse EEG stream not found.")

    def bandpass_filter(self, data, lowcut, highcut, order=5, padlen=10):
        nyq = 0.5 * self.fs
        low, high = lowcut / nyq, highcut / nyq
        b, a = butter(order, [low, high], btype='band')
        return filtfilt(b, a, data, axis=0, padlen=padlen)

    def process_eeg(self):
        chunk_size = 2048
        eeg_chunk, _ = self.inlet.pull_chunk(max_samples=chunk_size)
        if not eeg_chunk:
            return None
        eeg_data = np.array(eeg_chunk)
        self.eeg_data_log.append(eeg_data)

        if eeg_data.shape[0] < 10:
            return None

        motor_channels = eeg_data[:, [1, 2]]  # AF7, AF8
        mu_band = self.bandpass_filter(motor_channels, 8, 12)
        beta_band = self.bandpass_filter(motor_channels, 13, 30)
        mu_power = np.mean(np.square(mu_band))
        beta_power = np.mean(np.square(beta_band))
        movement = (mu_power > self.thresholds['mu_threshold']) or (beta_power > self.thresholds['beta_threshold'])
        return {"movement": movement, "mu_power": mu_power, "beta_power": beta_power}

    def calibrate(self):
        print("Calibrating... Relax for 60 seconds.")
        print("Tips: Close your eyes, breathe deeply, and relax.")
        
        # Calibration messages with timing
        calibration_messages = [
            (5, "Take a deep breath in for 3 seconds..."),
            (8, "And slowly breathe out..."),
            (12, "Gently relax your shoulders..."),
            (15, "Let your hands rest comfortably..."),
            (20, "Release any tension in your neck..."),
            (25, "Feel your thoughts becoming quieter..."),
            (30, "Halfway there - you're doing great!"),
            (35, "Keep your breathing slow and steady..."),
            (40, "Let your jaw relax completely..."),
            (45, "You're almost done - stay relaxed..."),
            (50, "Keep your mind clear and calm..."),
            (55, "Just a few more seconds...")
        ]
        
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(r'C:\Users\munmu\OneDrive\Desktop\BCI_MotorImagery\calibration_music.mp3')
            pygame.mixer.music.play(-1)
        except pygame.error as e:
            print(f"Warning: Could not load or play calibration music: {e}")
            print("Calibration will continue without music")

        baseline_data = []
        start_time = time.time()
        last_message_index = 0
        
        try:
            while time.time() - start_time < 60:
                current_time = time.time() - start_time
                
                # Display calibration messages at appropriate times
                while (last_message_index < len(calibration_messages) and 
                       current_time >= calibration_messages[last_message_index][0]):
                    print(calibration_messages[last_message_index][1])
                    last_message_index += 1
                
                chunk, _ = self.inlet.pull_chunk()
                if chunk:
                    baseline_data.extend(chunk)
                time.sleep(0.1)
                
        finally:
            if pygame.mixer.get_init():
                try:
                    pygame.mixer.music.stop()
                    pygame.mixer.quit()
                except pygame.error:
                    pass

        baseline_data = np.array(baseline_data)
        motor_channels = baseline_data[:, [1, 2]]
        mu_baseline = np.mean(np.square(self.bandpass_filter(motor_channels, 8, 12)))
        beta_baseline = np.mean(np.square(self.bandpass_filter(motor_channels, 13, 30)))
        self.thresholds = {'mu_threshold': mu_baseline * 0.8, 'beta_threshold': beta_baseline * 0.8}
        np.save('muse_calibration.npy', self.thresholds)
        print(f"Calibration complete! Thresholds: {self.thresholds}")

# Pygame Integration: Visualizing and playing the game
class PygameBCI:
    def __init__(self):
        pygame.init()
        # Initialize mixer with specific settings for better performance
        pygame.mixer.pre_init(44100, -16, 2, 2048)
        pygame.mixer.init()
        self.screen_width = 800
        self.screen_height = 600
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("BCI Motor Imagery Game")
        self.clock = pygame.time.Clock()
        self.player_x = 100
        self.player_y = self.screen_height // 2
        self.player_size = 30
        self.gravity = 0.5
        self.lift = -15
        self.velocity = 0
        self.running = True
        self.bg_color = (30, 30, 30)
        self.obstacle_speed = 5
        self.obstacles = []
        self.score = 0  # Initialize score to 0
        self.passed_obstacles = set()  # Track passed obstacles
        self.font = pygame.font.SysFont('Arial', 24)
        self.bg_animation_offset = 0
        self.eeg_points = 0

        # Add error handling for music loading
        try:
            pygame.mixer.music.load(r'C:\Users\munmu\OneDrive\Desktop\BCI_MotorImagery\game_music.mp3')
            pygame.mixer.music.play(-1)
        except pygame.error as e:
            print(f"Warning: Could not load or play music: {e}")
            print("Game will continue without music")

    def cleanup(self):
        """Safely clean up pygame resources"""
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.quit()
            pygame.quit()
        except pygame.error:
            pass

    def generate_obstacle(self):
        gap_size = 150
        obstacle_width = 50
        obstacle_x = self.screen_width
        top_height = np.random.randint(100, self.screen_height - gap_size - 100)
        bottom_height = self.screen_height - top_height - gap_size
        self.obstacles.append((obstacle_x, top_height, bottom_height))

    def draw_background(self):
        self.bg_animation_offset = (self.bg_animation_offset - 2) % self.screen_width
        pygame.draw.rect(self.screen, (50, 50, 100), (0, 0, self.screen_width, self.screen_height))
        for x in range(-self.screen_width, self.screen_width, 100):
            pygame.draw.rect(self.screen, (80, 80, 200), 
                           (x + self.bg_animation_offset, self.screen_height // 2, 50, 100))

    def draw_player(self):
        pygame.draw.circle(self.screen, (200, 0, 0), (int(self.player_x), int(self.player_y)), self.player_size)

    def draw_obstacles(self):
        for obstacle in self.obstacles:
            pygame.draw.rect(self.screen, (0, 200, 0), (obstacle[0], 0, 50, obstacle[1]))
            pygame.draw.rect(self.screen, (0, 200, 0), 
                           (obstacle[0], self.screen_height - obstacle[2], 50, obstacle[2]))

    def check_score(self):
        """Check if player has passed through obstacle gap and update score"""
        for i, (x, top, bottom) in enumerate(self.obstacles):
            # Define the gap area
            gap_top = top
            gap_bottom = self.screen_height - bottom
            
            # Check if player is in horizontal range of obstacle
            if (self.player_x > x and self.player_x < x + 50 and 
                i not in self.passed_obstacles):
                # Check if player is within the gap
                if (self.player_y > gap_top and 
                    self.player_y < gap_bottom):
                    self.score += 10
                    self.passed_obstacles.add(i)
                    return True
        return False

    def update_obstacles(self):
        """Update obstacles and clean up passed ones"""
        new_obstacles = []
        for i, (x, top, bottom) in enumerate(self.obstacles):
            new_x = x - self.obstacle_speed
            if new_x > -50:  # Keep obstacle if still on screen
                new_obstacles.append((new_x, top, bottom))
            else:  # Remove obstacle and its score tracking
                self.passed_obstacles = {j for j in self.passed_obstacles if j != i}
        self.obstacles = new_obstacles

    def show_score(self):
        score_surface = self.font.render(f"Score: {self.score}", True, (255, 255, 255))
        self.screen.blit(score_surface, (10, 10))

    def run_game(self, muse_bci):
        obstacle_timer = 0
        try:
            while self.running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                
                self.screen.fill(self.bg_color)
                self.draw_background()
                self.draw_player()
                self.draw_obstacles()
                self.update_obstacles()
                self.show_score()
                self.check_score()  # Check for scoring opportunities

                obstacle_timer += 1
                if obstacle_timer > 120:
                    self.generate_obstacle()
                    obstacle_timer = 0

                eeg_data = muse_bci.process_eeg()
                if eeg_data and eeg_data["movement"]:
                    self.velocity += self.lift

                self.velocity += self.gravity
                self.player_y += self.velocity

                if self.player_y > self.screen_height - self.player_size:
                    self.player_y = self.screen_height - self.player_size
                    self.velocity = 0

                if self.player_y < self.player_size:
                    self.player_y = self.player_size
                    self.velocity = 0

                pygame.display.flip()
                self.clock.tick(60)

        finally:
            self.cleanup()
            
        self.plot_eeg_analysis(muse_bci.eeg_data_log, self.score)

    def plot_eeg_analysis(self, eeg_log, score):
        print("Generating EEG analysis...")
        mu_power = [np.mean(np.square(data[:, 1])) for data in eeg_log if data.shape[0] > 1]
        beta_power = [np.mean(np.square(data[:, 2])) for data in eeg_log if data.shape[0] > 1]
        plt.figure(figsize=(10, 6))
        plt.plot(mu_power, label='Mu Power')
        plt.plot(beta_power, label='Beta Power')
        plt.title(f'EEG Analysis (Score: {score})')
        plt.xlabel('Time (chunks)')
        plt.ylabel('Power')
        plt.legend()
        plt.show()

# Main Function
def main():
    print("Starting BCI Motor Imagery Game...")
    print("Ensure Muse is streaming via BlueMuse.")
    bci = MuseBCI()
    bci.connect_muse()
    print("Calibration required. Please follow the instructions.")
    bci.calibrate()
    print("Launching game!")
    game = PygameBCI()
    game.run_game(bci)

if __name__ == "__main__":
    main()


