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
            #self.client.ALTextToSpeech.getAvailableLanguages()
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
        self.client.ALMotion.rest()
        print("Robot is at rest.")

    def is_awake(self):
        """Returns True if the robot is awake."""
        try:
             # robotIsWakeUp returns True if awake
             return self.client.ALMotion.robotIsWakeUp()
        except Exception:
             return False

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
            # 1. Set ALTracker Mode (Low-level)
            self.client.ALTracker.setMode(mode_name)
            self.client.ALTracker.setMode(mode_name) # Send command twice for robustnes
            self.logger.info("TrackingModeSet", {"mode": mode_name})
            
            # 2. Set ALBasicAwareness Mode (High-level Social)
            # Map standard modes to BasicAwareness modes
            ba_mode = mode_name
            if mode_name == "Move":
                ba_mode = "MoveContextually"
            elif mode_name == "WholeBody":
                # "BodyRotation" allows rotation to face the human.
                ba_mode = "BodyRotation"
            
            try:
                self.client.ALBasicAwareness.setTrackingMode(ba_mode)
                self.logger.info("BasicAwarenessModeSet", {"mode": ba_mode})
            except Exception as e:
                # BasicAwareness might not be available or proxy error
                print(f"Warning: Could not set BasicAwareness mode: {e}")
        except NaoqiProxyError as e:
            print(f"Failed to set tracking mode: {e}")

    def stop_tracking(self):
        """Stops the native tracker and sets mode to Head for safety."""
        print("Stopping native tracker...")
        try:
            self.client.ALTracker.stopTracker()
            self.client.ALTracker.unregisterAllTargets()
            # Set to a neutral mode
            self.client.ALTracker.setMode("Head")
            self.logger.info("TrackingStopped")
        except NaoqiProxyError as e:
            print(f"Failed to stop tracker: {e}")

    def get_tracking_mode(self):
        """Returns the current tracking mode."""
        try:
             return self.client.ALTracker.getMode()
        except NaoqiProxyError as e:
             print(f"Failed to get tracking mode: {e}")
             return None

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

    def get_joint_temperatures(self):
        """
        Fetches the temperature of all major joints.
        Returns:
            dict: {JointName: Temperature_in_Celsius}
        """
        # Define the list of keys we want to monitor
        # These are standard ALMemory keys for Pepper
        joint_names = [
            "HeadYaw", "HeadPitch",
            "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw",
            "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw",
            "LHipYawPitch", "LHipRoll", "LHipPitch", "LKneePitch", "LAnklePitch", "LAnkleRoll",
            "RHipYawPitch", "RHipRoll", "RHipPitch", "RKneePitch", "RAnklePitch", "RAnkleRoll",
            "HipRoll", "HipPitch", "KneePitch" # Common variants or Nao/Pepper differences
        ]
        
        # Construct ALMemory keys: Device/SubDeviceList/[JointName]/Temperature/Sensor/Value
        memory_keys = [f"Device/SubDeviceList/{name}/Temperature/Sensor/Value" for name in joint_names]
        
        try:
            # Use getListData to fetch all in one call
            temps = self.client.ALMemory.getListData(memory_keys)
            
            result = {}
            for i, name in enumerate(joint_names):
                val = temps[i]
                if val is not None:
                     result[name] = val
            
            return result
        except NaoqiProxyError as e:
            # Don't spam logs, this is a polling function
            if self.verbose:
                 print(f"Failed to get temperatures: {e}")
            return {}

    def get_temperature_diagnosis(self):
        """
        Retrieves the temperature diagnosis from ALBodyTemperature.
        Returns:
            list: [SeverityLevel (int), FailedDevices (list<str>)]
            Severity: 0=Negligible, 1=Serious, 2=Critical
        """
        try:
            # ALBodyTemperature.getTemperatureDiagnosis returns [int, [str, str, ...]]
            result = self.client.ALBodyTemperature.getTemperatureDiagnosis()
            
            if result is not None:
                return result
            
            # FALLBACK: Native diagnosis failed (None). Try manual ALMemory check.
            if self.verbose:
                print("Native diagnosis returned None. Falling back to ALMemory sensors.")
            
            temps = self.get_joint_temperatures()
            if not temps:
                return [2, ["SensorDataMissing"]]
            
            # Check thresholds (defaults matching typical Naoqi limits)
            # 80°C is the critical shutdown point for Pepper/Nao joints
            failed_joints = []
            max_severity = 0
            
            for joint, temp in temps.items():
                if temp >= 80:
                    failed_joints.append(joint)
                    max_severity = 2
                elif temp >= 65 and max_severity < 1:
                    failed_joints.append(joint)
                    max_severity = 1
            
            if max_severity > 0:
                return [max_severity, failed_joints]
                
            return [0, []]

        except Exception as e:
            if self.verbose:
                 print(f"Failed to get temperature diagnosis: {e}")
            return [2, ["ExceptionCheckLogs"]]