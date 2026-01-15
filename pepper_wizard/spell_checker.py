from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

class SpellChecker:
    """
    A context-aware spell checker using a T5-Base model fine-tuned for grammar correction.
    Model: vennify/t5-base-grammar-correction
    """
    def __init__(self, model_name="vennify/t5-base-grammar-correction"):
        print(f"Loading SpellChecker model: {model_name}...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = self.model.to(self.device)
        print(f"SpellChecker loaded on {self.device}.")

    def correct_sentence(self, sentence):
        """
        Corrects grammar and spelling in a given sentence.
        """
        if not sentence:
            return ""


        input_text = f"grammar: {sentence}"
        tokenized_input = self.tokenizer(input_text, return_tensors="pt").to(self.device)

        # Calculate dynamic max_length to prevent hallucinations on short inputs
        input_len = tokenized_input['input_ids'].shape[1]
        # Allow for some expansion (correction might be longer), but constrain it.
        # e.g. 2x input length + fixed buffer of 8 tokens
        dynamic_max_len = int(input_len * 2) + 8

        # Generate correction
        # Tuned parameters for higher accuracy on short inputs:
        # - num_beams=5: Better search for optimal sequence (vs 2)
        # - early_stopping=True: Stop when best candidates found
        # - length_penalty=1.0: Neutral length bias (don't force long outputs)
        with torch.no_grad():
            outputs = self.model.generate(
                **tokenized_input,
                max_length=dynamic_max_len,
                num_beams=5, 
                do_sample=False,
                early_stopping=True,
                length_penalty=0.6,
                repetition_penalty=2.0,
                no_repeat_ngram_size=3
            )
        
        corrected_sentence = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Post-processing to clean up model artifacts
        # Remove common prefixes like "grammar:", "grammar :", "grammar test:"
        import re
        corrected_sentence = re.sub(r"^(grammar\s*:|grammar\s+test\s*:)\s*", "", corrected_sentence, flags=re.IGNORECASE)
        
        return corrected_sentence
