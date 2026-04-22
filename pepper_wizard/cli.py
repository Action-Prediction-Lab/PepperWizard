# Command-line interface (UI) elements
from .spell_checker import SpellChecker
from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.patch_stdout import patch_stdout
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
        if self.on_toggle and (self.options[self.selected_index][0] in ['t', 'j', 'a', 'w', 's']):
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
    
    def format_talk_label(mode):
        if mode == "Voice":
            return f"Talk Mode [<ansigreen>{mode}</ansigreen>]"
        elif mode == "LLM":
            return f"Talk Mode [<ansimagenta>{mode}</ansimagenta>]"
        else:
            return f"Talk Mode [<ansiyellow>{mode}</ansiyellow>]"

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
            if opt[0] == 't':
                opts[i] = ('t', format_talk_label(teleop_state.get('talk_mode', 'Voice')))
            elif opt[0] == 'j':
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
        ("t", format_talk_label(teleop_state.get('talk_mode', 'Voice'))),
        ("j", format_teleop_label(current_mode)),
        ("a", format_social_label(teleop_state.get('social_mode', 'Disabled'))),
        ("s", format_tracking_label(teleop_state.get('tracking_mode', 'Head'))),
        ("w", format_robot_state_label(teleop_state.get('robot_state', 'Rest'))),
        ("gm", "Gaze at Marker"),
    ]
    if teleop_state.get('tracker_available', True):
        options.append(("tr", "Track Object"))
    options.extend([
        ("tm", "Joint Temperatures"),
        ("exit", "Exit Application"),
    ])
    
    # Convert tuples to lists to make them mutable for the menu
    options = [list(o) for o in options]

    def on_toggle(index, opts):
        key = opts[index][0]
        if key == 't':
            # Cycle Talk mode: Voice -> Text -> LLM -> Voice
            modes = ["Voice", "Text", "LLM"]
            current = teleop_state.get('talk_mode', 'Voice')
            try:
                idx = modes.index(current)
            except ValueError:
                idx = 0
            teleop_state['talk_mode'] = modes[(idx + 1) % len(modes)]
            update_label(opts)
        elif key == 'j':
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


