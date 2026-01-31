# Command-line interface (UI) elements
from .spell_checker import SpellChecker
from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.application import Application
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML

class InteractiveMenu:
    def __init__(self, title, options, on_toggle=None):
        self.title = title
        self.options = options # List of [key, label] (mutable for label updates)
        self.selected_index = 0
        self.on_toggle = on_toggle # Callback(index, options) -> None

    def get_text(self):
        # Resolve title if callable
        title_text = self.title() if callable(self.title) else self.title
        text = [f"<b>{title_text}</b>\n"]
        for i, (key, label) in enumerate(self.options):
            if i == self.selected_index:
                text.append(f" <ansicyan>&gt; {label}</ansicyan>\n")
            else:
                text.append(f"   {label}\n")
        
        # Add footer instruction if toggle is available for selected item
        if self.on_toggle and (self.options[self.selected_index][0] in ['j', 'a', 'w', 's']): # Hardcoded hint for now
             text.append("\n <i>[Tab] Toggle Input Mode</i>")
             
        return HTML("".join(text))

    def run(self):
        bindings = KeyBindings()

        @bindings.add('up')
        def _(event):
            self.selected_index = (self.selected_index - 1) % len(self.options)

        @bindings.add('down')
        def _(event):
            self.selected_index = (self.selected_index + 1) % len(self.options)
        
        @bindings.add('tab')
        def _(event):
            if self.on_toggle:
                self.on_toggle(self.selected_index, self.options)

        @bindings.add('enter')
        def _(event):
            event.app.exit(result=self.options[self.selected_index][0])

        @bindings.add('c-c')
        def _(event):
            event.app.exit(result="exit")

        app = Application(
            layout=Layout(Window(content=FormattedTextControl(text=self.get_text))),
            key_bindings=bindings,
            mouse_support=False,
            full_screen=False,
            refresh_interval=0.5 # Refresh every 0.5s for live updates (battery/status)
        )
        from prompt_toolkit.patch_stdout import patch_stdout
        with patch_stdout():
            return app.run()

