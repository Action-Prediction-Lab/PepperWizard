# Handles all communication with the robot
from naoqi_proxy import NaoqiClient, NaoqiProxyError

class RobotClient:
    """A wrapper around the NaoqiClient to provide a high-level API for controlling the robot."""
    def __init__(self, host, port, verbose=False):
        from .logger import get_logger
        self.logger = get_logger("RobotClient")
        
        self.verbose = verbose
        
        # Throttling for high-frequency logs
        self.last_move_log_time = 0
        self.move_log_interval = 0.5 # Log max every 0.5 seconds (2Hz)
        try:
            self.client = NaoqiClient(host=host, port=port)
            # Ping a service to ensure connection
            self.client.ALTextToSpeech.getAvailableLanguages()
            self.client.ALTextToSpeech.getAvailableLanguages()
        except NaoqiProxyError as e:
            print(f"Failed to connect to PepperBox proxy at {host}:{port}")
            print(f"Error: {e}")
            print("Please ensure the PepperBox container is running and accessible.")
            raise

    def wake_up(self):
        """Wakes up the robot."""
        print("Waking up robot...")
        self.logger.info("WakeUp")
        self.client.ALMotion.wakeUp()
        print("Robot is awake.")

    def rest(self):
        """Puts the robot to rest."""
        print("Putting robot to rest...")
        self.logger.info("Rest")
        self.client.ALMotion.rest()
        print("Robot is at rest.")

    def talk(self, message):
        """Makes the robot say a message."""
        try:
            if self.verbose:
                print(f"[DEBUG] RobotClient.talk: '{message}'")
            self.logger.info("Speech", {"text": message, "type": "plain"})
            self.client.ALTextToSpeech.say(message)
        except NaoqiProxyError as e:
            print(f"TTS Error: {e}")

    def animated_talk(self, animation_tag, message):
        """Makes the robot say a message with an animation."""
        try:
            say_string = f"^startTag({animation_tag}) {message} ^stopTag({animation_tag})"
            if self.verbose:
                print(f"[DEBUG] RobotClient.animated_talk: '{say_string}'")
            self.logger.info("Speech", {"text": message, "type": "animated", "animation": animation_tag})
            self.client.ALAnimatedSpeech.say(say_string)
        except NaoqiProxyError as e:
            print(f"TTS Error: {e}")

    def play_animation_blocking(self, animation_name):
        """Plays an animation and waits for it to finish."""
        try:
            if self.verbose:
                print(f"[DEBUG] RobotClient.play_animation_blocking with tag: '{animation_name}'")
            # runTag is blocking by default
            self.logger.info("AnimationStarted", {"animation": animation_name})
            self.client.ALAnimationPlayer.runTag(animation_name)
        except NaoqiProxyError as e:
            print(f"Animation Error: {e}")

    def get_battery_charge(self):
        """Returns the robot's battery charge percentage."""
        try:
            charge = self.client.ALBattery.getBatteryCharge()
            self.logger.info("BatteryStatus", {"charge": charge})
            return charge
        except NaoqiProxyError as e:
            print(f"Could not get battery status: {e}")
            return None

    def set_tracking_mode(self, mode_name):
        """Sets the robot's tracking mode directly."""
        print(f"Setting tracking mode to: {mode_name}")
        try:
            self.client.ALTracker.setMode(mode_name)
            self.client.ALTracker.setMode(mode_name) # Send command twice for robustnes
            self.logger.info("TrackingModeSet", {"mode": mode_name})
        except NaoqiProxyError as e:
            print(f"Failed to set tracking mode: {e}")

    def toggle_tracking_mode(self, current_mode_index, tracking_modes):
        """Toggles the robot's tracking mode."""
        new_mode_index = (current_mode_index + 1) % len(tracking_modes)
        new_mode = tracking_modes[new_mode_index]
        self.set_tracking_mode(new_mode)
        return new_mode_index

    def set_social_state(self, enabled):
        """Idempotently sets the robot's social state."""
        try:
            self.client.ALAutonomousLife.setAutonomousAbilityEnabled("BackgroundMovement", enabled)
            self.client.ALAutonomousLife.setAutonomousAbilityEnabled("BasicAwareness", enabled)
            self.client.ALAutonomousLife.setAutonomousAbilityEnabled("ListeningMovement", enabled)
            self.client.ALAutonomousLife.setAutonomousAbilityEnabled("SpeakingMovement", enabled)
            self.client.ALAutonomousLife.setAutonomousAbilityEnabled("AutonomousBlinking", enabled)
            self.client.ALFaceDetection.setTrackingEnabled(enabled)
            self.client.ALBasicAwareness.setEnabled(enabled)
            
            self.logger.info("SocialStateSet", {"enabled": enabled})
            return enabled
        except NaoqiProxyError as e:
            print(f"Error setting social state: {e}")
            return None

    def get_social_state(self):
        """Returns True if social state (Basic Awareness) is active."""
        try:
            return self.client.ALBasicAwareness.isEnabled()
        except Exception:
            return False

    def toggle_social_state(self, social_state_enabled):
        """Toggles the robot's social state."""
        new_state = not social_state_enabled
        return self.set_social_state(new_state)

    def move_toward(self, x, y, theta):
        """Commands the robot to move."""
        import time 
        try:
            # Throttled Logging
            now = time.time()
            if now - self.last_move_log_time >= self.move_log_interval:
                self.logger.info("MoveCommand", {"x": x, "y": y, "theta": theta})
                self.last_move_log_time = now
                
            self.client.ALMotion.moveToward(x, y, theta)
        except NaoqiProxyError as e:
            print(f"Failed to send move command: {e}")
            raise

    def stop_move(self):
        """Stops the robot's movement."""
        self.client.ALMotion.stopMove()

    def set_stiffnesses(self, body_part, stiffness):
        """Sets the stiffness of a body part."""
        self.client.ALMotion.setStiffnesses(body_part, stiffness)

    def get_angles(self, names, use_sensors=True):
        """Gets the angles of joins."""
        return self.client.ALMotion.getAngles(names, use_sensors)
        
    def set_angles(self, names, angles, fraction_max_speed):
        """Sets the angles of joints (Absolute Position Control)."""
        self.client.ALMotion.setAngles(names, angles, fraction_max_speed)