def voice_talk_session(robot_client, config, verbose=False):
    """Handles an interactive Voice-to-TTS session using the STT service."""
    from .stt_client import STTClient
    from .logger import get_logger

    logger = get_logger("VoiceTalk")
    stt_config = config.stt_config
    review_mode = stt_config.get("review_mode", True)

    # Connect to STT service
    stt_client = STTClient(stt_config.get("zmq_address", "tcp://localhost:5562"))
    if not stt_client.ping():
        print_formatted_text(HTML(
            "<ansired>Error: Could not connect to the STT service.</ansired>\n"
            "<ansired>Is stt-service running? (docker compose up stt-service)</ansired>"
        ))
        stt_client.close()
        return

    review_label = "<ansigreen>ON</ansigreen>" if review_mode else "<ansired>OFF</ansired>"
    print_formatted_text(HTML(
        f" --- Entering Voice Talk Mode ---\n"
        f" Review mode: {review_label}\n"
        f" Press <b>[Space]</b> to start recording, <b>[Enter]</b> to stop.\n"
        f" Type <b>/review</b> to toggle review mode, <b>/q</b> to exit.\n"
        f" ---"
    ))

    session = PromptSession()

    try:
        while True:
            # Prompt for commands
            bindings = KeyBindings()

            @bindings.add("space")
            def _on_space(event):
                """Start recording if buffer is empty, otherwise insert a space."""
                if not event.current_buffer.text.strip():
                    event.current_buffer.text = ""
                    event.app.exit(result="__record__")
                else:
                    event.current_buffer.insert_text(" ")

            try:
                mode_label = "review" if review_mode else "direct"
                line = session.prompt(
                    HTML(f"<b><ansimagenta>Voice [{mode_label}]:</ansimagenta></b> "),
                    key_bindings=bindings,
                )
            except (EOFError, KeyboardInterrupt):
                break

            # Check for recording trigger FIRST
            if line == "__record__":
                started = stt_client.start_recording()
                if not started:
                    print_formatted_text(HTML(
                        "<ansired>Failed to start recording.</ansired>"
                    ))
                    continue

                print_formatted_text(HTML(
                    " <b><ansicyan>Recording...</ansicyan></b> "
                    "Press <b>[Enter]</b> to stop."
                ))

                # Wait for Enter to stop recording, with guard against
                # buffered keystrokes from previous interactions
                import time
                rec_start = time.time()
                while True:
                    try:
                        session.prompt(
                            HTML("<ansicyan>  ... </ansicyan>"),
                        )
                    except (EOFError, KeyboardInterrupt):
                        pass
                    # Reject instant stops caused by buffered input
                    if time.time() - rec_start >= 0.5:
                        break

                # Stop and get transcription
                print_formatted_text(HTML(
                    " <i>Transcribing...</i>"
                ))
                result = stt_client.stop_and_transcribe()
                transcription = result.get("transcription", "").strip()
                duration = result.get("duration", 0.0)
                error = result.get("error")

                if error:
                    print_formatted_text(HTML(
                        f"<ansired>STT Error: {error}</ansired>"
                    ))
                    continue

                if not transcription:
                    print_formatted_text(HTML(
                        "<ansiyellow>No speech detected.</ansiyellow>"
                    ))
                    continue

                logger.info("VoiceTalkTranscribed", {
                    "transcription": transcription,
                    "duration": duration,
                })

                if review_mode:
                    # Show transcription for review
                    print_formatted_text(HTML(
                        f" <b>Heard:</b> \"{transcription}\" "
                        f"<i>({duration:.1f}s)</i>"
                    ))
                    try:
                        review_bindings = KeyBindings()

                        @review_bindings.add("escape")
                        def _on_escape(event):
                            event.current_buffer.text = ""
                            event.app.exit(result="")

                        edited = session.prompt(
                            HTML("<b><ansigreen>Confirm [Enter] / Edit / [Esc] Discard:</ansigreen></b> "),
                            default=transcription,
                            key_bindings=review_bindings,
                        )
                    except (EOFError, KeyboardInterrupt):
                        print(" Discarded.")
                        continue

                    if not edited.strip():
                        print(" Discarded.")
                        continue

                    final_text = edited.strip()
                else:
                    # Direct mode — send immediately
                    final_text = transcription

                robot_client.talk(final_text)
                print_formatted_text(HTML(
                    f"<ansiyellow>[Pepper] Said:</ansiyellow> \"{final_text}\""
                ))
                logger.info("VoiceTalkSpoken", {
                    "text": final_text,
                    "was_edited": (final_text != transcription),
                    "original_transcription": transcription,
                    "duration": duration,
                })
                continue

            # Handle slash commands and typed text
            if line is not None and line.strip():
                cmd = line.strip().lower()
                if cmd == "/q":
                    break
                elif cmd == "/review":
                    review_mode = not review_mode
                    state_label = "ON" if review_mode else "OFF"
                    print_formatted_text(HTML(
                        f" Review mode: <b>{state_label}</b>"
                    ))
                    continue
                elif cmd == "/help":
                    print_formatted_text(HTML(
                        " <b>Voice Talk Mode Help</b>\n"
                        "  Press <b>[Space]</b> — Start recording\n"
                        "  Press <b>[Enter]</b> — Stop and transcribe\n"
                        "  <b>/review</b> — Toggle review mode\n"
                        "  <b>/q</b> — Exit voice talk mode"
                    ))
                    continue
                else:
                    # Treat typed text as direct speech (fallback to keyboard)
                    robot_client.talk(line.strip())
                    print_formatted_text(HTML(
                        f"<ansiyellow>[Pepper] Said:</ansiyellow> \"{line.strip()}\""
                    ))
                    logger.info("VoiceTalkTyped", {"text": line.strip()})
                    continue

    finally:
        stt_client.close()

    print(" --- Exiting Voice Talk Mode ---")