def show_main_menu(teleop_state):
    """
    Displays the main menu.
    teleop_state: A dictionary {'mode': 'Joystick' or 'Keyboard'}
    """
    current_mode = teleop_state.get('mode', 'Joystick')
    
    def format_social_label(state):
        if state == "Autonomous":
            return f"Set Social State [<ansigreen>{state}</ansigreen>]"
        else:
            return f"Set Social State [<ansired>{state}</ansired>]"

    def format_teleop_label(mode):
        is_running = teleop_state.get('teleop_running', False)
        if mode == "Joystick":
             if is_running:
                 return f"Teleop Mode [<ansigreen>{mode}</ansigreen>]"
             else:
                 return f"Teleop Mode [<ansired>{mode}</ansired>]"
        else:
             return f"Teleop Mode [<ansiyellow>{mode}</ansiyellow>]"

    def format_robot_state_label(state):
        if state == "Wake":
            return f"Robot State [<ansigreen>{state}</ansigreen>]"
        else:
             return f"Robot State [<ansired>{state}</ansired>]"

    def format_tracking_label(mode):
        if mode == "Head":
             return f"Tracking Mode [<ansimagenta>{mode}</ansimagenta>]"
        elif mode == "WholeBody":
             return f"Tracking Mode [<ansicyan>{mode}</ansicyan>]"
        elif mode == "Move":
             return f"Tracking Mode [<ansiyellow>{mode}</ansiyellow>]"
        else:
             return f"Tracking Mode [{mode}]"

    def format_battery_status(charge):
        if charge is None:
            return "[?]"
        
        # 10 bars
        bars = int(charge / 10)
        empty = 10 - bars
        bar_str = "|" * bars + " " * empty
        
        # Determine color
        color = "ansiwhite"
        if charge > 75:
            color = "ansigreen"
        elif charge > 30:
            color = "ansiyellow"
        else:
            color = "ansired"
            
        return f"Battery: [<{color}>{bar_str}</{color}>] {charge}%"

    # helper to update label
    def update_label(opts):
        for i, opt in enumerate(opts):
            if opt[0] == 'j':
                opts[i] = ('j', format_teleop_label(teleop_state['mode']))
            elif opt[0] == 'a':
                opts[i] = ('a', format_social_label(teleop_state.get('social_mode', 'Disabled')))
            elif opt[0] == 'w':
                opts[i] = ('w', format_robot_state_label(teleop_state.get('robot_state', 'Rest')))
            elif opt[0] == 's':
                 opts[i] = ('s', format_tracking_label(teleop_state.get('tracking_mode', 'Head')))
    
    # Dynamic header
    def get_title():
        batt = format_battery_status(teleop_state.get('battery', 0))
        title = f"Select Action:             {batt}"
        
        temp_warn = teleop_state.get('temp_warning')
        if temp_warn:
             title += f"\n <ansired>!!! {temp_warn} !!!</ansired>"
        
        return title

    options = [
        ("t", "Unified Talk Mode"),
        ("j", format_teleop_label(current_mode)),
        ("a", format_social_label(teleop_state.get('social_mode', 'Disabled'))),
        ("s", format_tracking_label(teleop_state.get('tracking_mode', 'Head'))),
        ("w", format_robot_state_label(teleop_state.get('robot_state', 'Rest'))),
        ("gm", "Gaze at Marker"),
        ("tr", "Track Object"),
        ("tm", "Joint Temperatures"),
        ("exit", "Exit Application")
    ]
    
    # Convert tuples to lists to make them mutable for the menu
    options = [list(o) for o in options]

    def on_toggle(index, opts):
        key = opts[index][0]
        if key == 'j':
            # Toggle Teleop state
            new_mode = "Keyboard" if teleop_state['mode'] == "Joystick" else "Joystick"
            teleop_state['mode'] = new_mode
            update_label(opts)
        elif key == 'a':
            # Toggle Social state
            current = teleop_state.get('social_mode', 'Disabled')
            new_state = "Autonomous" if current == "Disabled" else "Disabled"
            teleop_state['social_mode'] = new_state
            update_label(opts)
        elif key == 'w':
            # Toggle Robot state
            current = teleop_state.get('robot_state', 'Rest')
            new_state = "Wake" if current == "Rest" else "Rest"
            teleop_state['robot_state'] = new_state
            update_label(opts)
        elif key == 's':
            # Toggle Tracking Mode
            modes = ["Head", "WholeBody", "Move"]
            current = teleop_state.get('tracking_mode', 'Head')
            try:
                current_idx = modes.index(current)
            except ValueError:
                current_idx = 0
            
            new_idx = (current_idx + 1) % len(modes)
            teleop_state['tracking_mode'] = modes[new_idx]
            update_label(opts)

    menu = InteractiveMenu(
        title=get_title,
        options=options,
        on_toggle=on_toggle
    )
    return menu.run()


