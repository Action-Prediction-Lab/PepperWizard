from pepper_wizard.spell_checker import SpellChecker
import time

def verify():
    # Timer to check initialization speed
    start_time = time.time()
    checker = SpellChecker()
    print(f"Model loaded in {time.time() - start_time:.2f} seconds.")

    examples = [
        "Wht is your nme?",         # Context: What is your name?
        "Im going to the parkk",    # Context: I'm going to the park.
        "She don't like apples",    # Grammar: She doesn't like apples.
        "Hello world this is a test", # Identity
        "I have 123 apples",        # Numbers
        "peper robot is cool",      # Entity: Pepper robot is cool
    ]

    print(f"{'Original':<30} | {'Corrected':<40}")
    print("-" * 75)
    for ex in examples:
        start_time = time.time()
        corrected = checker.correct_sentence(ex)
        latency = time.time() - start_time
        print(f"{ex:<30} | {corrected:<40} ({latency:.2f}s)")

if __name__ == "__main__":
    verify()
