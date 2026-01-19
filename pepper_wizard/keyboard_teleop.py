import threading
import time
from .teleop import BaseTeleopController, teleop_running
from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.formatted_text import HTML

class KeyboardTeleopController(BaseTeleopController):
    """
    Control the robot using keyboard inputs via prompt_toolkit.
    Implements a watchdog safety mechanism to stop the robot on key release.
    """
    def __init__(self, robot_client, config, verbose=False):
        super(KeyboardTeleopController, self).__init__(robot_client, config, verbose)
        
        self.kb_config = self.config.keyboard_config
        self.watchdog_timeout = self.kb_config.get("watchdog_timeout", 0.2)
        
        # Current velocities
        self.vx = 0.0
        self.vy = 0.0
        self.vtheta = 0.0
        
        # Speed multipliers (can be adjusted at runtime)
        self.speed_multiplier = 1.0
        
        # Last key press time for watchdog
        self.last_interaction_time = 0
        self.active_keys = set()
        self.lock = threading.Lock()
        
        # Application instance
        self.app = None

    def run(self):
        """Main loop for keyboard teleop."""
        print(" --- Keyboard Teleoperation Started ---")
        self.logger.info("KeyboardTeleopStarted")
        print(" Controls: Arrow Keys / WASD to move. +/- to adjust speed.")
        print(" Press 'q' or 'Ctrl-C' to exit.")
        
        self.robot_client.set_stiffnesses("Body", 1.0)
        self.logger.info("StiffnessSet", {"body_part": "Body", "value": 1.0})

        # Start the safety watchdog thread
        self.watchdog_thread = threading.Thread(target=self._watchdog_loop)
        self.watchdog_thread.daemon = True
        self.watchdog_thread.start()

        # Setup prompt_toolkit application
        kb = KeyBindings()
        
        # Helper to register keys
        mapping = self.kb_config.get("key_mapping", {})
        
        @kb.add('q')
        @kb.add('c-c')
        def _(event):
            event.app.exit()

        # Dynamic binding based on config is tricky with decorators, 
        # so we'll bind common keys and map them inside the handler.
        keys_to_bind = ['up', 'down', 'left', 'right', 'w', 's', 'a', 'd', '+', '-', '=']
        
        for k in keys_to_bind:
            @kb.add(k)
            def _(event, key_bind=k):
                self._handle_key(key_bind)

        # Simple UI
        def get_text():
            return HTML(
                f"<b>Keyboard Teleop Running</b>\n"
                f"Speed: {self.speed_multiplier:.1f}x\n"
                f"Cmd: x={self.vx:.2f}, y={self.vy:.2f}, theta={self.vtheta:.2f}\n"
                f"<i>Press 'q' to stop</i>"
            )

        self.app = Application(
            layout=Layout(Window(content=FormattedTextControl(get_text))),
            key_bindings=kb,
            full_screen=False,
            refresh_interval=0.1
        )
        
        try:
            self.app.run()
        except Exception as e:
            print(f"Keyboard Teleop Error: {e}")
        finally:
             # Stop signal
            teleop_running.set()
            self.stop_robot()
            print(" --- Keyboard Teleoperation Finished ---")

    def _handle_key(self, key_name):
        """Process a key press event."""
        with self.lock:
            self.last_interaction_time = time.time()
            
            mapping = self.kb_config.get("key_mapping", {})

            if key_name == '=': key_name = '+' # Common mapping
            
            action = mapping.get(key_name)
            if not action:
                if key_name == 'up': action = 'forward'
                elif key_name == 'down': action = 'backward'
                elif key_name == 'left': action = 'turn_left'
                elif key_name == 'right': action = 'turn_right'

            if action == 'increase_speed':
                self.speed_multiplier = min(2.0, self.speed_multiplier + 0.1)
                return
            elif action == 'decrease_speed':
                self.speed_multiplier = max(0.1, self.speed_multiplier - 0.1)
                return

            # Get base speeds
            speeds = self.config.teleop_config.get("speeds", {})
            base_vx = speeds.get("v_x", 0.2) * self.speed_multiplier
            base_vy = speeds.get("v_y", 0.2) * self.speed_multiplier
            base_vtheta = speeds.get("v_theta", 0.5) * self.speed_multiplier

            if action == 'forward':
                self.vx = base_vx
            elif action == 'backward':
                self.vx = -base_vx
            elif action == 'strafe_left':
                self.vy = base_vy
            elif action == 'strafe_right':
                self.vy = -base_vy
            elif action == 'turn_left':
                self.vtheta = base_vtheta
            elif action == 'turn_right':
                self.vtheta = -base_vtheta
            
            self.robot_client.move_toward(self.vx, self.vy, self.vtheta)
            if self.app:
                self.app.invalidate()


    def _watchdog_loop(self):
        """Monitor key activity and stop robot if idle."""
        while not teleop_running.is_set():
            time.sleep(0.05)
            with self.lock:
                if time.time() - self.last_interaction_time > self.watchdog_timeout:
                    # Timeout reached, stop robot
                    if self.vx != 0 or self.vy != 0 or self.vtheta != 0:
                        self.vx = 0
                        self.vy = 0
                        self.vtheta = 0
                        self.robot_client.move_toward(0, 0, 0)