def show_temperature_view(robot_client, config):
    """
    Displays a live-updating table of joint temperatures.
    """
    # Load thresholds from config or use defaults
    thresholds = config.temperature_config.get("thresholds", {"warm": 65, "hot": 80})
    warm_th = thresholds.get("warm", 65)
    hot_th = thresholds.get("hot", 80)

    def get_content():
        temps = robot_client.get_joint_temperatures()
        
        # Sort keys for consistent display
        sorted_keys = sorted(temps.keys())
        
        # Build table
        lines = []
        lines.append("<b><ansicyan>--- Joint Temperatures (Ctrl+C to Exit) ---</ansicyan></b>\n")
        lines.append(f"<b>{'Joint Name':<20} | {'Temp (°C)':<10} | {'Status'}</b>\n")
        lines.append("-" * 45 + "\n")
        
        if not temps:
            lines.append("<ansired>No temperature data available (is robot connected?)</ansired>\n")
        else:
            for joint in sorted_keys:
                temp = temps[joint]
                
                # Color Coding
                if temp < warm_th:
                    status = "<ansigreen>OK</ansigreen>"
                    temp_fmt = f"<ansigreen>{temp:.1f}</ansigreen>"
                elif temp < hot_th:
                    status = "<ansiyellow>WARM</ansiyellow>"
                    temp_fmt = f"<ansiyellow>{temp:.1f}</ansiyellow>"
                else:
                    status = "<ansired>HOT!</ansired>"
                    temp_fmt = f"<ansired><b>{temp:.1f}</b></ansired>"
                
                # Force string conversion just in case
                line_str = f"{joint:<20} | {temp_fmt:<24} | {status}\n"
                lines.append(str(line_str)) 
                
        return HTML("".join(lines))

    # Simple loop for custom refreshing view
    # We re-use Application for auto-refresh, similar to InteractiveMenu but with no selection
    bindings = KeyBindings()
    
    @bindings.add('c-c')
    def _(event):
        event.app.exit()

    app = Application(
        layout=Layout(Window(content=FormattedTextControl(text=get_content))),
        key_bindings=bindings,
        mouse_support=False,
        full_screen=False, # Use False to keep previous output visible above
        refresh_interval=1.0 # Update every second
    )
    
    print("\nStarting Temperature Monitor...")
    from prompt_toolkit.patch_stdout import patch_stdout
    with patch_stdout():
        app.run()




class SlashCompleter(Completer):
    """
    Custom completer that provides suggestions only when triggered by a slash '/'.
    It completes the word immediately following the slash.
    """
    def __init__(self, words, ignore_case=False):
        self.words = sorted(list(set(words)))
        self.ignore_case = ignore_case

    def get_completions(self, document, complete_event):
        text_before_cursor = document.text_before_cursor
        
        # We only care if there is a slash for quick commands
        if '/' not in text_before_cursor:
            return

        # Get text after the LAST slash
        current_word = text_before_cursor.split('/')[-1]

        # If the current "word" contains spaces, it means we are past the slash token
        if ' ' in current_word:
            return
            
        search_prefix = "/" + current_word
        if self.ignore_case:
            search_prefix = search_prefix.lower()

        for word in self.words:
            check_word = word.lower() if self.ignore_case else word
            if check_word.startswith(search_prefix):
                # Yield completion
                yield Completion(word, start_position=-(len(current_word) + 1))

def get_tracking_target():
    """Prompts the user for an object to track."""
    session = PromptSession()
    try:
        print("Enter object class to track (e.g. 'bottle', 'person'). Leave empty to stop.")
        target = session.prompt("Track Object: ")
        return target.strip() if target else None
    except (EOFError, KeyboardInterrupt):
        return None

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

def print_help():
    """Prints the help message."""
    print("Available commands:")
    print("  A    - Toggle Autonomous/Social State")
    print("  J    - Start Joystick Teleoperation")
    print("  W    - Toggle Robot Wake/Rest State")
    print("  T    - Enter Talk Mode")
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

def confirm_correction(session, suggestion, original, tag=None):
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
        tag_disp = f" <ansimagenta>[{tag}]</ansimagenta>" if tag else ""
        if state[0]:
            return HTML(f"<b><ansicyan>Pepper (Suggestion){tag_disp}:</ansicyan></b> ")
        else:
            return HTML(f"<b><ansiwhite>Pepper (Raw){tag_disp}:</ansiwhite></b> ")

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

