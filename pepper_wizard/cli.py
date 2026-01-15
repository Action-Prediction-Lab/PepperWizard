# Command-line interface (UI) elements
from .spell_checker import SpellChecker
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

def print_title():
    """Prints the application title."""
    print("__________                                   __      __.__                         .__")
    print("\______   \ ____ ______ ______   ___________/  \    /  \__|____________ _______  __| /")
    print(" |     ___// __  \____  \____ \_/ __ \_  __ \   \/\   /  \___   /\__  \_  __ \/ __  | ")
    print(" |    |   \  ___/|  |_> >  |_> >  ___/|  | \/        /|  |/    /  / __ \|  | \/ /_/ | ")
    print(" |____|    \___  >   __/|   __/ \___  >__|    \_/\  / |__/_____ \(____  /__|  \____ | ")
    print("                 |__|   |__|                      \/           \/     \/           \/ ")
    print("---------------------------------------------------------------------------------------")
    print(" - jwgcurrie")
    print(" - V 2.0")

def print_help():
    """Prints the help message."""
    print("Available commands:")
    print("  A    - Toggle Autonomous/Social State")
    print("  J    - Start Joystick Teleoperation")
    print("  W    - Wake Up Robot")
    print("  R    - Put Robot to Rest")
    print("  T    - Enter Talk Mode")
    print("  Bat  - Check Battery Status")
    print("  q    - Quit Joystick Teleoperation")
    print("  gm   - Gaze at NAOqi marker")
    print("  help - Show this help message")
    print("  exit - Exit PepperWizard application")

def user_input(session, prompt_text="Pepper: "):
    """Gets input from the user using prompt_toolkit session."""
    try:
        return session.prompt(prompt_text)
    except (EOFError, KeyboardInterrupt):
        return None

def print_talk_mode_help():
    """Prints the help message for the talk mode."""
    print("--- Talk Mode Help ---")
    print("Speak any sentence directly.")
    print("Trigger animations using:")
    print("  - Emoticons: Add an emoticon (e.g., :), :( )) anywhere in your sentence.")
    print("  - Hotkeys: Add a hotkey (e.g., /N, /Y) anywhere in your sentence.")
    print("Commands:")
    print("  /help - Show this help message")
    print("  /q    - Quit talk mode")
    print("---------------------")

def confirm_correction(session, suggestion, original):
    """
    Presents a Tab-Toggle interface to choose between suggestion and original text.
    """
    bindings = KeyBindings()
    
    # State validation: [is_showing_suggestion]
    state = [True]

    @bindings.add('tab')
    def _(event):
        state[0] = not state[0]
        buff = event.app.current_buffer
        # Swap text
        buff.text = suggestion if state[0] else original
        # Move cursor to end
        buff.cursor_position = len(buff.text)

    def get_prompt_message():
        if state[0]:
            return HTML("<b><ansicyan>Pepper (Suggestion):</ansicyan></b> ")
        else:
            return HTML("<b><ansiwhite>Pepper (Raw):</ansiwhite></b> ")

    def get_bottom_toolbar():
        if state[0]:
            return HTML(" <b>[Tab]</b> Revert to Raw  <b>[Enter]</b> Confirm Suggestion")
        else:
            return HTML(" <b>[Tab]</b> Apply Suggestion  <b>[Enter]</b> Confirm Raw Input")

    
    result = session.prompt(
        get_prompt_message,
        default=suggestion,
        key_bindings=bindings,
        bottom_toolbar=get_bottom_toolbar
    )
    return result

def get_verified_text(session, spell_checker, text):
    """Checks spelling and runs confirmation loop if needed."""
    if not text.strip() or not spell_checker:
        return text
    
    try:
        corrected = spell_checker.correct_sentence(text)
    except Exception as e:
        print(f"Spellcheck error: {e}")
        return text

    # Basic cleanup normalization for comparison
    if corrected.strip() == text.strip():
        return text

    # They differ, run confirmation
    return confirm_correction(session, corrected, text)


def pepper_talk_session(robot_client, config, verbose=False):
    """Handles an interactive Text-to-Speech session with emoticon-triggered animations."""
    print(" --- Entering PepperTalk --- (type /help for options, /q to exit)")

    # Initialize spell checker
    try:
        spell_checker = SpellChecker()
        print("Spell Checker Initialized.")
    except Exception as e:
        print(f"Warning: Could not initialize spell checker: {e}")
        spell_checker = None

    # Initialize PromptSession
    session = PromptSession()

    while True:
        line = user_input(session, "Pepper: ")
        if line is None: # Handle Ctrl+C/D
            break

        if line.lower() == '/q':
            break
        if line.lower() == '/help':
            print_talk_mode_help()
            continue

        if verbose:
            print(f"[DEBUG] Raw input: '{line}'")

        found_emoticon = False
        found_hotkey = False

        # 1. Check for emoticons (non-blocking animation)
        sorted_emoticons = sorted(config.emoticon_map.keys(), key=len, reverse=True)
        for emoticon in sorted_emoticons:
            if emoticon in line:
                if verbose:
                    print(f"[DEBUG] Found emoticon: '{emoticon}'")
                animation_tag = config.emoticon_map[emoticon]
                
                message_part = line.replace(emoticon, '').strip()
                message_to_speak = get_verified_text(session, spell_checker, message_part)

                if verbose:
                    print(f"[DEBUG] Final Message to speak: '{message_to_speak}'")

                robot_client.animated_talk(animation_tag, message_to_speak)
                found_emoticon = True
                break
        
        if found_emoticon:
            continue

        # 2. If no emoticon, check for quick response hotkeys (blocking animation)
        for key, response_data in config.quick_responses.items():
            hotkey = f"/{key}"
            if hotkey in line:
                if verbose:
                    print(f"[DEBUG] Found hotkey: '{hotkey}'")
                animation_tag = response_data.get('animation')
                if animation_tag:
                    message_part = line.replace(hotkey, '').strip()
                    message_to_speak = get_verified_text(session, spell_checker, message_part)
                    
                    if verbose:
                        print(f"[DEBUG] Final Message to speak: '{message_to_speak}'")
                    
                    # Speak first, then play animation
                    if message_to_speak:
                        robot_client.talk(message_to_speak)
                    robot_client.play_animation_blocking(animation_tag)

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
                print(f"[DEBUG] No emoticon or hotkey found. Verifying regular message: '{line}'")
            
            message_to_speak = get_verified_text(session, spell_checker, line)
            
            robot_client.talk(message_to_speak)