# Main application entry point
import argparse
import sys
from . import cli
from .config import load_config
from .robot_client import RobotClient
from .command_handler import CommandHandler

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

    cli.print_title()

    config = load_config()

    try:
        robot_client = RobotClient(host=args.proxy_ip, port=args.proxy_port, verbose=args.verbose)
    except Exception:
        sys.exit(1)

    print(" --- PepperWizard Ready ---")
    cli.print_help()

    command_handler = CommandHandler(robot_client, config, verbose=args.verbose)

    try:
        while True:
            command = cli.user_input("Enter Command: ")
            
            if command.lower() == 'exit':
                print("Shutting down PepperWizard...")
                break
            
            command_handler.handle_command(command)
            
    except KeyboardInterrupt:
        print("\nCaught KeyboardInterrupt. Shutting down...")
    finally:
        command_handler.cleanup()
    
    print(" --- Exiting Pepper Wizard ---")

if __name__ == "__main__":
    main()