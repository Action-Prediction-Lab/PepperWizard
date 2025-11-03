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
    print("  T    - Enter Unified Talk Mode")
    print("  Bat  - Check Robot Battery Status")
    print("  q    - Quit Joystick Teleoperation")
    print("  help - Show this help message")
    print("  exit - Exit PepperWizard application")

def user_input(prompt):
    """Gets input from the user."""
    return input(prompt)

def print_talk_mode_help():
    """Prints the help message for the unified talk mode."""
    print("--- Talk Mode Help ---")
    print("Speak any sentence directly.")
    print("Trigger animations using:")
    print("  - Emoticons: Add an emoticon (e.g., :), XD) anywhere in your sentence.")
    print("  - Hotkeys: Add a hotkey (e.g., \\N, \\Y) anywhere in your sentence.")
    print("Commands:")
    print("  /help - Show this help message")
    print("  /q    - Quit talk mode")
    print("---------------------")

def pepper_talk_session(robot_client, config, verbose=False):
    """Handles an interactive unified Text-to-Speech session with emoticon-triggered animations."""
    print(" --- Entering Unified PepperTalk --- (type /help for options, /q to exit)")
    while True:
        line = user_input("Pepper: ")
        if line.lower() == '/q':
            break
        if line.lower() == '/help':
            print_talk_mode_help()
            continue

        if verbose:
            print(f"[DEBUG] Raw input: '{line}'")

        found_emoticon = False
        found_hotkey = False

        # 1. Check for emoticons
        # Prioritize longer emoticons to avoid partial matches
        sorted_emoticons = sorted(config.emoticon_map.keys(), key=len, reverse=True)
        for emoticon in sorted_emoticons:
            if emoticon in line:
                if verbose:
                    print(f"[DEBUG] Found emoticon: '{emoticon}'")
                animation_tag = config.emoticon_map[emoticon]
                if verbose:
                    print(f"[DEBUG] Found animation tag: '{animation_tag}'")
                
                message_to_speak = line.replace(emoticon, '').strip()
                if verbose:
                    print(f"[DEBUG] Message to speak: '{message_to_speak}'")

                robot_client.animated_talk(animation_tag, message_to_speak)
                found_emoticon = True
                break
        
        if found_emoticon:
            continue

        # 2. If no emoticon, check for quick response hotkeys (e.g., \N)
        for key, response_data in config.quick_responses.items():
            hotkey = f"\\{key}"
            if hotkey in line:
                if verbose:
                    print(f"[DEBUG] Found hotkey: '{hotkey}'")
                animation_tag = response_data.get('animation')
                if animation_tag:
                    if verbose:
                        print(f"[DEBUG] Found animation tag: '{animation_tag}'")
                    message_to_speak = line.replace(hotkey, '').strip()
                    if verbose:
                        print(f"[DEBUG] Message to speak: '{message_to_speak}'")
                    
                    robot_client.animated_talk(animation_tag, message_to_speak)
                    found_hotkey = True
                    break
                else:
                    if verbose:
                        print(f"[DEBUG] Hotkey '{hotkey}' found, but no animation defined for it.")

        if found_hotkey:
            continue

        # 3. If nothing else, perform regular talk
        if line:
            if verbose:
                print(f"[DEBUG] No emoticon or hotkey found. Calling talk with message: '{line}'")
            robot_client.talk(line)