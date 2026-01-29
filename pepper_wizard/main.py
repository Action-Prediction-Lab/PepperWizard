# Main application entry point
import argparse
import sys
from . import cli
from .config import load_config
from .robot_client import RobotClient
from .command_handler import CommandHandler

from prompt_toolkit import PromptSession

def main():
    """Main function to run the PepperWizard application."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy-ip", type=str, default="pepper-robot-env",
                        help="IP address of the PepperBox shim server.")
    parser.add_argument("--proxy-port", type=int, default=5000,
                        help="Port number of the PepperBox shim server.")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose debug output.")
    parser.add_argument("--session-id", type=str, default=None,
                        help="Optional session identifier for the log file.")
    args = parser.parse_args()

    # Initialise Logging
    from .logger import setup_logging, get_logger
    setup_logging(session_id=args.session_id, verbose=args.verbose)
    logger = get_logger("Main")

    cli.print_title()
    logger.info("ApplicationStarted", {"proxy_ip": args.proxy_ip, "proxy_port": args.proxy_port})

    config = load_config()

    try:
        robot_client = RobotClient(host=args.proxy_ip, port=args.proxy_port, verbose=args.verbose)
    except Exception as e:
        logger.error("RobotConnectionFailed", {"error": str(e)})
        sys.exit(1)

    print(" --- PepperWizard Ready ---")

    command_handler = CommandHandler(robot_client, config, verbose=args.verbose)
    
    # Teleop State (shared between CLI menu and CommandHandler)
    default_mode = config.teleop_config.get("default_mode", "Joystick")
    initial_social_state = robot_client.get_social_state()
    social_mode_label = "Autonomous" if initial_social_state else "Disabled"
    
    is_awake = robot_client.is_awake()
    robot_state_label = "Wake" if is_awake else "Rest"

    initial_tracking_mode = robot_client.get_tracking_mode() or "Head"

    teleop_state = {
        "mode": default_mode,
        "social_mode": social_mode_label,
        "robot_state": robot_state_label,
        "tracking_mode": initial_tracking_mode,
        "battery": None
    } 

    # Start battery polling thread
    import threading
    import time
    def poll_battery():
        while True:
            try:
                charge = robot_client.get_battery_charge()
                teleop_state['battery'] = charge
            except Exception as e:
                print(f"Battery Poll Error: {e}")
            time.sleep(10) # Poll every 10 seconds

    battery_thread = threading.Thread(target=poll_battery, daemon=True)
    battery_thread.start()

    try:
        while True:
            # Update dynamic state
            teleop_state['teleop_running'] = command_handler.is_teleop_running()

            # command = cli.user_input(session, "Enter Command: ")
            command = cli.show_main_menu(teleop_state)
            
            if command is None or command == 'exit': # Handle Cancel or Exit
                print("Shutting down PepperWizard...")
                logger.info("ApplicationShutdown", {"reason": "UserExit"})
                break
            
            command_handler.handle_command(command, teleop_state)
            
    except KeyboardInterrupt:
        print("\nCaught KeyboardInterrupt. Shutting down...")
        logger.info("ApplicationShutdown", {"reason": "KeyboardInterrupt"})
    finally:
        command_handler.cleanup()
    
    print(" --- Exiting Pepper Wizard ---")

if __name__ == "__main__":
    main()