def llm_talk_session(robot_client, config, verbose=False):
    """LLM dialogue via always-on VAD on Pepper's front microphone."""
    from .logger import get_logger
    from .stt_client import STTClient
    from .llm.client import LLMClient, LLMUnavailable

    logger = get_logger("LLMTalk")
    stt_config = config.stt_config

    try:
        llm = LLMClient(config.llm_config)
    except LLMUnavailable as e:
        print_formatted_text(
            HTML("<ansired>LLM unavailable: {}</ansired>").format(str(e))
        )
        return

    stt_client = STTClient(stt_config.get("zmq_address", "tcp://localhost:5562"))
    if not stt_client.ping():
        print_formatted_text(HTML(
            "<ansired>Error: Could not connect to the STT service.</ansired>"
        ))
        stt_client.close()
        return

    if not stt_client.enable_streaming():
        print_formatted_text(HTML(
            "<ansired>Error: Could not enable streaming on STT service.</ansired>"
        ))
        stt_client.close()
        return
    logger.info("StreamingEnabled", {})

    import queue
    import zmq
    import threading
    vad_queue = queue.Queue()
    ctx = zmq.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.connect(stt_config.get("transcription_zmq_address", "tcp://localhost:5564"))
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVTIMEO, 200)

    sub_stop = threading.Event()

    # Mutable holder so the background thread always reads the current value.
    review_mode = [bool(stt_config.get("llm_review_mode", True))]

    def _sub_loop():
        import json
        while not sub_stop.is_set():
            try:
                msg = sub.recv()
            except zmq.Again:
                continue
            try:
                evt = json.loads(msg.decode())
            except Exception:
                continue
            if review_mode[0]:
                # Review mode: queue for main thread to handle with a review prompt.
                vad_queue.put(evt)
            else:
                # Auto-dispatch mode: fire directly from background thread.
                _handle_vad_event(evt, review_mode=False,
                                  llm=llm, stt=stt_client,
                                  robot_client=robot_client, logger=logger,
                                  session=session)

    session = PromptSession()
    sub_thread = threading.Thread(target=_sub_loop, daemon=True)
    sub_thread.start()

    review_label = "on" if review_mode[0] else "off"
    print_formatted_text(HTML(
        f" --- Entering <ansimagenta>LLM</ansimagenta> Talk Mode ---\n"
        f" Model: <b>{llm.model}</b> | review gate: <b>{review_label}</b>\n"
        f" Pepper is listening. Type to override, <b>/review</b> to toggle review gate,\n"
        f" <b>/reset</b> to clear context, <b>/q</b> to exit.\n"
        f" ---"
    ))
    try:
        with patch_stdout():
            while True:
                # Drain any queued events (only populated when review_mode[0] is True).
                while not vad_queue.empty():
                    evt = vad_queue.get_nowait()
                    _handle_vad_event(evt, review_mode=review_mode[0],
                                      llm=llm, stt=stt_client,
                                      robot_client=robot_client, logger=logger,
                                      session=session)
                try:
                    line = session.prompt(HTML("<b><ansimagenta>LLM:</ansimagenta></b> "))
                except (EOFError, KeyboardInterrupt):
                    break

                stripped = line.strip()
                if not stripped:
                    continue
                if stripped == "/q":
                    break
                if stripped == "/reset":
                    llm.reset()
                    print_formatted_text(HTML("<ansiyellow>Context cleared.</ansiyellow>"))
                    continue
                if stripped == "/review":
                    review_mode[0] = not review_mode[0]
                    label = "on" if review_mode[0] else "off"
                    print_formatted_text(HTML(f"<ansiyellow>Review gate: {label}</ansiyellow>"))
                    continue

                _dispatch_to_llm(stripped, source="typed", llm=llm, stt=stt_client,
                                 robot_client=robot_client, logger=logger)
    finally:
        sub_stop.set()
        sub_thread.join(timeout=1.0)
        sub.close()
        stt_client.disable_streaming()
        stt_client.close()
        logger.info("StreamingDisabled", {})
        print_formatted_text(HTML(" --- Exiting LLM Talk Mode ---"))


def _handle_vad_event(evt, *, review_mode, llm, stt, robot_client, logger, session):
    if "error" in evt:
        print_formatted_text(
            HTML("<ansired>[VAD error] {}: {}</ansired>").format(evt.get("error", ""), evt.get("detail", ""))
        )
        return

    text = (evt.get("text") or "").strip()
    duration_s = float(evt.get("duration_s") or 0.0)
    if not text:
        logger.info("VADUtterance", {"duration_s": duration_s, "sent": False, "reason": "empty"})
        return

    if review_mode:
        review_session = PromptSession()
        try:
            final = review_session.prompt(
                HTML("<ansicyan>Heard [review]:</ansicyan> "),
                default=text,
            )
        except (EOFError, KeyboardInterrupt):
            final = None

        if final is None or not final.strip():
            logger.info("VADUtterance", {"text": text, "duration_s": duration_s,
                                          "sent": False, "reason": "discarded"})
            return
        logger.info("VADUtterance", {"text": final.strip(), "duration_s": duration_s,
                                      "sent": True, "edited": final.strip() != text})
        _dispatch_to_llm(final.strip(), source="robot_mic",
                         llm=llm, stt=stt,
                         robot_client=robot_client, logger=logger)
        return

    logger.info("VADUtterance", {"text": text, "duration_s": duration_s, "sent": True})
    _dispatch_to_llm(text, source="robot_mic", llm=llm, stt=stt,
                     robot_client=robot_client, logger=logger)


def _dispatch_to_llm(user_text, *, source, llm, stt, robot_client, logger):
    # Mute while Pepper is speaking so stt-service ignores self-hearing.
    stt.mute()
    logger.info("MuteStart", {})
    try:
        reply = llm.reply(user_text)
    except Exception as e:
        print_formatted_text(
            HTML("<ansired>LLM error: {}</ansired>").format(str(e))
        )
        logger.error("LLMError", {"error": str(e), "user_text": user_text})
        stt.unmute()
        logger.info("MuteEnd", {})
        return

    if not reply:
        print_formatted_text(HTML("<ansiyellow>LLM returned empty reply.</ansiyellow>"))
        stt.unmute()
        logger.info("MuteEnd", {})
        return

    print_formatted_text(
        HTML(
            "<ansicyan>[You]</ansicyan> \"{}\"\n"
            "<ansiyellow>[Pepper]</ansiyellow> \"{}\""
        ).format(user_text, reply)
    )
    try:
        robot_client.talk(reply)
    except Exception as e:
        print_formatted_text(HTML("<ansired>talk() failed: {}</ansired>").format(str(e)))
        logger.error("TalkFailed", {"error": str(e)})
    stt.unmute()
    logger.info("MuteEnd", {})
    logger.info("LLMTurn", {"user": user_text, "reply": reply, "source": source})