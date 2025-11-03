# Handles all communication with the robot
from naoqi_proxy import NaoqiClient, NaoqiProxyError

class RobotClient:
    """A wrapper around the NaoqiClient to provide a high-level API for controlling the robot."""
    def __init__(self, host, port, verbose=False):
        self.verbose = verbose
        try:
            self.client = NaoqiClient(host=host, port=port)
            # Ping a service to ensure connection
            self.client.ALTextToSpeech.getAvailableLanguages()
            print("--- PepperBox Proxy Connected ---")
        except NaoqiProxyError as e:
            print(f"Failed to connect to PepperBox proxy at {host}:{port}")
            print(f"Error: {e}")
            print("Please ensure the PepperBox container is running and accessible.")
            raise

    def wake_up(self):
        """Wakes up the robot."""
        print("Waking up robot...")
        self.client.ALMotion.wakeUp()
        print("Robot is awake.")

    def rest(self):
        """Puts the robot to rest."""
        print("Putting robot to rest...")
        self.client.ALMotion.rest()
        print("Robot is at rest.")

    def talk(self, message):
        """Makes the robot say a message."""
        try:
            if self.verbose:
                print(f"[DEBUG] RobotClient.talk: '{message}'")
            self.client.ALTextToSpeech.say(message)
        except NaoqiProxyError as e:
            print(f"TTS Error: {e}")

    def animated_talk(self, animation_tag, message):
        """Makes the robot say a message with an animation."""
        try:
            say_string = f"^startTag({animation_tag}) {message} ^stopTag({animation_tag})"
            if self.verbose:
                print(f"[DEBUG] RobotClient.animated_talk: '{say_string}'")
            self.client.ALAnimatedSpeech.say(say_string)
        except NaoqiProxyError as e:
            print(f"TTS Error: {e}")

    def play_animation_blocking(self, animation_name):
        """Plays an animation and waits for it to finish."""
        try:
            if self.verbose:
                print(f"[DEBUG] RobotClient.play_animation_blocking with tag: '{animation_name}'")
            # runTag is blocking by default
            self.client.ALAnimationPlayer.runTag(animation_name)
        except NaoqiProxyError as e:
            print(f"Animation Error: {e}")

    def get_battery_charge(self):
        """Returns the robot's battery charge percentage."""
        try:
            return self.client.ALBattery.getBatteryCharge()
        except NaoqiProxyError as e:
            print(f"Could not get battery status: {e}")
            return None

    def toggle_tracking_mode(self, current_mode_index, tracking_modes):
        """Toggles the robot's tracking mode."""
        new_mode_index = (current_mode_index + 1) % len(tracking_modes)
        new_mode = tracking_modes[new_mode_index]
        print(f"Setting tracking mode to: {new_mode}")
        self.client.ALTracker.setMode(new_mode)
        self.client.ALTracker.setMode(new_mode) # Send command twice
        return new_mode_index

    def toggle_social_state(self, social_state_enabled):
        """Toggles the robot's social state."""
        new_state = not social_state_enabled
        self.client.ALAutonomousLife.setAutonomousAbilityEnabled("BackgroundMovement", new_state)
        self.client.ALAutonomousLife.setAutonomousAbilityEnabled("BasicAwareness", new_state)
        self.client.ALAutonomousLife.setAutonomousAbilityEnabled("ListeningMovement", new_state)
        self.client.ALAutonomousLife.setAutonomousAbilityEnabled("SpeakingMovement", new_state)
        self.client.ALAutonomousLife.setAutonomousAbilityEnabled("AutonomousBlinking", new_state)
        self.client.ALFaceDetection.setTrackingEnabled(new_state)
        self.client.ALBasicAwareness.setEnabled(new_state)
        
        basic_awareness_state = self.client.ALBasicAwareness.isEnabled()
        print(f"SocialState Status: {basic_awareness_state}")
        return new_state

    def move_toward(self, x, y, theta):
        """Commands the robot to move."""
        try:
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