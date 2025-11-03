# Command-line interface (UI) elements

def print_title():
    """Prints the application title."""
    print("__________                                   __      __.__                         .__")
    print("\______   \ ____ ______ ______   ___________/  \    /  \__|____________ _______  __| /")
    print(" |     ___// __  \____  \____ \_/ __ \_  __ \   \/\   /  \___   /\__  \_  __ \/ __  | ")
    print(" |    |   \  ___/|  |_> >  |_> >  ___/|  | \/        /|  |/    /  / __ \|  | \/ /_/ | ")
    print(" |____|    \___  >   __/|   __/ \___  >__|    \_/\  / |__/_____ \(____  /__|  \____ | ")
    print("               |__|   |__|                       \/           \/     \/           \/ ")
    print("---------------------------------------------------------------------------------------")
    print(" - jwgcurrie (Refactored for modular architecture)")

def print_help():
    """Prints the help message."""
    print("Available commands:")
    print("  A    - Toggle Autonomous/Social State")
    print("  J    - Start Joystick Teleoperation")
    print("  W    - Wake Up Robot")
    print("  R    - Put Robot to Rest")
    print("  T    - Enter Text-to-Speech mode")
    print("  AT   - Enter Animated Text-to-Speech mode")
    print("  Bat  - Check Robot Battery Status")
    print("  q    - Quit Joystick Teleoperation")
    print("  help - Show this help message")
    print("  exit - Exit PepperWizard application")

def user_input(prompt):
    """Gets input from the user."""
    return input(prompt)

def pepper_talk_session(robot_client):
    """Handles an interactive Text-to-Speech session."""
    print(" --- Entering PepperTalk --- (type 'q' to exit)")
    while True:
        line = user_input("Pepper: ")
        if line.lower() == 'q':
            break
        robot_client.talk(line)

def animated_pepper_talk_session(robot_client, animations):
    """Handles an interactive animated Text-to-Speech session."""
    if not animations:
        print("Animations not loaded. Please check the animations.json file.")
        return

    print(" --- Entering Animated PepperTalk ---")
    print("Available animations:")
    for key, value in animations.items():
        print(f"  {value} - {key}")
    
    animation_key = user_input("Select an animation key: ")
    animation_tag = None
    for key, value in animations.items():
        if value.lower() == animation_key.lower():
            animation_tag = key
            break
    
    if not animation_tag:
        print("Invalid animation key.")
        return

    while True:
        line = user_input(f"Pepper ({animation_tag}): ")
        if line.lower() == 'q':
            break
        robot_client.animated_talk(animation_tag, line)