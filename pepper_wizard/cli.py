# Command-line interface (UI) elements

def print_title():
    """Prints the application title."""
    print("__________                                   __      __.__                         .__")
    print("\______   \ ____ ______ ______   ___________/  \    /  \__|____________ _______  __| /")
    print(" |     ___// __  \____  \____ \_/ __ \_  __ \   \/\   /  \___   /\__  \_  __ \/ __  | ")
    print(" |    |   \  ___/|  |_> >  |_> >  ___/|  | \/        /|  |/    /  / __ \|  | \/ /_/ | ")
    print(" |____|    \___  >   __/|   __/ \___  >__|    \_/\  / |__/_____ \(____  /__|  \____ | ")
    print("                 |__|   |__|                      \/           \/     \/           \/ ")
    print("---------------------------------------------------------------------------------------")
    print(" - jwgcurrie V0.2")

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

def pepper_talk_session(robot_client, config, verbose=False):
    """Handles an interactive unified Text-to-Speech session with emoticon-triggered animations."""
    print(" --- Entering Unified PepperTalk --- (prefix with :) :( XD for animations, type /q to exit)")
    while True:
        line = user_input("Pepper: ")
        if line.lower() == '/q':
            break

        if verbose:
            print(f"[DEBUG] Raw input: '{line}'")

        found_emoticon = None
        animation_tag = None
        message_to_speak = line

        # Check for emoticons anywhere in the line
        for emoticon, tag in config.emoticon_map.items():
            if emoticon in line:
                if verbose:
                    print(f"[DEBUG] Found emoticon: '{emoticon}' which maps to animation name: '{tag}'")
                found_emoticon = emoticon
                animation_tag = tag # The tag from the emoticon map IS the animation name (e.g., 'happy')
                if verbose:
                    print(f"[DEBUG] Found animation tag: '{animation_tag}'")
                message_to_speak = line.replace(emoticon, '').strip()
                if verbose:
                    print(f"[DEBUG] Message to speak: '{message_to_speak}'")
                break
        
        if found_emoticon and animation_tag:
            if verbose:
                print(f"[DEBUG] Calling animated_talk with tag: '{animation_tag}' and message: '{message_to_speak}'")
            if message_to_speak:
                robot_client.animated_talk(animation_tag, message_to_speak)
            else:
                print("No message provided after emoticon. Speaking with animation.")
                robot_client.animated_talk(animation_tag, "")
        elif message_to_speak:
            if verbose:
                print(f"[DEBUG] Calling talk with message: '{message_to_speak}'")
            robot_client.talk(message_to_speak)
        else:
            print("No message to speak.")