def get_verified_text(session, spell_checker, text, tag=None):
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
    return confirm_correction(session, corrected, text, tag=tag)


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
    # --- Autocomplete Setup ---
    completer_words = []
    # 1. Commands
    completer_words.extend(['/help', '/q'])
    # 2. Hotkeys (already have /)
    completer_words.extend([f"/{k}" for k in config.quick_responses.keys()])
    # 3. Emoticons (ADD slash only)
    completer_words.extend([f"/{k}" for k in config.emoticon_map.keys()])
    # 4. Tags (Animation names) - Add slash only
    unique_tags = set(config.emoticon_map.values())
    completer_words.extend([f"/{t}" for t in unique_tags])

    completer = SlashCompleter(completer_words, ignore_case=True)

    # Initialize PromptSession with completer
    session = PromptSession(completer=completer, complete_while_typing=True)

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
        # Handle both raw :) and autocomplete /:)
        sorted_emoticons = sorted(config.emoticon_map.keys(), key=len, reverse=True)
        for emoticon in sorted_emoticons:
            target_emoticon = emoticon
            
            # Check if it exists with or without slash
            if f"/{emoticon}" in line:
                 # Remove the slashed version
                 message_part = line.replace(f"/{emoticon}", '').strip()
            elif emoticon in line:
                 message_part = line.replace(emoticon, '').strip()
            else:
                continue

            animation_tag = config.emoticon_map[emoticon]
            message_to_speak = get_verified_text(session, spell_checker, message_part, tag=animation_tag)

            if message_to_speak:
                robot_client.animated_talk(animation_tag, message_to_speak)
                # Feedback to user
                print_formatted_text(HTML(f"<ansiyellow>[Pepper] Said:</ansiyellow> \"{message_to_speak} [{animation_tag}]\""))
            elif message_part == "" and not message_to_speak:
                 # Just animation
                 robot_client.play_animation_blocking(animation_tag)
                 print_formatted_text(HTML(f"<ansiyellow>[Pepper] Said:</ansiyellow> \"[{animation_tag}]\""))
            
            found_emoticon = True
            break
        
        if found_emoticon:
            continue
            
        # 1b. Check for Tags (Animation Names) - STRICTLY SLASH PREFIXED
        # e.g. /happy -> play 'happy' animation
        sorted_tags = sorted(unique_tags, key=len, reverse=True)
        found_tag = False
        for tag in sorted_tags:
            slash_tag = f"/{tag}"
            if slash_tag in line:
                 # Remove the tag
                 message_part = line.replace(slash_tag, '').strip()
                 animation_tag = tag 
                 
                 message_to_speak = get_verified_text(session, spell_checker, message_part, tag=animation_tag)

                 if message_to_speak:
                    robot_client.animated_talk(animation_tag, message_to_speak)
                    print_formatted_text(HTML(f"<ansiyellow>[Pepper] Said:</ansiyellow> \"{message_to_speak} [{animation_tag}]\""))
                 elif message_part == "" and not message_to_speak:
                    robot_client.play_animation_blocking(animation_tag)
                    print_formatted_text(HTML(f"<ansiyellow>[Pepper] Said:</ansiyellow> \"[{animation_tag}]\""))
                 
                 found_tag = True
                 break
        
        if found_tag:
            continue

        # 2. If no emoticon, check for quick response hotkeys (blocking animation)
        for key, response_data in config.quick_responses.items():
            hotkey = f"/{key}"
            if hotkey in line:
                animation_tag = response_data.get('animation')
                if animation_tag:
                    message_part = line.replace(hotkey, '').strip()
                    message_to_speak = get_verified_text(session, spell_checker, message_part, tag=animation_tag)
                    
                    if message_to_speak:
                        # Speak first, then play animation
                        robot_client.talk(message_to_speak)
                        robot_client.play_animation_blocking(animation_tag)
                        print_formatted_text(HTML(f"<ansiyellow>[Pepper] Said:</ansiyellow> \"{message_to_speak} [{animation_tag}]\""))

                    found_hotkey = True
                    break

        if found_hotkey:
            continue

        # 3. If nothing else, perform regular talk
        if line:
            message_to_speak = get_verified_text(session, spell_checker, line)
            
            if message_to_speak:
                robot_client.talk(message_to_speak)
                print_formatted_text(HTML(f"<ansiyellow>[Pepper] Said:</ansiyellow> \"{message_to_speak}\""))