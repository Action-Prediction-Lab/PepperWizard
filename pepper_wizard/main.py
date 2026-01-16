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
    args = parser.parse_args()

    # Initialise Logging
    from .logger import setup_logging, get_logger
    setup_logging(verbose=args.verbose)
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

    try:
        while True:
            # command = cli.user_input(session, "Enter Command: ")
            command = cli.show_main_menu()
            
            if command is None or command == 'exit': # Handle Cancel or Exit
                print("Shutting down PepperWizard...")
                logger.info("ApplicationShutdown", {"reason": "UserExit"})
                break
            
            command_handler.handle_command(command)
            
    except KeyboardInterrupt:
        print("\nCaught KeyboardInterrupt. Shutting down...")
        logger.info("ApplicationShutdown", {"reason": "KeyboardInterrupt"})
    finally:
        command_handler.cleanup()
    
    print(" --- Exiting Pepper Wizard ---")

if __name__ == "__main__":
    main()